"""Guarded wrapper around unchanged legacy exporters; no model calls.

This is new presentation/release tooling, not a historical extraction method.
"""
import argparse
import json
from pathlib import Path
from scripts.offline_runtime import load_staged, no_network


def export(json_dir: Path, output: Path):
    files = sorted(json_dir.glob('*_final.json'))
    if not files:
        raise ValueError('No *_final.json inputs')
    if output.exists():
        raise FileExistsError('Refusing to overwrite output')
    if not output.parent.is_dir():
        raise ValueError('Output parent directory must exist')
    seen = set()
    for fp in files:
        d = json.loads(fp.read_text())
        pid = d.get('reference', {}).get('doi') or fp.stem.replace('_final', '')
        if pid in seen:
            raise ValueError('Ambiguous duplicate paper_id; review DOI/filename before aggregation')
        seen.add(pid)
        ids = [s['id'] for s in d.get('samples', [])]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate sample_id within a paper')
        if any('statistical_model' in e or 'distribution_state' in e
               for s in d.get('samples', []) for e in s.get('measure_events', [])):
            raise ValueError('v2/top-level event statistics require the matching v2 exporter; no implicit schema conversion')
    with no_network():
        load_staged('export_total').export_total(json_dir, output)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--json-dir', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    export(a.json_dir, a.output)


if __name__ == '__main__':
    main()
