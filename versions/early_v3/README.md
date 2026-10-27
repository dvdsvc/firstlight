# Early incremental v3 archive

[Main overview](../../README.md) · [Version contracts](../../docs/versions.md)

This is the smaller original Agent package retained in the main extraction checkout, including its byte-identical README and matching twelve-test file. It has one implemented `upb_in_situ` specialist, a delta validator/reducer and coverage audit; the README also contains design intentions beyond implemented code. It is isolated because its wire/state contract differs from the root controls/MCP package.

From this directory, use the root environment while keeping the current directory as the import root:

```bash
uv run --project ../.. --locked --all-extras python -B -m unittest discover -s tests -v
```

Do not import this snapshot into the root package namespace or run its tests in the combined root discovery. See the original [archival README](geochron_agent_v3/README.md) for historical context, interpreted alongside the current version guide.
