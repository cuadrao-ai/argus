"""Two approved synthetic diagnostics; no retries, no financial-record writes."""
import asyncio
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx
from PIL import Image
from pydantic import ValidationError
from argus.domain.ingestion.documents.config import DocumentExtractionSettings
from argus.domain.ingestion.documents.extractor import DocumentExtractor
from argus.domain.ingestion.documents.models import DocumentExtractionError, ExtractionResult
from argus.llm import openrouter
from scripts.documents.benchmark import MANIFEST, receipt_cost, row_score, validate_fixtures
from scripts.documents.budget import BenchmarkBudget, price_envelope

FIELDS = {'page', 'row', 'evidence', 'status', 'amount', 'currency', 'occurred_on', 'posted_on', 'direction', 'kind_hint', 'balance_scope', 'due_on', 'period_start', 'period_end', 'uncertain'}
ROOT = Path('temp/document-extraction')
LIVE = '--live' in sys.argv
FAIL_FIRST = '--fail-first' in sys.argv
MODE = 'live' if LIVE else ('offline-failure' if FAIL_FIRST else 'offline-success')
OUT = ROOT / f'qwen-diagnostics-6usd-{MODE}.json'


def projection(row):
    return {k: v[:80] if isinstance(v, str) else v for k, v in row.items() if k in FIELDS and (v is None or isinstance(v, (str, int)) or k == 'uncertain' and isinstance(v, list) and all(isinstance(x, str) and len(x) <= 20 for x in v))}


def validation_errors(exc):
    return [{'type': e['type'], 'location': e['loc']} for e in exc.errors(include_input=False, include_context=False, include_url=False)]


async def main():
    model = openrouter.resolve_openrouter_model(task='document_extraction')
    assert model == 'qwen/qwen3.7-plus'
    assert os.getenv('APP_ENV') == 'development'
    assert not (LIVE and FAIL_FIRST)
    samples_by_id = {s['id']: s for s in validate_fixtures(MANIFEST)}
    samples = [samples_by_id[x] for x in ('statement-usd', 'receipt-dop')]
    assert all(s['synthetic'] for s in samples)
    prior = json.loads(Path('docs/reports/evidence/document-extraction/live-benchmark-summary-2026-10-02.json').read_text())
    prior_reserved = Decimal(prior['budget']['reserved_usd'])
    endpoints = json.loads((ROOT / 'qwen-endpoints-budget6.json').read_text())['data']['endpoints']
    envelope = price_envelope(model, endpoints)
    budget = BenchmarkBudget(envelope, Decimal('6') - prior_reserved, 2)
    assert prior_reserved + envelope.maximum_cost * 2 < Decimal('6')
    report = dict(mode=MODE, model=model, git_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(), runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), started_at=datetime.now(timezone.utc).isoformat(), cumulative_ceiling_usd='6', prior_reserved_usd=str(prior_reserved), prior_known_cost_usd=prior['known_cost_usd'], prior_cost_unknown=True, endpoint_snapshot=endpoints, proposed_cumulative_reservation_usd=str(prior_reserved + envelope.maximum_cost * 2), results=[], stop_reason=None, complete=False)
    with OUT.open('x') as stream:
        json.dump(report, stream)

    def save():
        report['new_budget'] = budget.evidence()
        report['cumulative_reserved_usd'] = str(prior_reserved + budget.reserved)
        OUT.write_text(json.dumps(report, indent=2) + '\n')

    known_cost = Decimal(0)
    original_guard = openrouter._guard_request
    original_post = openrouter._post_openrouter_json_schema
    for sample in samples:
        item = dict(fixture_id=sample['id'], fixture_sha256=sample['sha256'], model_observations=[], canonical_candidates=[], error_code=None)
        report['results'].append(item)
        metadata = {}
        def capture_guard(task, payload):
            guarded = original_guard(task, payload)
            assert 'cache_control' not in json.dumps(guarded)
            item['request'] = dict(model=guarded['model'], max_tokens=guarded['max_tokens'], provider=guarded['provider'], schema_sha256=hashlib.sha256(json.dumps(guarded['response_format'],sort_keys=True).encode()).hexdigest(), images=[], supplemental_pdf_text_chars=0)
            for msg in guarded['messages']:
                if not isinstance(msg['content'], list):
                    continue
                for block in msg['content']:
                    if block['type'] == 'image_url':
                        encoded = block['image_url']['url']
                        assert encoded.startswith('data:image/jpeg;base64,')
                        image_bytes = base64.b64decode(encoded.split(',',1)[1],validate=True)
                        picture = Image.open(io.BytesIO(image_bytes)); picture.load()
                        digest = hashlib.sha256(image_bytes).hexdigest()
                        reference = Path('docs/reports/evidence/document-extraction') / f"qwen-preflight-{sample['id']}-p1.jpg"
                        assert digest == hashlib.sha256(reference.read_bytes()).hexdigest()
                        item['request']['images'].append(dict(width=picture.width,height=picture.height,sha256=digest,bytes=len(image_bytes)))
                    elif block['type']=='text' and block['text'].startswith('Supplemental local PDF text'):
                        item['request']['supplemental_pdf_text_chars'] = len(block['text'])
            assert len(item['request']['images']) == sample['pages']
            save()
            return guarded

        async def observe_post(**kwargs):
            if LIVE:
                try:
                    response = await original_post(**kwargs)
                except httpx.HTTPStatusError as exc:
                    item['http_status'] = exc.response.status_code
                    try:
                        body = exc.response.json()
                        error = body.get('error', {}) if isinstance(body, dict) else {}
                        if isinstance(error, dict):
                            item['provider_error_code'] = error.get('code')
                            message = str(error.get('message', '')).lower()
                            item['provider_error_terms'] = [term for term in ('schema', 'unsupported', 'image', 'privacy', 'zdr', 'credits', 'quota', 'rate limit', 'no endpoints', 'no available') if term in message]
                    except ValueError:
                        item['provider_error_code'] = 'non_json_error'
                    save()
                    raise
            else:
                openrouter._guard_request('document_extraction', kwargs['payload'])
                observations = [dict(page=r['page'], row=i+1, evidence='transaction', amount=r['amount'], currency=r['currency'], occurred_on=r['date'], direction='inflow' if r['kind']=='income' else 'outflow', kind_hint=r['kind']) for i,r in enumerate(sample['expected_rows'])]
                if FAIL_FIRST:
                    observations[0]['evidence'] = 'unclassified'
                body = dict(complete=True,readable=True,pages_read=[1],observations=observations)
                response = httpx.Response(200,json=dict(model=model,choices=[dict(finish_reason='stop',message=dict(content=json.dumps(body)))],usage=dict(prompt_tokens=1,completion_tokens=1,cost=0)))
            if response is None:
                return response
            data = response.json()
            item['http_status'] = response.status_code
            item['response_model'] = data.get('model')
            item['provider_error_code'] = data.get('error',{}).get('code') if isinstance(data.get('error',{}),dict) else None
            choices = data.get('choices', [])
            item['finish_reasons'] = [c.get('finish_reason') for c in choices if isinstance(c,dict)]
            try:
                content = openrouter._openrouter_message_content(data)
                raw = json.loads(openrouter._json_content_without_code_fences(content))
                item['model_completion'] = {k:raw.get(k) for k in ('readable','complete','pages_read')}
                item['model_observations'] = [projection(r) for r in raw.get('observations',[]) if isinstance(r,dict)]
                try:
                    ExtractionResult.model_validate(raw)
                    item['schema_validation'] = 'passed'
                except ValidationError as exc:
                    item['schema_validation'] = validation_errors(exc)
            except (ValueError, TypeError, AttributeError):
                item['schema_validation'] = 'no_parseable_observations'
            save()
            return response

        started = time.perf_counter()
        try:
            with patch('argus.llm.openrouter._guard_request',capture_guard), patch('argus.llm.openrouter._post_openrouter_json_schema',observe_post), budget.attempt(sample['id'],save):
                batch = await DocumentExtractor(DocumentExtractionSettings(enabled=True)).extract((MANIFEST.parent/sample['file']).read_bytes(),sample['file'],'application/pdf' if sample['file'].endswith('.pdf') else 'image/png','synthetic-qwen-diagnostic',datetime.now(timezone.utc))
            metadata = batch.metadata
            item['canonical_candidates'] = [projection(r.model_dump(mode='json')) for r in batch.candidates]
            item['candidate_validation'] = 'passed'
            item['quality'] = row_score(sample,batch.candidates)
        except DocumentExtractionError as exc:
            item['error_code'] = exc.code
            metadata = exc.metadata
            item['candidate_validation'] = 'failed_or_not_reached'
        except Exception as exc:
            item['error_code'] = type(exc).__name__
        item['latency_ms'] = round((time.perf_counter()-started)*1000)
        try:
            cost, usage = receipt_cost(metadata)
            item['usage'] = usage
            known_cost += cost
            if cost > envelope.maximum_cost:
                report['stop_reason'] = 'request_price_bound_exceeded'
        except ValueError:
            report['stop_reason'] = 'unknown_cost_or_multiple_attempts'
        score = item.get('quality',{})
        item['accuracy_passed'] = item['error_code'] is None and score.get('exact_matches') == len(sample['expected_rows']) and score.get('missing_or_mismatched') == 0 and score.get('invented_or_mismatched') == 0 and score.get('balances_as_transactions') == 0
        if item['error_code'] or not item['accuracy_passed']:
            report['stop_reason'] = report['stop_reason'] or 'extraction_or_accuracy_failed'
        report['new_known_cost_usd'] = str(known_cost)
        report['new_actual_cost_usd'] = None if report['stop_reason']=='unknown_cost_or_multiple_attempts' else str(known_cost)
        report['cumulative_known_cost_usd'] = str(Decimal(prior['known_cost_usd']) + known_cost)
        report['cumulative_actual_cost_usd'] = None
        save()
        if report['stop_reason']:
            break
    report['complete'] = len(report['results']) == 2 and not report['stop_reason']
    save()
    print(json.dumps({k:report.get(k) for k in ('mode','complete','stop_reason','new_actual_cost_usd','cumulative_reserved_usd')}))

if __name__ == '__main__':
    asyncio.run(main())
