import json, subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
EVAL = BASE / 'scripts' / 'evaluate_mapping.py'
VALIDATE = BASE / 'scripts' / 'validate_mapping.py'


def run(script, tmp_path, payload, *extra):
    p = tmp_path / 'input.json'; p.write_text(json.dumps(payload), encoding='utf-8')
    r = subprocess.run([sys.executable, str(script), '--input', str(p), '--format', 'json', *extra], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def pg(data, pid): return next(x for x in data['pages'] if x['page_id'] == pid)


def core(page_id, keyword, demand, **kw):
    return {'page_id':page_id,'keyword':keyword,'role_candidate':'core','ownership_status':'confirmed','ownership_page_id':page_id,'serp_fast_status':'confirmed','target_scope_demand':demand,'metric_scope_id':'scope',**kw}


def test_structure_description_and_readme():
    for p in ['SKILL.md','references/workflow.md','references/data-contracts.md','references/decision-rules.md','references/demand-scope.md','references/source-acquisition.md','scripts/evaluate_mapping.py','scripts/validate_mapping.py']:
        assert (BASE / p).exists()
    skill=(BASE/'SKILL.md').read_text(encoding='utf-8'); lines=skill.splitlines()
    desc=next(x.split(':',1)[1].strip() for x in lines if x.startswith('description:'))
    assert desc.startswith('Use when ') and len(desc) < 500
    assert len(skill.split('---',2)[-1].split()) < 500
    readme=(BASE.parents[1]/'README.md').read_text(encoding='utf-8')
    assert 'seo-page-keyword-mapping' in readme and 'python3 -m pytest skills/seo-page-keyword-mapping/tests -q' in readme


def test_trigger_fixture_boundaries():
    d=json.loads((BASE/'tests/trigger-evals.json').read_text(encoding='utf-8'))
    assert len(d['should_trigger']) >= 6 and len(d['should_not_trigger']) >= 6


def test_source_seed_never_creates_ownership(tmp_path):
    row={'page_id':'hex-1','keyword':'hexagram 11.1','role_candidate':'core','source_seed':'hexagram 1','ownership_status':'unknown','serp_fast_status':'confirmed','target_scope_demand':200,'metric_scope_id':'scope'}
    d=run(EVAL,tmp_path,{'rows':[row]})
    assert pg(d,'hex-1')['primary_keyword'] is None and d['rows'][0]['eligible_core'] is False


def test_unknown_is_not_zero_and_serp_fast_is_required(tmp_path):
    rows=[core('p','good',None,cluster_include=True), core('p','big-but-unchecked',5000)]
    rows[1]['serp_fast_status']='unknown'
    d=run(EVAL,tmp_path,{'rows':rows}); p=pg(d,'p')
    assert p['primary_keyword']=='good' and p['core_keyword_demand'] is None
    assert p['cluster_observed_demand'] is None and p['cluster_unknown_keyword_count']==1 and p['cluster_demand_complete'] is False


def test_modifier_can_be_primary_after_core_reclassification(tmp_path):
    rows=[{'page_id':'lovers','keyword':'the lovers','role_candidate':'non_target','ownership_status':'rejected','serp_fast_status':'mismatch','target_scope_demand':18000,'metric_scope_id':'scope'}, core('lovers','the lovers tarot meaning',33100,is_modifier=True)]
    assert pg(run(EVAL,tmp_path,{'rows':rows}),'lovers')['primary_keyword']=='the lovers tarot meaning'


def test_cpc_is_not_primary_signal_except_optional_final_tiebreak(tmp_path):
    rows=[core('p','a',1000,target_market_volume=500,cpc=.1),core('p','b',900,target_market_volume=500,cpc=15)]
    assert pg(run(EVAL,tmp_path,{'rows':rows}),'p')['primary_keyword']=='a'
    tied=[core('p','a',1000,target_market_volume=500,cpc=.1),core('p','b',1000,target_market_volume=500,cpc=15)]
    assert pg(run(EVAL,tmp_path,{'rows':tied}),'p')['primary_keyword']=='a'
    assert pg(run(EVAL,tmp_path,{'rows':tied},'--cpc-tiebreak'),'p')['primary_keyword']=='b'


def test_cluster_observed_demand_deduplicates_and_keeps_scope(tmp_path):
    rows=[core('p','hexagram 1',1470,cluster_include=True),
          {'page_id':'p','keyword':'hexagram 1 love','role_candidate':'intent','ownership_status':'confirmed','ownership_page_id':'p','serp_fast_status':'confirmed','target_scope_demand':290,'metric_scope_id':'scope','cluster_include':True},
          {'page_id':'p','keyword':'HEXAGRAM 1 LOVE','role_candidate':'intent','ownership_status':'confirmed','ownership_page_id':'p','serp_fast_status':'confirmed','target_scope_demand':290,'metric_scope_id':'scope','cluster_include':True},
          {'page_id':'p','keyword':'unknown intent','role_candidate':'intent','ownership_status':'confirmed','ownership_page_id':'p','serp_fast_status':'confirmed','target_scope_demand':None,'metric_scope_id':'scope','cluster_include':True},
          {'page_id':'p','keyword':'other scope','role_candidate':'intent','ownership_status':'confirmed','ownership_page_id':'p','serp_fast_status':'confirmed','target_scope_demand':999,'metric_scope_id':'other','cluster_include':True}]
    p=pg(run(EVAL,tmp_path,{'rows':rows}),'p')
    assert p['core_keyword_demand']==1470 and p['cluster_observed_demand']==1760
    assert p['cluster_keyword_count']==3 and p['cluster_unknown_keyword_count']==1 and p['cluster_scope_mismatch_count']==1
    assert p['cluster_demand_complete'] is False


def test_architecture_uses_serp_overlap_task_and_content_not_fixed_volume(tmp_path):
    items=[{'parent_page_id':'h54','child_page_id':'h54-romance','keyword':'romance','serp_overlap':.2,'task_divergence':True,'content_independent':True,'target_scope_demand':260}, {'parent_page_id':'h1','child_page_id':'h1-love','keyword':'love','serp_overlap':.8,'task_divergence':True,'content_independent':True,'target_scope_demand':10000}]
    a={x['child_page_id']:x['recommended_treatment'] for x in run(EVAL,tmp_path,{'rows':[],'architecture_candidates':items})['architecture_candidates']}
    assert a['h54-romance']=='independent_url_candidate' and a['h1-love']=='content_module'


def test_validator_detects_ownership_serp_and_split_conflicts(tmp_path):
    rows=[core('a','same term',100),core('b','SAME TERM',100),core('c','unchecked',100)]
    rows[2]['serp_fast_status']='unknown'
    arch=[{'parent_page_id':'a','child_page_id':'a-child','serp_overlap':.75,'proposed_treatment':'independent_url_candidate'}]
    d=run(VALIDATE,tmp_path,{'rows':rows,'architecture_candidates':arch})
    codes={x['code'] for x in d['issues']}
    assert {'exact_ownership_collision','core_missing_serp_fast','high_overlap_split'} <= codes and d['valid'] is False


def test_docs_encode_nonnegotiable_rules():
    text='\n'.join((BASE/p).read_text(encoding='utf-8') for p in ['SKILL.md','references/workflow.md','references/decision-rules.md','references/demand-scope.md']).lower()
    for term in ['source_seed','page ownership','unknown','zero','cluster observed demand','cpc','tie-break','serp fast','serp deep','cannibal','language','market']:
        assert term in text


def test_cluster_demand_is_unresolved_without_primary_scope(tmp_path):
    rows=[
        {'page_id':'p','keyword':'intent-a','role_candidate':'intent','ownership_status':'confirmed','ownership_page_id':'p','serp_fast_status':'confirmed','target_scope_demand':100,'metric_scope_id':'scope-a','cluster_include':True},
        {'page_id':'p','keyword':'intent-b','role_candidate':'intent','ownership_status':'confirmed','ownership_page_id':'p','serp_fast_status':'confirmed','target_scope_demand':200,'metric_scope_id':'scope-b','cluster_include':True},
    ]
    p=pg(run(EVAL,tmp_path,{'rows':rows}),'p')
    assert p['primary_keyword'] is None
    assert p['cluster_observed_demand'] is None
    assert p['cluster_demand_complete'] is False
    assert p['cluster_scope_mismatch_count']==2


def test_cluster_demand_is_unresolved_when_primary_has_no_metric_scope(tmp_path):
    rows=[
        {'page_id':'p','keyword':'core','role_candidate':'core','ownership_status':'confirmed','ownership_page_id':'p','serp_fast_status':'confirmed','target_scope_demand':100,'metric_scope_id':None,'cluster_include':True},
        {'page_id':'p','keyword':'intent','role_candidate':'intent','ownership_status':'confirmed','ownership_page_id':'p','serp_fast_status':'confirmed','target_scope_demand':200,'metric_scope_id':'scope-b','cluster_include':True},
    ]
    p=pg(run(EVAL,tmp_path,{'rows':rows}),'p')
    assert p['primary_keyword']=='core'
    assert p['cluster_metric_scope_id'] is None
    assert p['cluster_observed_demand'] is None
    assert p['cluster_demand_complete'] is False
    assert p['cluster_scope_mismatch_count']==2
