# City ECC intake contract

Three Pydantic request models, a Supabase schema, and a loader that validates the labeled expected payloads in the supplied 40-chat test set. There is no agent, message classifier, LLM call, or database writer in the Python package.

## Results

The unchanged CSV has **80 resident-turn rows grouped into 40 chats: 30 routine and 10 handoff. All 30 routine chats validate. Zero failures.** Each request type has 10 routine chats.

- [Committed loader terminal output](evidence/loader-output.txt), including every chat and the explicit failure section.
- [Regression test output](evidence/tests-output.txt).
- [Supabase requests Table Editor screenshot](evidence/supabase-requests.jpg).
- [Supabase handoffs Table Editor screenshot](evidence/supabase-handoffs.jpg).
- [Applied SQL migration](sql/001_create_intake_tables.sql).
- [Live database constraint-check result](evidence/database-verification.txt) and [rollback-only SQL checks](sql/verify_constraints.sql).

## Run locally

Use Python 3.10 or newer. From the repository root:

```sh
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e .
python -m ecc_intake.loader
python -m unittest discover -s tests -v
```

The dependency list is pinned in [requirements.txt](requirements.txt). An explicit CSV path can be passed to the loader. The command enforces the acceptance totals for this 40-chat fixture and exits with status 1 on any validation, annotation, input, or count failure.

## Dispatch field mapping

All model keys are required and extra fields are rejected. `request_type` is a type-specific literal and `conversation_id` maps from `chat_id`. Text fields are nonblank strings. Boolean fields are actual booleans; the CSV loader explicitly converts only `true` and `false`.

| Model | Dispatch fields |
| --- | --- |
| `NoiseComplaint` | `location: str`, `noise_source: str`, `callback_phone: str` |
| `IllegallyParkedVehicle` | `location: str`, `vehicle_description: str`, `license_plate: str \| None`, `blocking_driveway: bool`, `callback_phone: str` |
| `Pothole` | `location: str`, `pothole_size: str`, `hazard_to_traffic: bool`, `callback_phone: str` |

[`models.py`](src/ecc_intake/models.py) defines three separate models. Only the vehicle license plate permits a null value. Its inline comment names all three routine samples that require this:

- `ECC-T-010`: plate covered in dirt.
- `ECC-T-025`: plate obscured by a cover.
- `ECC-T-037`: trailer blocks the view of the plate.

`license_plate` has no default: callers must provide the key, using `None` when unreadable. Empty CSV cells become `None` in the in-memory payload, without changing the source file. All other applicable dispatch fields are populated in every routine sample. Fields for other request types are absent from that model, rather than optional catch-all fields. Callback numbers are stored as text to preserve their formatting; this contract does not verify phone reachability.

The requested dispatch scope is `expected_location` through `expected_callback_phone`. `incident_observed_at` and `source_call_date` remain source metadata in the original CSV, outside these dispatch models. Database `created_at` records insertion time and `updated_at` records the latest row change, not incident time.

## Loader behavior

[`loader.py`](src/ecc_intake/loader.py) groups all rows by `chat_id` before counting. It checks that repeated outcome, type, trigger, and dispatch annotations agree across the turns, and that turn numbers are unique and consecutive from 1. Row order does not matter.

Routing requires both labels to agree: `routine` + `create_request`, or `handoff` + `handoff`. Routine payloads are validated with the model selected by `expected_request_type`. Populated fields from a different request type are reported as errors. Handoffs are counted separately and checked for a recognized trigger and absence of routine payloads. The six trigger labels come from the fixture: `weapon`, `injury`, `fire`, `danger`, `person_in_distress`, and `unclassified_after_two_tries`.

The loader checks **expected structured fields**, not extraction accuracy from the resident messages. Resident text is fixture data, never executable instructions. It prints all detected failures and returns a nonzero exit code when any exist. Tests mutate temporary copies only.

## Supabase

Project: `city-ecc-intake`, in the `Nicolas Anema` free organization, region `ap-south-1`. [Open Table Editor](https://supabase.com/dashboard/project/ncwquehhluggrvjzyqga/editor) (project access required).

The migration creates:

- `public.requests`: request type, unique conversation ID, a column for every model field, identity ID, and creation time. A conditional constraint enforces each type's required fields and requires irrelevant fields to be null. The license plate exception matches the Pydantic model.
- `public.handoffs`: unique conversation ID, nonblank transcript, required trigger label, identity ID, and creation time. A transcript represents the resident turns in turn-number order; the source contains resident messages only.

Both tables also have a required `updated_at timestamptz` column. The SQL defines `public.set_intake_updated_at()` and two actual PostgreSQL triggers, `requests_set_updated_at` and `handoffs_set_updated_at`. Each fires `BEFORE UPDATE FOR EACH ROW` when old and new row values differ, setting `updated_at` to the current clock time. Updates that change no values leave the timestamp alone; `created_at` stays unchanged. The constrained `handoffs.trigger_label` remains the handoff reason.

Both tables have Row Level Security enabled, with no public API policies. Future agent access is outside this contract. The SQL supports a fresh schema and can be rerun on the original ECC schema: it preserves existing tables and rows, adds missing `updated_at` columns, and replaces its function and triggers. It is not a general schema-drift repair script. It contains no credentials. The tables are created empty; validation does not persist the fixture. `sql/verify_constraints.sql` exercises both triggers and the shape constraints in a transaction that is rolled back.

## Source and implementation

The CSV under `data/` is copied byte-for-byte from the supplied file. SHA-256:

```text
000cc38c40ec129fc0019043115d01ecfc049d2aca419e267a458b9818d39b03
```

Built and checked in Codex with the user's approval to substitute for the Claude Code tooling step. Schema deployment uses the connected Supabase migration tool; screenshots show the resulting tables in Table Editor.

References: [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/) and [Supabase tables](https://supabase.com/docs/guides/database/tables).
