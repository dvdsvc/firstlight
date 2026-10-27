"""Optional local wrapper; makes model API calls only when explicitly executed."""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
from geochron_agent_v3.controller import run_document_agent
from geochron_agent_v3.state import create_state

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", type=Path, required=True, help="UTF-8 paper text, already parsed")
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--output", type=Path, required=True, help="Local state JSON; includes input text")
    parser.add_argument("--no-audit", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new path to preserve previous results")
    text = args.text.read_text(encoding="utf-8")
    state = asyncio.run(run_document_agent(create_state(args.document_id, text), run_audit=not args.no_audit))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Saved local research state to {args.output}")

if __name__ == "__main__":
    main()
