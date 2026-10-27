# Provenance, contribution and preservation

[Overview](../README.md) · [Methods](methods.md) · [Versions](versions.md) · [Evidence](evidence.md) · [Validation](validation.md)

## Source selection

The primary extraction source is the owner's `structured-extract` folder in a broad AI workspace. Read-only Git inspection shows that folder is untracked by the ancestor repository and has no component-specific commits. The source had no top-level README or dependency declaration. Its staged pipeline, prompt/schema modules, vocabulary/filter and two aggregation scripts are preserved as twelve byte-identical top-level files.

The controls/MCP core is the coherent retained `v3_stage` research snapshot already selected for the earlier local presentation, together with its matching test suite and adjacent graph probes. The smaller v3 core found in the main extraction folder is preserved separately under `versions/early_v3` with its own tests. These are deliberately not mixed into one runtime import namespace.

[Source manifest](../provenance/source_manifest.json) records logical original paths, output paths and SHA-256 for every copied source/support file. An owner-only manifest outside this candidate retains absolute source paths. Historical count evidence was derived freshly from local JSON files; hashes identify the source bytes. The earlier graph report extracts retain their earlier scope and are not mislabeled as new real-paper evaluations.

## Added during presentation preparation

The new README/docs explain research methods, boundaries and execution evidence. New fictional examples/tests exercise the unchanged staged orchestrator and key adverse-response cases. New run/export wrappers add collision/configuration/contract guards around existing entry points. Packaging, locked dependencies, CI, link/payload checks and a simple geometric SVG are presentation and release work. They should not be retroactively attributed as completed historical research experiments.

The original research core is not refactored, bug-fixed or algorithmically changed. Known limitations are documented and some are explicitly characterized by tests. No original corpus, extraction JSON, workbook, Git state or existing showcase is rewritten. Before/after source hashes and packaging checks are retained outside the publication candidate.

## Original code and external components

No inspected component-level Git history proves individual authorship or excludes collaborators/assistance. The owner should confirm contributor names and personal changes before using independent-authorship wording. `vocab.py` explicitly credits copying its vocabulary/constraint basis from the adjacent `geochron_pipeline_v3` project; it is not described as wholly new in this repository.

The runtime uses third-party OpenAI client, MCP SDK, python-docx, openpyxl, dotenv, NumPy/SciPy and packaging tools; those libraries are dependencies, not vendored original contributions. Field cards retain their source reference to a USGS template release, without claiming certified compliance. See [third-party notices](../THIRD_PARTY_NOTICES.md).

## Candidate exclusions and publication

No source `.env`, actual paper DOCX/PDF/Markdown corpus, raw predictions/annotations/sample-ID lists, output workbooks, private environments, caches, credentials or models are included. Path-bound bulk scripts, geocoding/HTTP helpers and the import-time workbook-deletion batch exporter are excluded; their originals remain untouched. The read-only scan checks high-confidence key patterns and private paths but does not replace owner review of rights/attribution.

No repository-wide open-source license was found or invented. [LICENSE_PENDING.md](../LICENSE_PENDING.md) records the decision still needed from the owner. This pass creates a local review ZIP and checks; it makes no remote repository, push, package upload or website deployment.
