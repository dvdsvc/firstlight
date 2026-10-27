# Running and configuration

[Overview](../README.md) · [Versions](versions.md) · [Exports](exports.md) · [Validation](validation.md)

## Dependencies

Use Python 3.11+ and run from the repository root. `pyproject.toml` declares OpenAI client, DOCX reading, dotenv and workbook support; `agent` adds the MCP SDK; `graph` adds NumPy/SciPy. `uv.lock` records a new presentation-environment resolution, not the original experimental environment.

```bash
uv sync --locked --all-extras
uv run --locked --all-extras python -B -m unittest discover -s tests -v
uv run --locked --all-extras python -B -m examples.staged_demo
uv run --locked --all-extras python -B -m examples.offline_demo
uv run --locked --all-extras python -B -m examples.graph_demo
uv run --locked --all-extras python -B -m scripts.mcp_smoke
uv run --locked --all-extras python -B -m scripts.check_repository
```

First installation requires package-index access. After dependencies are present, `uv run --offline --locked --all-extras ...` prevents dependency downloads. The staged fixture harness blocks network sockets, supplies dummy credentials only during import, suppresses `.env` reads and replaces the model client and OpenAlex enrichment. It exercises real loading/orchestration/merge/export functions while supplying handwritten responses. The controls demo supplies expected observations; the graph demo constructs a fictional XML table. None is a model score.

## Main extraction with a model

Provide a DOCX in a unique parent directory, for example `local_runs/paper-A/full.docx`. Configure `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_MODEL` in your shell or an untracked repository-local `.env`; `.env.example` contains names only. Set `OPENALEX_EMAIL` if using the original metadata-enrichment request.

```bash
uv run --locked python -B -m scripts.run_staged --help
uv run --locked python -B -m scripts.run_staged local_runs/paper-A/full.docx
```

This command performs paid/provider model requests and may query OpenAlex; it was **not executed with a real model in this preparation pass**. Provider support for `reasoning_effort`, thinking options and JSON mode must match the selected endpoint. Source prompt wording is not a tested model specification. The untouched stage scripts require all three DEEPSEEK variables even at import. The wrapper parses help and checks input/configuration/collisions before that import.

Both original variants write `output/<parent-folder>_*`; use different showcase copies or unique parent names to preserve runs. The wrapper refuses pre-existing R1/final/flat/tree targets. Direct historical entry points do not have that guard.

## Export existing main-contract JSON

```bash
uv run --locked python -B -m scripts.export_linked --help
uv run --locked python -B -m scripts.export_linked --json-dir local_runs/final_json --output local_runs/total_tree.xlsx
uv run --locked python -B merge_tree_xlsx.py local_runs/tree_inputs -o local_runs/merged_tree.xlsx
```

The guarded JSON wrapper makes no model requests, blocks network and does not require credentials. The tree merger is an original script and can overwrite its target; choose a new output name and unique input basenames. Neither command transforms the incompatible v2/Agent schema. The legacy batch exporter that deletes old `.xlsx` files was deliberately excluded from this candidate; no original file was deleted.

## Alternative staged v2

```bash
uv run --locked python -B -m scripts.run_staged --variant v2 local_runs/paper-v2/full.docx
```

This optional live path uses its own prompts and event/worksheet format. It assumes at least one retained self sample when warming the first R2a request; an empty selection can raise an index error. It was syntax/import checked, and its merge contract is tested, but no fresh full v2 model extraction is claimed. See [versions](versions.md) before mixing outputs.

## Agent and MCP

```bash
uv run --locked --extra agent geochron-mcp
uv run --locked --extra agent python -B -m examples.run_live --help
```

The optional `examples.run_live` wrapper runs the coherent stateful Agent on text; it is separate from `scripts.run_staged`. Agent core reads environment variables directly and does not load `.env` automatically. The [MCP client template](../examples/mcp_client.example.json) explicitly selects the `agent` extra. Replace its absolute-path placeholder with this checkout. Never insert keys in client configuration. Four model-backed tools require an appropriate provider; the local smoke check uses seven deterministic operations only.

## Early v3 in isolation

```bash
cd versions/early_v3
uv run --project ../.. --locked --all-extras python -B -m unittest discover -s tests -v
```

This working directory selects the archived package, not the incompatible root Agent package. The check runs its original twelve tests without model requests. Return to the root before normal commands.

## CI and local-only scope

[Offline workflow](../.github/workflows/offline-checks.yml) installs dependencies, then runs the same fixture checks and MCP session. It needs no API keys and deploys nothing. Hosted CI has not run because this candidate has not been pushed. Research corpora and raw predictions are intentionally absent; reproducing historical model output requires the owner's data, configuration and provider access.
