"""Start project-local PostgreSQL, apply migrations, import, and serve the API."""
from pathlib import Path
import json
import logging
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg
from psycopg import sql
import uvicorn

from app import database


def prepare_local_database():
    if os.environ.get('DATABASE_URL'):
        return
    config = json.loads((ROOT / '.local/database.json').read_text(encoding='utf-8'))
    admin_config = dict(config, dbname='postgres')
    try:
        connection = psycopg.connect(**admin_config, connect_timeout=3, autocommit=True)
    except psycopg.OperationalError:
        subprocess.run([str(ROOT / '.local/pgsql/bin/pg_ctl.exe'),
                        '-D', str(ROOT / '.local/pgdata'), '-l', str(ROOT / '.local/postgres.log'),
                        '-w', 'start'], check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        connection = psycopg.connect(**admin_config, connect_timeout=3, autocommit=True)
    with connection:
        exists = connection.execute('SELECT 1 FROM pg_database WHERE datname = %s',
                                    (config['dbname'],)).fetchone()
        if not exists:
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(config['dbname'])))


def main():
    os.chdir(ROOT)
    (ROOT / 'outputs').mkdir(exist_ok=True)
    logging.basicConfig(filename=ROOT / 'outputs/stage1-server.log', level=logging.INFO,
                        format='%(asctime)s %(name)s %(levelname)s %(message)s', encoding='utf-8')
    try:
        prepare_local_database()
        database.migrate()
        stats = database.import_sources()
        logging.info('Imported verified package: %s', stats)
        (ROOT / '.local/api.pid').write_text(str(os.getpid()), encoding='ascii')
        uvicorn.run('app.api:app', host='127.0.0.1', port=8767, access_log=False,
                    log_config=None)
    except Exception as exception:
        # Do not log arbitrary error text containing database credentials.
        logging.error('Stage 1 startup failed: %s', type(exception).__name__)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
