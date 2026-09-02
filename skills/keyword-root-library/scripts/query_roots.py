#!/usr/bin/env python3
"""Query root-library.csv with deterministic relevance ordering."""
import argparse, csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "references" / "root-library.csv"
STATUS_RANK={'verified':0,'active':1,'candidate':2,'deprecated':3}
EVIDENCE_RANK={'L3':0,'L2':1,'L1':2,'L0':3}

def norm(s): return (s or "").strip().lower()
def domains(r): return {norm(x) for x in r['applicable_domains'].split(';') if norm(x)}

def domain_tier(r, domain):
    """Lower is better: domain-specific match, explicit universal match, then universal-all."""
    if not domain: return 0
    d=norm(domain); ds=domains(r)
    if d in ds and r['scope']=='domain': return 0
    if d in ds: return 1
    if 'all' in ds and r['scope']=='universal': return 2
    return 99

def lifecycle_bucket(r):
    return 0 if r['status'] in {'verified','active'} else (1 if r['status']=='candidate' else 2)

def read_rows():
    with ROOT.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))

def overview():
    """Human-readable inventory: which industries the library already covers.

    Answers 'what do I actually have?' without requiring filter arguments, so a
    non-technical operator can see coverage before starting a research batch.
    """
    rows=read_rows()
    dom=[r for r in rows if r['scope']=='domain']
    uni=[r for r in rows if r['scope']=='universal']
    counts={}
    for r in dom:
        for d in domains(r):
            if d and d!='all': counts[d]=counts.get(d,0)+1
    print(f"词根库共 {len(rows)} 条：领域词根 {len(dom)} 条，通用词根 {len(uni)} 条\n")
    print(f"=== 已覆盖 {len(counts)} 个行业（领域词根）===")
    print(f"{'行业':<18}{'词根数':>6}   示例词根")
    print("-"*72)
    for d,n in sorted(counts.items(), key=lambda kv:(-kv[1],kv[0])):
        ex=[r['root'] for r in sorted(dom,key=lifecycle_bucket) if d in domains(r)][:3]
        print(f"{d:<18}{n:>6}   {', '.join(ex)}")
    cat={}
    for r in uni: cat[r['demand_category']]=cat.get(r['demand_category'],0)+1
    print(f"\n=== 通用词根 {len(uni)} 条（可套到任何行业）===")
    print(f"{'需求类型':<16}{'词根数':>6}   示例词根")
    print("-"*72)
    for c,n in sorted(cat.items(), key=lambda kv:(-kv[1],kv[0])):
        ex=[r['root'] for r in sorted(uni,key=lifecycle_bucket) if r['demand_category']==c][:3]
        print(f"{c:<16}{n:>6}   {', '.join(ex)}")
    print("\n看某个行业的全部词根： --domain <行业名> --format tsv")

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--overview', action='store_true', help='列出库里已覆盖的行业与通用词根，无需其他参数')
    p.add_argument('--domain')
    p.add_argument('--category')
    p.add_argument('--status')
    p.add_argument('--scope', choices=['universal','domain'])
    p.add_argument('--text')
    p.add_argument('--evidence', choices=['L0','L1','L2','L3'])
    p.add_argument('--limit', type=int, default=50)
    p.add_argument('--format', choices=['json','tsv'], default='json')
    a=p.parse_args()
    if a.overview:
        overview(); return
    if a.limit < 1: p.error('--limit must be >= 1')

    out=[]
    with ROOT.open(encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            tier=domain_tier(r,a.domain)
            if a.domain and tier==99: continue
            if a.category and norm(r['demand_category']) != norm(a.category): continue
            if a.status and norm(r['status']) != norm(a.status): continue
            if a.scope and r['scope'] != a.scope: continue
            if a.evidence and r['evidence_level'] != a.evidence: continue
            if a.text:
                hay=' '.join(str(v) for v in r.values()).lower()
                if norm(a.text) not in hay: continue
            r=dict(r)
            r['_match_group'] = {0:'domain_specific',1:'explicit_universal',2:'universal_all'}.get(tier,'general')
            out.append(r)

    out.sort(key=lambda r:(
        lifecycle_bucket(r),
        domain_tier(r,a.domain),
        STATUS_RANK.get(r['status'],9),
        EVIDENCE_RANK.get(r['evidence_level'],9),
        r['root']
    ))
    out=out[:a.limit]

    if a.format=='json':
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        fields=['root','canonical_pattern','scope','demand_category','primary_intent','status','evidence_level','applicable_domains','_match_group']
        print('\t'.join(fields))
        for r in out: print('\t'.join(r.get(x,'') for x in fields))

if __name__=='__main__': main()
