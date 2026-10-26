# ECC routing and handoff specification

This document records the agreed trigger classes, six-node LangGraph flow, and routing state for the next agent stage. It is a specification, not an implemented agent.

Sources: the supplied **ECC Non-Emergency Chat Handoff Criteria** (sections 2-4 for trigger classes, section 5 for timing, section 6 for borderline wording, and section 7 for handoff context), the agreed flow, and the existing [Stage 1 Pydantic models](../src/ecc_intake/models.py).

## Part one: handoff trigger classes

Each trigger class is one mandatory-handoff rule. The agent's `handoff_reason` supplies the dispatcher-facing `handoffs.trigger_label`. There are exactly three classes:

| Source section | Trigger class |
| --- | --- |
| 2: emergency language | `emergency_language` |
| 3: resident asks for a person | `asked_for_person` |
| 4: cannot classify after two attempts | `classification_failed` |

### emergency_language

Catch danger or threats to a person; injury or medical concerns; fire, smoke or gas; weapons; and a person in distress. These are five emergency categories within one trigger class, not five separate classes. Apply the rule even when the emergency is mentioned alongside a routine report. When in doubt about real risk to a person, hand off.

**Must catch**

- "There is smoke coming out of the building next door. It looks like a fire."
- "My dad fell and he is not breathing right."
- "I smell gas outside my house, even though it's faint."
- "Someone just crashed into a pole and is bleeding."
- "Those loud bangs might be gunshots."
- "Someone is screaming for help next door."

**Must not catch**

- "Someone parked in the fire lane. Nothing is burning."
- "There's a pothole outside the gas station. No crash or injury."
- "My neighbor's music is killing me."
- "That pothole bent my rim, but nobody is hurt."
- "The bangs are fireworks. Nobody is hurt."

**Separating rule:** Catch the actual emergency conditions in section 2, including uncertain real risk to a person and any smell of gas. Do not catch alarming words used only as names or figures of speech, vehicle damage alone, or an ordinary traffic hazard without a crash or injury, as specified in section 6.

### asked_for_person

**Must catch**

- "Please connect me to a dispatcher."
- "I want to speak to a real person."
- "Can you transfer me to an operator?"

**Must not catch**

- "Are you a real person or a bot?"
- "I spoke to a dispatcher yesterday about this pothole."
- "Please call me back at 202-555-0142."

**Separating rule:** A clear request to speak to a dispatcher, operator, human or real person requires immediate handoff without collecting more fields. Asking whether the chat is a bot, mentioning a past dispatcher conversation, or supplying a callback request does not itself trigger this class.

### classification_failed

The only supported request types are `noise_complaint`, `illegally_parked_vehicle`, and `pothole`. An unsupported or ambiguous report has not resolved to exactly one supported type.

**Attempt counting:** Start `classify_attempts` at 0. Increment it once whenever a classification turn fails to identify exactly one supported request type, before evaluating the outgoing edge. The first failed turn includes asking a clarification question; do not count that question as a second, separate failure. If the resident's reply still cannot be classified, increment to 2 and hand off immediately without a third classification question. The count accumulates across the whole chat and never resets. Field collection after a type is confirmed does not count as classification.

Each example below contains two resident messages, with an agent question between them.

**Must catch**

1. Resident: "Something is wrong on my street."
   Agent: "What would you like to report?"
   Resident: "I don't know, just stuff."
   Result: two failed attempts; hand off with `classification_failed`.

2. Resident: "There's a car and loud music outside."
   Agent: "Are you reporting the noise or an illegally parked vehicle?"
   Resident: "I can't say which. There's just a lot going on."
   Result: no single request type after two attempts; hand off with `classification_failed`.

3. Resident: "The streetlight outside is broken."
   Agent: "Is your report about noise, an illegally parked vehicle, or a pothole?"
   Resident: "None of those. The streetlight won't turn on."
   Result: no supported request type after two attempts; hand off with `classification_failed`. Do not invent a streetlight request model.

**Must not catch**

1. Resident: "There's a thing on the road."
   Agent: "What is it?"
   Resident: "A pothole on Elm Street."
   Result: the first attempt failed, but the second succeeds. Set `request_type = pothole`, retain `classify_attempts = 1`, and continue to collection.

2. Resident: "My neighbor's music is too loud."
   Agent: "Where is the noise coming from?"
   Resident: "I don't know the exact address."
   Result: `noise_complaint` was already confirmed. The unclear field answer does not increment `classify_attempts` and does not trigger this class.

**Separating rule:** Hand off only after two failed attempts to identify exactly one supported request type. A successful second classification or difficulty collecting fields after classification does not trigger this class; emergency language and requests for a person are still checked first on every reply.

## Part two: LangGraph flow

The six nodes are `safety`, `classify`, `collect`, `validate`, `save`, and `handoff`. Entry, end turn, and end are graph boundaries, not additional nodes.

Every resident message in an active chat enters `safety`, including replies to clarification, collection, and validation questions. `safety` decides only whether to hand off now or allow the turn to continue. Emergency language takes priority if both immediate triggers apply.

### Edges

```text
entry to safety: always

safety to handoff: safety_trigger is emergency_language or asked_for_person
safety to classify: safety_trigger is empty and request_type is empty
safety to collect: safety_trigger is empty and request_type is set

classify to collect: request_type is set
classify to end turn, ask again: request_type is empty and classify_attempts is 1
classify to handoff: request_type is empty and classify_attempts is 2

collect to end turn, ask next field: missing_fields is not empty
collect to validate: missing_fields is empty

validate to save: validation_errors is empty
validate to collect: validation_errors is not empty, re-ask the malformed field

save to end: always
handoff to end: always
```

An end-turn edge asks its question and waits. The next resident reply starts at `safety`; it never resumes directly at `classify` or `collect`. After `handoff`, the agent sends nothing further and the dispatcher owns the conversation.

### collect

- `NoiseComplaint`: `location`, `noise_source`, `callback_phone`
- `IllegallyParkedVehicle`: `location`, `vehicle_description`, `license_plate`, `blocking_driveway`, `callback_phone`
- `Pothole`: `location`, `pothole_size`, `hazard_to_traffic`, `callback_phone`

Collection uses fields already supplied in the conversation and asks only for missing or malformed fields of the confirmed model. `request_type` comes from classification and `conversation_id` from chat context; neither is a resident collection question. An explicitly unreadable plate is recorded as `license_plate = None` with the key present. A boolean `false` is a valid supplied answer, not a missing value.

### Failure paths and handoff behavior

- **Classification failure:** after the first failed classification, ask and end the turn. After the second, hand off with `classification_failed`; no third attempt.
- **Validation failure:** `validate` records errors that identify the malformed model fields and adds those field names to `missing_fields`. Returning to `collect` asks for correction and ends the turn, without reprocessing the same rejected answer as a new correction. A new resident answer enters `safety`, then `collect`; once pending fields are supplied, `validate` runs again and replaces the error list with its current result.
- **Immediate handoff:** when `safety` finds either immediate trigger, hand off in that turn without further classification or field questions. `handoff` copies the safety trigger into `handoff_reason`; on the second failed classification it instead sets `handoff_reason = classification_failed`.
- **Resident notice:** tell the resident a dispatcher is taking over. For emergency language, also say to call 911 if anyone is in immediate danger. Then stop the agent.
- **Handoff context:** preserve the chat ID, exact triggering resident message, full resident/agent transcript, classification attempt count, confirmed type if any, fields already collected, handoff time, and emergency category when applicable.

The three class labels are the target agent contract. Stage 1 fixture labels such as `injury` and `unclassified_after_two_tries` remain source annotations; they do not create additional trigger classes. This document does not change the existing loader, database constraints, or implement persistence.

### Trace: pothole report

Illustrative resident opening: "There's a pothole outside 20 Elm Street, about two feet wide. Traffic can pass safely."

| Step | Node result | Edge that fires |
| --- | --- | --- |
| 1 | The resident message arrives. | `entry to safety: always` |
| 2 | `safety_trigger = None`; `request_type = None`. | `safety to classify` |
| 3 | `classify` sets `request_type = pothole`; attempts remain 0. | `classify to collect` |
| 4 | `collect` records location, size, and `hazard_to_traffic = false`. Only `callback_phone` is missing; ask for it. | `collect to end turn, ask next field` |

Illustrative resident reply: "202-555-0142."

| Step | Node result | Edge that fires |
| --- | --- | --- |
| 5 | The resident reply arrives. | `entry to safety: always` |
| 6 | `safety_trigger = None`; `request_type = pothole`. | `safety to collect` |
| 7 | `collect` records the callback number. `missing_fields = []`. | `collect to validate` |
| 8 | `validate` checks the complete Pothole payload, including the conversation ID supplied by chat context. `validation_errors = []`. | `validate to save` |
| 9 | `save` stores the validated report. | `save to end: always` |

### Trace: injury message

Illustrative resident message: "A car hit a pothole and crashed into a pole. The driver is bleeding."

| Step | Node result | Edge that fires |
| --- | --- | --- |
| 1 | The resident message arrives. | `entry to safety: always` |
| 2 | `safety_trigger = emergency_language`, with injury or medical as the emergency category. | `safety to handoff` |
| 3 | `handoff` records `handoff_reason = emergency_language` and the context, gives the dispatcher-takeover and immediate-danger notice, and stops. | `handoff to end: always` |

Every step in both illustrative traces has a matching edge. The traces describe intended behavior; they are not evidence of an implemented graph or actual database writes.

## Part three: routing state

For optional strings, "empty" means `None`; "set" means a valid non-`None` value. `request_type` is restricted to the three Stage 1 type literals. `safety_trigger` is restricted to `None`, `emergency_language`, or `asked_for_person`. `handoff_reason` is restricted to `None` or one of the three trigger classes.

| name | type | edge condition that reads it |
| --- | --- | --- |
| `safety_trigger` | `str or None` | `safety to handoff` checks for either immediate trigger; `safety to classify` and `safety to collect` check that it is empty. |
| `request_type` | `str or None` | `safety to classify`, `classify to end turn`, and `classify to handoff` require empty; `safety to collect` and `classify to collect` require set. |
| `classify_attempts` | `int` | `classify to end turn` requires 1; `classify to handoff` requires 2. |
| `collected_fields` | `dict` | No direct edge condition. Filled by `collect` and checked by `validate`. |
| `missing_fields` | `list[str]` | `collect to end turn` requires not empty; `collect to validate` requires empty. |
| `validation_errors` | `list[str]` | `validate to save` requires empty; `validate to collect` requires not empty. Each error identifies its malformed field. |
| `handoff_reason` | `str or None` | No direct edge condition. Set by `handoff` before recording one of the three trigger labels. |

Initialize the optional strings to `None`, the counter to 0, `collected_fields` to an empty dictionary, and the lists to empty lists. Recompute `safety_trigger` from each new resident message; preserve the confirmed type, accumulated fields, and attempt count across turns. Recompute `missing_fields` for the selected model before evaluating a collection edge, carrying unresolved validation corrections forward.

These seven fields cover the routing conditions. The current resident message, conversation ID, transcript, and handoff metadata come from chat context; they are required node inputs or outputs, not extra edge conditions.

### Edge-by-edge state audit

| Edge | Condition | Fields behind it |
| --- | --- | --- |
| entry to safety | always | None needed |
| safety to handoff | Trigger is `emergency_language` or `asked_for_person` | `safety_trigger` |
| safety to classify | Trigger empty and request type empty | `safety_trigger`, `request_type` |
| safety to collect | Trigger empty and request type set | `safety_trigger`, `request_type` |
| classify to collect | Request type set | `request_type` |
| classify to end turn, ask again | Request type empty and attempts = 1 | `request_type`, `classify_attempts` |
| classify to handoff | Request type empty and attempts = 2 | `request_type`, `classify_attempts` |
| collect to end turn, ask next field | Missing fields not empty | `missing_fields` |
| collect to validate | Missing fields empty | `missing_fields` |
| validate to save | Validation errors empty | `validation_errors` |
| validate to collect | Validation errors not empty; re-ask malformed field | `validation_errors`; malformed field added to `missing_fields` |
| save to end | always | None needed |
| handoff to end | always | None needed |

All 10 conditional edges have fields behind them. The 3 `always` edges require no state checks. Under the stated counter and type invariants, each nonterminal step in the two traces selects exactly one outgoing edge; the two failure routes also have explicit conditions.
