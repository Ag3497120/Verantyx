#!/usr/bin/env python3
import unittest

from photoloset.garment_ir import (
    CommandRefusal, GarmentCommand, Intent, RefusalCode,
    parse, parse_garment_command, validate, validate_command_envelope,
)


class GarmentIRTests(unittest.TestCase):
    def test_japanese_span_edit_has_explicit_unit(self):
        result = parse_garment_command("30番から35番を3cm広げて", "c-1")
        self.assertIsInstance(result, GarmentCommand)
        self.assertEqual(result.intent, Intent.ADJUST_PATTERN_SPAN)
        self.assertEqual(result.target["first"], 30)
        self.assertEqual(result.operation["kind"], "ADD_EASE")
        self.assertEqual(result.operation["value"], 3.0)
        self.assertEqual(result.operation["unit"], "cm")
        self.assertFalse(result.commit)

    def test_missing_unit_refuses_instead_of_guessing(self):
        result = parse_garment_command("30番から35番を3広げて", "c-2")
        self.assertIsInstance(result, CommandRefusal)
        self.assertEqual(result.verdict, RefusalCode.MISSING_UNIT)

    def test_dimension_without_span_is_ambiguous(self):
        result = parse_garment_command("3cm広げて", "c-3")
        self.assertEqual(result.verdict, RefusalCode.AMBIGUOUS_TARGET)

    def test_reverse_span_is_refused(self):
        result = parse_garment_command("35番から30番を3cm広げて", "c-4")
        self.assertEqual(result.verdict, RefusalCode.AMBIGUOUS_TARGET)

    def test_unknown_sentence_is_not_mapped_to_nearest_intent(self):
        result = parse_garment_command("たぶんいい感じにしてください", "c-5")
        self.assertEqual(result.verdict, RefusalCode.UNKNOWN_WORDS)

    def test_simple_closed_intent_is_deterministic(self):
        result = parse_garment_command("立体十字シミュレーションを実行", "c-6")
        self.assertEqual(result.intent, Intent.RUN_SIMULATION)
        self.assertEqual(result.target["kind"], "CURRENT_GARMENT")

    def test_envelope_requires_all_fields_and_explicit_unit(self):
        envelope = {"schema": "garment.command.v1", "command_id": "c-7",
                    "intent": "ADJUST_PATTERN_SPAN",
                    "target": {"first": 1, "last": 2},
                    "operation": {"kind": "ADD_EASE", "value": 2},
                    "commit": False, "provenance": "HUMAN_INPUT"}
        result = validate_command_envelope(envelope)
        self.assertEqual(result.verdict, RefusalCode.MISSING_UNIT)

    def test_command_is_immutable_and_export_is_detached(self):
        result = parse_garment_command("30から35を3cm広げて", "c-8")
        with self.assertRaises(TypeError):
            result.target["first"] = 99
        exported = result.as_dict()
        exported["target"]["first"] = 99
        self.assertEqual(result.target["first"], 30)

    def test_public_parse_and_validate_are_stable_json_dicts(self):
        parsed = parse("30番から35番を3cm広げて")
        self.assertEqual(parsed, parse("30番から35番を3cm広げて"))
        self.assertEqual(parsed["intent"], "ADJUST_PATTERN_SPAN")
        self.assertEqual(validate(parsed), parsed)

    def test_model_requirement_ir_accepts_text_and_requires_units_for_numbers(self):
        command = {
            "schema": "garment.command.v1", "command_id": "req-1",
            "intent": "SET_REQUIREMENTS", "target": {"kind": "ACTIVE_GARMENT"},
            "operation": {"kind": "SET_REQUIREMENTS", "requirements": [
                {"kind": "STANDARD_SIZE", "target": "whole garment", "text": "M"},
                {"kind": "GARMENT_MEASUREMENT", "target": "finished chest",
                 "value": 96, "unit": "cm"},
                {"kind": "DETAIL", "target": "collar", "text": "more rounded"},
            ]},
            "commit": False, "provenance": "MODEL_PROPOSAL",
        }
        accepted = validate_command_envelope(command)
        self.assertEqual(accepted.intent, Intent.SET_REQUIREMENTS)
        command["operation"]["requirements"][1].pop("unit")
        refused = validate_command_envelope(command)
        self.assertEqual(refused.verdict, RefusalCode.MISSING_UNIT)


if __name__ == "__main__":
    unittest.main()
