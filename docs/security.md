# Environment configuration / 环境配置

Set the selected model provider in `.env.example`. Staged extraction scripts load a local `.env`; Agent entrypoints read process environment variables. `OPENALEX_EMAIL` identifies enrichment requests.

按所选模型服务配置变量。分阶段抽取脚本读取本地 `.env`，Agent 入口读取进程环境变量；`OPENALEX_EMAIL` 用于文献补充请求标识。

## Local setup

```bash
cp .env.example .env
```

Fill in the supported variables in your local `.env`. The file is ignored by Git; keep the committed template's credential fields empty. For entrypoints that read process variables, add `--env-file .env` to the documented `uv run` command. See the repository's running guide for provider and data options.

在本地 `.env` 中填写所需变量，提交的示例文件保持空白。读取进程环境变量的入口可通过 `uv run --env-file .env ...` 载入配置，具体运行方式见对应说明。

## Repository check

With [Gitleaks](https://github.com/gitleaks/gitleaks) installed and on PATH:

```bash
uv run python scripts/check_secrets.py --history
```

This checks publication files and reachable Git history using the repository's detector configuration. Reports show locations without credential values.
