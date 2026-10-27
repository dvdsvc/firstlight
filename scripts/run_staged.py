"""Optional live wrapper: checks configuration and output collisions first."""
import argparse
import asyncio
import importlib
import os
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('document', type=Path)
    p.add_argument('--variant', choices=('main', 'v2'), default='main')
    a = p.parse_args()
    doc = a.document.resolve()
    if not doc.is_file() or doc.suffix.lower() != '.docx':
        p.error('Supply an existing DOCX you may process')
    root = Path(__file__).resolve().parents[1]
    # Both historical orchestrators write output/, irrespective of variant name.
    out = root / 'output'
    stem = doc.parent.name or doc.stem
    targets = [out / f'{stem}_{suffix}' for suffix in ('r1.json','final.json','flat.xlsx','tree.xlsx')]
    if any(x.exists() for x in targets):
        p.error('An output for this document folder already exists; use a fresh showcase copy or unique input folder')
    from dotenv import load_dotenv
    load_dotenv(root / '.env')
    if any(not os.environ.get(k) for k in ('DEEPSEEK_API_KEY','DEEPSEEK_BASE_URL','DEEPSEEK_MODEL')):
        p.error('Configure all three DEEPSEEK environment variables locally')
    module = importlib.import_module('pipeline' if a.variant == 'main' else 'pipeline_v2')
    asyncio.run(module.run_pipeline(str(doc)))


if __name__ == '__main__':
    main()
