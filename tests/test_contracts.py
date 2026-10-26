"""Regression checks for required fields, routing, and fixture corruption."""

import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from ecc_intake.loader import DEFAULT_CSV, decode_value, main, validate_csv
from ecc_intake.models import MODEL_BY_TYPE, IllegallyParkedVehicle


class ContractsTest(unittest.TestCase):
    def setUp(self) -> None:
        with DEFAULT_CSV.open(encoding="utf-8-sig", newline="") as source:
            self.rows = list(csv.DictReader(source))

    def write_fixture(self, directory: str) -> Path:
        path = Path(directory) / "mutated.csv"
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=list(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)
        return path

    def test_original_counts_and_explicit_zero_failures(self) -> None:
        report = validate_csv(DEFAULT_CSV)
        self.assertEqual((report.rows, report.chats, report.routine, report.handoff, report.valid), (80, 40, 30, 10, 30))
        self.assertEqual(report.failures, [])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main([str(DEFAULT_CSV)]), 0)
        self.assertIn("Failures:\nZero failures.", output.getvalue())

    def test_every_model_key_is_required(self) -> None:
        for request_type, model in MODEL_BY_TYPE.items():
            row = next(row for row in self.rows if row["expected_request_type"] == request_type)
            payload = {
                name: decode_value(name, row[f"expected_{name}"])
                for name in model.model_fields if name not in {"conversation_id", "request_type"}
            }
            payload.update(conversation_id=row["chat_id"], request_type=request_type)
            model.model_validate(payload)
            for name, definition in model.model_fields.items():
                with self.subTest(model=request_type, field=name):
                    self.assertTrue(definition.is_required())
                    incomplete = dict(payload)
                    del incomplete[name]
                    with self.assertRaises(ValidationError):
                        model.model_validate(incomplete)

    def test_unreadable_plate_accepts_explicit_null_only(self) -> None:
        payload = dict(request_type="illegally_parked_vehicle", conversation_id="ECC-T-010", location="400 block of Sutter St", vehicle_description="tan Ford Econoline van", license_plate=None, blocking_driveway=False, callback_phone="(555) 016-5523")
        self.assertIsNone(IllegallyParkedVehicle.model_validate(payload).license_plate)
        payload["license_plate"] = "   "
        with self.assertRaises(ValidationError):
            IllegallyParkedVehicle.model_validate(payload)

    def test_false_is_false_and_invalid_boolean_is_rejected(self) -> None:
        self.assertIs(decode_value("blocking_driveway", "false"), False)
        for row in self.rows:
            if row["chat_id"] == "ECC-T-002":
                row["expected_blocking_driveway"] = "maybe"
        with tempfile.TemporaryDirectory() as directory:
            report = validate_csv(self.write_fixture(directory))
        self.assertEqual(report.valid, 29)
        self.assertTrue(any("blocking_driveway" in failure for failure in report.failures))

    def test_blank_required_and_cross_type_fields_are_both_reported(self) -> None:
        for row in self.rows:
            if row["chat_id"] == "ECC-T-001":
                row["expected_location"] = ""
                row["expected_vehicle_description"] = "unexpected car"
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_fixture(directory)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main([str(path)]), 1)
        self.assertIn("location:", output.getvalue())
        self.assertIn("vehicle_description:", output.getvalue())
        self.assertNotIn("Zero failures.", output.getvalue())

    def test_conflicting_turn_annotations_fail_instead_of_selecting_a_row(self) -> None:
        self.rows[1]["expected_location"] = "a different location"
        with tempfile.TemporaryDirectory() as directory:
            report = validate_csv(self.write_fixture(directory))
        self.assertTrue(any("ECC-T-001: conflicting annotations" in failure for failure in report.failures))

    def test_handoff_trigger_and_label_mismatch_are_failures(self) -> None:
        for row in self.rows:
            if row["chat_id"] == "ECC-T-004":
                row["expected_handoff_trigger"] = ""
            if row["chat_id"] == "ECC-T-008":
                row["chat_label"] = "routine"
        with tempfile.TemporaryDirectory() as directory:
            report = validate_csv(self.write_fixture(directory))
        self.assertTrue(any("ECC-T-004: missing/unknown handoff trigger" in failure for failure in report.failures))
        self.assertTrue(any("ECC-T-008: inconsistent/unknown" in failure for failure in report.failures))

    def test_unordered_rows_work_but_duplicate_turns_fail(self) -> None:
        self.rows.reverse()
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(validate_csv(self.write_fixture(directory)).valid, 30)
            self.rows.append(self.rows[0].copy())
            report = validate_csv(self.write_fixture(directory))
        self.assertTrue(any("invalid turn_number" in failure for failure in report.failures))

    def test_missing_chat_fails_acceptance_totals(self) -> None:
        self.rows = [row for row in self.rows if row["chat_id"] != "ECC-T-040"]
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main([str(self.write_fixture(directory))]), 1)
        self.assertIn("Acceptance totals", output.getvalue())


if __name__ == "__main__":
    unittest.main()
