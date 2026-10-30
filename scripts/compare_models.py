"""One entrypoint for fixed-input profile trials. Preview is the default and free."""
from pathlib import Path
from time import perf_counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import database
from app.baseline import search, verified_sources
from app.model_gateway import ModelError, generate_draft, load_settings, model_profiles, preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles', nargs='+', choices=list(model_profiles()), default=['openai_luna'])
    parser.add_argument('--cases', nargs='+', default=['SD-001','SD-002','SD-003'])
    parser.add_argument('--language', choices=['zh','en'], default='en')
    parser.add_argument('--retrieval', choices=['keyword','vector','hybrid'], default='keyword')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    sources, segments = verified_sources(), database.current_segments()
    cases = json.loads((ROOT/'evaluation/development.json').read_text(encoding='utf-8'))['cases']
    selected = [c for c in cases if c['id'] in args.cases]
    if set(args.cases) != {c['id'] for c in selected}:
        raise ModelError('scope','This command runs selected development cases only; it does not read holdout cases.')
    settings = [(name, load_settings(profile=name,output_language=args.language)) for name in dict.fromkeys(args.profiles)]
    inputs = []
    for case in selected:
        if args.retrieval=='keyword':
            result = search(segments,case['question'],limit=3)
        else:
            # Preview must never embed a new query. Explicit execution required.
            if not args.execute:
                raise ModelError('scope','New vector queries may incur charges; preview keyword retrieval first or explicitly authorize --execute.')
            from app.vector_search import retrieve
            result = retrieve(segments,case['question'],args.retrieval,limit=3)
        inputs.append((case,result))
    plans = [{'case_id':case['id'],'profile':name,**preview(case['question'],result['citations'],setting)}
             for case,result in inputs for name,setting in settings]
    (ROOT/'outputs/model-comparison-plan.json').write_text(json.dumps(plans,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Profiles:', ', '.join(name for name,_ in settings), '| Cases:', len(inputs))
    print('Plan: outputs/model-comparison-plan.json | Execution:', args.execute)
    if not args.execute:
        print('No HTTP requests. Same question/excerpts/language for each profile.')
        return
    # Validate all selected credentials before generating; no automatic provider fallback.
    for _,setting in settings:
        setting.require_enabled()
    rows=[]
    path=ROOT/'outputs'/('model-comparison-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
    for case,result in inputs:
        ticket=database.save_ticket(case['question'],result,0,True)
        fixed_digest=hashlib.sha256(json.dumps({'question':case['question'],'citations':result['citations']},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        for name,setting in settings:
            generation=generate_draft(case['question'],result['citations'],setting,
                                      database.reserve_model_call,database.finish_model_call)
            if generation['model_called']:
                generation['retrieval_method']=args.retrieval
                generation=database.save_generated_run(ticket['ticket_id'],case['question'],generation)
            rows.append({'case_id':case['id'],'profile':name,'fixed_input_sha256':fixed_digest,
                         'quality_review':'pending_human_review',**generation})
            path.write_text(json.dumps({'source_hashes':{s['source_id']:s['sha256'] for s in sources},
                'results':rows},ensure_ascii=False,indent=2),encoding='utf-8')
            print(case['id'],name,generation['status'])
    print('Result:',path)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except ModelError as error:
        print('Stopped:',error.code,str(error))
        raise SystemExit(2)
