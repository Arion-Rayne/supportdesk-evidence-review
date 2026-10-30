# Project map

This is a small, local, single-reviewer portfolio application. Start with the request flow below; you do not need to read every directory to understand one feature.

## Follow a question through the application

1. `app/stage1.html`, `app/stage1.css`, and `app/stage1.js` define the workspace, its appearance, and browser interactions. Submitting the form sends `POST /tickets`.
2. `app/api.py` validates the request, selects keyword or vector retrieval, and calls the database. It also serves the page and handles model previews, generation, and reviews.
3. `app/baseline.py` verifies the fixed documentation snapshots, divides them into traceable segments, and implements keyword search. `app/vector_search.py` implements the optional vector and hybrid searches. `app/evidence_context.py` attaches nearby source context.
4. `app/database.py` stores the ticket, retrieval result, generated runs, and separate human reviews in PostgreSQL. `migrations/` contains the versioned SQL schema changes.
5. For optional generation, `app/workflow.py` checks saved citations against verified source files. `app/generation_contract.py` prepares the prompt and validates the response, while `app/model_gateway.py` handles provider requests and local call controls. A reviewer must inspect the draft.

## Directories at a glance

| Directory | Purpose |
| --- | --- |
| `app/` | Application code, API, retrieval, persistence, and frontend. |
| `config/` | Source manifest and model-profile configuration. |
| `data/` | Fixed documentation snapshots and source attribution. |
| `demo/` | Static example showing evidence and recorded drafts. |
| `docs/` | Setup, architecture, demo, evaluation, and interview notes. |
| `evaluation/` | Synthetic questions and recorded diagnostic results, including failures. |
| `migrations/` | PostgreSQL schema changes; `migrations/vector/` is optional. |
| `scripts/` | Setup, starting the app, evaluation, model comparison, and packaging. |
| `tests/` | Unit and integration checks; test fixtures are not model outputs. |

The local `.env`, `.local/`, and `outputs/` are ignored and are not part of the release archive. They contain local configuration, database files, and generated output respectively. `.env.example` lists configuration names without containing your credentials.

## Where to start a change

- Change text, layout, or controls: inspect the three `app/stage1.*` files and `tests/test_frontend_i18n.js`.
- Change an API request or response: start at `app/api.py` and `tests/test_stage1.py`.
- Change how evidence is found or contextualized: start at `app/baseline.py`, `app/vector_search.py`, and `app/evidence_context.py`, with their corresponding tests.
- Change the model prompt, validation, or provider: start at `app/generation_contract.py`, `app/workflow.py`, and `app/model_gateway.py`, with the model and contract tests.
- Change storage: inspect `app/database.py` and add a new migration rather than editing an already-applied migration.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the system diagram and boundaries, [SETUP.md](SETUP.md) to run it, and [EVALUATION.md](EVALUATION.md) for measured results and limitations. The JavaScript currently keeps translations, rendering, and HTTP interaction together; further separation is appropriate if the interface grows.
