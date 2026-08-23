import json, subprocess, sys
from pathlib import Path
import pytest

BASE=Path(__file__).resolve().parents[1]
VALIDATE=BASE/'scripts'/'validate_observations.py'
AGGREGATE=BASE/'scripts'/'aggregate_signals.py'
CLASSIFY=BASE/'scripts'/'classify_emergence.py'
ROUTE=BASE/'scripts'/'route_candidates.py'

def run(script,tmp,payload,*args):
    p=tmp/'input.json'; p.write_text(json.dumps(payload),encoding='utf-8')
    r=subprocess.run([sys.executable,str(script),'--input',str(p),'--format','json',*args],capture_output=True,text=True,check=True)
    return json.loads(r.stdout)

def obs(**kw):
    r={'keyword':'example query','observed_at':'2026-08-20','source':'google_trends','source_type':'trend_index','source_url':'https://trends.google.com/example','root_id':'example','signal_value':20,'signal_unit':'index_0_100','country':'US','time_window':'daily','metric_source':'google_trends','metric_database':'US'}
    r.update(kw); return r

def cand(**kw):
    r={'keyword':'candidate query','root_id':'candidate','first_observed_at':'2026-07-01','estimated_birth_window':None,'age_days':53,'baseline_signal':0.0,'recent_signal':30.0,'growth_rate':None,'growth_status':'from_observed_zero_baseline','acceleration':None,'persistence':1.0,'persistence_observations':4,'source_count':2,'source_evidence':[{'source':'google_trends','provenance_status':'verified'},{'source':'semrush_export','provenance_status':'verified'}],'primary_series':{'source':'google_trends','provenance_status':'verified','baseline_observations':3,'recent_observations':4,'observation_count':7,'peak_signal':30.0,'latest_signal':30.0},'anchor_event':None,'anchor_event_date':None,'anchor_event_source':None,'volume':None,'kd':None,'cpc':None,'intitle_results':None,'metric_status':'incomplete','observed_at':'2026-08-23'}
    r.update(kw); return r

def classify(tmp,row): return run(CLASSIFY,tmp,{'candidates':[row]},'--as-of','2026-08-23')['candidates'][0]
def route(tmp,row): return run(ROUTE,tmp,{'candidates':[row]})['routes'][0]

@pytest.mark.parametrize('field,value',[('signal_value',-1),('volume',-1),('cpc',-0.1),('kd',-1),('kd',101),('signal_value','NaN'),('signal_value','Infinity')])
def test_invalid_numeric_input_is_invalid(tmp_path,field,value):
    x=run(VALIDATE,tmp_path,[obs(**{field:value})],'--as-of','2026-08-23')['rows'][0]
    assert x['validation_status']=='invalid' and x['validation_errors']

def test_empty_keyword_and_bad_dates_are_invalid(tmp_path):
    rows=[obs(keyword=' '),obs(observed_at='2026-99-99'),obs(first_observed_at='2026-08-24')]
    out=run(VALIDATE,tmp_path,rows,'--as-of','2026-08-23')['rows']
    assert all(x['validation_status']=='invalid' for x in out)
    assert 'first_observed_at_future' in out[2]['validation_errors']

def test_unknown_zero_and_provenance_semantics(tmp_path):
    rows=[obs(volume=None,kd=None,cpc=None,intitle_results=None),obs(signal_value=0,volume=0,kd=0,cpc=0,intitle_results=0),obs(source_url=None,country=None)]
    a,z,p=run(VALIDATE,tmp_path,rows,'--as-of','2026-08-23')['rows']
    assert [a[k] for k in ('volume','kd','cpc','intitle_results')]==[None]*4
    assert [z[k] for k in ('signal_value','volume','kd','cpc','intitle_results')]==[0,0,0,0,0]
    assert p['validation_status']=='valid' and p['provenance_status']=='incomplete'
    assert sorted(p['missing_provenance'])==['country','source_url']

def test_missing_signal_unit_makes_provenance_incomplete(tmp_path):
    x=run(VALIDATE,tmp_path,[obs(signal_unit=None)],'--as-of','2026-08-23')['rows'][0]
    assert x['validation_status']=='valid'
    assert x['provenance_status']=='incomplete'
    assert 'signal_unit' in x['missing_provenance']

def test_zero_only_series_is_not_a_new_signal(tmp_path):
    x=classify(tmp_path,cand(baseline_signal=None,recent_signal=0,persistence=0,persistence_observations=1,source_count=1,source_evidence=[{'source':'google_trends','provenance_status':'verified'}],primary_series={'source':'google_trends','provenance_status':'verified','baseline_observations':0,'recent_observations':1,'observation_count':1,'positive_observations':0,'peak_signal':0,'latest_signal':0}))
    assert x['status']=='insufficient_evidence'
    assert x['signal_type'] is None

def test_complete_provenance_and_duplicate_audit(tmp_path):
    r=obs(); out=run(VALIDATE,tmp_path,[r,dict(r)],'--as-of','2026-08-23')['rows']
    assert out[0]['provenance_status']=='verified'
    assert all(x['duplicate_count']==2 and x['duplicate_warning'] for x in out)

def dated(keyword,source,unit,vals,days):
    return [obs(keyword=keyword,source=source,source_url=f'https://example.com/{source}',source_type='mentions' if unit=='mentions' else 'trend_index',signal_unit=unit,signal_value=v,observed_at=f'2026-08-{d:02d}',metric_source=source) for d,v in zip(days,vals)]

def test_aggregate_does_not_sum_incompatible_units(tmp_path):
    rows=dated('mixed','google_trends','index_0_100',[10,20,30],[20,21,22])+dated('mixed','community','mentions',[100,200,300],[20,21,22])
    x=run(AGGREGATE,tmp_path,rows,'--as-of','2026-08-23')['candidates'][0]
    assert len(x['source_evidence'])==2 and x['recent_signal'] in (20.0,200.0) and x['recent_signal']!=220
    assert x['aggregation_policy']=='no_cross_series_addition'

def test_duplicate_and_source_count_do_not_inflate(tmp_path):
    rows=dated('dup','google_trends','index_0_100',[10,20,30],[20,21,22]); rows.append(dict(rows[-1])); rows+=dated('dup','semrush','monthly_volume',[50],[22])
    x=run(AGGREGATE,tmp_path,rows,'--as-of','2026-08-23')['candidates'][0]
    assert x['duplicate_observation_count']==1 and x['source_count']==2
    gt=next(s for s in x['source_evidence'] if s['source']=='google_trends')
    assert gt['observation_count']==3

def test_aggregate_baseline_recent_growth_and_metrics(tmp_path):
    rows=[obs(keyword='g',observed_at=f'2026-08-{d:02d}',signal_value=v) for d,v in [(1,10),(5,10),(10,10),(17,10),(20,30),(21,40),(22,50)]]
    rows[-1].update(volume=120,kd=33,intitle_results=12)
    x=run(AGGREGATE,tmp_path,rows,'--as-of','2026-08-23')['candidates'][0]
    assert x['baseline_signal']==10 and x['recent_signal']==32.5 and x['growth_rate']==2.25
    assert x['first_observed_at']=='2026-08-01' and x['age_days']==22 and x['metric_status']=='incomplete'
    assert x['volume']==120 and x['kd']==33 and x['cpc'] is None

def test_aggregate_evidence_depth_and_decay_fields(tmp_path):
    rows=[obs(keyword='d',observed_at=f'2026-08-{d:02d}',signal_value=v) for d,v in [(1,0),(10,0),(20,100),(21,10),(22,0)]]
    x=run(AGGREGATE,tmp_path,rows,'--as-of','2026-08-23')['candidates'][0]['primary_series']
    assert x['baseline_observations']==2 and x['recent_observations']==3
    assert x['peak_signal']==100 and x['latest_signal']==0

@pytest.mark.parametrize('subtype',['new_expression','typo','modifier_shift'])
def test_emerging_variant_subtypes(tmp_path,subtype):
    x=classify(tmp_path,cand(variant_subtype=subtype,variant_evidence='observed relationship',baseline_signal=5,growth_rate=0.4,growth_status='calculated'))
    assert x['signal_type']=='emerging_variant' and x['variant_subtype']==subtype and x['status']=='emerging'

def test_net_new_is_newly_observed_not_absolute_birth(tmp_path):
    x=classify(tmp_path,cand())
    assert x['signal_type']=='net_new' and x['status']=='emerging' and x['confidence']=='high'
    assert x['estimated_birth_window'] is None and 'newly observed' in x['status_reason'].lower()

def test_breakout_requires_positive_baseline(tmp_path):
    x=classify(tmp_path,cand(baseline_signal=10,recent_signal=30,growth_rate=2,growth_status='calculated',age_days=180,primary_series={'source':'google_trends','provenance_status':'verified','baseline_observations':5,'recent_observations':4,'observation_count':9,'peak_signal':30,'latest_signal':30}))
    assert x['signal_type']=='breakout' and x['status']=='breakout'

def test_one_day_spike_is_new_signal_not_noise(tmp_path):
    x=classify(tmp_path,cand(baseline_signal=None,recent_signal=100,persistence=1,persistence_observations=1,source_count=1,source_evidence=[{'source':'google_trends','provenance_status':'verified'}],primary_series={'source':'google_trends','provenance_status':'verified','baseline_observations':0,'recent_observations':1,'observation_count':1,'peak_signal':100,'latest_signal':100}))
    assert x['status']=='new_signal' and x['signal_type'] is None

def test_spike_decay_can_be_noise_but_durable_event_is_not_forced_noise(tmp_path):
    base=cand(baseline_signal=0,recent_signal=0,persistence=.25,persistence_observations=4,source_count=1,source_evidence=[{'source':'google_trends','provenance_status':'verified'}],primary_series={'source':'google_trends','provenance_status':'verified','baseline_observations':2,'recent_observations':4,'observation_count':6,'peak_signal':100,'latest_signal':0},repeatable_page_or_product_fit=False)
    assert classify(tmp_path,dict(base,durable_search_intent=False))['status']=='noise'
    assert classify(tmp_path,dict(base,durable_search_intent=True))['status']!='noise'

def test_unknown_durability_does_not_become_noise(tmp_path):
    x=classify(tmp_path,cand(baseline_signal=0,recent_signal=0,persistence=.25,persistence_observations=4,source_count=1,source_evidence=[{'source':'google_trends','provenance_status':'verified'}],primary_series={'source':'google_trends','provenance_status':'verified','baseline_observations':2,'recent_observations':4,'observation_count':6,'peak_signal':100,'latest_signal':0},durable_search_intent=None,repeatable_page_or_product_fit=None))
    assert x['status']!='noise'

def test_supply_context_and_emd_are_preserved(tmp_path):
    rows=[obs(keyword='supply',observed_at='2026-08-20',signal_value=10,serp_dedicated_pages=2,serp_ugc_pages=3,serp_intent_mismatch=True,emd_status='available')]
    x=run(AGGREGATE,tmp_path,rows,'--as-of','2026-08-23')['candidates'][0]
    assert x['serp_dedicated_pages']==2 and x['serp_ugc_pages']==3
    assert x['serp_intent_mismatch'] is True and x['emd_status']=='available'

def test_persistence_and_cross_source_raise_confidence(tmp_path):
    one=classify(tmp_path,cand(source_count=1,source_evidence=[{'source':'google_trends','provenance_status':'verified'}]))
    two=classify(tmp_path,cand())
    assert one['status']=='emerging' and one['confidence']=='medium' and two['confidence']=='high'

def test_no_anchor_is_not_a_gate(tmp_path):
    x=classify(tmp_path,cand(anchor_event=None,anchor_event_date=None,anchor_event_source=None))
    assert x['status']=='emerging'

def test_unknown_metrics_and_kgr_boundary(tmp_path):
    x=classify(tmp_path,cand(volume=None,kd=None,cpc=.3,intitle_results=80))
    assert x['volume'] is None and x['kd'] is None and x['metric_status']=='incomplete'
    assert x['kgr'] is None and x['supply_signal']=='low_supply_signal'
    y=classify(tmp_path,cand(volume=1000,kd=20,cpc=.3,intitle_results=100))
    assert y['kgr']==.1 and 'kgr_signal' not in y

def test_mature_and_incomplete_provenance_states(tmp_path):
    mature=classify(tmp_path,cand(age_days=365,baseline_signal=50,recent_signal=55,growth_rate=.1,growth_status='calculated',primary_series={'source':'google_trends','provenance_status':'verified','baseline_observations':8,'recent_observations':4,'observation_count':12,'peak_signal':60,'latest_signal':55}))
    weak=classify(tmp_path,cand(source_count=1,source_evidence=[{'source':'manual','provenance_status':'incomplete'}],primary_series={'source':'manual','provenance_status':'incomplete','baseline_observations':3,'recent_observations':4,'observation_count':7,'peak_signal':30,'latest_signal':30}))
    assert mature['status']=='mature' and mature['signal_type'] is None
    assert weak['status']=='insufficient_evidence'

def test_state_transition_is_explainable(tmp_path):
    x=classify(tmp_path,cand(previous_status='watch'))
    assert x['state_changed'] is True and x['previous_status']=='watch'
    assert x['status_reason'] and x['evidence_used'] and isinstance(x['unknown_fields'],list)

def test_existing_root_routes_only_confirmed_to_selection(tmp_path):
    a=route(tmp_path,cand(status='emerging',signal_type='net_new',root_relation='existing_root'))
    b=route(tmp_path,cand(status='watch',signal_type=None,root_relation='existing_root'))
    assert a['route']=='selection_handoff' and b['route']=='monitor_only'
    assert a['handoff']['metric_status']=='incomplete' and a['mutates_root_library'] is False
    assert 'do_candidate' not in json.dumps(a) and 'principle_eliminate' not in json.dumps(a)

def test_root_candidate_and_unresolved_routes(tmp_path):
    r=route(tmp_path,cand(status='emerging',signal_type='emerging_variant',root_id=None,root_relation='root_candidate',root_candidate_hypothesis='stable agent-memory migration family',related_keywords=['agent memory migration']))
    u=route(tmp_path,cand(status='watch',signal_type=None,root_id=None,root_relation='unresolved'))
    assert r['route']=='root_candidate_handoff' and r['mutates_root_library'] is False
    assert u['route']=='new_root_watchlist'

@pytest.mark.parametrize('status',['mature','noise','insufficient_evidence'])
def test_non_actionable_states_never_route_selection(tmp_path,status):
    x=route(tmp_path,cand(status=status,signal_type=None,root_relation='existing_root'))
    assert x['route']=='no_handoff' and x['handoff'] is None

def test_structure_trigger_fixture_and_threshold_boundaries():
    for p in ['SKILL.md','references/data-contracts.md','references/source-policy.md','references/classification-rules.md','references/state-machine.md','references/routing-rules.md','references/thresholds.json','tests/trigger-evals.json','tests/trigger-eval-status.md']:
        assert (BASE/p).exists()
    assert not (BASE/'references/root-library.csv').exists()
    trig=json.loads((BASE/'tests/trigger-evals.json').read_text())
    assert len(trig['should_trigger'])>=6 and len(trig['should_not_trigger'])>=6
    neg=' '.join(trig['should_not_trigger']).lower(); assert 'kd<40' in neg and 'genealogy' in neg
    th=json.loads((BASE/'references/thresholds.json').read_text())
    assert th['evidence']['min_recent_observations_confirmed']==3
    assert 'main_volume_min' not in json.dumps(th) and 'do_kd_max_exclusive' not in json.dumps(th)

def test_raw_observations_flow_to_net_new_without_birth_invention(tmp_path):
    rows=[obs(keyword='pipeline',observed_at=f'2026-08-{d:02d}',signal_value=v) for d,v in [(1,0),(10,0),(20,10),(21,20),(22,30)]]
    a=run(AGGREGATE,tmp_path,rows,'--as-of','2026-08-23')['candidates'][0]
    x=classify(tmp_path,a)
    assert x['signal_type']=='net_new' and x['status']=='emerging'
    assert x['first_observed_at']=='2026-08-01' and x['estimated_birth_window'] is None

def test_code_never_generates_final_selection_states():
    text='\n'.join(p.read_text() for p in (VALIDATE,AGGREGATE,CLASSIFY,ROUTE))
    assert "'do_candidate'" not in text and '"do_candidate"' not in text
    assert "'principle_eliminate'" not in text and '"principle_eliminate"' not in text
