# JSON, workbook projection and cross-paper association

[Overview](../README.md) · [Methods](methods.md) · [Versions](versions.md) · [Running](running.md)

## Distinguish three data layers

| Layer | What it records | What an omission can mean |
|---|---|---|
| `*_r1.json` | Saved raw merged R1 response, before reference enrichment and R2 selection | Initial discovery output; not a final classified result |
| `*_final.json` | R2 stage results joined into the final sample tree | Selection, model response and merge behavior must be inspected at this boundary |
| Flat/tree/total XLSX | An explicit projection of the final tree | Rows/fields can be suppressed or transformed by the exporter without deletion from JSON |

The original merged JSON is written before workbook export. The main `_export_*` functions read it without modifying its event list. Empty workbook content therefore cannot independently diagnose an extraction failure.

## Main single-paper projection

The main tree workbook has a two-column key/value `reference` sheet and tabular `samples`, `observations`, `measure_events` sheets. Spot rows include `sample_id` and `spot_id`; event rows include `sample_id`. Single-paper worksheets do not independently carry a global paper ID in each row.

`_is_noise_event` suppresses events whose **nested** statistical-model and distribution-state fields are both absent, empty or the string `null`. `_is_empty_event` suppresses events with neither numeric value nor annotation. `_dedup_events` groups by `(physical_method, statistical_model, distribution_state)` and, if a group occurs at least five times, keeps only its first member. This is an output heuristic, not scientifically validated equivalence: distinct ages with the same classification can be collapsed.

Spot rows with no numeric-like payload are skipped. The main flat workbook does not retain a dedicated `spot_id` column, whereas the tree workbook does. If no spot payload and no numeric event survive, the function returns without saving the workbook, even if sample metadata exists. The JSON remains independent. The total JSON exporter has its own empty-spot predicate and always saves when inputs exist, so exact row equality between all export paths is not promised.

## JSON to a linked total workbook

[export_total.py](../export_total.py) reads sorted `*_final.json` and creates:

| Sheet | Link fields | Payload |
|---|---|---|
| `reference` | `paper_id` | Title, authors, journal, year, volume, pages, DOI |
| `samples` | `paper_id`, `sample_id` | Sample properties and coordinates |
| `observations` | `paper_id`, `sample_id`, `spot_id` | Concentrations, ratios, ages and uncertainties |
| `measure_events` | `paper_id`, `sample_id` | Aggregate number/error, annotation and classification |

Use `(paper_id, sample_id)` as the sample join key. A sample string alone is not unique across papers. The original exporter chooses `reference.doi` when nonempty, otherwise a filename stem. It does not normalize/verify DOI identity or detect duplicate paper IDs. Its tables do not provide a stable per-event primary key or an event-to-spot evidence link.

The new [guarded wrapper](../scripts/export_linked.py) refuses an existing output, duplicate resulting paper IDs, duplicate sample IDs within one paper, and detectable v2 event-statistics contracts before invoking the unchanged exporter. This is release tooling added during this pass, not a historical contribution or a complete identity-resolution system. Missing/incorrect DOI, malformed inputs, and scientific misbinding still require review.

## Existing tree-workbook aggregation

The inspected [merge_tree_xlsx.py](../merge_tree_xlsx.py) already handles reference key/value rows and wide reference sheets. It aligns subsequent tables by column name, rather than pasting rows positionally. It derives a source paper ID by removing a **trailing** `_tree` from each filename; it does not use DOI as the primary ID. The current implementation also adds separate native-coordinate normalization/status columns while retaining source coordinates. No external geocoder is called by this script.

Two workbooks with the same basename in different folders can still collide. It does not deduplicate repeated input files; later-only columns not present in the first sheet contract can be dropped. It expects the main sheet names, so a v2 workbook is not interchangeable. These are current boundaries, not an assertion that an earlier reference-reading bug is still present.

## Verified fictional example

[staged_demo](../examples/staged_demo.py) executes the original orchestrator with fixture responses, then exports two papers that both use `DEMO-SAME`. Their events carry 120 and 240 respectively. The check reads all four worksheet tables and verifies that `(DEMO-PAPER-A, DEMO-SAME)` and `(DEMO-PAPER-B, DEMO-SAME)` retain their own values. A separate test reorders columns in a second tree workbook and checks the merger's attribution and alignment. No real paper accuracy is inferred from this exercise.
