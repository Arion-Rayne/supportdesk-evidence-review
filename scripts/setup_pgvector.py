"""Build official pgvector v0.8.6 into this project's PostgreSQL on Windows."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'.local'
URL='https://codeload.github.com/pgvector/pgvector/zip/refs/tags/v0.8.6'

def extract_inside(archive, parent, prefix):
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            if entry.filename.startswith(prefix):
                target=(parent/entry.filename).resolve()
                if not target.is_relative_to(parent.resolve()):
                    raise ValueError('Archive path outside project runtime')
                package.extract(entry,parent)

def main():
    if os.name!='nt':
        raise SystemExit('This setup script targets Windows. On other systems use the official pgvector installation guide.')
    pgroot=LOCAL/'pgsql'
    if not (pgroot/'bin/pg_config.exe').exists():
        raise SystemExit('Run python scripts/setup_postgres.py first.')
    if not (pgroot/'include/server/postgres.h').exists():
        archive=LOCAL/'postgresql-17.11-5.zip'
        if not archive.exists():
            raise SystemExit('PostgreSQL development headers missing; retain the EDB archive from setup_postgres.py.')
        extract_inside(archive,LOCAL,'pgsql/include/')
    vswhere=Path(os.environ.get('ProgramFiles(x86)',r'C:\Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
    if not vswhere.exists():
        raise SystemExit('Visual Studio Build Tools with Desktop development with C++ is required.')
    install=subprocess.check_output([str(vswhere),'-latest','-products','*','-requires',
        'Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
    vcvars=Path(install)/'VC/Auxiliary/Build/vcvars64.bat'
    if not install or not vcvars.exists():
        raise SystemExit('Install the Desktop development with C++ workload, then retry.')
    archive=LOCAL/'pgvector-v0.8.6.zip'
    if not archive.exists():
        with urllib.request.urlopen(URL,timeout=60) as response:
            archive.write_bytes(response.read())
    extract_inside(archive,LOCAL,'pgvector-0.8.6/')
    source=LOCAL/'pgvector-0.8.6'
    script=LOCAL/'build_pgvector.cmd'
    script.write_text('@echo off\ncall "'+str(vcvars)+'"\nif errorlevel 1 exit /b 1\nset "PGROOT='+str(pgroot)+'"\ncd /d "'+str(source)+'"\nnmake /F Makefile.win\nif errorlevel 1 exit /b 1\nnmake /F Makefile.win install\n',encoding='utf-8')
    subprocess.run(['cmd.exe','/d','/c',str(script)],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    (ROOT/'data/PGVECTOR_LICENSE.txt').write_bytes((source/'LICENSE').read_bytes())
    (LOCAL/'pgvector-build.json').write_text(json.dumps({'version':'0.8.6','url':URL,
        'source_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'verification':'HTTPS official repository release; locally recorded digest'},indent=2),encoding='utf-8')
    print('Installed pgvector into project-local PostgreSQL. No system service changed.')

if __name__=='__main__':
    main()
