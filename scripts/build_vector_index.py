"""Preview embedding workload; execute only within explicitly authorized local settings."""
from pathlib import Path
import argparse
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import database
from app.baseline import verified_sources
from app.model_gateway import ModelError
from app.vector_search import MODEL, DIMENSIONS, build_index, digest, ensure_schema, index_text, index_status

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    verified_sources()
    ensure_schema()
    segments = database.current_segments()
    status = index_status()
    plan = {**status, 'max_new_requests': math.ceil(status['current_segments'] / 64),
        'input_characters': sum(len(index_text(segment)) for segment in segments),
        'model_called': False, 'input_tokens': None, 'cost_usd': None}
    (ROOT / 'outputs/vector-index-plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    print(json.dumps(plan, indent=2))
    if args.execute:
        print(json.dumps(build_index(), indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except ModelError as error:
        print('Stopped:', error.code, str(error))
        raise SystemExit(2)
