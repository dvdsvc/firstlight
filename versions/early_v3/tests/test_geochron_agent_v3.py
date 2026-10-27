from __future__ import annotations

import unittest

from geochron_agent_v3.router import route_geochronology
from geochron_agent_v3.state import (
    apply_profile_delta,
    coverage_context,
    create_state,
    queue_tool_jobs,
    route_state,
    state_digest,
)
from geochron_agent_v3.tools import validate_profile_delta


def _valid_delta() -> dict:
    return {
        "profile_id": "upb_in_situ",
        "sample_patches": [
            {
                "sample_id": "js-jch",
                "sample_fields_add": {"origin": "self", "rock_type": "tuff"},
                "sample_evidence": {
                    "evidence_text": "Sample js-jch is a tuff.",
                    "source_locator": "Sample description",
                },
                "analytical_context_add": {
                    "isotope_system": "U-Pb",
                    "technique": "LA-ICP-MS",
                    "mineral": "zircon",
                },
                "analytical_evidence": {
                    "evidence_text": "Zircons were analyzed by LA-ICP-MS.",
                    "source_locator": "Methods",
                },
                "spots_add": [
                    {
                        "id": "js-jch-01",
                        "material": "zircon",
                        "evidence": {
                            "evidence_text": "js-jch-01",
                            "source_locator": "Table 1",
                        },
                    }
                ],
                "age_results_add": [
                    {
                        "id": "result_js_jch_134",
                        "result_type": "peak_age",
                        "value": {"number": 134, "unit": "Ma", "error": {"value": 2}},
                        "statistical_model": None,
                        "distribution_state": "youngest_peak",
                        "source_spot_ids": ["js-jch-01"],
                        "evidence": {
                            "evidence_text": "js-jch has a 134 +/- 2 Ma peak",
                            "source_locator": "Figure 4",
                        },
                    }
                ],
                "events_add": [
                    {
                        "id": "event_js_jch_eruption",
                        "result_ids": ["result_js_jch_134"],
                        "geologic_process": "eruption",
                        "isotopic_role": "primary",
                        "preferred": True,
                        "annotation": None,
                        "evidence": {
                            "evidence_text": "the volcanic activity erupted at 134 +/- 2 Ma",
                            "source_locator": "Discussion",
                        },
                    }
                ],
            }
        ],
        "conflicts": [],
        "uncovered": [],
    }


class RouterTests(unittest.TestCase):
    def test_routes_la_icp_ms(self) -> None:
        decisions = route_geochronology(
            "Zircon U-Pb dating was performed by LA-ICP-MS using 30 um spots."
        )
        selected = [decision for decision in decisions if decision["status"] == "selected"]
        self.assertEqual(selected[0]["profile_id"], "upb_in_situ")
        self.assertEqual(selected[0]["technique"], "LA-ICP-MS")

    def test_literature_shrimp_mentions_do_not_override_dominant_la_icp_ms(self) -> None:
        decisions = route_geochronology(
            "LA-ICP-MS zircon U-Pb spot analyses. "
            "Laser ablation conditions are reported in the methods. "
            "A previous SHRIMP study is cited for comparison."
        )
        selected = [decision for decision in decisions if decision["status"] == "selected"]
        self.assertEqual(selected[0]["technique"], "LA-ICP-MS")

    def test_id_tims_grain_words_do_not_imply_in_situ_profile(self) -> None:
        decisions = route_geochronology(
            "Zircon grains and analysis points were dissolved as fractions for "
            "CA-ID-TIMS U-Pb isotope dilution with a tracer."
        )
        self.assertFalse(any(d["status"] == "selected" for d in decisions))
        self.assertTrue(any(d["profile_id"] == "upb_id_tims" for d in decisions))


class StateTests(unittest.TestCase):
    def test_router_fallback_creates_profile_job(self) -> None:
        state = create_state("paper-1", "锆石 U-Pb LA-ICP-MS 测点分析")
        routed = route_state(state)
        self.assertEqual(routed["jobs"][0]["profile_id"], "upb_in_situ")
        self.assertEqual(routed["jobs"][0]["status"], "pending")

    def test_job_queue_accepts_batch_and_records_unknown_tool_request(self) -> None:
        state = create_state("paper-1", "text")
        queued = queue_tool_jobs(
            state,
            [
                {"profile_id": "upb_in_situ", "reason": "U-Pb", "evidence": ["U-Pb"]},
                {"profile_id": "arar_step_heating", "reason": "Ar-Ar", "evidence": ["plateau"]},
            ],
            trigger="router",
        )
        self.assertEqual(len(queued["jobs"]), 1)
        self.assertEqual(queued["jobs"][0]["profile_id"], "upb_in_situ")
        self.assertEqual(queued["unresolved"][0]["type"], "unknown_profile_request")

    def test_delta_reducer_preserves_sample_tree(self) -> None:
        state = create_state("paper-1", "text")
        queued = queue_tool_jobs(
            state,
            [{"profile_id": "upb_in_situ", "reason": "U-Pb", "evidence": ["U-Pb"]}],
            trigger="router",
        )
        applied = apply_profile_delta(queued, queued["jobs"][0]["job_id"], _valid_delta())
        sample = applied["profile_states"]["upb_in_situ"]["samples"]["js-jch"]
        self.assertEqual(applied["jobs"][0]["status"], "completed")
        self.assertEqual(sample["analytical_context"]["technique"], "LA-ICP-MS")
        self.assertEqual(sample["spots"][0]["id"], "js-jch-01")
        self.assertEqual(sample["age_results"][0]["id"], "result_js_jch_134")
        self.assertEqual(sample["events"][0]["result_ids"], ["result_js_jch_134"])
        self.assertIn("js-jch", applied["shared_sample_registry"])

    def test_delta_reducer_rejects_arar_disguised_as_upb(self) -> None:
        state = create_state("paper-1", "text")
        queued = queue_tool_jobs(
            state,
            [{"profile_id": "upb_in_situ", "reason": "U-Pb", "evidence": ["U-Pb"]}],
            trigger="router",
        )
        delta = _valid_delta()
        delta["sample_patches"][0]["analytical_context_add"]["isotope_system"] = "Ar-Ar"
        applied = apply_profile_delta(queued, queued["jobs"][0]["job_id"], delta)
        self.assertEqual(applied["jobs"][0]["status"], "rejected")
        self.assertTrue(
            any(flag["type"] == "tool_contract_violation" for flag in applied["audit_flags"])
        )

    def test_event_reference_must_exist_in_same_sample_tree(self) -> None:
        state = create_state("paper-1", "text")
        queued = queue_tool_jobs(
            state,
            [{"profile_id": "upb_in_situ", "reason": "U-Pb", "evidence": ["U-Pb"]}],
            trigger="router",
        )
        delta = _valid_delta()
        delta["sample_patches"][0]["events_add"][0]["result_ids"] = ["missing"]
        applied = apply_profile_delta(queued, queued["jobs"][0]["job_id"], delta)
        self.assertEqual(applied["jobs"][0]["status"], "rejected")

    def test_state_digest_does_not_repeat_paper_text(self) -> None:
        state = create_state("paper-1", "very long paper")
        digest = state_digest(state)
        self.assertNotIn("document_text", digest)
        self.assertEqual(digest["document_id"], "paper-1")

    def test_coverage_context_keeps_results_and_events_under_sample(self) -> None:
        state = create_state("paper-1", "text")
        queued = queue_tool_jobs(
            state,
            [{"profile_id": "upb_in_situ", "reason": "U-Pb", "evidence": ["U-Pb"]}],
            trigger="router",
        )
        applied = apply_profile_delta(queued, queued["jobs"][0]["job_id"], _valid_delta())
        context = coverage_context(applied)
        sample = context["profiles"]["upb_in_situ"]["samples"][0]
        self.assertEqual(sample["spot_count"], 1)
        self.assertEqual(sample["age_results"][0]["result_type"], "peak_age")
        self.assertEqual(sample["events"][0]["geologic_process"], "eruption")


class ProfileTests(unittest.TestCase):
    def test_delta_contract_accepts_valid_tree_patch(self) -> None:
        report = validate_profile_delta("upb_in_situ", _valid_delta())
        self.assertTrue(report["valid"], report["errors"])

    def test_delta_contract_rejects_foreign_method(self) -> None:
        delta = _valid_delta()
        delta["sample_patches"][0]["analytical_context_add"]["isotope_system"] = "Ar-Ar"
        report = validate_profile_delta("upb_in_situ", delta)
        self.assertFalse(report["valid"])
        self.assertTrue(any("isotope_system" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
