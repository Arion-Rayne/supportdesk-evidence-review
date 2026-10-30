"""Export actual attempts and list-price estimates; never pretend to be a bill."""
from pathlib import Path
from decimal import Decimal
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import database

PRICES={'gpt-6-luna':('0.10','0.50'),'text-embedding-3-small':('0.02','0')}
CACHE_PRICES={'gpt-6-luna':('0.01','0.125')}

def estimate(row):
    usage=row['usage']
    rates=PRICES.get(row['requested_model'])
    if not rates or not isinstance(usage,dict):
        return None
    input_tokens=usage.get('input_tokens',usage.get('prompt_tokens'))
    output_tokens=usage.get('output_tokens',0 if row['requested_model']=='text-embedding-3-small' else None)
    if any(type(value) is not int or value<0 for value in (input_tokens,output_tokens)):
        return None
    details=usage.get('input_tokens_details') or {}
    if not isinstance(details,dict):
        return None
    cached=details.get('cached_tokens',0)
    writes=details.get('cache_write_tokens',0)
    if any(type(value) is not int or value<0 for value in (cached,writes)) or cached+writes>input_tokens:
        return None
    cache_rates=CACHE_PRICES.get(row['requested_model'])
    if (cached or writes) and not cache_rates:
        return None
    # Returned cache token buckets are included in input_tokens, not extra input.
    input_cost=Decimal(input_tokens-cached-writes)*Decimal(rates[0])
    if cache_rates:
        input_cost+=Decimal(cached)*Decimal(cache_rates[0])+Decimal(writes)*Decimal(cache_rates[1])
    return float((input_cost+Decimal(output_tokens)*Decimal(rates[1]))/Decimal(1000000))

def main():
    with database.connect() as connection:
        rows=connection.execute('''SELECT id,batch,provider,requested_model,actual_model,status,
            usage,latency_ms,error_code,created_at FROM model_call_attempts ORDER BY created_at,id''').fetchall()
    attempts=[{**r,'estimated_list_price_usd':estimate(r)} for r in rows]
    known=[r['estimated_list_price_usd'] for r in attempts if r['estimated_list_price_usd'] is not None]
    report={'attempt_count':len(attempts),'known_usage_estimate_usd':sum(known),
        'unknown_cost_attempts':len(attempts)-len(known),'actual_provider_bill_usd':None,
        'pricing_checked_date':'2026-10-09','note':'List-price estimate from returned usage including reported cache read/write token buckets, not account billing. Failed/unknown requests may have charges. Unreported cache details, discounts, regional adjustments and taxes may affect billing.',
        'pricing_sources':['https://developers.openai.com/api/docs/models/gpt-6-luna',
                           'https://developers.openai.com/api/docs/models/text-embedding-3-small'],
        'attempts':attempts}
    (ROOT/'outputs/actual-usage-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print({k:report[k] for k in ('attempt_count','known_usage_estimate_usd','unknown_cost_attempts')})

if __name__=='__main__':
    main()
