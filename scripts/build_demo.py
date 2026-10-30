"""Build an English static example using verified sources and a labelled translation."""
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import baseline


def main():
    example = json.loads((ROOT / 'demo/example.json').read_text(encoding='utf-8'))
    historical = json.loads((ROOT / 'demo/historical-english.json').read_text(encoding='utf-8'))
    current = json.loads((ROOT / 'evaluation/english-model-followup-06-2026-10-30.json').read_text(encoding='utf-8'))
    assert current['status'] == 'success' and current['readback_verified']
    current = current['generation']
    sources = baseline.verified_sources()
    partials = {Path(source['local_file']).name: source for source in sources[5:]}
    segments = [item for source in sources[:5] for item in baseline.segments_for(source, partials)]
    by_id = {segment['segment_id']: segment for segment in segments}
    citations = [by_id[identifier] for identifier in example['source_segment_ids']]
    historical_citations = [by_id[identifier] for identifier in historical['source_segment_ids']]
    current_citations = [by_id[c['segment_id']] for c in current['citations']]
    assert any(c['source_id'] == 'rls' and c['line_start'] == 758 for c in citations)
    e = html.escape
    cards = ''.join(f'<article><h3>{e(c["title"])} · line {c["line_start"]}</h3><pre>{e(c["text"])}</pre>'
                    f'<p><a href="{e(c["url"], quote=True)}">Official documentation</a> · '
                    f'Local snapshot: {e(c["local_file"])} · SHA256 {e(c["sha256"])}</p></article>' for c in citations)
    historical_sources = ''.join(f'<li><a href="{e(c["url"], quote=True)}">{e(c["title"])} · line {c["line_start"]}</a></li>'
                                 for c in historical_citations)
    current_sources = ''.join(f'<li><a href="{e(c["url"], quote=True)}">{e(c["title"])} · line {c["line_start"]}</a>: {e(c["text"])}</li>' for c in current_citations)
    page = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SupportDesk | Evidence-backed support</title><style>*{box-sizing:border-box}body{margin:0;font:16px/1.65 system-ui,sans-serif;color:#18342c;background:#f3f7f5}main{max-width:1040px;margin:auto;padding:40px 24px 80px}h1{font-size:clamp(30px,5vw,45px);line-height:1.1;margin:12px 0}.eyebrow{color:#176851;text-transform:uppercase;font-weight:700;letter-spacing:.12em;font-size:13px}.lead{max-width:720px;color:#50695d;font-size:18px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}section,article{background:white;border:1px solid #d5e3db;border-radius:12px;padding:22px;margin:18px 0}.grid section{margin:0}.tag{font-size:13px;font-weight:700;color:#176851}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 ui-monospace,monospace}blockquote{margin:0;border-left:3px solid #258263;padding-left:16px}a{color:#176851}footer{color:#50695d;font-size:14px} @media(max-width:700px){.grid{grid-template-columns:1fr}}</style></head><body><main><p class="eyebrow">SupportDesk · Local portfolio demo</p><h1>Find the evidence.<br>Review the answer.</h1><p class="lead">A support drafting workflow that keeps the source visible and the reviewer in control.</p><p><a href="http://127.0.0.1:8767/">Open the local app</a> · <a href="../docs/EVALUATION.md">Evaluation and limitations</a></p>
<section><p class="tag">CURRENT RELEASE · REAL ENGLISH MODEL RESPONSE</p><h2>A real response and its sources</h2><p><strong>Question:</strong> ''' + e(current['question']) + '''</p><blockquote>''' + e(current['draft']) + '''</blockquote><p>This is the recorded model draft, not a translation. Human review is required.</p><ul>''' + current_sources + '''</ul><p>On six follow-up attempts for this previously seen case, five passed validation and one failed schema validation. An earlier English attempt also failed validation. These results are not a general accuracy or stability measurement.</p></section><div class="grid"><section><p class="tag">SYNTHETIC QUESTION</p><h2>Customer question</h2><p>''' + e(example['question']) + '''</p><p class="tag">WORKFLOW</p><p>Retrieve documentation → generate a draft → review and save.</p></section><section><p class="tag">MODEL RESPONSE · TRANSLATED</p><h2>Historical translated draft</h2><blockquote>''' + e(example['response_english_translation']) + '''</blockquote><p>''' + e(example['translation_disclosure']) + ''' Human review is required.</p></section></div><section><p class="tag">TRACEABLE SOURCES</p><h2>Evidence cited by the original response</h2>''' + cards + '''</section><section><p class="tag">HISTORICAL MODEL RESPONSE · ORIGINAL ENGLISH</p><h2>A real English response from the original project</h2><p><strong>Question:</strong> ''' + e(historical['question']) + '''</p><blockquote>''' + e(historical['actual_model_draft']) + '''</blockquote><p>This is the exact historical English model draft, not a translation. It predates the current English-release prompt.</p><ul>''' + historical_sources + '''</ul><p>Original response SHA256: ''' + e(historical['source_draft_sha256']) + '''</p></section><footer><p>These are previously seen examples, not an independent accuracy or stability evaluation. The exact cause of the earlier English validation failure was not retained.</p><p>Translated example's original response SHA256: ''' + e(example['source_original_draft_sha256']) + '''</p></footer></main></body></html>'''
    (ROOT / 'demo/index.html').write_text(page, encoding='utf-8')
    print('Built demo/index.html from verified snapshots; no model request was sent.')


if __name__ == '__main__':
    main()
