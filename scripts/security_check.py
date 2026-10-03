"""Read-only repository secret/export check; never prints matching secret values.

Scans tracked/unignored files and all reachable Git blobs. This is a focused
portfolio check, not a substitute for a maintained secret/vulnerability scanner.
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str, input: bytes | None = None) -> bytes:
    return subprocess.run(['git', *args], cwd=ROOT, input=input, capture_output=True, check=True).stdout


def main() -> None:
    known = []
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.partition('=')
            if sep and key.strip() in {'OPENAI_API_KEY', 'POSTGRES_PASSWORD', 'N8N_ENCRYPTION_KEY'}:
                value = value.strip().strip('\"\'')
                if len(value) >= 8:
                    known.append(value.encode())
    patterns = [rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}', rb'\bgh[pousr]_[A-Za-z0-9]{30,}',
                rb'\bAKIA[0-9A-Z]{16}\b', rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
    findings = []

    def inspect(label: str, data: bytes) -> None:
        if any(secret in data for secret in known) or any(re.search(pattern, data) for pattern in patterns):
            findings.append(label)

    paths = git('ls-files', '--cached', '--others', '--exclude-standard', '-z').decode().split('\0')
    for name in filter(None, paths):
        path = ROOT / name
        if path.is_file():
            inspect(name, path.read_bytes())
    history = git('rev-list', '--objects', '--all').decode().splitlines()
    identifiers = [line.split(' ', 1)[0] for line in history]
    names = {line.split(' ', 1)[0]: line.split(' ', 1)[1] for line in history if ' ' in line}
    data = git('cat-file', '--batch', input=('\n'.join(identifiers) + '\n').encode())
    offset = 0
    blobs = 0
    for identifier in identifiers:
        end = data.index(b'\n', offset)
        header = data[offset:end].split()
        size = int(header[2])
        body = data[end + 1:end + 1 + size]
        offset = end + 2 + size
        if header[1] == b'blob':
            blobs += 1
            name = names.get(identifier, identifier[:10])
            if Path(name).name == '.env':
                findings.append('historical .env file')
            inspect('history:' + name, body)
    assert '.env' not in git('ls-files', '--', '.env').decode().splitlines(), '.env is tracked'
    for path in (ROOT / 'n8n/workflows').glob('*.json'):
        workflow = json.loads(path.read_text(encoding='utf-8'))
        assert not workflow.get('pinData'), 'Workflow contains pinned data'
        assert all(not node.get('credentials') for node in workflow['nodes']), 'Workflow contains credential references'
    if findings:
        print('Review required in files (values withheld): ' + ', '.join(sorted(set(findings))))
        raise SystemExit(1)
    print(f'PASS: workspace and {blobs} reachable Git blobs checked; no known local secrets/key patterns found; .env untracked; workflow exports clean.')


if __name__ == '__main__':
    main()
