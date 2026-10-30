"""Download EDB PostgreSQL binaries and initialize a project-local cluster."""
from pathlib import Path
import hashlib
import json
import secrets
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
URL = 'https://get.enterprisedb.com/postgresql/postgresql-17.11-5-windows-x64-binaries.zip'


def main():
    LOCAL.mkdir(exist_ok=True)
    archive = LOCAL / 'postgresql-17.11-5.zip'
    executable = LOCAL / 'pgsql/bin/initdb.exe'
    if not executable.exists():
        if not archive.exists():
            temporary = archive.with_suffix('.part')
            print('Downloading project-local PostgreSQL from EDB...', flush=True)
            with urllib.request.urlopen(URL, timeout=60) as response, temporary.open('wb') as target:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
            temporary.replace(archive)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (LOCAL / 'postgres-download.json').write_text(json.dumps({
            'url': URL, 'sha256': digest,
            'verification': 'HTTPS download; locally recorded hash, not an independently published checksum',
        }, indent=2), encoding='utf-8')
        with zipfile.ZipFile(archive) as package:
            for entry in package.infolist():
                if entry.filename.startswith(('pgsql/bin/', 'pgsql/lib/', 'pgsql/share/', 'pgsql/include/')):
                    destination = (LOCAL / entry.filename).resolve()
                    if not destination.is_relative_to(LOCAL.resolve()):
                        raise ValueError('Archive path escapes project runtime')
                    package.extract(entry, LOCAL)
        print('Extracted PostgreSQL runtime (no installer or Windows service).', flush=True)
    config_path = LOCAL / 'database.json'
    if not config_path.exists():
        config_path.write_text(json.dumps({'host': '127.0.0.1', 'port': 55433,
            'user': 'supportdesk', 'password': secrets.token_urlsafe(32),
            'dbname': 'supportdesk'}), encoding='utf-8')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    data = LOCAL / 'pgdata'
    if not (data / 'PG_VERSION').exists():
        password_file = LOCAL / 'initdb-password'
        password_file.write_text(config['password'] + '\n', encoding='utf-8')
        try:
            subprocess.run([str(executable), '-D', str(data), '-U', config['user'],
                '-E', 'UTF8', '--locale=C', '--auth=scram-sha-256',
                '--pwfile=' + str(password_file)], check=True)
        finally:
            password_file.unlink(missing_ok=True)
        with (data / 'postgresql.conf').open('a', encoding='utf-8') as target:
            target.write("\nlisten_addresses = '127.0.0.1'\nport = 55433\n")
    print('PostgreSQL initialized. Credentials remain in ignored .local/database.json.', flush=True)


if __name__ == '__main__':
    main()
