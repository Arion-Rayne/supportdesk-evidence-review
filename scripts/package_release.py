"""Create a GitHub-ready archive with explicitly selected source files."""
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import re
import zipfile
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ('app', 'config', 'data', 'demo', 'docs', 'evaluation', 'migrations', 'scripts', 'tests')
TOP_LEVEL = ('README.md', 'requirements.txt', '.env.example', '.gitignore', 'START_SUPPORTDESK.cmd')
FORBIDDEN = {'.env', '.local', '.venv', '.git', '__pycache__', 'outputs', 'sources'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='SupportDesk_English_GitHub.zip', help='Archive filename in the project parent directory')
    args = parser.parse_args()
    if Path(args.output).name != args.output or not args.output.lower().endswith('.zip'):
        raise ValueError('Output must be a ZIP filename without path components')
    destination = ROOT.parent / args.output
    files = [ROOT / name for name in TOP_LEVEL]
    for directory in DIRECTORIES:
        files.extend(path for path in (ROOT / directory).rglob('*') if path.is_file()
                     and not any(part in FORBIDDEN for part in path.relative_to(ROOT).parts)
                     and path.suffix not in ('.pyc', '.part'))
    files = sorted(set(files))
    # Compare against locally configured secret values without ever printing them.
    sensitive = []
    for env_path in (ROOT / '.env', ROOT.parent / 'supportdesk-work-starter/.env'):
        if env_path.exists():
            sensitive.extend(value.encode() for key, value in dotenv_values(env_path, interpolate=False).items()
                             if value and (key.endswith('API_KEY') or key == 'DATABASE_URL'))
    for config in (ROOT / '.local/database.json', ROOT.parent / 'supportdesk-work-starter/.local/database.json'):
        if config.exists():
            sensitive.append(json.loads(config.read_text(encoding='utf-8'))['password'].encode())
    manifest = []
    for path in files:
        relative = path.relative_to(ROOT)
        if path.is_symlink() or any(part in FORBIDDEN for part in relative.parts):
            raise ValueError('Forbidden or symlinked file in release')
        data = path.read_bytes()
        if any(secret in data for secret in sensitive):
            raise ValueError('A configured credential appears in a release file; packaging stopped')
        manifest.append({'path': relative.as_posix(), 'bytes': len(data), 'sha256': sha256(data).hexdigest()})
    if destination.exists():
        raise FileExistsError('Release archive already exists; choose a new destination before packaging again.')
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, 'supportdesk-english/' + path.relative_to(ROOT).as_posix())
        archive.writestr('supportdesk-english/RELEASE_MANIFEST.json', json.dumps(manifest, indent=2))
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        for entry in manifest:
            data = archive.read('supportdesk-english/' + entry['path'])
            assert len(data) == entry['bytes'] and sha256(data).hexdigest() == entry['sha256']
    print(json.dumps({'archive': str(destination), 'files': len(files), 'zip_verified': True,
                      'configured_credentials_excluded': True, 'sha256': sha256(destination.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
