# Setup and operation

## 1. Install dependencies

Install Python 3.10 or newer. In the project directory, create and activate a virtual environment if desired, then run:

```powershell
python -m pip install -r requirements.txt
python -m app.baseline
```

The second command verifies seven fixed source snapshots, segments them, and writes an English report to `outputs/stage0.html`. It does not call a model or require a database.

## 2. Start PostgreSQL and the app

On Windows, the setup script downloads project-local PostgreSQL binaries from the URL stated in `scripts/setup_postgres.py`, initializes a local cluster, and writes local credentials under `.local/`. It does not install a Windows service.

```powershell
python scripts/setup_postgres.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_stage1.ps1 -Detached
```

Open http://127.0.0.1:8767/ for the app or http://127.0.0.1:8767/demo for the static English example. The English demo uses ports 8767 (app), 8768 (optional report preview), and 55433 (project-local database) so it can coexist with the original Chinese project. On an existing Windows installation, `START_SUPPORTDESK.cmd` starts the app.

For an existing PostgreSQL server on another platform, set `DATABASE_URL` in the process environment, install dependencies, and run `python scripts/run_stage1.py`. The app applies migrations and imports verified sources at startup. The Windows automatic setup path is not a cross-platform installer.

## 3. Optional model generation

Copy `.env.example` to `.env`. Enter the appropriate provider key locally; never commit the file. Calls default to disabled. A paid call requires setting `ENABLE_PAID_CALLS=true`, a positive `MODEL_CALL_LIMIT`, and a budget and batch. The reservation is a local application control, **not** an enforced OpenAI account spending limit. Timeouts may still be billable; the app does not retry automatically.

Choose a model profile and reply language in the interface. The free preview shows the request content without exposing the key. OpenAI generation was exercised on a known English question: five of six follow-up attempts passed validation, while one failed schema validation and an earlier attempt also failed validation. These are not a general quality guarantee; see [EVALUATION.md](EVALUATION.md). Gemini has fixture tests but has not been verified with a real call in this project.

To preview the same questions and evidence across profiles without changing `.env` or sending requests:

```powershell
python scripts/compare_models.py --profiles openai_luna gemini_lite --cases SD-001 SD-002 --language en
```

The preview is free; adding `--execute` requires paid-call settings and sends requests. The profiles must each have their own configured credentials. For one saved ticket, use `python scripts/run_model_trial.py --ticket <ticket-id> --profile openai_luna --language en` to preview, or add `--execute` only after configuring and authorizing paid calls.

## 4. Optional vector search

On Windows, `python scripts/setup_pgvector.py` builds pgvector into project-local PostgreSQL. It requires Visual Studio C++ Build Tools. Run `python scripts/build_vector_index.py` for a free workload preview. `--execute` performs embedding requests and requires explicit paid-call configuration. A new question may require an additional embedding call. Keep keyword search as the default when no vector index is available.

## 5. Verify

```powershell
python -m unittest discover -s tests -v
python scripts/evaluate_retrieval.py
```

Database integration tests require a running project-local PostgreSQL and `SUPPORTDESK_TEST_POSTGRES=1`; without it, those tests are skipped. They create and drop a randomly named disposable database. The English development retrieval script is free and does not establish answer accuracy. See [EVALUATION.md](EVALUATION.md).

The repository excludes `.env`, `.local/`, database data, and generated output. An existing ticket URL is local to its database and is not portable to a fresh clone.
