# Hooks and seeded document-graph recovery

[Overview](../README.md) · [Controls](agent_controls.md) · [Validation](validation.md) · [Operation](running.md) · [Provenance](provenance.md)

## From existing extraction to structural recovery

The hook is an already-extracted entity or sample/value/error relation. It supplies a locatable boundary condition in the source document. The experiments aim to recover structurally related records and propose missing relations, while preserving evidence for review. Two original implementations explore this at different levels.

## Repeated table-path probe

[seeded_path_probe.py](../research/seeded_graph/seeded_path_probe.py) reads MinerU-style HTML tables embedded in Markdown. Known spot IDs locate a common entity column and repeated cell-type signature. The probe follows a contiguous entity-root/template path and extends to neighboring physical table segments with the same structure. It does not need semantic table headers for that decision. The preserved artifact uses three hooks for each sample group and reports 21 and 29 records respectively in one paper. This probe is structural path following, not a Dijkstra implementation.

## Weighted graph and minimum-energy candidate forest

[seeded_document_forest.py](../research/seeded_graph/seeded_document_forest.py) reads DOCX XML into one graph of text sentences, table cells/rows, value/error nodes and entity roots. Edge types encode local text adjacency, table geometry, value membership and explicit entity mentions. Numbered headings form hard local boundaries. Its graph weights and thresholds are research heuristics recorded in the code/config, not calibrated scientific probabilities.

The algorithm grounds known bindings by Dijkstra search, choosing a reachable source occurrence of the same value/error pair. Accepted seeds get low-resistance `fixed_seed_binding` channels. A restricted OCR repair can reconnect a known numeric signature when local glyph insertion/deletion supports it. Table seeds can also transfer measured entity-to-value/error coordinate offsets to other known entity cells in the same table.

`harmonic_extension` constructs a conductance-weighted graph Laplacian and solves a Dirichlet boundary-value problem with sample roots fixed as labels. This produces a minimum-Dirichlet-energy extension over the graph. Candidate filtering combines broad structural neighbors and translated templates, with section ownership constraints. Candidate output reports potential, `-log(potential)` energy, source kind, template paths and evidence.

Dijkstra supplies least-cost grounding; harmonic extension supplies the subsequent propagation. The complete method should therefore be described as seed-grounded graph completion/minimum-energy propagation rather than only a shortest-path algorithm. It returns competing candidates instead of enforcing one final sample assignment. Those candidates require validation before entering a scientific database.

## Archived evidence and current demo

[Archived aggregate summary](validation/archived-graph-summary.json) is derived from the retained path reports and ten-paper forest JSON, with artifact hashes. It contains counts and bibliographic labels only; no original full text or raw extracted table is redistributed. Counts from different graph revisions are kept separate. The ten-paper output records candidate production, not verified missing-data recovery or a benchmark against exhaustive gold labels.

The [synthetic graph demo](../examples/graph_demo.py) creates a tiny XML table and an earlier-style seed JSON. It calls the unchanged original forest code and checks whether two known synthetic relationships are proposed. [Actual output](../examples/outputs/graph-demo.json) is a mechanism demonstration, not an extraction-quality metric.

## Data contract and integration status

The graph CLI expects a legacy seed structure: `samples[].id` plus `samples[].measure_events[].value.number/error.value`. It does not directly consume the newer Agent's `profile_states` tree. No adapter or automatic graph-to-Agent writeback is claimed in this snapshot. [document_graph_completion_probe.py](../research/seeded_graph/document_graph_completion_probe.py) retains an earlier holdout-oriented graph exploration alongside the later forest code.

The current graph prototype also has cases requiring maintenance: missing grounded roots are not consistently handled by all return paths, and candidate quality depends on OCR, document structure and trusted seeds. The presentation pass preserves these algorithms and records scope; it does not silently repair or replace them.
