# Local validation record

[Overview](../README.md) · [Method](methods.md) · [Exports](exports.md) · [Evidence](evidence.md) · [Running](running.md)

## Scope and environment

Checked on 2026-10-27 with Python 3.12.13 in a new independent environment synchronized from `uv.lock`. This presentation environment uses OpenAI client 2.54.0, MCP SDK 1.30.0, python-docx 1.2.0, openpyxl 3.1.5, python-dotenv 1.2.4, NumPy 2.5.4 and SciPy 1.18.1. It is not asserted to be the historical extraction environment. Package installation accessed the package index; tests and demonstrations made no model requests.

## Executed checks

| Check | Evidence and meaning |
|---|---|
| Root tests | 27 matching original controls/Agent tests plus 15 new staged/guard tests; all 42 pass. See [test log](validation/root-tests.txt). |
| Early-v3 tests | 12 original tests pass in the isolated historical import root; [log](validation/early-tests.txt). |
| Main staged demo | Original DOCX loading, R1/R2 orchestration, cleaners, merge and workbook export execute on fictional responses. Six fixture calls; zero model calls; linked rows checked for two papers sharing a sample ID. [Output](../examples/outputs/staged-demo.json). |
| Controls demo | Expected, omitted and misbound observations are supplied deliberately; injection, evaluation, control stripping and state write are exercised. [Output](../examples/outputs/controls-demo.json). |
| Graph demo | Original graph algorithm proposes two required fictional relationships from a small XML table and seed state. [Output](../examples/outputs/graph-demo.json). |
| Actual MCP stdio | Eleven tools listed, seventeen profile cards, seven deterministic tool calls, control status `pass`, zero model calls. [Output](validation/mcp-smoke.json). |
| Live/export commands | `--help` executes for staged wrapper, linked-export wrapper and optional Agent wrapper. Existing-output rejection is tested for both staged variants before research imports. No real provider extraction was executed. |
| Historical evidence | All 722 released count rows are recomputed from the original local JSON files and summarized by collection. Counts/hashes establish artifact contents, not accuracy. |
| Existing-output export audit | Twenty-one real final JSON inputs were read without mutation and exported into an owner-only workbook. Counts and key checks are released separately; see below. |
| Structural QA | Copied-source hashes, root checksums, Python syntax, bilingual section parity, local links, dependency TOML, candidate sizes and heuristic credential/private-path patterns. [Summary](validation/structural-qa.json). |

The combined total is **54 passing tests across two isolated suites**. They are not 54 scientific benchmark cases. R2c positional association, unenforced vocabulary values, R2b ID/list behavior and export suppression are explicitly characterized rather than described as already repaired.

## Real-output mechanical audit

[Audit counts](../evidence/real_export_audit.json) record 21 existing final files, 168 sample records, and an export containing 21 reference rows, 168 sample rows, 1,310 observation rows and 161 event rows. Every exported row has a source parent `(paper_id, sample_id)` key. However, the DOI-first IDs have **two duplicate occurrences**, leaving **19 distinct reference IDs** and 162 distinct paper/sample keys. Passing parent-key existence does not resolve collisions or establish scientific binding correctness.

The new guarded export helper refuses duplicate resulting paper IDs. It does not rewrite the archived DOI strings, alter extraction results, or claim those historical identity collisions are solved. The original workbook generated for this audit remains outside the candidate, together with its source-path mapping. Projection rules explain why event/spot row totals need not match JSON record counts.

## Preserved scope

All twelve main modules and the selected research cores are byte-identical copies. The sole copied support-file adjustment is the MCP client template's checkout placeholder and explicit `agent` extra. Before/after hashes for the original main tree, earlier showcase and selected controls sources are checked in owner-side records; private paths are not redistributed.

The GitHub workflow is prepared and its constituent commands were executed locally; no hosted run is claimed. No live model extraction, real-paper precision/recall/F1 benchmark, automatic graph writeback, public upload or browser/visual QA was performed.
