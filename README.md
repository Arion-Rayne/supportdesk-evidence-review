# SupportDesk: evidence-backed support drafts

SupportDesk is a local portfolio demo that helps a support reviewer answer synthetic Supabase questions. It finds relevant documentation, presents the original evidence, optionally asks a model for a draft, and saves the reviewer's edits. It does not send replies or modify customer systems.

```text
Synthetic question → retrieve source excerpts → inspect evidence
                   → optional model draft → human review → save and reopen
```

**Start here:** [Project map](docs/PROJECT_MAP.md) · [Demo walkthrough](docs/DEMO.md) · [Setup and run](docs/SETUP.md) · [Architecture](docs/ARCHITECTURE.md) · [Evaluation and limitations](docs/EVALUATION.md) · [Interview notes](docs/INTERVIEW.md). After starting the local app, view the rendered example at http://127.0.0.1:8767/demo.

## What it includes

- Seven verified Supabase documentation snapshots and 314 traceable segments, with file names, line numbers, source URLs, and SHA256 hashes.
- Free keyword retrieval, plus optional real OpenAI embeddings, PostgreSQL pgvector search, and hybrid retrieval.
- A FastAPI backend and PostgreSQL storage for tickets, retrievals, model runs, and append-only human reviews.
- An English-first web interface with an optional Chinese UI and Chinese or English reply language. Original source material remains in its original language.
- Optional OpenAI model generation with explicit local opt-in, per-batch reservations, bounded output, source-ID validation, and no automatic retries.
- A single model-comparison command that previews multiple profiles with the same question and evidence without repeatedly editing `.env`.
- A targeted rule that adds a relevant user-token qualification when the fixed documentation's secret-key summary would otherwise omit it.

The default retrieval method is keyword search. This is a local single-reviewer demo, not a production help desk or a hosted multi-user service.

## Quick start

Requirements: Python 3.10+ and PostgreSQL. Windows users may use the included project-local PostgreSQL setup; pgvector is optional for the keyword baseline.

```powershell
python -m pip install -r requirements.txt
python -m app.baseline
python scripts/setup_postgres.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_stage1.ps1 -Detached
```

Open **http://127.0.0.1:8767/**. The free baseline report is written to `outputs/stage0.html`; open it locally or run `scripts/start_preview.ps1` and visit http://127.0.0.1:8768/stage0.html. No model key is required for keyword retrieval, evidence inspection, or manually saved reviews. For setup on other platforms and optional model calls, see [SETUP.md](docs/SETUP.md).

## Results and boundaries

- The English release passed **64 engineering tests**, including tests against a disposable PostgreSQL database. These check software behavior, not answer accuracy.
- On 20 assistant-translated, previously seen development questions, free keyword retrieval found at least one selected reference in the top three for **13 of 19 scored questions**. This narrow metric is not an independent test or an answer-quality score. The original Chinese development set and first holdout runs are preserved separately in the original project.
- The original project made three real GPT-6 Luna calls on one known question. After changing the prompt and output checks, the third answer included the user-token qualification. The prompt changed between calls, so this is **one successful result under the final prompt**, not a stability measurement.
- The demo shows a real English response from this release, a labelled **assistant translation** of a historical Chinese response, and a separate original English response from the earlier project. Of six follow-up attempts on the same known question, five passed validation and one failed schema validation; an earlier English attempt also failed validation. These are not a general reliability measurement.
- Model responses require human review. Source coverage is limited, vector similarity is not a correctness guarantee, and this version has not been independently installed on a separate clean computer.

See [EVALUATION.md](docs/EVALUATION.md) for the evidence, failure cases, measurement definitions, and limitations.

## Privacy and licensing

Only synthetic questions and fixed public-source snapshots are supplied. Keep `.env`, API keys, `.local/`, database contents, and generated outputs out of version control. Supabase documentation attribution and licensing are in [data/ATTRIBUTION.md](data/ATTRIBUTION.md). This project is independent and is not affiliated with Supabase.
