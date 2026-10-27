"""Read-only source, documentation, evidence and candidate-payload QA."""
import ast
import hashlib
import json
from pathlib import Path
import re
import tomllib
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', '.venv', '__pycache__', 'output', 'local_runs'}


def candidate_files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
                  and not any(x in EXCLUDED or x.endswith('.egg-info') for x in p.relative_to(ROOT).parts))


def main():
    failures = []
    manifest = json.loads((ROOT / 'provenance/source_manifest.json').read_text())
    for row in manifest['files']:
        p = ROOT / row['path']
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != row['sha256']:
            failures.append('Source hash mismatch: ' + row['path'])
    files = candidate_files()
    py_count = links = 0
    patterns = {
        'credential-shaped value': re.compile(r'\bsk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
        'private home path': re.compile('/' + r'(?:Users|home)/[^\s"<>]+'),
        'secret assignment': re.compile(r'(?im)^\s*(?:[A-Z_]*(?:API_KEY|TOKEN|PASSWORD))\s*=\s*["\x27]([^"\x27\n]{18,})["\x27]'),
    }
    forbidden_extensions = {'.pdf','.docx','.xlsx','.sqlite','.db','.pem','.key','.pt','.bin','.safetensors'}
    for p in files:
        rel = str(p.relative_to(ROOT))
        if p.is_symlink() or p.name == '.env' or p.suffix in forbidden_extensions:
            failures.append('Unexpected candidate payload: ' + rel)
        if p.stat().st_size >= 5 * 1024 * 1024:
            failures.append('Unexpected file >= 5 MiB: ' + rel)
        try:
            content = p.read_text()
        except UnicodeDecodeError:
            failures.append('Unexpected non-text file: ' + rel)
            continue
        for label, pattern in patterns.items():
            if pattern.search(content):
                failures.append(f'Potential {label}: {rel} (value suppressed)')
        if p.suffix == '.py':
            try:
                ast.parse(content)
                py_count += 1
            except SyntaxError as e:
                failures.append(f'Syntax error: {rel}:{e.lineno}')
        if p.suffix == '.md':
            if len(re.findall(r'^```', content, re.M)) % 2:
                failures.append('Unbalanced code fences: ' + rel)
            targets = re.findall(r'\]\(([^)]+)\)', content) + re.findall(r'<img[^>]+src="([^"]+)"', content)
            for target in targets:
                parsed = urlsplit(target.split(' "',1)[0])
                if parsed.scheme or target.startswith('#'):
                    continue
                links += 1
                resolved = (p.parent / unquote(parsed.path)).resolve()
                if not resolved.is_relative_to(ROOT) or not resolved.exists():
                    failures.append(f'Broken/local-escape link: {rel} -> {target}')
    headings = [re.findall(r'^## ', (ROOT / n).read_text(), re.M) for n in ('README.md','README.zh-CN.md')]
    if len(headings[0]) != len(headings[1]):
        failures.append('README section parity mismatch')
    for name in ('pyproject.toml','uv.lock'):
        tomllib.loads((ROOT / name).read_text())
    rows = [json.loads(line) for line in (ROOT / 'evidence/historical_artifacts.jsonl').read_text().splitlines()]
    allowed = {'artifact_id','collection','sha256','sample_count','spot_count','event_count','observation_count','reference_present','is_final'}
    if any(set(row) != allowed for row in rows):
        failures.append('Unexpected historical evidence fields')
    summary = json.loads((ROOT / 'evidence/historical_summary.json').read_text())['collections']
    for group, stats in summary.items():
        selected = [r for r in rows if r['collection'] == group]
        finals = [r for r in selected if r['is_final']]
        derived = {'json_artifacts': len(selected), 'final_artifacts': len(finals),
                   'final_samples': sum(r['sample_count'] for r in finals),
                   'final_spots': sum(r['spot_count'] for r in finals),
                   'final_events': sum(r['event_count'] for r in finals),
                   'empty_final_artifacts': sum(r['sample_count'] == 0 for r in finals)}
        if stats != derived:
            failures.append('Historical count mismatch: ' + group)
    sums = ROOT / 'SHA256SUMS'
    if sums.exists():
        listed = {}
        for line in sums.read_text().splitlines():
            digest, name = line.split('  ',1)
            listed[name] = digest
        actual = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p != sums}
        if listed != actual:
            failures.append('Root checksum inventory differs from candidate files')
    result = {'copied_source_records': len(manifest['files']), 'candidate_files':len(files),
              'candidate_bytes': sum(p.stat().st_size for p in files), 'python_files_parsed':py_count,
              'local_document_links_checked':links, 'historical_artifacts_checked':len(rows),
              'readme_sections_each':len(headings[0]), 'failures':failures,
              'scan_scope':'Candidate text patterns, file inventory and source hashes; not an exhaustive rights/security review'}
    print(json.dumps(result, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
