# Version relationships

[Overview](../README.md) · [Methods](methods.md) · [Exports](exports.md) · [Controls](agent_controls.md) · [Graph](graph_recovery.md)

## One research repository, distinct implementations

This candidate consolidates the previously separate extraction and MCP/control presentation into one primary repository. It keeps incompatible original implementations intact and supplies shared documentation, dependencies and offline checks. Consolidation does not introduce a new automatic data-flow bridge.

| Snapshot | Entry / source evidence | Representation and scope | Direct export / integration |
|---|---|---|---|
| Main staged extraction | [pipeline.py](../pipeline.py), twelve original top-level modules | `samples → spots / measure_events`; event statistics nested under `value`; three-temperature R1 and batched R2a/R2c | JSON, flat/tree XLSX; JSON aggregation and tree aggregation |
| Alternative staged v2 | [pipeline_v2.py](../pipeline_v2.py), [prompts_v2.py](../prompts_v2.py) | R1 `observations[].measurements` scaffold; R2b independently reads spots; statistics at event top level | Own flat/tree XLSX uses `events` and `spots`, not main `measure_events` / `observations` sheets |
| Early incremental v3 | [archive guide](../versions/early_v3/README.md) and archived matching 12 tests | One implemented `upb_in_situ` specialist; `sample_fields_add / spots_add / age_results_add / events_add` | Incremental state/reducer/audit; no connected final JSON/XLSX compiler |
| Controls/MCP research snapshot | [controller](../geochron_agent_v3/controller.py), matching 27 original tests | Seventeen registered profile cards; `sample_attributes_add / method_context_add / raw_observations_add / aggregate_observations_add / author_inferences_add`; discover/enrichment operations | Stateful controller, known-answer controls and MCP. No compiler into the staged final JSON contract |
| Seeded graph probes | [graph method](graph_recovery.md) and three original research scripts | Legacy `samples[].id` and `measure_events[].value` seeds, plus DOCX XML or Markdown tables | Independent candidate proposals; no automatic controller invocation or validated writeback |

The labels “early” and “controls snapshot” describe differences confirmed in files. Directory names and filesystem times do not prove a complete chronological branch lineage. No component-specific commits are asserted.

## Important migration boundaries

The main and v2 routines both write to `output/` and derive the file stem from the input's **parent folder name**. A second variant can overwrite a first variant if called directly. The new [live wrapper](../scripts/run_staged.py) checks target collisions before running; use a separate showcase copy for comparison runs.

The v2 merge explicitly discards its R1 `observations` scaffold and attaches fresh R2b spots. Its final event statistics live at the event top level. Sending those JSON objects through the main `export_total.py` would lose the intended statistical interpretation and can filter the affected events. The new guarded JSON export wrapper rejects detectable top-level v2 statistics instead of silently converting them. The existing tree merger recognizes only main sheet names: passing a v2 tree workbook would omit its `spots`/`events` sheets. A reviewed schema adapter is not implemented here.

The early v3 README includes intended control/cache behavior beyond the smaller source snapshot. It is preserved as an archival document, not current capability documentation. Run its matching tests in its isolated import root; do not mix them with the incompatible root Agent package.

The controls snapshot has real standard-profile cards and shared validators, but seventeen cards do not imply seventeen validated specialist benchmarks. Its coherent source was selected from a retained research workspace because the smaller main checkout did not contain `honeypot.py`.

## Connection to downstream scientific analysis

The main linked workbook contract uses `reference`, `samples`, `observations`, and `measure_events` with paper/sample identifiers. A separately organized Deep Research system contains a `TotalTreeXlsxSource` reader for this table family. That is evidence of a designed interface. This repository does not bundle that analysis runtime or claim a newly completed end-to-end geological study. GeoViz and the Deep Research Agent remain separate downstream projects.
