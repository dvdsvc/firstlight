# Main extraction method

[Overview](../README.md) · [Versions](versions.md) · [Exports](exports.md) · [Evidence](evidence.md) · [Operation](running.md)

## Problem and intermediate representation

A number becomes a usable scientific record only when its parent sample, analytical context, uncertainty and interpretation remain identifiable. The main implementation separates an entity skeleton from attribute completion, raw measurement reading and vocabulary mapping. This makes stage responsibilities and deterministic write rules inspectable. It is an LLM extraction workflow and research implementation; no model weights are trained here and calling an existing model is not presented as a new learning algorithm.

```text
reference {title, authors, journal, year, volume, pages, doi}
samples[]
  id, origin, rock_type, formation, group, member, location, ...
  spots[]
    id, u_ppm, th_ppm, th_u_ratio, concordance
    r207_206 / r207_235 / r206_238 {value, err_1s}
    age_206_238 / age_207_235 {value, err_1s}
  measure_events[]
    value {number, error {value, scale}, statistical_model, distribution_state}
    annotation, technique, mineral, isotope_system, physical_method
```

This is the **main** final-event contract. The v2 and incremental Agent contracts differ; see [versions](versions.md). A sample aggregate/interpretation event is not interchangeable with a single spot's isotopic measurement.

## Document input and shared context

[run_layer1.load_docx](../run_layer1.py) reads nonempty DOCX paragraphs first and then all tables, joining table cells with ` | ` and inserting table markers. It does not preserve paragraph/table interleaving, recover OCR or implement layout-aware parsing. MinerU conversion and paper acquisition are upstream processes outside this repository.

[prompts.make_system](../prompts.py) places the full projected text in the shared system message; each user message supplies the current stage task and tree. Sharing that prefix is designed to permit provider prompt caching. The code logs provider cache-token counters, but the candidate contains no controlled cache-speed benchmark. The original role prompt's “1M tokens” / exhaustive wording is a prompt instruction, not evidence of actual model context capacity or completeness.

## R1: discover the entity tree

The [R1 prompt](../prompts.py) asks for reference metadata, sample IDs, self/cited origin, spots and age events. [run_r1_multi](../pipeline.py) requests temperatures 0, 0.3 and 0.7 concurrently. `merge_r1_events` unions events for the samples retained from the first response. Its within-sample key is `(value.number, value.error.value)`.

The procedure provides another opportunity to collect events observed across samples of the model, but it is not majority voting or verified self-consistency. It does not add samples found only in a later response. Equal number/error pairs can collapse scientifically distinct events; the key does not include system, technique or interpretation. No ablation here establishes that the multi-temperature setting improves extraction quality.

Reference enrichment fills missing bibliographic fields from the first OpenAlex title-search hit. It is a separate network request, not an adjudicated paper-identity match. Original R1 JSON is saved before this enrichment and before R2 selection.

## R1 to R2 selection

[filter.py](../filter.py) deep-copies the skeleton, retains samples whose `origin` is exactly `self`, removes event `method` and `technique`, and prefixes numeric spot-ID suffixes with the sample ID. This creates a stage input without changing the saved raw R1 object. The origin is itself model-produced; this function cannot establish citation attribution correctness.

This is an implemented stage selection rule. It does not by itself explain why any particular archived final JSON or workbook has fewer records. Establishing that would require the actual pre-write state and that run's output projection.

## R2: concurrent, specialized completion

| Stage | Model task | Deterministic handling in the main pipeline |
|---|---|---|
| R2a | Fill lithology, stratigraphic units and geographic attributes | Only eight named attribute fields plus `location` are updated; sample IDs, spots and events come from the base sample. Missing approved attributes can replace old values with empty strings. |
| R2b | Read spot concentrations, ratios, ages and uncertainties from tables | Returned spots are restricted to `_SPOT_KEYS`; for matching IDs, allowed numeric fields update a base spot. The result is the returned spot list, so omitted base spots can disappear and previously unknown returned IDs are accepted. |
| R2c | Map original descriptions to closed vocabularies | Retain R1 `value.number`, `error.value` and `annotation`; add technique/mineral/system/physical method and nested error scale/statistical/distribution fields. Events are aligned by list position, not a stable event ID. |

R2a and R2c batch up to five samples per call. All their batches and one whole-skeleton R2b call run through `asyncio.gather`. The code records some API errors and applies fallbacks; JSON decoding and response-shape handling are not comprehensive across all paths.

These restrictions separate field ownership and protect specific numeric slots, which is a substantive system design choice. They do not enforce every instruction in the prompt. In particular, the actual main calls set `response_format={"type":"json_object"}`; the schema builder functions are not passed as strict server schemas. [vocab.py](../vocab.py) supplies mapping options and an available compatibility-constraint helper, but the main cleaner does not call that helper or reject all out-of-vocabulary values.

## Final merge and output

`run_pipeline` joins stage results by sample ID, attaches cleaned spots and events, saves `*_final.json`, then invokes the flat and tree workbook exporters. R1 raw, merged JSON and workbook projections are different evidence layers. Some workbook rows are intentionally suppressed without mutating the saved merged JSON. [Export semantics and cross-paper keys](exports.md).

## Local research contribution supported by the code

The files support presenting problem decomposition, scientific entity/slot modeling, domain prompts and vocabularies, concurrent stage orchestration, deterministic merge rules and relational output engineering. The adjacent Agent work adds write capabilities, local deltas, controls and coverage diagnostics. The graph work explores structural completion from existing seeds. Contribution attribution to a named person still requires owner confirmation because the component lacks tracked Git history; these mechanisms are not claimed as universally novel algorithms or demonstrated accuracy gains.
