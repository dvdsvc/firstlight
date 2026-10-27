"""Known-answer control demo with hand-written observations, not model predictions."""
from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
from geochron_agent_v3.honeypot import build_control_run, evaluate_control_run, expected_relations, plan_structural_injections, inject_controls_into_structure, strip_control_relations, recovery_tasks
from geochron_agent_v3.state import apply_profile_delta, create_state, route_state

def main():
    paper = "3.1 Results\nSample DEMO101 zircon U-Pb LA-ICP-MS age is 120±1 Ma.\n4 Discussion\n"
    run = plan_structural_injections(paper, build_control_run("synthetic", ["upb_in_situ"]))
    augmented = inject_controls_into_structure(paper, run)
    observed = [{**r, "profile_id": "upb_in_situ"} for r in expected_relations(run)]
    passed = evaluate_control_run(run, observed, ["upb_in_situ"])
    omitted = evaluate_control_run(run, observed[1:], ["upb_in_situ"])
    wrong = deepcopy(observed);wrong[0]["sample_id"] = "wrong-sample"
    misbound = evaluate_control_run(run, wrong, ["upb_in_situ"])
    real_delta = json.loads((Path(__file__).parent / "fixtures/synthetic_delta.json").read_text())
    control = {"sample_id": observed[0]["sample_id"], "aggregate_observations_add": [], "author_inferences_add": []}
    mixed = deepcopy(real_delta);mixed["sample_patches"].append(control)
    cleaned = strip_control_relations(run, mixed)
    queued = route_state(create_state("synthetic", "Zircon U-Pb LA-ICP-MS spot analyses."))
    applied = apply_profile_delta(queued, queued["jobs"][0]["job_id"], cleaned)
    assert passed["status"] == "pass" and "merged" in omitted["fail_reasons"] and "misbound" in misbound["fail_reasons"]
    assert len(cleaned["sample_patches"]) == 1 and applied["jobs"][0]["status"] == "completed"
    print(json.dumps({"data_kind": "synthetic; expected observations supplied by fixture, no model call", "source_text_preserved_outside_augmented_copy": "HPUPB-01" not in paper and augmented != paper, "control_count": len(run["controls"]), "expected_relation_count": len(observed), "injected_text_contains_control": "HPUPB-01" in augmented, "exact_observations": passed, "one_relation_omitted": omitted, "wrong_sample": misbound, "recovery_tasks": recovery_tasks(omitted), "control_sample_removed_before_write": len(cleaned["sample_patches"]) == 1, "real_job_status": applied["jobs"][0]["status"]}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
