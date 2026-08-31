#!/usr/bin/env python3
import argparse
import csv
import importlib.util
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

NULL_STRINGS = {'', 'unknown', 'null', 'none', 'n/a', 'na', '-'}
RULES_PATH = Path(__file__).resolve().parents[1] / 'references' / 'thresholds.json'
RULES = json.loads(RULES_PATH.read_text(encoding='utf-8'))
BINDING_PATH = Path(__file__).resolve().parents[3] / 'runtime' / 'evidence_binding.py'
HOOK_PATH = Path(__file__).resolve().parents[3] / 'runtime' / 'stage_hook.py'


def _binding():
    spec = importlib.util.spec_from_file_location('seo_evidence_binding_for_evaluator', BINDING_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stage_hook():
    spec = importlib.util.spec_from_file_location('seo_stage_hook_for_evaluator', HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_missing(value):
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in NULL_STRINGS:
        return True
    return False


def parse_number(value, field, *, min_value=None, max_value=None, integer=False):
    if is_missing(value):
        return None, None
    if isinstance(value, bool):
        return None, f'{field}:boolean_not_numeric'
    try:
        text = str(value).strip().replace(',', '') if not isinstance(value, (int, float)) else value
        v = float(text)
    except (TypeError, ValueError):
        return None, f'{field}:not_numeric'
    if not math.isfinite(v):
        return None, f'{field}:not_finite'
    if integer and not v.is_integer():
        return None, f'{field}:must_be_integer'
    if min_value is not None and v < min_value:
        return None, f'{field}:below_min_{min_value}'
    if max_value is not None and v > max_value:
        return None, f'{field}:above_max_{max_value}'
    return v, None


def compact_number(v):
    if v is None:
        return None
    if float(v).is_integer():
        return int(v)
    return float(v)


def load_input(path):
    p = Path(path)
    if p.suffix.lower() == '.csv':
        with p.open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f)), {}
    data = json.loads(p.read_text(encoding='utf-8'))
    if isinstance(data, list):
        return data, {}
    if isinstance(data, dict):
        for key in ('rows', 'keywords'):
            if isinstance(data.get(key), list):
                meta = {k: v for k, v in data.items() if k not in ('rows', 'keywords')}
                return data[key], meta
    raise ValueError('JSON input must be an array or contain a rows/keywords array')


def collapse_keyword(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def recall_pool(volume, kd):
    if volume is None or kd is None:
        return 'pending_metrics'
    if volume >= RULES['ideas']['main_volume_min'] and kd <= RULES['ideas']['main_kd_max_inclusive']:
        return 'main_recall'
    if volume >= RULES['ideas']['blue_volume_min'] and kd < RULES['ideas']['blue_kd_max_exclusive']:
        return 'blue_recall'
    return 'excluded_recall'


def exact_pool(volume):
    if volume is None:
        return 'unknown'
    if volume >= RULES['exact']['main_volume_min']:
        return 'main'
    if volume >= RULES['exact']['blue_volume_min']:
        return 'blue_ocean'
    return 'below_floor'


def kd_band(kd):
    if kd is None:
        return 'unknown'
    if kd < RULES['exact']['do_kd_max_exclusive']:
        return 'do_candidate'
    if kd <= RULES['exact']['observe_kd_max_inclusive']:
        return 'observe'
    return 'principle_eliminate'


def cpc_signal(cpc):
    if cpc is None:
        return 'unknown'
    if cpc >= RULES['cpc_positive_min']:
        return 'positive_ge_0_10'
    return 'low_lt_0_10'


def calc_kgr(intitle, volume):
    if intitle is None or volume is None or volume <= 0:
        return None
    return intitle / volume


def calc_kdroi(volume, cpc, kd):
    if volume is None or cpc is None or kd is None or kd <= 0:
        return None
    return volume * cpc / kd


def parse_serp_evidence(value):
    if is_missing(value):
        return None, [], []
    raw = value
    if isinstance(value, str):
        try:
            raw = json.loads(value)
        except json.JSONDecodeError:
            return None, [], ['serp_weak_evidence:invalid_json']
    if not isinstance(raw, list):
        return None, [], ['serp_weak_evidence:must_be_array']

    valid = []
    errors = []
    seen_ranks = set()
    for idx, item in enumerate(raw):
        prefix = f'serp_weak_evidence[{idx}]'
        if not isinstance(item, dict):
            errors.append(f'{prefix}:must_be_object')
            continue
        rank, rank_err = parse_number(item.get('rank'), f'{prefix}.rank', min_value=1, max_value=10, integer=True)
        url = str(item.get('url', '')).strip()
        weakness_type = str(item.get('weakness_type', '')).strip()
        observed_fact = str(item.get('observed_fact', '')).strip()
        item_errors = []
        if rank_err:
            item_errors.append(rank_err)
        if not url:
            item_errors.append(f'{prefix}.url:required')
        if not weakness_type:
            item_errors.append(f'{prefix}.weakness_type:required')
        if not observed_fact:
            item_errors.append(f'{prefix}.observed_fact:required')
        if item_errors:
            errors.extend(item_errors)
            continue
        rank_i = int(rank)
        if rank_i in seen_ranks:
            errors.append(f'{prefix}.rank:duplicate_rank_{rank_i}')
            continue
        seen_ranks.add(rank_i)
        valid.append({
            'rank': rank_i,
            'url': url,
            'weakness_type': weakness_type,
            'observed_fact': observed_fact,
        })
    return valid, valid, errors


def _norm_keyword(value):
    return ' '.join(str(value or '').split()).casefold()


def _verified_serp_results(row):
    if is_missing(row.get('serp_weak_evidence')):
        return None
    manifest_ref = str(os.environ.get('SEO_RUN_MANIFEST') or '').strip()
    candidate_id = str(os.environ.get('SEO_CANDIDATE_ID') or '').strip()
    if not manifest_ref or not candidate_id:
        return None
    try:
        manifest = json.loads(Path(manifest_ref).read_text(encoding='utf-8'))
        candidates = manifest.get('candidates')
        candidate = candidates.get(candidate_id) if isinstance(candidates, dict) else None
        if not isinstance(candidate, dict):
            return None
        if _norm_keyword(candidate.get('keyword')) != _norm_keyword(row.get('keyword')):
            return None
        record = candidate.get('serp_review')
        hook = _stage_hook()
        valid, _ = hook._verify_candidate_receipt(
            manifest, candidate_id, candidate, record, 'serp_review'
        )
        if not valid:
            return None
        report, _ = hook._load_validation_report(record, 'serp_review', candidate_id)
        complete = report.get('complete') if isinstance(report, dict) else None
        if not isinstance(complete, list) or len(complete) != 1:
            return None
        results = complete[0].get('results') if isinstance(complete[0], dict) else None
        if not isinstance(results, list):
            return None
        verified = {}
        for item in results:
            if not isinstance(item, dict):
                return None
            rank, error = parse_number(item.get('rank'), 'serp_result.rank', min_value=1, max_value=10, integer=True)
            url = str(item.get('url') or '').strip()
            if error or not url:
                return None
            verified[int(rank)] = url
        return verified
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def provenance_fields(row, batch_meta):
    metric_source = str(row.get('metric_source') or batch_meta.get('metric_source') or '').strip()
    metric_database = str(row.get('metric_database') or batch_meta.get('metric_database') or batch_meta.get('database') or '').strip()
    observed_at = str(row.get('observed_at') or batch_meta.get('observed_at') or batch_meta.get('generated_at') or '').strip()
    metric_stage = str(row.get('metric_stage') or batch_meta.get('metric_stage') or '').strip()
    if not all((metric_source, metric_database, observed_at, metric_stage)):
        return metric_source, metric_database, observed_at, metric_stage, 'incomplete'

    combined = dict(batch_meta)
    combined.update(row)
    binding = _binding()
    try:
        if not is_missing(combined.get('intitle_results')) and combined.get('intitle_evidence_receipt_ref'):
            binding.verify_kgr_payload(combined)
            status = 'verified'
        elif metric_source == 'Semrush' and metric_stage == 'exact' and combined.get('evidence_receipt_ref'):
            binding.verify_payload(combined, 'semrush_exact')
            status = 'verified'
        elif metric_source == 'Semrush' and metric_stage == 'ideas' and combined.get('evidence_receipt_ref'):
            binding.verify_payload(combined, 'semrush_ideas')
            status = 'verified'
        else:
            status = 'unverified'
    except Exception:
        status = 'invalid'
    return metric_source, metric_database, observed_at, metric_stage, status


def final_status(row, volume, kd, kgr, weak_points, validation_errors):
    if validation_errors:
        return 'invalid_row'
    if str(row.get('exclude_reason', '')).strip():
        return 'excluded_manual'
    if volume is None or kd is None:
        return 'pending_metrics'
    if volume < RULES['exact']['blue_volume_min']:
        return 'principle_eliminate_volume'
    if kd > RULES['exact']['observe_kd_max_inclusive']:
        return 'principle_eliminate_kd'
    if kgr is None:
        return 'pending_kgr'
    if kgr >= RULES['kgr_pass_max_exclusive']:
        return 'observe_kgr'
    if kd < RULES['exact']['do_kd_max_exclusive']:
        return 'do_candidate'
    if weak_points is None:
        return 'observe_serp'
    if weak_points >= RULES['serp_upgrade_weak_points_min']:
        return 'do_candidate'
    return 'observe_serp'


def normalize(row, stage, batch_meta=None):
    batch_meta = batch_meta or {}
    out = dict(row)
    errors = []
    keyword = collapse_keyword(row.get('keyword', row.get('phrase', '')))
    if not keyword:
        errors.append('keyword:required')

    volume, err = parse_number(row.get('volume'), 'volume', min_value=0)
    if err: errors.append(err)
    kd, err = parse_number(row.get('difficulty', row.get('kd')), 'difficulty', min_value=0, max_value=100)
    if err: errors.append(err)
    cpc, err = parse_number(row.get('cpc'), 'cpc', min_value=0)
    if err: errors.append(err)
    intitle, err = parse_number(row.get('intitle_results'), 'intitle_results', min_value=0, integer=True)
    if err: errors.append(err)

    legacy_weak, err = parse_number(row.get('serp_weak_points'), 'serp_weak_points', min_value=0, max_value=10, integer=True)
    if err: errors.append(err)

    verified_serp_results = _verified_serp_results(row) if stage == 'final' else None
    evidence_present = not is_missing(row.get('serp_weak_evidence'))
    valid_evidence, evidence_out, evidence_errors = parse_serp_evidence(row.get('serp_weak_evidence'))
    verified_evidence = []
    if evidence_present and verified_serp_results is None:
        evidence_errors.append('serp_weak_evidence:unverified_serp_review')
    elif evidence_present and valid_evidence is not None:
        for idx, item in enumerate(valid_evidence):
            if verified_serp_results.get(item['rank']) == item['url']:
                verified_evidence.append(item)
            else:
                evidence_errors.append(f'serp_weak_evidence[{idx}]:rank_url_not_in_verified_serp')
    weak_points = len(verified_evidence) if evidence_present and verified_serp_results is not None else None
    if legacy_weak is not None:
        out['reported_serp_weak_points'] = int(legacy_weak)

    if errors:
        kgr = None
        kdroi = None
    else:
        kgr = calc_kgr(intitle, volume)
        kdroi = calc_kdroi(volume, cpc, kd)

    metric_source, metric_database, observed_at, metric_stage, provenance_status = provenance_fields(row, batch_meta)

    out['keyword'] = keyword
    out['volume'] = compact_number(volume)
    out['difficulty'] = compact_number(kd)
    out['cpc'] = compact_number(cpc)
    out['intitle_results'] = compact_number(intitle)
    out['serp_weak_evidence'] = evidence_out if evidence_present else None
    out['serp_weak_points'] = weak_points
    out['serp_evidence_status'] = 'verified' if evidence_present and verified_serp_results is not None else ('unverified' if evidence_present else 'absent')
    out['serp_evidence_errors'] = ' | '.join(evidence_errors)
    out['validation_errors'] = ' | '.join(errors)
    out['row_valid'] = not errors
    out['metric_source'] = metric_source
    out['metric_database'] = metric_database
    out['observed_at'] = observed_at
    out['metric_stage'] = metric_stage
    out['provenance_status'] = provenance_status
    out['recall_pool'] = recall_pool(volume, kd) if not errors else 'invalid_row'
    out['exact_pool'] = exact_pool(volume) if not errors else 'invalid_row'
    out['kd_band'] = kd_band(kd) if not errors else 'invalid_row'
    out['cpc_signal'] = cpc_signal(cpc) if not errors else 'invalid_row'
    out['kgr'] = None if kgr is None else round(kgr, 8)
    out['kgr_signal'] = 'unknown' if kgr is None else ('pass_lt_0_25' if kgr < RULES['kgr_pass_max_exclusive'] else 'not_blue_ocean')
    out['kdroi'] = None if kdroi is None else round(kdroi, 8)

    if errors:
        out['mechanical_status'] = 'invalid_row'
    elif stage == 'ideas':
        out['mechanical_status'] = out['recall_pool']
    elif stage == 'exact':
        if str(row.get('exclude_reason', '')).strip():
            out['mechanical_status'] = 'excluded_manual'
        elif volume is None or kd is None:
            out['mechanical_status'] = 'pending_metrics'
        elif volume < RULES['exact']['blue_volume_min']:
            out['mechanical_status'] = 'principle_eliminate_volume'
        elif kd > RULES['exact']['observe_kd_max_inclusive']:
            out['mechanical_status'] = 'principle_eliminate_kd'
        else:
            out['mechanical_status'] = out['kd_band']
    else:
        out['mechanical_status'] = final_status(row, volume, kd, kgr, weak_points, errors)
    return out


def annotate_duplicates(rows):
    keys = [collapse_keyword(r.get('keyword', '')).lower() for r in rows]
    counts = Counter(k for k in keys if k)
    for row, key in zip(rows, keys):
        count = counts.get(key, 1) if key else 1
        row['duplicate_count'] = count
        row['duplicate_warning'] = count > 1
    return rows


def summary(rows):
    counts = {}
    for r in rows:
        key = r.get('mechanical_status', 'unknown')
        counts[key] = counts.get(key, 0) + 1
    return {
        'count': len(rows),
        'status_counts': counts,
        'duplicate_rows': sum(1 for r in rows if r.get('duplicate_warning')),
        'invalid_rows': sum(1 for r in rows if r.get('mechanical_status') == 'invalid_row'),
        'provenance_incomplete_rows': sum(1 for r in rows if r.get('provenance_status') != 'verified'),
    }


def write_csv(rows):
    if not rows:
        return ''
    preferred = [
        'keyword','domain','root','parent_seed','volume','difficulty','cpc','metric_source','metric_database',
        'observed_at','metric_stage','provenance_status','intitle_results','serp_weak_evidence','serp_weak_points',
        'serp_evidence_errors','duplicate_count','duplicate_warning','validation_errors','row_valid','recall_pool',
        'exact_pool','kd_band','cpc_signal','kgr','kgr_signal','kdroi','mechanical_status','exclude_reason'
    ]
    keys = []
    seen = set()
    for k in preferred + [k for r in rows for k in r.keys()]:
        if k not in seen:
            seen.add(k); keys.append(k)
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=keys, extrasaction='ignore')
    w.writeheader()
    for row in rows:
        serial = {}
        for key, value in row.items():
            if isinstance(value, (list, dict)):
                serial[key] = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
            else:
                serial[key] = value
        w.writerow(serial)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description='Mechanically evaluate SEO keyword candidate rows without inventing metrics.')
    ap.add_argument('--input', required=True)
    ap.add_argument('--stage', choices=['ideas','exact','final'], default='final')
    ap.add_argument('--format', choices=['json','csv'], default='json')
    args = ap.parse_args()

    raw_rows, batch_meta = load_input(args.input)
    rows = annotate_duplicates([
        normalize(row, args.stage, batch_meta)
        for row in raw_rows
    ])
    if args.format == 'csv':
        print(write_csv(rows), end='')
    else:
        print(json.dumps({'stage': args.stage, 'summary': summary(rows), 'rows': rows}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
