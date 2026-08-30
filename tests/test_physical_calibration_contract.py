#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import unittest

from photoloset import physical_calibration_contract as contract


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rights(*uses: str) -> contract.RightsRecord:
    return contract.RightsRecord(
        "fixture-license", "fixture-owner", tuple(uses),
        "fixture://physical-calibration")


def _provenance(label: str, *, producer=contract.ProducerKind.LAB,
                uses=(contract.CALIBRATION_USE,
                      contract.CLAIM_VALIDATION_USE)
                ) -> contract.ProvenanceRecord:
    return contract.ProvenanceRecord(
        source_id=label,
        source_digest=_sha(label),
        method="fixture-method",
        revision="1",
        producer_kind=producer,
        rights=_rights(*uses),
    )


_PROPERTY_VALUES = {
    "composition": {"acrylic": 1.0},
    "thickness": 0.001,
    "stretch_warp": 0.14,
    "stretch_weft": 0.10,
    "friction_static": 0.51,
    "friction_dynamic": 0.42,
    "bending_warp": 0.002,
    "bending_weft": 0.0015,
}


def _properties(*, producer=contract.ProducerKind.LAB,
                authority=contract.EvidenceAuthority.MEASURED,
                uses=(contract.CALIBRATION_USE,
                      contract.CLAIM_VALIDATION_USE),
                overrides=None):
    values = dict(_PROPERTY_VALUES)
    values.update(overrides or {})
    return tuple(
        contract.MaterialPropertyInput(
            name, values[name], contract.MATERIAL_PROPERTY_UNITS[name],
            authority, _provenance("property-%s" % name,
                                   producer=producer, uses=uses),
            conditions={"temperature_c": 20.0, "humidity_percent": 65.0},
        )
        for name in contract.REQUIRED_MATERIAL_PROPERTIES
    )


def _limit_for_unit(unit: str) -> float:
    if unit == "%":
        return 3.0
    if unit == "Pa":
        return 10.0
    if unit == "m":
        return 0.01
    raise AssertionError("unexpected fixture unit")


def _observed_value(unit: str) -> float:
    if unit == "%":
        return 1.0
    if unit == "Pa":
        return 2.0
    if unit == "m":
        return 0.002
    raise AssertionError("unexpected fixture unit")


def _dataset(domain, *, producer=contract.ProducerKind.LAB,
             authority=contract.EvidenceAuthority.MEASURED,
             uses=(contract.CALIBRATION_USE,
                   contract.CLAIM_VALIDATION_USE), reverse=False):
    plan = contract.validation_plan(domain)
    tests = []
    for requirement in plan.requirements:
        observations = tuple(
            contract.CalibrationObservation(
                observation_id="%s-%s-%s" % (
                    requirement.test_kind, requirement.metric, index),
                domain=domain,
                test_kind=requirement.test_kind,
                metric=requirement.metric,
                sample_id="sample-%s" % index,
                value=_observed_value(requirement.unit),
                unit=requirement.unit,
                authority=authority,
                provenance=_provenance(
                    "observation-%s-%s" % (requirement.metric, index),
                    producer=producer, uses=uses),
                conditions={"fixture": "same-specimen"},
            )
            for index in range(requirement.minimum_samples)
        )
        if reverse:
            observations = tuple(reversed(observations))
        tests.append(contract.CalibrationTest(
            test_id="test-%s" % requirement.test_kind,
            domain=domain,
            test_kind=requirement.test_kind,
            observations=observations,
            provenance=_provenance("test-%s" % requirement.test_kind,
                                   producer=producer, uses=uses),
        ))
    if reverse:
        tests.reverse()
    return contract.CalibrationDataset(
        dataset_id="dataset-%s" % domain.value.lower(),
        domain=domain,
        tests=tuple(tests),
        provenance=_provenance("dataset-%s" % domain.value.lower(),
                               producer=producer, uses=uses),
    )


def _thresholds(domain, *, producer=contract.ProducerKind.HUMAN,
                uses=(contract.CALIBRATION_USE,
                      contract.CLAIM_VALIDATION_USE), reverse=False,
                percent_limit=3.0):
    rows = []
    for requirement in contract.validation_plan(domain).requirements:
        value = (percent_limit if requirement.unit == "%"
                 else _limit_for_unit(requirement.unit))
        rows.append(contract.AcceptanceThreshold(
            threshold_id="threshold-%s" % requirement.metric,
            domain=domain,
            metric=requirement.metric,
            operator=contract.ThresholdOperator.MAXIMUM,
            value=value,
            unit=requirement.unit,
            minimum_samples=requirement.minimum_samples,
            approved_by="human-reviewer",
            provenance=_provenance("threshold-%s" % requirement.metric,
                                   producer=producer, uses=uses),
        ))
    if reverse:
        rows.reverse()
    return tuple(rows)


def _claim(kind, *, properties=None, datasets=None, thresholds=None,
           requested_error_percent=None):
    domain = {
        contract.ClaimKind.MATERIAL_CALIBRATED:
            contract.CalibrationDomain.MATERIAL,
        contract.ClaimKind.REAL_CLOTH_ERROR_BOUND:
            contract.CalibrationDomain.REAL_CLOTH,
        contract.ClaimKind.SEAM_CALIBRATED:
            contract.CalibrationDomain.SEAM,
        contract.ClaimKind.WIND_TUNNEL_CALIBRATED:
            contract.CalibrationDomain.WIND_TUNNEL,
    }[kind]
    return contract.ClaimRequest(
        claim_id="claim-%s" % kind.value.lower(),
        subject_id="garment-7",
        claim_kind=kind,
        material_properties=(
            _properties() if properties is None else tuple(properties)),
        datasets=((_dataset(domain),) if datasets is None
                  else tuple(datasets)),
        thresholds=(_thresholds(domain) if thresholds is None
                    else tuple(thresholds)),
        requested_error_percent=requested_error_percent,
    )


class TypedInputTests(unittest.TestCase):
    def test_model_cannot_self_promote_material_to_measured(self):
        item = _properties(producer=contract.ProducerKind.MODEL)[0]
        self.assertEqual(item.authority,
                         contract.EvidenceAuthority.MEASURED)
        self.assertEqual(item.effective_authority,
                         contract.EvidenceAuthority.PROPOSED)
        self.assertEqual(item.to_dict()["effective_authority"], "PROPOSED")

    def test_simulation_has_the_same_proposed_ceiling(self):
        item = _properties(producer=contract.ProducerKind.SIMULATION)[0]
        self.assertEqual(item.effective_authority.value, "PROPOSED")

    def test_non_model_measurement_keeps_measured_authority(self):
        item = _properties()[0]
        self.assertEqual(item.effective_authority.value, "MEASURED")

    def test_material_units_and_composition_are_strict(self):
        with self.assertRaisesRegex(ValueError, "unit must be m"):
            contract.MaterialPropertyInput(
                "thickness", 1.0, "mm", contract.EvidenceAuthority.MEASURED,
                _provenance("bad-unit"))
        with self.assertRaisesRegex(ValueError, "sum to 1"):
            contract.MaterialPropertyInput(
                "composition", {"acrylic": 0.5}, "mass_fraction",
                contract.EvidenceAuthority.MEASURED,
                _provenance("bad-composition"))

    def test_provenance_requires_digest_and_rights_object(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            contract.ProvenanceRecord(
                "source", "not-a-digest", "method", "1",
                contract.ProducerKind.LAB,
                _rights(contract.CALIBRATION_USE))


class DeterministicReductionTests(unittest.TestCase):
    def test_reduction_is_order_independent(self):
        rows = _properties()
        forward = contract.reduce_material_properties(rows)
        backward = contract.reduce_material_properties(tuple(reversed(rows)))
        self.assertEqual(forward, backward)
        self.assertEqual(len(forward["reduction_digest"]), 64)

    def test_conflicts_are_preserved_and_never_averaged(self):
        base = next(row for row in _properties()
                    if row.property_name == "composition")
        conflict = contract.MaterialPropertyInput(
            base.property_name, {"acrylic": 0.5, "wool": 0.5}, base.unit,
            contract.EvidenceAuthority.MEASURED,
            _provenance("conflicting-composition"))
        reduced = contract.reduce_material_properties((base, conflict))
        entry = reduced["entries"][0]
        self.assertEqual(entry["state"], "CONTESTED")
        self.assertEqual(len(entry["distinct_values"]), 2)
        self.assertIsNone(entry["single_supported_value"])
        self.assertFalse(reduced["averaging_performed"])
        self.assertEqual(len(reduced["conflicts"]), 1)

    def test_agreeing_proposal_does_not_erase_measured_source(self):
        measured = _properties()[0]
        proposed = contract.MaterialPropertyInput(
            measured.property_name, measured.value, measured.unit,
            contract.EvidenceAuthority.MEASURED,
            _provenance("model-agrees", producer=contract.ProducerKind.MODEL),
            conditions=measured.conditions)
        result = contract.reduce_material_properties((proposed, measured))
        self.assertEqual(result["entries"][0]["state"], "MEASURED")
        self.assertEqual(len(result["entries"][0]["evidence"]), 2)


class ValidationPlanTests(unittest.TestCase):
    def test_material_seam_and_wind_plans_are_explicit(self):
        material = contract.validation_plan(contract.CalibrationDomain.MATERIAL)
        seam = contract.validation_plan(contract.CalibrationDomain.SEAM)
        wind = contract.validation_plan(contract.CalibrationDomain.WIND_TUNNEL)
        self.assertIn("composition_assay",
                      {row.test_kind for row in material.requirements})
        self.assertIn("seam_puckering",
                      {row.test_kind for row in seam.requirements})
        self.assertIn("pressure_taps",
                      {row.test_kind for row in wind.requirements})
        self.assertEqual(len(material.plan_digest), 64)

    def test_capabilities_name_all_resolution_paths_and_no_imputation(self):
        result = contract.capabilities()
        self.assertEqual(
            result["resolution_options"],
            ["MEASURE", "CONNECT_PROVIDER", "BOUNDED_ALTERNATIVES",
             "TYPED_STOP"])
        self.assertFalse(result["unobserved_is_imputed"])
        self.assertFalse(result["reduction"]["averaging_performed"])


class ClaimGateTests(unittest.TestCase):
    def test_complete_non_model_material_evidence_authorizes_claim(self):
        result = contract.assess_claim(_claim(
            contract.ClaimKind.MATERIAL_CALIBRATED))
        self.assertEqual(result["verdict"], contract.CLAIM_AUTHORIZED)
        self.assertTrue(result["claim_authorized"])
        self.assertEqual(result["claim_authority"], "MEASURED")
        self.assertIsNotNone(result["authorized_claim"])
        self.assertIsNone(result["resolution_request"])

    def test_model_only_properties_block_calibrated_claim(self):
        request = _claim(
            contract.ClaimKind.MATERIAL_CALIBRATED,
            properties=_properties(producer=contract.ProducerKind.MODEL))
        result = contract.assess_claim(request)
        self.assertEqual(result["verdict"], contract.CLAIM_BLOCKED)
        self.assertIsNone(result["authorized_claim"])
        self.assertIn("PROPOSED_MATERIAL_PROPERTY",
                      {row["code"] for row in result["blocking_reasons"]})

    def test_model_only_test_rows_do_not_count_as_measurements(self):
        domain = contract.CalibrationDomain.SEAM
        request = _claim(
            contract.ClaimKind.SEAM_CALIBRATED,
            datasets=(_dataset(domain, producer=contract.ProducerKind.MODEL),))
        result = contract.assess_claim(request)
        self.assertIn(
            "INSUFFICIENT_NON_MODEL_MEASUREMENTS",
            {row["code"] for row in result["blocking_reasons"]})
        self.assertFalse(result["claim_authorized"])

    def test_missing_threshold_cannot_produce_calibrated_claim(self):
        result = contract.assess_claim(_claim(
            contract.ClaimKind.SEAM_CALIBRATED, thresholds=()))
        self.assertIn("MISSING_ACCEPTANCE_THRESHOLD",
                      {row["code"] for row in result["blocking_reasons"]})
        self.assertIsNone(result["authorized_claim"])

    def test_model_proposed_threshold_cannot_authorize_claim(self):
        domain = contract.CalibrationDomain.WIND_TUNNEL
        result = contract.assess_claim(_claim(
            contract.ClaimKind.WIND_TUNNEL_CALIBRATED,
            thresholds=_thresholds(
                domain, producer=contract.ProducerKind.MODEL)))
        self.assertIn("THRESHOLD_NOT_NON_MODEL_APPROVED",
                      {row["code"] for row in result["blocking_reasons"]})

    def test_rights_must_cover_calibration_and_claim_validation(self):
        properties = _properties(uses=(contract.CALIBRATION_USE,))
        result = contract.assess_claim(_claim(
            contract.ClaimKind.MATERIAL_CALIBRATED,
            properties=properties))
        self.assertIn("MATERIAL_RIGHTS_NOT_CLEARED",
                      {row["code"] for row in result["blocking_reasons"]})

    def test_outside_threshold_measurement_blocks_claim(self):
        domain = contract.CalibrationDomain.WIND_TUNNEL
        dataset = _dataset(domain)
        first_test = dataset.tests[0]
        first_observation = first_test.observations[0]
        failing = contract.CalibrationObservation(
            first_observation.observation_id,
            first_observation.domain,
            first_observation.test_kind,
            first_observation.metric,
            first_observation.sample_id,
            1000.0,
            first_observation.unit,
            first_observation.authority,
            first_observation.provenance,
            first_observation.conditions,
        )
        changed_test = contract.CalibrationTest(
            first_test.test_id, first_test.domain, first_test.test_kind,
            (failing,) + first_test.observations[1:], first_test.provenance)
        changed_dataset = contract.CalibrationDataset(
            dataset.dataset_id, dataset.domain,
            (changed_test,) + dataset.tests[1:], dataset.provenance)
        result = contract.assess_claim(_claim(
            contract.ClaimKind.WIND_TUNNEL_CALIBRATED,
            datasets=(changed_dataset,)))
        self.assertIn("MEASUREMENT_OUTSIDE_THRESHOLD",
                      {row["code"] for row in result["blocking_reasons"]})

    def test_seam_and_wind_claims_pass_only_with_their_complete_plans(self):
        seam = contract.assess_claim(_claim(
            contract.ClaimKind.SEAM_CALIBRATED))
        wind = contract.assess_claim(_claim(
            contract.ClaimKind.WIND_TUNNEL_CALIBRATED))
        self.assertEqual(seam["verdict"], contract.CLAIM_AUTHORIZED)
        self.assertEqual(wind["verdict"], contract.CLAIM_AUTHORIZED)
        missing_test_dataset = contract.CalibrationDataset(
            _dataset(contract.CalibrationDomain.WIND_TUNNEL).dataset_id,
            contract.CalibrationDomain.WIND_TUNNEL,
            _dataset(contract.CalibrationDomain.WIND_TUNNEL).tests[:-1],
            _dataset(contract.CalibrationDomain.WIND_TUNNEL).provenance)
        blocked = contract.assess_claim(_claim(
            contract.ClaimKind.WIND_TUNNEL_CALIBRATED,
            datasets=(missing_test_dataset,)))
        self.assertIn("MISSING_VALIDATION_TEST",
                      {row["code"] for row in blocked["blocking_reasons"]})

    def test_decision_digest_is_independent_of_input_order(self):
        domain = contract.CalibrationDomain.MATERIAL
        forward = contract.ClaimRequest(
            "ordered", "garment-7",
            contract.ClaimKind.MATERIAL_CALIBRATED,
            _properties(), (_dataset(domain),), _thresholds(domain))
        backward = contract.ClaimRequest(
            "ordered", "garment-7",
            contract.ClaimKind.MATERIAL_CALIBRATED,
            tuple(reversed(_properties())), (_dataset(domain, reverse=True),),
            _thresholds(domain, reverse=True))
        self.assertEqual(forward.request_digest, backward.request_digest)
        self.assertEqual(contract.assess_claim(forward),
                         contract.assess_claim(backward))

    def test_observation_conflict_is_preserved_not_averaged(self):
        domain = contract.CalibrationDomain.SEAM
        dataset = _dataset(domain)
        test = dataset.tests[0]
        original = test.observations[0]
        conflict = contract.CalibrationObservation(
            "conflict", original.domain, original.test_kind, original.metric,
            original.sample_id, original.value + 0.5, original.unit,
            contract.EvidenceAuthority.MEASURED,
            _provenance("conflict-observation"), original.conditions)
        changed_test = contract.CalibrationTest(
            test.test_id, test.domain, test.test_kind,
            test.observations + (conflict,), test.provenance)
        changed_dataset = contract.CalibrationDataset(
            dataset.dataset_id, dataset.domain,
            (changed_test,) + dataset.tests[1:], dataset.provenance)
        result = contract.assess_claim(_claim(
            contract.ClaimKind.SEAM_CALIBRATED,
            datasets=(changed_dataset,)))
        self.assertIn("CONTESTED_CALIBRATION_OBSERVATION",
                      {row["code"] for row in result["blocking_reasons"]})
        self.assertEqual(len(result["observation_conflicts"]), 1)
        self.assertEqual(
            result["observation_conflicts"][0]["aggregate_operation"], "NONE")

    def test_blocked_decision_has_all_typed_resolution_options(self):
        result = contract.assess_claim(_claim(
            contract.ClaimKind.MATERIAL_CALIBRATED,
            properties=(), datasets=(), thresholds=()))
        resolution = result["resolution_request"]
        options = {row["kind"]: row for row in resolution["options"]}
        self.assertEqual(
            set(options),
            {"MEASURE", "CONNECT_PROVIDER", "BOUNDED_ALTERNATIVES",
             "TYPED_STOP"})
        self.assertFalse(options["BOUNDED_ALTERNATIVES"]
                         ["can_satisfy_claim"])
        self.assertFalse(options["TYPED_STOP"]["can_satisfy_claim"])
        self.assertFalse(resolution["model_may_author_measurements"])


class RealClothErrorClaimTests(unittest.TestCase):
    def test_few_percent_claim_needs_explicit_measured_evidence(self):
        domain = contract.CalibrationDomain.REAL_CLOTH
        model_dataset = _dataset(domain, producer=contract.ProducerKind.MODEL)
        result = contract.assess_claim(_claim(
            contract.ClaimKind.REAL_CLOTH_ERROR_BOUND,
            datasets=(model_dataset,), requested_error_percent=3.0))
        self.assertEqual(result["verdict"], contract.CLAIM_BLOCKED)
        self.assertIsNone(result["authorized_claim"])

    def test_explicit_three_percent_validation_can_authorize_claim(self):
        result = contract.assess_claim(_claim(
            contract.ClaimKind.REAL_CLOTH_ERROR_BOUND,
            requested_error_percent=3.0))
        self.assertEqual(result["verdict"], contract.CLAIM_AUTHORIZED)
        self.assertEqual(
            result["authorized_claim"]["maximum_error_percent"], 3.0)
        self.assertTrue(result["authorized_claim"]["few_percent_claim"])

    def test_weaker_threshold_cannot_support_tighter_claim(self):
        domain = contract.CalibrationDomain.REAL_CLOTH
        result = contract.assess_claim(_claim(
            contract.ClaimKind.REAL_CLOTH_ERROR_BOUND,
            thresholds=_thresholds(domain, percent_limit=6.0),
            requested_error_percent=3.0))
        self.assertIn("REQUESTED_ERROR_BOUND_NOT_COVERED",
                      {row["code"] for row in result["blocking_reasons"]})
        self.assertIsNone(result["authorized_claim"])


if __name__ == "__main__":
    unittest.main()
