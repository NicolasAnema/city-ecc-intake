"""Validate labeled expected payloads, grouped by chat_id; no LLM or DB writes."""

import argparse
import csv
import hashlib
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .models import MODEL_BY_TYPE

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = PROJECT_ROOT / "data" / "ECC Non-Emergency Intake Test Set (40 Labeled Chats).csv"
DISPATCH_FIELDS = (
    "location", "noise_source", "vehicle_description", "license_plate",
    "blocking_driveway", "pothole_size", "hazard_to_traffic", "callback_phone",
)
LABEL_COLUMNS = ("chat_label", "expected_outcome", "expected_request_type", "expected_handoff_trigger")
EXPECTED_COLUMNS = tuple(f"expected_{name}" for name in DISPATCH_FIELDS)
REQUIRED_COLUMNS = ("chat_id", "turn_number", "resident_message", *LABEL_COLUMNS, *EXPECTED_COLUMNS)
HANDOFF_TRIGGERS = frozenset({
    "weapon", "injury", "fire", "danger", "person_in_distress", "unclassified_after_two_tries",
})
BOOLEAN_FIELDS = frozenset({"blocking_driveway", "hazard_to_traffic"})


@dataclass
class Report:
    rows: int = 0
    chats: int = 0
    routine: int = 0
    handoff: int = 0
    valid: int = 0
    by_type: Counter[str] = field(default_factory=Counter)
    by_trigger: Counter[str] = field(default_factory=Counter)
    results: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def decode_value(name: str, raw: str) -> object:
    """Only exact CSV true/false tokens become booleans; blank is explicit None."""
    if raw == "":
        return None
    if name in BOOLEAN_FIELDS:
        # Leave invalid tokens intact so strict Pydantic validation reports them.
        return {"true": True, "false": False}.get(raw, raw)
    return raw


def validate_csv(path: Path) -> Report:
    report = Report()
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        header = reader.fieldnames or []
        missing = set(REQUIRED_COLUMNS) - set(header)
        if missing or len(header) != len(set(header)):
            report.failures.append(f"CSV header: missing={sorted(missing)}, duplicate_columns={len(header) != len(set(header))}")
            return report
        for line, row in enumerate(reader, start=2):
            report.rows += 1
            if None in row or any(value is None for value in row.values()):
                report.failures.append(f"CSV line {line}: wrong number of columns")
                continue
            if not row["chat_id"].strip():
                report.failures.append(f"CSV line {line}: blank chat_id")
                continue
            groups[row["chat_id"]].append(row)

    report.chats = len(groups)
    for chat_id, turns in sorted(groups.items()):
        before = len(report.failures)
        # Repeated annotations must agree exactly. Never repair the fixture or choose a last row.
        conflicts = [
            name for name in (*LABEL_COLUMNS, *EXPECTED_COLUMNS)
            if len({turn[name] for turn in turns}) != 1
        ]
        if conflicts:
            report.failures.append(f"{chat_id}: conflicting annotations across turns: {', '.join(conflicts)}")
            report.results.append(f"{chat_id}: FAIL (conflicting annotations)")
            continue

        row = turns[0]
        route = (row["chat_label"], row["expected_outcome"])
        if route == ("routine", "create_request"):
            report.routine += 1
        elif route == ("handoff", "handoff"):
            report.handoff += 1
        else:
            report.failures.append(f"{chat_id}: inconsistent/unknown label and outcome: {route!r}")

        try:
            numbers = sorted(int(turn["turn_number"]) for turn in turns)
            if numbers != list(range(1, len(turns) + 1)):
                raise ValueError("turn numbers must be unique and consecutive from 1")
        except ValueError as error:
            report.failures.append(f"{chat_id}: invalid turn_number: {error}")
        if any(not turn["resident_message"].strip() for turn in turns):
            report.failures.append(f"{chat_id}: blank resident_message")

        if route == ("routine", "create_request"):
            request_type = row["expected_request_type"]
            report.by_type[request_type] += 1
            if row["expected_handoff_trigger"]:
                report.failures.append(f"{chat_id}: routine chat has a handoff trigger")
            model = MODEL_BY_TYPE.get(request_type)
            if model is None:
                report.failures.append(f"{chat_id}: unknown request type {request_type!r}")
            else:
                payload: dict[str, object] = {"conversation_id": chat_id, "request_type": request_type}
                for name in DISPATCH_FIELDS:
                    raw = row[f"expected_{name}"]
                    if name in model.model_fields or raw != "":
                        # A populated field belonging to another type is rejected as extra.
                        payload[name] = decode_value(name, raw)
                try:
                    model.model_validate(payload)
                except ValidationError as error:
                    for item in error.errors(include_url=False, include_input=False):
                        location = ".".join(str(part) for part in item["loc"])
                        report.failures.append(f"{chat_id} [{request_type}] {location}: {item['msg']}")
            if len(report.failures) == before:
                report.valid += 1
                report.results.append(f"{chat_id}: VALID {request_type}")
            else:
                report.results.append(f"{chat_id}: FAIL {request_type}")
        elif route == ("handoff", "handoff"):
            trigger = row["expected_handoff_trigger"]
            report.by_trigger[trigger] += 1
            if trigger not in HANDOFF_TRIGGERS:
                report.failures.append(f"{chat_id}: missing/unknown handoff trigger {trigger!r}")
            if row["expected_request_type"] or any(row[name] for name in EXPECTED_COLUMNS):
                report.failures.append(f"{chat_id}: handoff has routine request fields")
            status = "HANDOFF" if len(report.failures) == before else "FAIL handoff"
            report.results.append(f"{chat_id}: {status} {trigger}")
        else:
            report.results.append(f"{chat_id}: FAIL (routing labels)")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", nargs="?", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args(argv)
    try:
        report = validate_csv(args.csv_path)
        digest = hashlib.sha256(args.csv_path.read_bytes()).hexdigest()
    except (OSError, UnicodeError, csv.Error) as error:
        print(f"Failures:\n- Input could not be read: {error}")
        return 1

    actual = (report.chats, report.routine, report.handoff, report.valid)
    target = (40, 30, 10, 30)
    if actual != target:
        report.failures.append(f"Acceptance totals: expected chats/routine/handoff/valid={target}, got {actual}")
    print("City ECC intake contract validation")
    print(f"Input: {args.csv_path.name}")
    print(f"SHA-256: {digest}")
    print(f"Resident-turn rows: {report.rows}")
    print(f"Unique chats (grouped by chat_id): {report.chats}")
    print(f"Routine chats: {report.routine}")
    print(f"Handoff chats: {report.handoff}")
    print(f"Routine validation: {report.valid} of {report.routine} valid")
    print("\nRoutine counts by request type:")
    for name, count in sorted(report.by_type.items()):
        print(f"- {name}: {count}")
    print("\nHandoff counts by trigger label:")
    for name, count in sorted(report.by_trigger.items()):
        print(f"- {name}: {count}")
    print("\nPer-chat results:")
    print("\n".join(report.results))
    print("\nFailures:")
    if report.failures:
        print("\n".join(f"- {failure}" for failure in report.failures))
    else:
        print("Zero failures.")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
