import csv
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SCRIPT = BASE / 'scripts' / 'evaluate_candidates.py'


def run_eval(tmp_path, rows, stage='final'):
    path = tmp_path / 'input.csv'
    fields = sorted({k for r in rows for k in r})
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
    p = subprocess.run(
        [sys.executable, str(SCRIPT), '--input', str(path), '--stage', stage, '--format', 'json'],
        capture_output=True, text=True, check=True,
    )
    return json.loads(p.stdout)


def by_keyword(data):
    return {r['keyword']: r for r in data['rows']}


def test_skill_structure_and_no_root_library_duplication():
    assert (BASE / 'SKILL.md').exists()
    assert (BASE / 'references' / 'selection-sop.md').exists()
    assert (BASE / 'references' / 'data-contracts.md').exists()
    assert (BASE / 'references' / 'decision-rules.md').exists()
    assert not (BASE / 'references' / 'root-library.csv').exists()


def test_skill_description_is_trigger_focused_and_compact():
    lines = (BASE / 'SKILL.md').read_text(encoding='utf-8').splitlines()
    desc = next(line.split(':', 1)[1].strip() for line in lines if line.startswith('description:'))
    assert desc.startswith('Use when ')
    assert len(desc) < 500


def test_trigger_eval_fixture_has_positive_and_negative_cases():
    data = json.loads((BASE / 'tests' / 'trigger-evals.json').read_text(encoding='utf-8'))
    assert len(data['should_trigger']) >= 6
    assert len(data['should_not_trigger']) >= 6


def test_ideas_recall_is_wider_than_exact_thresholds(tmp_path):
    rows = [
        {'keyword':'main-edge','volume':6000,'difficulty':50},
        {'keyword':'blue-edge','volume':400,'difficulty':44},
        {'keyword':'too-small','volume':200,'difficulty':20},
        {'keyword':'too-hard','volume':6000,'difficulty':56},
    ]
    d = by_keyword(run_eval(tmp_path, rows, 'ideas'))
    assert d['main-edge']['recall_pool'] == 'main_recall'
    assert d['blue-edge']['recall_pool'] == 'blue_recall'
    assert d['too-small']['recall_pool'] == 'excluded_recall'
    assert d['too-hard']['recall_pool'] == 'excluded_recall'


def test_exact_pool_and_kd_bands(tmp_path):
    rows = [
        {'keyword':'main-do','volume':9500,'difficulty':35,'cpc':0.2},
        {'keyword':'blue-do','volume':3000,'difficulty':20,'cpc':0.2},
        {'keyword':'below','volume':400,'difficulty':20,'cpc':1.0},
        {'keyword':'observe','volume':10000,'difficulty':45,'cpc':1.0},
        {'keyword':'hard','volume':10000,'difficulty':51,'cpc':1.0},
    ]
    d = by_keyword(run_eval(tmp_path, rows, 'exact'))
    assert d['main-do']['exact_pool'] == 'main'
    assert d['main-do']['kd_band'] == 'do_candidate'
    assert d['blue-do']['exact_pool'] == 'blue_ocean'
    assert d['below']['exact_pool'] == 'below_floor'
    assert d['observe']['kd_band'] == 'observe'
    assert d['hard']['kd_band'] == 'principle_eliminate'


def test_unknown_is_not_coerced_to_zero(tmp_path):
    rows = [{'keyword':'unknown','volume':'','difficulty':'','cpc':''}]
    r = by_keyword(run_eval(tmp_path, rows, 'final'))['unknown']
    assert r['volume'] is None
    assert r['difficulty'] is None
    assert r['cpc'] is None
    assert r['kgr'] is None
    assert r['kdroi'] is None
    assert r['mechanical_status'] == 'pending_metrics'


def test_kgr_formula_and_blue_ocean_signal(tmp_path):
    rows = [{'keyword':'k','volume':10000,'difficulty':20,'cpc':1,'intitle_results':1000}]
    r = by_keyword(run_eval(tmp_path, rows, 'final'))['k']
    assert r['kgr'] == 0.1
    assert r['kgr_signal'] == 'pass_lt_0_25'
    assert r['mechanical_status'] == 'do_candidate'


def test_kgr_not_blue_ocean_does_not_become_do(tmp_path):
    rows = [{'keyword':'k','volume':10000,'difficulty':20,'cpc':1,'intitle_results':3000}]
    r = by_keyword(run_eval(tmp_path, rows, 'final'))['k']
    assert r['kgr'] == 0.3
    assert r['mechanical_status'] == 'observe_kgr'


def test_kd_40_50_requires_two_serp_weak_points_to_upgrade(tmp_path):
    one_evidence = json.dumps([
        {'rank':4,'url':'https://example.com/a','weakness_type':'low_dr_site','observed_fact':'DR 18'},
    ])
    two_evidence = json.dumps([
        {'rank':4,'url':'https://example.com/a','weakness_type':'low_dr_site','observed_fact':'DR 18'},
        {'rank':8,'url':'https://example.com/b','weakness_type':'intent_mismatch','observed_fact':'No requested calculator'},
    ])
    rows = [
        {'keyword':'one','volume':10000,'difficulty':45,'cpc':1,'intitle_results':1000,'serp_weak_evidence':one_evidence},
        {'keyword':'two','volume':10000,'difficulty':45,'cpc':1,'intitle_results':1000,'serp_weak_evidence':two_evidence},
    ]
    d = by_keyword(run_eval(tmp_path, rows, 'final'))
    assert d['one']['mechanical_status'] == 'observe_serp'
    assert d['two']['mechanical_status'] == 'do_candidate'


def test_low_cpc_is_signal_not_hard_elimination(tmp_path):
    rows = [{'keyword':'low-cpc','volume':10000,'difficulty':20,'cpc':0.03,'intitle_results':1000}]
    r = by_keyword(run_eval(tmp_path, rows, 'final'))['low-cpc']
    assert r['cpc_signal'] == 'low_lt_0_10'
    assert r['mechanical_status'] == 'do_candidate'


def test_kdroi_requires_positive_kd_and_cpc_present(tmp_path):
    rows = [
        {'keyword':'normal','volume':12100,'difficulty':15,'cpc':2.38,'intitle_results':100},
        {'keyword':'zero-kd','volume':10000,'difficulty':0,'cpc':2,'intitle_results':100},
        {'keyword':'missing-cpc','volume':10000,'difficulty':20,'cpc':'','intitle_results':100},
    ]
    d = by_keyword(run_eval(tmp_path, rows, 'final'))
    assert round(d['normal']['kdroi'], 4) == round(12100*2.38/15, 4)
    assert d['zero-kd']['kdroi'] is None
    assert d['missing-cpc']['kdroi'] is None


def test_manual_exclusion_overrides_mechanical_scoring(tmp_path):
    rows = [{'keyword':'brand','volume':50000,'difficulty':10,'cpc':5,'intitle_results':10,'exclude_reason':'brand navigation'}]
    r = by_keyword(run_eval(tmp_path, rows, 'final'))['brand']
    assert r['mechanical_status'] == 'excluded_manual'


def test_locked_thresholds_are_machine_readable_single_source():
    rules = json.loads((BASE / 'references' / 'thresholds.json').read_text(encoding='utf-8'))
    assert rules['ideas']['main_volume_min'] == 5000
    assert rules['ideas']['main_kd_max_inclusive'] == 55
    assert rules['ideas']['blue_volume_min'] == 300
    assert rules['ideas']['blue_kd_max_exclusive'] == 45
    assert rules['exact']['main_volume_min'] == 9000
    assert rules['exact']['blue_volume_min'] == 500
    assert rules['exact']['do_kd_max_exclusive'] == 40
    assert rules['exact']['observe_kd_max_inclusive'] == 50
    assert rules['cpc_positive_min'] == 0.10
    assert rules['kgr_pass_max_exclusive'] == 0.25
    assert rules['serp_upgrade_weak_points_min'] == 2
    assert rules['calibration_batches'] == 2


def test_skill_main_file_stays_under_500_words():
    text = (BASE / 'SKILL.md').read_text(encoding='utf-8')
    body = text.split('---', 2)[-1]
    assert len(body.split()) < 500


def test_evaluator_accepts_semrush_keywords_wrapper(tmp_path):
    p = tmp_path / 'ideas.json'
    p.write_text(json.dumps({'keywords':[{'keyword':'x','volume':6000,'difficulty':30}]}), encoding='utf-8')
    proc = subprocess.run([sys.executable, str(SCRIPT), '--input', str(p), '--stage', 'ideas', '--format', 'json'], capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout)
    assert data['rows'][0]['recall_pool'] == 'main_recall'


def test_evaluator_accepts_semrush_rows_wrapper(tmp_path):
    p = tmp_path / 'exact.json'
    p.write_text(json.dumps({'rows':[{'keyword':'x','volume':10000,'difficulty':30,'cpc':1}]}), encoding='utf-8')
    proc = subprocess.run([sys.executable, str(SCRIPT), '--input', str(p), '--stage', 'exact', '--format', 'json'], capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout)
    assert data['rows'][0]['exact_pool'] == 'main'


def test_invalid_numeric_ranges_are_rejected_not_scored(tmp_path):
    rows = [
        {'keyword':'negative-intitle','volume':10000,'difficulty':20,'cpc':1,'intitle_results':-1},
        {'keyword':'negative-kd','volume':10000,'difficulty':-5,'cpc':1,'intitle_results':100},
        {'keyword':'too-high-kd','volume':10000,'difficulty':101,'cpc':1,'intitle_results':100},
        {'keyword':'negative-volume','volume':-1,'difficulty':20,'cpc':1,'intitle_results':1},
        {'keyword':'negative-cpc','volume':10000,'difficulty':20,'cpc':-0.1,'intitle_results':100},
        {'keyword':'too-many-weak','volume':10000,'difficulty':45,'cpc':1,'intitle_results':100,'serp_weak_points':11},
    ]
    d = by_keyword(run_eval(tmp_path, rows, 'final'))
    for name in [r['keyword'] for r in rows]:
        assert d[name]['mechanical_status'] == 'invalid_row'
        assert d[name]['validation_errors']
        assert d[name]['kgr'] is None or name not in ('negative-intitle','negative-volume')


def test_nan_and_infinity_are_invalid(tmp_path):
    rows = [
        {'keyword':'nan','volume':'NaN','difficulty':20,'cpc':1,'intitle_results':100},
        {'keyword':'inf','volume':'Infinity','difficulty':20,'cpc':1,'intitle_results':100},
    ]
    d = by_keyword(run_eval(tmp_path, rows, 'final'))
    assert d['nan']['mechanical_status'] == 'invalid_row'
    assert d['inf']['mechanical_status'] == 'invalid_row'


def test_empty_keyword_is_invalid_row(tmp_path):
    rows = [{'keyword':'','volume':10000,'difficulty':20,'cpc':1,'intitle_results':100}]
    data = run_eval(tmp_path, rows, 'final')
    r = data['rows'][0]
    assert r['mechanical_status'] == 'invalid_row'
    assert 'keyword' in r['validation_errors']


def test_serp_upgrade_requires_structured_documented_evidence(tmp_path):
    valid_evidence = json.dumps([
        {'rank':4,'url':'https://example.com/a','weakness_type':'low_dr_site','observed_fact':'DR 18'},
        {'rank':8,'url':'https://example.com/b','weakness_type':'intent_mismatch','observed_fact':'No requested calculator'},
    ])
    rows = [
        {'keyword':'count-only','volume':10000,'difficulty':45,'cpc':1,'intitle_results':1000,'serp_weak_points':2},
        {'keyword':'documented','volume':10000,'difficulty':45,'cpc':1,'intitle_results':1000,'serp_weak_evidence':valid_evidence},
    ]
    d = by_keyword(run_eval(tmp_path, rows, 'final'))
    assert d['count-only']['mechanical_status'] != 'do_candidate'
    assert d['count-only']['serp_weak_points'] is None
    assert d['documented']['serp_weak_points'] == 2
    assert d['documented']['mechanical_status'] == 'do_candidate'


def test_invalid_serp_evidence_does_not_count(tmp_path):
    evidence = json.dumps([
        {'rank':0,'url':'https://example.com/a','weakness_type':'low_dr_site','observed_fact':'DR 18'},
        {'rank':4,'url':'','weakness_type':'intent_mismatch','observed_fact':'Mismatch'},
        {'rank':5,'url':'https://example.com/c','weakness_type':'','observed_fact':'Mismatch'},
        {'rank':6,'url':'https://example.com/d','weakness_type':'intent_mismatch','observed_fact':''},
        {'rank':7,'url':'https://example.com/e','weakness_type':'intent_mismatch','observed_fact':'Mismatch'},
    ])
    rows = [{'keyword':'partial','volume':10000,'difficulty':45,'cpc':1,'intitle_results':1000,'serp_weak_evidence':evidence}]
    r = by_keyword(run_eval(tmp_path, rows, 'final'))['partial']
    assert r['serp_weak_points'] == 1
    assert r['mechanical_status'] == 'observe_serp'


def test_provenance_status_is_explicit_and_does_not_block_math(tmp_path):
    rows = [
        {'keyword':'incomplete','volume':10000,'difficulty':20,'cpc':1,'intitle_results':1000},
        {'keyword':'metadata-only','volume':10000,'difficulty':20,'cpc':1,'intitle_results':1000,
         'metric_source':'Semrush','metric_database':'us','observed_at':'2026-08-22T07:59:51Z','metric_stage':'exact'},
    ]
    d = by_keyword(run_eval(tmp_path, rows, 'final'))
    assert d['incomplete']['provenance_status'] == 'incomplete'
    assert d['incomplete']['kgr'] == 0.1
    assert d['metadata-only']['provenance_status'] == 'unverified'


def test_duplicate_keywords_are_preserved_and_flagged(tmp_path):
    rows = [
        {'keyword':'Same Keyword','volume':10000,'difficulty':20},
        {'keyword':' same   keyword ','volume':9000,'difficulty':21},
        {'keyword':'other','volume':5000,'difficulty':20},
    ]
    data = run_eval(tmp_path, rows, 'exact')
    assert len(data['rows']) == 3
    same_rows = [r for r in data['rows'] if r['keyword'].lower().strip().replace('  ',' ') == 'same keyword']
    assert len(same_rows) == 2
    assert all(r['duplicate_count'] == 2 for r in same_rows)
    assert all(r['duplicate_warning'] is True for r in same_rows)
    other = next(r for r in data['rows'] if r['keyword'] == 'other')
    assert other['duplicate_count'] == 1
    assert other['duplicate_warning'] is False


def test_top_level_batch_metadata_can_fill_provenance(tmp_path):
    p = tmp_path / 'batch.json'
    p.write_text(json.dumps({
        'generated_at':'2026-08-22T07:59:51Z',
        'database':'us',
        'metric_source':'Semrush',
        'metric_stage':'exact',
        'rows':[{'keyword':'x','volume':10000,'difficulty':20,'cpc':1}]
    }), encoding='utf-8')
    proc = subprocess.run([sys.executable, str(SCRIPT), '--input', str(p), '--stage', 'exact', '--format', 'json'], capture_output=True, text=True, check=True)
    r = json.loads(proc.stdout)['rows'][0]
    assert r['metric_database'] == 'us'
    assert r['observed_at'] == '2026-08-22T07:59:51Z'
    assert r['metric_source'] == 'Semrush'
    assert r['metric_stage'] == 'exact'
    assert r['provenance_status'] == 'unverified'


def test_csv_output_serializes_structured_evidence_as_json(tmp_path):
    evidence = [
        {'rank':3,'url':'https://example.com/a','weakness_type':'low_dr_site','observed_fact':'DR 12'}
    ]
    p = tmp_path / 'input.json'
    p.write_text(json.dumps([{'keyword':'x','volume':10000,'difficulty':45,'cpc':1,'intitle_results':1000,'serp_weak_evidence':evidence}]), encoding='utf-8')
    proc = subprocess.run([sys.executable, str(SCRIPT), '--input', str(p), '--stage', 'final', '--format', 'csv'], capture_output=True, text=True, check=True)
    rows = list(csv.DictReader(proc.stdout.splitlines()))
    parsed = json.loads(rows[0]['serp_weak_evidence'])
    assert parsed[0]['rank'] == 3