"""Evaluate keyword retrieval on translated development questions without model calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', help='Optional JSON report path (existing files are not overwritten)')
    args = parser.parse_args()
    sources = baseline.verified_sources()
    partials = {Path(source['local_file']).name: source for source in sources[5:]}
    segments = [item for source in sources[:5] for item in baseline.segments_for(source, partials)]
    cases = json.loads((ROOT / 'evaluation/development.json').read_text(encoding='utf-8'))['cases']
    rows = []
    for case in cases:
        result = baseline.search(segments, case['question'], limit=3)
        selected = set(case['acceptable_segment_ids'])
        ids = [c['segment_id'] for c in result['citations']]
        rows.append({'id': case['id'], 'question': case['question'],
                     'top_three_ids': ids, 'reference_hit': bool(selected.intersection(ids)) if selected else None,
                     'sources': [{'title': c['title'], 'url': c['url'], 'line': c['line_start']} for c in result['citations']]})
    report = {'scope': 'Assistant-translated, previously seen development questions; not an independent evaluation.',
              'definition': 'At least one preselected reference segment appears in the top three; not answer accuracy.',
              'model_called': False, 'total_cases': len(rows), 'scored_cases': sum(r['reference_hit'] is not None for r in rows),
              'reference_hits': sum(r['reference_hit'] is True for r in rows), 'results': rows}
    if args.output:
        with Path(args.output).open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
