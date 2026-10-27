# Extraction and known-answer controls

[Overview](../README.md) · [Graph recovery](graph_recovery.md) · [Validation](validation.md) · [Operation](running.md) · [Provenance](provenance.md)

## Coherent semantic tree and profile operations

The source represents `sample_attributes_add → method_context_add → raw_observations_add → aggregate_observations_add → author_inferences_add`. Aggregate observations reference raw observations within a sample; author inferences reference aggregates within that sample. Method context, technique and allowed field names are checked against a profile and operation. `profiles/standard.py` records the USGS template release used as a field-card reference; this is source-backed field organization, not a claim of independently certified standards compliance.

Seventeen cards are registered, spanning U-Pb in-situ/ID-TIMS, Ar-Ar heating/fusion and other geochronology workflows. `discover` builds the initial representation and `enrich_candidates` adds profile fields to existing state. Runtime/model support is separate from the presence of a registered card. [Registry](../geochron_agent_v3/registry.py), [field cards and wire decoder](../geochron_agent_v3/profiles/standard.py), [reducer](../geochron_agent_v3/state.py).

## Known-answer document controls

The [original honeypot implementation](../geochron_agent_v3/honeypot.py) contains three U-Pb control templates with five expected relations. It materializes control passages from fixed templates rather than using a model to invent their answers. Cases include two ages associated with one sample, distinct samples in the same batch, and typographic numeric variants.

Expected sample/age/error/system/scope relations remain outside the model-visible text. Placement can use normalized MinerU structural blocks or recovered title/paragraph domains. A second placement function uses a router-selected verbatim result anchor and checks that its sample and age can be found. Unsafe or unavailable anchors are skipped rather than moved arbitrarily to front matter. The router-anchor path selects at most one control per profile; the structural-placement utility can place the three-template suite.

`inject_controls_into_structure` creates a new augmented string while retaining source coordinates externally. It does not alter the source file. After extraction, `extract_delta_relations` obtains comparable aggregate relations. `evaluate_control_run` checks the known sample, number/error pair, isotope system and self/cited scope. Its reason categories are `missing`, `merged`, `misbound`, `misrouted`, `source_confusion` and `parse_noise`. These are the implemented diagnostic categories; their sensitivity and specificity on model outputs have not been benchmarked here.

`strip_control_relations` removes control samples and matching control aggregates/dependent inferences before the ordinary reducer writes real profile state. This prevents intentional control data from being presented as paper-derived findings. Control collision and other edge cases still need dedicated evaluation beyond the retained tests.

## Integration with controller and MCP

The [controller](../geochron_agent_v3/controller.py) first plans on the original text, obtains selected profiles and anchors, prepares a control run, executes profile calls on the augmented text, observes and strips control output, and records the validation report. `queue_recovery_enrichment` turns a rejected initial write or failed control into an `enrich_candidates` job with repair context. The default loop then performs coverage audit and any budget-permitted routing follow-up.

The [MCP facade](../geochron_agent_v3/mcp_server.py) exposes prepare/inject/evaluate controls as real tools, alongside registry, validation, planning, extraction and audit. Python orchestration still calls local functions directly. The standalone document-graph probes in `research/seeded_graph` are adjacent experiments; the controller's enrichment path does not import or run them.

## Execution boundaries

Budgets cap router rounds, per-profile attempts and audits. The implementation retains model artifacts, reports, conflicts and unresolved tasks in state. It contains no completed cache implementation despite the archival README's cache design notes. Validation of structure/field permissions is implemented; semantic correctness and full-document completeness require separate evidence. The copied source is retained unchanged.
