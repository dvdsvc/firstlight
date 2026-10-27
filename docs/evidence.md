# Historical outputs and evidence boundaries

[Overview](../README.md) · [Methods](methods.md) · [Validation](validation.md) · [Provenance](provenance.md)

## Saved extraction artifacts

The local review inspected JSON contents, not just filenames. [The released inventory](../evidence/historical_artifacts.jsonl) contains 722 numeric records with anonymous artifact IDs, collection labels, original SHA-256, sample/spot/event/observation counts, final-file flags and reference-presence flags. It does not contain titles, real sample IDs, annotations, source text or raw model generations. The original-path mapping is kept outside this candidate for owner review.

| Collection | JSON tree artifacts | Final artifacts | Sample records in finals | Spot records in finals | Event records in finals | Empty final artifacts |
|---|---:|---:|---:|---:|---:|---:|
| `doi_output/json` | 622 | 310 | 1,752 | 9,789 | 6,140 | 46 |
| `output/json` | 44 | 21 | 168 | 1,321 | 191 | 0 |
| `v1output/json` | 46 | 23 | 189 | 1,350 | 282 | 0 |
| `v2output` | 6 | 3 | 0 | 0 | 0 | 3 |
| `output` intermediate/test files | 4 | 0 | — | — | — | — |

The collections may contain the same papers, reruns and customized output projections. Counts must not be summed as unique papers. An artifact hash identifies bytes but cannot prove which exact source revision or model settings produced a file. Empty finals are observed facts; their cause cannot be assigned from this inventory alone. Original directories include exported workbooks as additional execution artifacts; those private binaries are not redistributed.

## What the evidence supports

The source and saved outputs support saying the project implemented and executed a staged scientific extraction workflow, produced nested records at batch scale, and provided linked downstream tables. Numeric slot protection and field boundaries can be exercised independently of the model. The control and graph extensions demonstrate additional approaches to diagnosing relational loss and using trusted extraction seeds for structural candidate recovery.

The inspected package does not provide a frozen, exhaustively labeled gold set with an official precision/recall/F1 evaluation for this main workflow. Record volume, valid JSON, present DOI strings and passing local tests do not establish correct sample/age/error binding or completeness. The primary staged v2 empty finals are not compared to other collections as a controlled model ablation.

## Adjacent graph artifacts

The current pass also read 21 existing main final JSON files and generated an owner-only workbook. [Numeric export audit](../evidence/real_export_audit.json) confirms source-parent membership for every exported row, while exposing two duplicate DOI-first paper-ID occurrences (19 distinct reference IDs). This is an observed identity ambiguity; the new wrapper stops before exporting duplicate IDs. Neither the original IDs nor research results were changed.

[Archived graph summary](validation/archived-graph-summary.json) and [prior local path recheck](validation/table-path-rerun.json) were retained from the already organized graph snapshot. Their original validation date/scope remains explicit. They include 21/29 candidate record counts in one table-path case and a separate ten-paper candidate-production artifact. These are not verified additional scientific findings. The current pass re-executes the fictional graph demo; it does not rerun all real-paper probes or merge their counts into main extraction accuracy.

## Contribution wording

Supported: “Implemented a staged entity-tree extraction workflow for scientific literature, with task-specific prompts, field-constrained merging and paper/sample-linked exports; explored stateful validation and seed-guided structural completion.” Individual authorship is pending owner confirmation. Unsupported: “Invented a new foundation model,” “proved exhaustive extraction,” “achieved a benchmark improvement,” or “completed an automatic MCP-to-graph-to-database recovery pipeline.”
