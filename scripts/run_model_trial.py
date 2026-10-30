"""Preview a saved ticket offline, or explicitly execute one guarded model request."""
from pathlib import Path
from uuid import UUID
import argparse
import html
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg
from app import database
from app.baseline import verified_sources
from app.model_gateway import ModelError, generate_draft, load_settings, model_profiles, preview


def write_result_page(saved):
    """Only real, validated generation is written here, never fixtures."""
    escape = html.escape
    citations = ''.join(f'<article><h2>Evidence {index} · {escape(c["title"])}</h2>'
        f'<pre>{escape(c["text"])}</pre><a href="{escape(c["url"], quote=True)}">Official source</a></article>'
        for index, c in enumerate(saved['citations'], 1))
    missing = ''.join(f'<li>{escape(value)}</li>' for value in saved['missing_information'])
    body = f'''<!doctype html><html lang="{saved['output_language']}"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SupportDesk · Model draft</title>
<style>body{{max-width:900px;margin:32px auto;padding:0 20px;font:18px/1.7 system-ui;background:#f4f8f6;color:#203a3d}}
article{{padding:20px;border:1px solid #d6e3de;background:white;border-radius:12px;margin:20px 0}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}}a{{color:#166956}}</style>
<h1>Model draft · Human review required</h1><p>Ticket: {escape(saved['ticket_id'])}</p>
<p>Provider: {escape(saved['provider'])}; actual model: {escape(saved['model_name'])}</p>
<h2>Customer question</h2><p>{escape(saved['question'])}</p>
<article><h2>Draft reply</h2><pre>{escape(saved['draft'] or 'The available sources did not support a draft.')}</pre>
<p>{escape(saved['review_reason'])}</p></article><h2>Missing information</h2><ul>{missing}</ul>
{citations}<p>Citation structure was checked; technical claims still require human review. No reply was sent.</p>
<details><summary>Actual usage and latency</summary><pre>{escape(json.dumps(saved['usage'], ensure_ascii=False, indent=2))}</pre>
<p>Request latency: {saved['latency_ms']:.0f} ms</p></details></html>'''
    output = ROOT / f"outputs/model-trial-{saved['run_id']}.html"
    output.write_text(body, encoding='utf-8')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticket', type=UUID, required=True, help='An existing synthetic ticket ID')
    parser.add_argument('--execute', action='store_true', help='One request; requires separately authorized settings')
    parser.add_argument('--profile', choices=list(model_profiles()), help='Select model without editing .env')
    parser.add_argument('--language', choices=('zh', 'en'), help='Requested reply language')
    args = parser.parse_args()
    settings = load_settings(profile=args.profile, output_language=args.language)
    verified_sources()
    record = database.read_ticket(args.ticket)
    if record is None or not record['runs']:
        raise ModelError('ticket_missing', 'The ticket or its retrieval record was not found.')
    if not record['ticket']['synthetic']:
        raise ModelError('scope', 'Model trials are limited to synthetic tickets.')
    # Freeze the original retrieval for this comparison, rather than re-searching per model.
    question = record['ticket']['question']
    citations = record['runs'][0]['result']['citations'][:3]
    current = {entry['segment_id']: entry for entry in database.current_segments()}
    for citation in citations:
        source = current.get(citation['segment_id'])
        if source is None or any(source[name] != citation[name] for name in ('source_id', 'sha256', 'text')):
            raise ModelError('source_changed', 'Saved evidence differs from the verified sources; generation stopped.')
    prepared = preview(question, citations, settings)
    prepared['ticket_id'] = str(args.ticket)
    plan_path = ROOT / 'outputs/model-trial-plan.json'
    plan_path.write_text(json.dumps(prepared, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Provider:', settings.provider, '; model:', settings.model)
    print('Key configured:', prepared['key_configured'], '; calls enabled:', prepared['calls_enabled'])
    print('Evidence:', len(citations), '; output token limit:', settings.max_output_tokens)
    print('Preview:', plan_path)
    if not args.execute:
        print('Preview only. Model calls: 0. No embedding calls or generated draft.')
        return
    generation = generate_draft(question, citations, settings,
        database.reserve_model_call, database.finish_model_call)
    if not generation['model_called']:
        print('No retrieved evidence; model call skipped. No generated draft.')
        return
    saved = database.save_generated_run(args.ticket, question, generation)
    output = ROOT / f"outputs/model-trial-{saved['run_id']}.json"
    output.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')
    # Read back the exact persisted run before displaying success.
    reread = database.read_ticket(args.ticket)
    persisted = next(run['result'] for run in reread['runs'] if str(run['id']) == saved['run_id'])
    if persisted != generation | {'question': question, 'method': 'keyword+model'}:
        raise ModelError('persistence', 'Draft readback failed; inspect the saved record before making another call.')
    print('Validated real draft saved to PostgreSQL. Requires human review.')
    print('Result:', write_result_page(saved))


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    try:
        main()
    except ModelError as exception:
        print('Model operation stopped:', exception.code, '-', str(exception))
        raise SystemExit(2)
    except psycopg.Error:
        print('PostgreSQL operation failed. If a call was attempted, do not immediately repeat it.')
        raise SystemExit(3)
