import csv
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CSV = BASE / 'references' / 'root-library.csv'
QUERY = BASE / 'scripts' / 'query_roots.py'
VALIDATE = BASE / 'scripts' / 'validate_root_library.py'


def rows():
    with CSV.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def run_query(*args):
    p = subprocess.run([sys.executable, str(QUERY), *args], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def test_domain_query_prioritizes_domain_specific_roots():
    data = run_query('--domain', 'pet', '--limit', '50')
    roots = [r['root'] for r in data]
    assert 'puppy weight calculator' in roots
    assert 'dog food calculator' in roots
    assert roots.index('puppy weight calculator') < 20


def test_domain_query_keeps_relevant_universal_roots_after_domain_roots():
    data = run_query('--domain', 'travel', '--limit', '50')
    roots = [r['root'] for r in data]
    assert 'travel itinerary' in roots
    assert 'trip planner' in roots
    assert 'best time to visit' in roots



def test_domain_query_does_not_rank_unverified_candidates_above_usable_roots():
    data = run_query('--domain', 'travel', '--limit', '100')
    usable_indexes = [i for i,r in enumerate(data) if r['status'] in {'active','verified'}]
    candidate_indexes = [i for i,r in enumerate(data) if r['status'] == 'candidate']
    assert usable_indexes and candidate_indexes
    assert max(usable_indexes) < min(candidate_indexes)

def test_verified_requires_real_evidence_level_l2_or_higher():
    bad = [(r['root'], r['evidence_level']) for r in rows() if r['status'] == 'verified' and r['evidence_level'] not in {'L2','L3'}]
    assert bad == []


def test_active_and_verified_have_natural_examples():
    bad = [r['root'] for r in rows() if r['status'] in {'active','verified'} and not r['example_keywords'].strip()]
    assert bad == []


def test_evidence_ref_field_exists_and_is_populated_for_l1_plus():
    rs = rows()
    assert 'evidence_ref' in rs[0]
    bad = [r['root'] for r in rs if r['evidence_level'] in {'L1','L2','L3'} and not r['evidence_ref'].strip()]
    assert bad == []


def test_no_alias_collides_with_another_canonical_root():
    rs = rows()
    roots_by_name = {r['root'].strip().lower(): r['root_id'] for r in rs}
    bad=[]
    for r in rs:
        for alias in [x.strip().lower() for x in r['aliases'].split(';') if x.strip()]:
            if alias in roots_by_name and alias != r['root'].strip().lower():
                bad.append((r['root'], alias))
    assert bad == []


def test_gefei_source_uses_live_mirror_and_preserves_original_source():
    gefei = [r for r in rows() if 'Gefei 51 tool roots' in r['source_name']]
    assert len(gefei) == 51
    for r in gefei:
        assert 'wangmingchang.com' in r['source_url']
        assert 'mp.weixin.qq.com' in r['source_url']
        assert 'alxgo.com/20663.html' not in r['source_url']


def test_validator_passes_current_library():
    p = subprocess.run([sys.executable, str(VALIDATE)], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr


def test_trigger_eval_fixture_exists_with_positive_and_negative_cases():
    path = BASE / 'tests' / 'trigger-evals.json'
    assert path.exists()
    data = json.loads(path.read_text(encoding='utf-8'))
    assert len(data.get('should_trigger', [])) >= 5
    assert len(data.get('should_not_trigger', [])) >= 5


def run_validator_on(path):
    return subprocess.run([sys.executable, str(VALIDATE), '--file', str(path)], capture_output=True, text=True)


def test_validator_rejects_alias_collision(tmp_path):
    rs = rows()
    rs[0]['aliases'] = rs[1]['root']
    out = tmp_path / 'bad.csv'
    with out.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rs[0].keys())
        w.writeheader(); w.writerows(rs)
    p = run_validator_on(out)
    assert p.returncode != 0
    assert 'alias' in (p.stdout + p.stderr).lower()


def test_validator_rejects_verified_l1(tmp_path):
    rs = rows()
    target = next(r for r in rs if r['status'] == 'verified')
    target['evidence_level'] = 'L1'
    out = tmp_path / 'bad.csv'
    with out.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rs[0].keys())
        w.writeheader(); w.writerows(rs)
    p = run_validator_on(out)
    assert p.returncode != 0
    assert 'verified' in (p.stdout + p.stderr).lower()


def test_validator_rejects_unknown_root_type(tmp_path):
    rs = rows(); rs[0]['root_type'] = 'made_up_type'
    out = tmp_path / 'bad.csv'
    with out.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rs[0].keys())
        w.writeheader(); w.writerows(rs)
    p = run_validator_on(out)
    assert p.returncode != 0
    assert 'root_type' in (p.stdout + p.stderr).lower()


def test_skill_description_is_trigger_focused_and_compact():
    skill = (BASE / 'SKILL.md').read_text(encoding='utf-8').splitlines()
    desc = next(line.split(':',1)[1].strip() for line in skill if line.startswith('description:'))
    assert desc.startswith('Use when ')
    assert len(desc) < 500


def test_validator_rejects_missing_local_evidence_ref(tmp_path):
    rs = rows()
    target = next(r for r in rs if r['evidence_level'] == 'L2')
    target['evidence_ref'] = 'references/evidence/does-not-exist.md#missing'
    out = tmp_path / 'bad.csv'
    with out.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rs[0].keys())
        w.writeheader(); w.writerows(rs)
    p = run_validator_on(out)
    assert p.returncode != 0
    assert 'evidence_ref' in (p.stdout + p.stderr).lower()

AUDIT = BASE / 'scripts' / 'audit_coverage.py'
MINE = BASE / 'scripts' / 'mine_root_candidates.py'


def test_coverage_audit_reports_bootstrap_balance():
    p = subprocess.run([sys.executable, str(AUDIT), '--format', 'json'], capture_output=True, text=True, check=True)
    data = json.loads(p.stdout)
    assert data['summary']['total_roots'] == len(rows())
    assert data['summary']['usable_roots'] == sum(r['status'] in {'active','verified'} for r in rows())
    assert data['summary']['verified_roots'] == sum(r['status'] == 'verified' for r in rows())
    assert 'weak_demand_categories' in data
    assert 'weak_domains' in data


def test_candidate_miner_excludes_existing_roots_and_does_not_mutate_library(tmp_path):
    library = tmp_path / 'roots.csv'
    fieldnames = rows()[0].keys()
    with library.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        base = rows()[0].copy()
        base.update({
            'root_id':'root-best-time-to-visit', 'root':'best time to visit', 'canonical_pattern':'best time to visit x',
            'aliases':'', 'scope':'universal', 'root_type':'decision_pattern', 'demand_category':'time',
            'primary_intent':'informational', 'applicable_domains':'travel', 'example_keywords':'best time to visit japan;best time to visit bali',
            'status':'active', 'evidence_level':'L1', 'validation_basis':'fixture', 'evidence_ref':'https://example.com',
            'source_name':'fixture', 'source_url':'https://example.com', 'added_at':'2026-08-22', 'last_verified_at':'', 'notes':''
        })
        w.writerow(base)
    before = library.read_bytes()
    batch = {
        'keywords': [
            {'keyword':'best time to visit japan','group':'travel','source_seed':'best time to visit'},
            {'keyword':'best time to visit bali','group':'travel','source_seed':'best time to visit'},
            {'keyword':'printer error code 123','group':'support','source_seed':'printer troubleshooting'},
            {'keyword':'printer error code 456','group':'support','source_seed':'printer troubleshooting'},
            {'keyword':'canon error code 789','group':'support','source_seed':'camera troubleshooting'},
        ]
    }
    inp = tmp_path / 'batch.json'; inp.write_text(json.dumps(batch), encoding='utf-8')
    p = subprocess.run([sys.executable, str(MINE), '--input', str(inp), '--library', str(library), '--min-count', '2', '--min-tokens', '2', '--limit', '20'], capture_output=True, text=True, check=True)
    data = json.loads(p.stdout)
    candidates = [x['candidate'] for x in data]
    assert 'best time to visit' not in candidates
    assert 'error code' in candidates
    assert before == library.read_bytes()


def test_candidate_miner_reports_supporting_evidence(tmp_path):
    batch = {
        'keywords': [
            {'keyword':'printer error code 123','group':'support','source_seed':'printer troubleshooting'},
            {'keyword':'printer error code 456','group':'support','source_seed':'printer troubleshooting'},
            {'keyword':'camera error code 10','group':'support','source_seed':'camera troubleshooting'},
            {'keyword':'router error code 20','group':'support','source_seed':'router troubleshooting'},
        ]
    }
    inp = tmp_path / 'batch.json'; inp.write_text(json.dumps(batch), encoding='utf-8')
    p = subprocess.run([sys.executable, str(MINE), '--input', str(inp), '--min-count', '3', '--min-tokens', '2', '--limit', '10'], capture_output=True, text=True, check=True)
    data = json.loads(p.stdout)
    row = next(x for x in data if x['candidate'] == 'error code')
    assert row['keyword_count'] == 4
    assert row['distinct_groups'] == 1
    assert row['distinct_source_seeds'] == 3
    assert len(row['examples']) >= 3


def test_candidate_miner_marks_fragments_of_existing_roots(tmp_path):
    batch = {'keywords': [
        {'keyword':'best time to visit japan','group':'travel','source_seed':'best time to visit'},
        {'keyword':'best time to visit bali','group':'travel','source_seed':'best time to visit'},
        {'keyword':'best time to visit italy','group':'travel','source_seed':'best time to visit'},
    ]}
    inp = tmp_path / 'batch.json'; inp.write_text(json.dumps(batch), encoding='utf-8')
    p = subprocess.run([sys.executable, str(MINE), '--input', str(inp), '--min-count', '2', '--min-tokens', '2', '--limit', '20'], capture_output=True, text=True, check=True)
    data = json.loads(p.stdout)
    frag = next(x for x in data if x['candidate'] == 'best time')
    assert frag['overlap_type'] == 'fragment_of_existing'
    assert 'best time to visit' in frag['overlap_roots']


def test_skill_documents_coverage_and_feedback_scripts():
    text = (BASE / 'SKILL.md').read_text(encoding='utf-8')
    assert 'audit_coverage.py' in text
    assert 'mine_root_candidates.py' in text
    assert 'never auto' in text.lower() or 'never mutate' in text.lower()


def test_real_batch_feedback_promotes_supported_roots():
    by_root = {r['root']: r for r in rows()}
    assert by_root['travel budget']['status'] == 'verified'
    assert by_root['travel budget']['evidence_level'] == 'L2'
    assert by_root['bitcoin mining']['status'] == 'verified'
    assert by_root['bitcoin mining']['evidence_level'] == 'L2'
    assert 'itinerary planner' in by_root
    assert by_root['itinerary planner']['status'] == 'verified'
    assert by_root['itinerary planner']['evidence_level'] == 'L2'


def test_coverage_snapshot_exists_and_states_bootstrap_not_complete():
    path = BASE / 'references' / 'root-coverage-2026-08-22.md'
    assert path.exists()
    text = path.read_text(encoding='utf-8').lower()
    assert 'bootstrap' in text
    assert 'not a complete' in text or 'not complete' in text
    assert '307' in text


def test_candidate_miner_marks_source_seed_fragments(tmp_path):
    batch = {'keywords': [
        {'keyword':'elden ring build calculator','group':'gaming','source_seed':'elden ring build calculator'},
        {'keyword':'elden ring best build calculator','group':'gaming','source_seed':'elden ring build calculator'},
        {'keyword':'elden ring weapon build calculator','group':'gaming','source_seed':'elden ring build calculator'},
    ]}
    inp = tmp_path / 'batch.json'; inp.write_text(json.dumps(batch), encoding='utf-8')
    p = subprocess.run([sys.executable, str(MINE), '--input', str(inp), '--min-count', '2', '--min-tokens', '2', '--limit', '20'], capture_output=True, text=True, check=True)
    data = json.loads(p.stdout)
    row = next(x for x in data if x['candidate'] == 'elden ring')
    assert row['seed_overlap_type'] == 'fragment_of_source_seed'


def test_wedding_cross_domain_experiment_promotes_supported_existing_roots():
    by_root = {r['root']: r for r in rows()}
    for root in ['wedding budget','wedding checklist','wedding timeline','guest list','seating chart','wedding vows']:
        assert root in by_root
        assert by_root[root]['status'] == 'verified'
        assert by_root[root]['evidence_level'] == 'L2'
        assert 'wedding-demand-evidence-2026-08-22.md' in by_root[root]['evidence_ref']


def test_wedding_cross_domain_experiment_adds_repeated_demand_roots():
    by_root = {r['root']: r for r in rows()}
    expected = [
        'wedding website', 'wedding registry', 'wedding venue', 'wedding vendor',
        'wedding rsvp', 'wedding invitation wording', 'wedding dress code'
    ]
    for root in expected:
        assert root in by_root
        assert by_root[root]['status'] == 'verified'
        assert by_root[root]['evidence_level'] == 'L2'
        assert 'wedding-demand-evidence-2026-08-22.md' in by_root[root]['evidence_ref']


def test_wedding_evidence_file_exists_and_names_independent_sites():
    path = BASE / 'references' / 'wedding-demand-evidence-2026-08-22.md'
    assert path.exists()
    text = path.read_text(encoding='utf-8').lower()
    assert 'the knot' in text
    assert 'weddingwire' in text
    assert 'zola' in text
    assert 'greenvelope' in text


def test_baking_fermentation_experiment_promotes_existing_supported_roots():
    by_root = {r['root']: r for r in rows()}
    expected = [
        "baker's percentage", 'hydration calculator', 'recipe scaler',
        'pan conversion', 'proofing time', 'substitute', 'recipe'
    ]
    for root in expected:
        assert root in by_root
        assert by_root[root]['status'] == 'verified'
        assert by_root[root]['evidence_level'] == 'L2'
        assert 'baking-fermentation-demand-evidence-2026-08-22.md' in by_root[root]['evidence_ref']


def test_baking_fermentation_experiment_adds_repeated_demand_roots():
    by_root = {r['root']: r for r in rows()}
    expected = [
        'sourdough starter', 'starter feeding ratio', 'bulk fermentation',
        'bulk fermentation calculator', 'fermentation time calculator',
        'fermentation brine calculator', 'fermentation troubleshooting',
        'sourdough schedule'
    ]
    for root in expected:
        assert root in by_root
        assert by_root[root]['status'] == 'verified'
        assert by_root[root]['evidence_level'] == 'L2'
        assert 'baking-fermentation-demand-evidence-2026-08-22.md' in by_root[root]['evidence_ref']


def test_baking_fermentation_evidence_file_exists_and_names_independent_sites():
    path = BASE / 'references' / 'baking-fermentation-demand-evidence-2026-08-22.md'
    assert path.exists()
    text = path.read_text(encoding='utf-8').lower()
    for name in ['king arthur baking', 'the perfect loaf', 'breadtopia', 'cultures for health']:
        assert name in text
