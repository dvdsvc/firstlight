from __future__ import annotations

import unittest

from geochron_agent_v3.honeypot import (
    build_control_run,
    evaluate_control_run,
    inject_controls_into_structure,
    plan_router_injections,
    plan_structural_injections,
    strip_control_relations,
)
from geochron_agent_v3.router import route_geochronology
from geochron_agent_v3.registry import get_profile, list_profiles
from geochron_agent_v3.profiles.standard import decode_delta_wire
from geochron_agent_v3.state import (
    apply_profile_delta,
    coverage_context,
    create_state,
    document_with_controls,
    prepare_honeypot_run,
    queue_tool_jobs,
    route_state,
    state_digest,
)
from geochron_agent_v3.tools import validate_profile_delta


def _valid_delta() -> dict:
    return {
        "profile_id": "upb_in_situ",
        "operation": "discover",
        "sample_patches": [
            {
                "sample_id": "js-jch",
                "sample_attributes_add": {"RockClass": "tuff"},
                "sample_evidence": {
                    "evidence_text": "Sample js-jch is a tuff.",
                    "source_locator": "Sample description",
                },
                "method_context_add": {
                    "isotope_system": "U-Pb",
                    "technique": "LA-ICP-MS",
                    "SampleMaterial": "zircon",
                    "scope": "self",
                },
                "method_evidence": {
                    "evidence_text": "Zircons were analyzed by LA-ICP-MS.",
                    "source_locator": "Methods",
                },
                "raw_observations_add": [
                    {
                        "id": "js-jch-01",
                        "unit_type": "spot",
                        "fields": {"Analysis_ID": "js-jch-01", "U": 200},
                        "evidence": {
                            "evidence_text": "js-jch-01",
                            "source_locator": "Table 1",
                        },
                    }
                ],
                "aggregate_observations_add": [
                    {
                        "id": "result_js_jch_134",
                        "fields": {
                            "Age_Text": "134 Ma",
                            "AgeUnc_Text": "2 Ma",
                            "AgeIntpnType": "peak age",
                        },
                        "source_raw_observation_ids": ["js-jch-01"],
                        "evidence": {
                            "evidence_text": "js-jch has a 134 +/- 2 Ma peak",
                            "source_locator": "Figure 4",
                        },
                    }
                ],
                "author_inferences_add": [
                    {
                        "id": "event_js_jch_eruption",
                        "aggregate_observation_ids": ["result_js_jch_134"],
                        "fields": {
                            "AgeIntpnClass": "eruption age",
                            "AgeIntprtdDesc": "volcanic eruption",
                        },
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


def _strict_wire_delta() -> dict:
    return {
        "profile_id": "upb_in_situ",
        "operation": "discover",
        "sample_patches": [
            {
                "sample_id": "MZ815",
                "sample_attributes": [{"name": "RockClass", "value": "basalt"}],
                "method_context": {
                    "isotope_system": "U-Pb",
                    "technique": "LA-ICP-MS",
                    "scope": "self",
                    "field_values": [],
                },
                "raw_observations": [
                    {
                        "id": "MZ815-1.1",
                        "unit_type": "spot",
                        "field_values": [
                            {"name": "Analysis_ID", "value": "MZ815-1.1"},
                            {"name": "U", "value": 200},
                        ],
                    }
                ],
                "aggregate_observations": [
                    {
                        "id": "MZ815_120",
                        "field_values": [
                            {"name": "Age_Text", "value": "120 Ma"},
                            {"name": "AgeUnc_Text", "value": "1 Ma"},
                        ],
                        "source_raw_observation_ids": ["MZ815-1.1"],
                    }
                ],
                "author_inferences": [
                    {
                        "id": "MZ815_eruption",
                        "aggregate_observation_ids": ["MZ815_120"],
                        "field_values": [
                            {"name": "AgeIntpnClass", "value": "eruption age"}
                        ],
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
        selected = [d for d in decisions if d["status"] == "selected"]
        self.assertEqual(selected[0]["profile_id"], "upb_id_tims")
        self.assertNotIn("upb_in_situ", [d["profile_id"] for d in selected])

    def test_router_can_select_multiple_isotope_tools(self) -> None:
        decisions = route_geochronology(
            "Zircon U-Pb was measured by LA-ICP-MS. "
            "Biotite 40Ar/39Ar incremental heating yielded a plateau age."
        )
        selected = {d["profile_id"] for d in decisions if d["status"] == "selected"}
        self.assertEqual(selected, {"upb_in_situ", "arar_incremental_heating"})


class HoneypotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run = build_control_run("paper-control", ["upb_in_situ"])
        self.relations = [
            {**relation, "profile_id": "upb_in_situ"}
            for control in self.run["controls"]
            for relation in control["expected_relations"]
        ]

    def test_control_suite_passes_on_exact_observations(self) -> None:
        report = evaluate_control_run(self.run, self.relations)
        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["fail_reasons"])

    def test_two_expected_relations_collapsed_to_one_is_merged(self) -> None:
        report = evaluate_control_run(self.run, self.relations[1:])
        first = next(item for item in report["controls"] if item["control_id"] == "hp_upb_relation_split")
        self.assertEqual(first["status"], "fail")
        self.assertEqual(first["fail_reasons"], ["merged"])

    def test_wrong_sample_is_reported_as_misbound(self) -> None:
        observed = [dict(item) for item in self.relations]
        observed[0]["sample_id"] = "wrong-sample"
        report = evaluate_control_run(self.run, observed)
        self.assertIn("misbound", report["fail_reasons"])

    def test_control_delta_is_removed_before_real_state_write(self) -> None:
        expected = self.relations[0]
        delta = {
            "profile_id": "upb_in_situ",
            "operation": "discover",
            "sample_patches": [
                {
                    "sample_id": expected["sample_id"],
                    "aggregate_observations_add": [
                        {
                            "id": "control-result",
                            "fields": {
                                "Age_Text": f"{expected['number']} Ma",
                                "AgeUnc_Text": f"{expected['error']} Ma",
                            },
                            "source_raw_observation_ids": [],
                        }
                    ],
                    "author_inferences_add": [],
                },
                {
                    "sample_id": "real-sample",
                    "aggregate_observations_add": [
                        {
                            "id": "real-result",
                            "fields": {"Age_Text": "88 Ma", "AgeUnc_Text": "1 Ma"},
                            "source_raw_observation_ids": [],
                        }
                    ],
                    "author_inferences_add": [],
                },
            ],
        }
        cleaned = strip_control_relations(self.run, delta)
        self.assertEqual([item["sample_id"] for item in cleaned["sample_patches"]], ["real-sample"])

    def test_controls_are_embedded_in_result_domains_before_next_heading(self) -> None:
        paper = (
            "3.1 MZ815 zircon U-Pb ages\n"
            "样品 MZ815 的锆石 LA-ICP-MS U-Pb 分析结果为（120±1）Ma。\n"
            "加权平均年龄与区域年龄一致。\n"
            "3.2 MZ819 zircon U-Pb ages\n"
            "样品 MZ819 的锆石 U-Pb 年龄为（128±3）Ma。\n"
            "4 Discussion\n"
            "前人 Ar-Ar 年龄用于区域对比。\n"
        )
        planned = plan_structural_injections(paper, self.run)
        augmented = inject_controls_into_structure(paper, planned)
        self.assertEqual(len(planned["controls"]), 3)
        self.assertNotIn("[Document validation controls]", augmented)
        self.assertIn("HPUPB-01", augmented)
        discussion = augmented.index("4 Discussion")
        self.assertLess(augmented.index("3.1 MZ815"), augmented.index("HPUPB-01"))
        self.assertLess(augmented.index("HPUPB-01"), discussion)
        self.assertTrue(all(item["anchor"]["heading_path"] for item in planned["injections"]))

    def test_mineru_blocks_can_supply_the_structural_anchor(self) -> None:
        paper = "3.1 Results\nSample MZ815 zircon U-Pb age is 120±1 Ma.\n4 Discussion\n"
        blocks = [
            {"type": "title", "text": "3.1 Results", "text_level": 2},
            {"type": "text", "text": "Sample MZ815 zircon U-Pb age is 120±1 Ma."},
            {"type": "title", "text": "4 Discussion", "text_level": 1},
        ]
        planned = plan_structural_injections(paper, self.run, blocks)
        self.assertEqual(planned["injections"][0]["anchor"]["heading_path"], ["3.1 Results"])

    def test_router_anchor_accepts_harmless_spacing_and_parenthesis_variants(self) -> None:
        paper = "3.1 Results\n样品 MZ819 的加权平均结果为（120±1） Ma。\n"
        planned = plan_router_injections(
            paper,
            build_control_run("router-anchor", ["upb_in_situ"], max_controls=1),
            {
                "upb_in_situ": [
                    {
                        "sample_id": "MZ819",
                        "age_text": "(120±1) Ma",
                        "evidence_text": "样品 MZ819 的加权平均结果为(120±1)Ma",
                    }
                ]
            },
        )
        self.assertEqual(len(planned["injections"]), 1)
        self.assertIn("HPUPB-01", inject_controls_into_structure(paper, planned))

    def test_unexecuted_expected_profile_is_misrouted(self) -> None:
        report = evaluate_control_run(self.run, [], executed_profile_ids=[])
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["fail_reasons"], ["misrouted"])


class StateTests(unittest.TestCase):
    def test_honeypot_is_prepared_inside_a_result_domain(self) -> None:
        paper = (
            "3.1 Zircon U-Pb ages\n"
            "样品 MZ815 的 LA-ICP-MS 锆石 U-Pb 加权平均年龄为（120±1）Ma。\n"
            "4 Discussion\n"
        )
        state = create_state("paper-control", paper)
        prepared = prepare_honeypot_run(state, ["upb_in_situ"])
        run = prepared["honeypot"]["active_run"]
        self.assertIsNotNone(run)
        self.assertTrue(run["injections"])
        self.assertIn("HPUPB-01", document_with_controls(prepared))
        self.assertNotIn("[Document validation controls]", document_with_controls(prepared))

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
                {
                    "profile_id": "arar_incremental_heating",
                    "reason": "Ar-Ar",
                    "evidence": ["plateau"],
                },
            ],
            trigger="router",
        )
        self.assertEqual(len(queued["jobs"]), 2)
        self.assertEqual(queued["jobs"][0]["profile_id"], "upb_in_situ")
        self.assertEqual(queued["jobs"][1]["profile_id"], "arar_incremental_heating")
        self.assertFalse(queued["unresolved"])

    def test_enrichment_is_a_distinct_profile_operation(self) -> None:
        state = create_state("paper-1", "text")
        queued = queue_tool_jobs(
            state,
            [
                {
                    "profile_id": "u_th_he",
                    "operation": "enrich_candidates",
                    "reason": "FT correction is present",
                    "evidence": ["Ft correction"],
                }
            ],
            trigger="coverage_follow_up",
        )
        self.assertEqual(queued["jobs"][0]["operation"], "enrich_candidates")

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
        self.assertEqual(sample["method_context"]["technique"], "LA-ICP-MS")
        self.assertEqual(sample["raw_observations"][0]["id"], "js-jch-01")
        self.assertEqual(sample["aggregate_observations"][0]["id"], "result_js_jch_134")
        self.assertEqual(
            sample["author_inferences"][0]["aggregate_observation_ids"],
            ["result_js_jch_134"],
        )
        self.assertIn("js-jch", applied["shared_sample_registry"])

    def test_delta_reducer_rejects_arar_disguised_as_upb(self) -> None:
        state = create_state("paper-1", "text")
        queued = queue_tool_jobs(
            state,
            [{"profile_id": "upb_in_situ", "reason": "U-Pb", "evidence": ["U-Pb"]}],
            trigger="router",
        )
        delta = _valid_delta()
        delta["sample_patches"][0]["method_context_add"]["isotope_system"] = "40Ar/39Ar"
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
        delta["sample_patches"][0]["author_inferences_add"][0]["aggregate_observation_ids"] = ["missing"]
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
        self.assertEqual(sample["raw_observation_count"], 1)
        self.assertEqual(sample["aggregate_observations"][0]["fields"]["AgeIntpnType"], "peak age")
        self.assertEqual(sample["author_inferences"][0]["fields"]["AgeIntpnClass"], "eruption age")


class ProfileTests(unittest.TestCase):
    def test_delta_contract_accepts_valid_tree_patch(self) -> None:
        report = validate_profile_delta("upb_in_situ", _valid_delta())
        self.assertTrue(report["valid"], report["errors"])

    def test_delta_contract_rejects_foreign_method(self) -> None:
        delta = _valid_delta()
        delta["sample_patches"][0]["method_context_add"]["isotope_system"] = "40Ar/39Ar"
        report = validate_profile_delta("upb_in_situ", delta)
        self.assertFalse(report["valid"])
        self.assertTrue(any("isotope_system" in error for error in report["errors"]))

    def test_catalog_exposes_method_mcp_and_instrument_profile(self) -> None:
        cards = {card["profile_id"]: card for card in list_profiles()}
        self.assertEqual(cards["upb_in_situ"]["mcp_server"], "geochron_upb")
        self.assertEqual(cards["upb_id_tims"]["mcp_server"], "geochron_upb")
        self.assertNotEqual(cards["upb_in_situ"]["tool_id"], cards["upb_id_tims"]["tool_id"])
        self.assertIn("rb_sr", cards)
        self.assertIn("radiocarbon_c14", cards)

    def test_completion_card_contains_standard_u_th_he_fields(self) -> None:
        contract = get_profile("u_th_he").public_contract()
        raw = contract["operations"]["enrich_candidates"]["raw_observations"]
        self.assertIn("FT", raw)
        self.assertIn("UThPit", raw)

    def test_strict_schema_closes_every_semantic_layer(self) -> None:
        schema = get_profile("upb_in_situ").json_schema_for("discover")

        def assert_closed_objects(node: object) -> None:
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertFalse(node.get("additionalProperties", True))
                    self.assertEqual(set(node.get("required", [])), set(node.get("properties", {})))
                for value in node.values():
                    assert_closed_objects(value)
            elif isinstance(node, list):
                for value in node:
                    assert_closed_objects(value)

        assert_closed_objects(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        patch = schema["properties"]["sample_patches"]["items"]
        self.assertFalse(patch["additionalProperties"])
        self.assertEqual(set(patch["required"]), set(patch["properties"]))
        raw = patch["properties"]["raw_observations"]["items"]
        aggregate = patch["properties"]["aggregate_observations"]["items"]
        inference = patch["properties"]["author_inferences"]["items"]
        raw_name = raw["properties"]["field_values"]["items"]["properties"]["name"]
        aggregate_name = aggregate["properties"]["field_values"]["items"]["properties"]["name"]
        inference_name = inference["properties"]["field_values"]["items"]["properties"]["name"]
        self.assertEqual(raw_name, {"type": "string"})
        self.assertEqual(aggregate_name, {"type": "string"})
        self.assertEqual(inference_name, {"type": "string"})
        self.assertEqual(raw["properties"]["unit_type"], {"type": "string"})

    def test_strict_wire_delta_decodes_to_the_existing_semantic_tree(self) -> None:
        profile = get_profile("upb_in_situ")
        decoded = decode_delta_wire(profile.spec, _strict_wire_delta())
        report = profile.validator(decoded)
        self.assertTrue(report["valid"], report["errors"])
        patch = decoded["sample_patches"][0]
        self.assertEqual(patch["raw_observations_add"][0]["fields"]["U"], 200)
        self.assertEqual(patch["aggregate_observations_add"][0]["fields"]["Age_Text"], "120 Ma")
        self.assertEqual(patch["author_inferences_add"][0]["fields"]["AgeIntpnClass"], "eruption age")


if __name__ == "__main__":
    unittest.main()
