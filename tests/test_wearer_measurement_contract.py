# -*- coding: utf-8 -*-
import copy
import math
import unittest

from photoloset.wearer_measurement_contract import (
    MEASUREMENT_NAMES,
    REQUEST_SCHEMA,
    compile_contract,
)


def _target_measurement(value, unit="cm", source_kind="TAPE_MEASURE"):
    return {
        "value": value,
        "unit": unit,
        "authority": "MEASURED",
        "source": {"kind": source_kind, "reference": "fitting-2026-08-29"},
    }


def _preview_measurement(minimum, maximum, unit="cm"):
    return {
        "minimum": minimum,
        "maximum": maximum,
        "unit": unit,
        "authority": "PROPOSED",
        "source": {
            "kind": "BOUNDED_PREVIEW_MANNEQUIN",
            "reference": "preview-default-v1",
        },
    }


def _request():
    values = {
        "bust": 92.0,
        "waist": 72.0,
        "hip": 98.0,
        "body_length": 42.0,
        "inseam": 76.0,
        "shoulder": 39.0,
        "sleeve_length": 58.0,
        "height": 164.0,
    }
    return {
        "schema": REQUEST_SCHEMA,
        "target_wearer": {
            "wearer_id": "wearer-a",
            "measurements": {
                name: _target_measurement(value)
                for name, value in values.items()
            },
        },
        "preview_mannequin": {
            "preview_id": "bounded-preview-a",
            "measurements": {
                "chest": _preview_measurement(84.0, 96.0),
                "waist": _preview_measurement(68.0, 82.0),
                "hip": _preview_measurement(90.0, 104.0),
            },
        },
        "fit": {"kind": "CUSTOM", "authority": "REQUESTED"},
        "ease": {
            "chest": {
                "minimum": 4.0,
                "maximum": 7.0,
                "unit": "cm",
                "authority": "REQUESTED",
            },
            "waist": {
                "delta": 3.0,
                "unit": "cm",
                "authority": "REQUESTED",
            },
        },
    }


class WearerMeasurementContractTests(unittest.TestCase):
    maxDiff = None

    def test_real_wearer_and_preview_authorities_stay_separate(self):
        result = compile_contract(_request())

        self.assertEqual(result["decision"], "READY")
        self.assertEqual(result["target_wearer"]["authority"], "MEASURED")
        self.assertEqual(
            result["target_wearer"]["measurements"]["chest_bust"]["value_cm"],
            92.0,
        )
        self.assertEqual(result["preview_mannequin"]["authority"], "PROPOSED")
        self.assertTrue(result["preview_mannequin"]["bounded"])
        self.assertFalse(
            result["preview_mannequin"]["satisfies_target_wearer_gate"])
        self.assertFalse(
            result["claims"]["body_measurements_inferred_from_front_photo"])
        self.assertFalse(result["manufacturing_ready"])

    def test_supports_all_named_measurements_and_explicit_ease(self):
        result = compile_contract(_request())

        self.assertEqual(
            set(result["target_wearer"]["measurements"]),
            set(MEASUREMENT_NAMES),
        )
        self.assertEqual(result["ease"]["chest_bust"], {
            "measurement": "chest_bust",
            "mode": "DELTA_RANGE",
            "minimum_delta_cm": 4.0,
            "maximum_delta_cm": 7.0,
            "unit": "cm",
            "authority": "REQUESTED",
        })
        self.assertEqual(result["ease"]["waist"]["mode"], "EXACT_DELTA")
        self.assertEqual(result["fit"]["kind"], "CUSTOM")
        self.assertFalse(result["fit"]["creates_numeric_ease"])

    def test_m_and_cm_aliases_have_the_same_semantic_digest(self):
        centimetres = _request()
        metres = copy.deepcopy(centimetres)
        measurements = metres["target_wearer"]["measurements"]
        measurements["chest"] = measurements.pop("bust")
        for record in measurements.values():
            record["value"] /= 100.0
            record["unit"] = "m"
        for record in metres["preview_mannequin"]["measurements"].values():
            record["minimum"] /= 100.0
            record["maximum"] /= 100.0
            record["unit"] = "m"
        for record in metres["ease"].values():
            for key in ("delta", "minimum", "maximum"):
                if key in record:
                    record[key] /= 100.0
            record["unit"] = "m"
        reordered = dict(reversed(list(metres.items())))

        first = compile_contract(centimetres)
        second = compile_contract(reordered)
        self.assertEqual(first["contract_digest"], second["contract_digest"])
        self.assertNotEqual(first["input_digest"], second["input_digest"])

    def test_equivalent_chest_and_bust_are_accepted_but_conflicts_stop(self):
        same = _request()
        same["target_wearer"]["measurements"]["chest"] = (
            _target_measurement(0.92, "m"))
        self.assertEqual(compile_contract(same)["decision"], "READY")

        conflicting = copy.deepcopy(same)
        conflicting["target_wearer"]["measurements"]["chest"]["value"] = 95.0
        conflicting["target_wearer"]["measurements"]["chest"]["unit"] = "cm"
        result = compile_contract(conflicting)
        self.assertEqual(result["decision"], "STOP")
        self.assertEqual(result["reason_code"],
                         "UNKNOWN_CONFLICTING_MEASUREMENTS")

    def test_unitless_nonfinite_boolean_and_out_of_bounds_values_stop(self):
        cases = [
            ("unitless", {"unit": None}, "UNKNOWN_EXPLICIT_LENGTH_UNIT_REQUIRED"),
            ("nan", {"value": math.nan},
             "UNKNOWN_NON_CANONICAL_MEASUREMENT_REQUEST"),
            ("boolean", {"value": True}, "UNKNOWN_INVALID_MEASUREMENT_VALUE"),
            ("too-large", {"value": 900.0},
             "UNKNOWN_MEASUREMENT_OUT_OF_BOUNDS"),
        ]
        for label, mutation, code in cases:
            with self.subTest(label=label):
                request = _request()
                request["target_wearer"]["measurements"]["waist"].update(mutation)
                result = compile_contract(request)
                self.assertEqual(result["decision"], "STOP")
                self.assertEqual(result["reason_code"], code)

    def test_target_must_be_measured_and_can_never_come_from_front_photo(self):
        proposed = _request()
        proposed["target_wearer"]["measurements"]["waist"][
            "authority"] = "PROPOSED"
        result = compile_contract(proposed)
        self.assertEqual(result["reason_code"],
                         "UNKNOWN_TARGET_MEASUREMENT_NOT_MEASURED")

        image = _request()
        image["target_wearer"]["measurements"]["waist"]["source"][
            "kind"] = "FRONT_PHOTO"
        result = compile_contract(image)
        self.assertEqual(result["reason_code"],
                         "UNKNOWN_MEASUREMENT_SOURCE_KIND")
        self.assertFalse(
            result["claims"]["body_measurements_inferred_from_front_photo"])

    def test_preview_must_be_bounded_and_proposed(self):
        measured = _request()
        measured["preview_mannequin"]["measurements"]["waist"][
            "authority"] = "MEASURED"
        result = compile_contract(measured)
        self.assertEqual(result["reason_code"],
                         "UNKNOWN_PREVIEW_MEASUREMENT_NOT_PROPOSED")

        reversed_range = _request()
        record = reversed_range["preview_mannequin"]["measurements"]["waist"]
        record["minimum"], record["maximum"] = 90.0, 70.0
        result = compile_contract(reversed_range)
        self.assertEqual(result["reason_code"],
                         "UNKNOWN_INVALID_MEASUREMENT_RANGE")

    def test_ease_requires_an_explicit_typed_delta_or_range(self):
        unitless = _request()
        unitless["ease"]["waist"].pop("unit")
        self.assertEqual(
            compile_contract(unitless)["reason_code"],
            "UNKNOWN_EXPLICIT_LENGTH_UNIT_REQUIRED",
        )

        ambiguous = _request()
        ambiguous["ease"]["waist"].update({"minimum": 1.0, "maximum": 2.0})
        self.assertEqual(
            compile_contract(ambiguous)["reason_code"],
            "UNKNOWN_EXPLICIT_EASE_DELTA_OR_RANGE_REQUIRED",
        )

        reversed_range = _request()
        reversed_range["ease"]["chest"]["minimum"] = 9.0
        self.assertEqual(
            compile_contract(reversed_range)["reason_code"],
            "UNKNOWN_INVALID_EASE_RANGE",
        )

    def test_missing_real_measurement_stops_even_with_preview_value(self):
        request = _request()
        del request["target_wearer"]["measurements"]["hip"]
        result = compile_contract(request)

        self.assertEqual(result["reason_code"],
                         "STOP_TARGET_WEARER_MEASUREMENTS_REQUIRED")
        self.assertEqual(result["missing_measurements"], ["hip"])
        self.assertFalse(
            result["preview_mannequin"]["satisfies_target_wearer_gate"])

    def test_required_measurements_can_be_typed_for_a_garment_scope(self):
        request = _request()
        request["required_measurements"] = ["chest", "body_length", "shoulder"]
        request["target_wearer"]["measurements"] = {
            key: request["target_wearer"]["measurements"][key]
            for key in ("bust", "body_length", "shoulder")
        }
        result = compile_contract(request)

        self.assertEqual(result["decision"], "READY")
        self.assertEqual(result["required_measurements"],
                         ["body_length", "chest_bust", "shoulder"])


if __name__ == "__main__":
    unittest.main()
