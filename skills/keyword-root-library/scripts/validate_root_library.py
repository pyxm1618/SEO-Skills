#!/usr/bin/env python3
"""Deterministic integrity checks for the keyword root library."""
import argparse, csv, re
from urllib.parse import urlparse
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "references" / "root-library.csv"
REQUIRED=['root_id','root','canonical_pattern','aliases','scope','root_type','demand_category','primary_intent','applicable_domains','example_keywords','status','evidence_level','validation_basis','evidence_ref','source_name','source_url','added_at','last_verified_at','notes']
STATUSES={'candidate','active','verified','deprecated'}
SCOPES={'universal','domain'}
EVIDENCE={'L0','L1','L2','L3'}
INTENTS={'tool','informational','commercial','resource','interactive','mixed'}
ROOT_TYPES={
'calculation_pattern','candidate_pattern','commercial_pattern','comparison_pattern','content_pattern','decision_pattern','discovery_pattern','domain_pattern','domain_topic','functional_suffix','identity_pattern','informational_pattern','interactive_pattern','knowledge_pattern','learning_pattern','local_pattern','planning_pattern','query_modifier','question_pattern','relationship_pattern','resource_format','resource_pattern','route_pattern','technology_modifier','time_pattern','topic_or_modality'
}
DEMAND_CATEGORIES={
'access','analyze','build','calculate','check','compare','content','convert','create','decide','discover','estimate','evaluate','find','generate','identify','interpret','learn','location','lookup','manage','measure','navigate','organize','other','plan','predict','price','relationship','replace','resource','simulate','technology','time','track','transfer','transform','understand','visualize'
}
DATE=re.compile(r'^\d{4}-\d{2}-\d{2}$')
SLUG_SAFE=re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

def norm(s): return (s or '').strip().lower()
def root_slug(s):
    s=re.sub(r"['’]",'',norm(s))
    return 'root-' + re.sub(r'[^a-z0-9]+','-',s).strip('-')
def fail(msg):
    print('ERROR:', msg)
    return 1

def heading_slug(text):
    s=norm(text)
    s=re.sub(r'[`*_~]', '', s)
    s=re.sub(r'[^a-z0-9\s-]', '', s)
    s=re.sub(r'\s+', '-', s).strip('-')
    return s

def validate_local_evidence_ref(ref, base_dir):
    """Return None if valid, else an error string. URLs are allowed but not network-fetched."""
    ref=ref.strip()
    if not ref or '://' in ref:
        return None
    path_part, sep, anchor = ref.partition('#')
    path=(base_dir / path_part).resolve()
    skill_root=base_dir.resolve()
    try:
        path.relative_to(skill_root)
    except ValueError:
        return f'evidence_ref escapes skill root: {ref!r}'
    if not path.exists() or not path.is_file():
        return f'local evidence_ref file not found: {ref!r}'
    if anchor:
        text=path.read_text(encoding='utf-8')
        headings=[]
        for line in text.splitlines():
            m=re.match(r'^#{1,6}\s+(.+?)\s*$', line)
            if m: headings.append(heading_slug(m.group(1)))
        if anchor not in headings:
            return f'local evidence_ref anchor not found: {ref!r}'
    return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--file', type=Path, default=DEFAULT_ROOT)
    a=ap.parse_args()
    errors=0
    with a.file.open(encoding='utf-8', newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames != REQUIRED:
            return fail(f'header mismatch: {reader.fieldnames}')
        rows=list(reader)

    ids={}; roots={}; patterns={}
    for n,r in enumerate(rows, start=2):
        rid=r['root_id'].strip(); root=r['root'].strip(); nr=norm(root); pat=norm(r['canonical_pattern'])
        if not rid or rid in ids: errors += fail(f'line {n}: duplicate/blank root_id {rid!r}')
        else: ids[rid]=n
        if rid != root_slug(root): errors += fail(f'line {n}: root_id must equal canonical slug {root_slug(root)!r}, got {rid!r}')
        if not root or nr in roots: errors += fail(f'line {n}: duplicate/blank root {root!r}')
        else: roots[nr]=n
        if root != nr: errors += fail(f'line {n}: root must be lowercase: {root!r}')
        if not pat: errors += fail(f'line {n}: canonical_pattern is blank')
        elif pat in patterns: errors += fail(f'line {n}: duplicate canonical_pattern {r["canonical_pattern"]!r}; first seen line {patterns[pat]}')
        else: patterns[pat]=n
        if r['status'] not in STATUSES: errors += fail(f'line {n}: invalid status {r["status"]!r}')
        if r['scope'] not in SCOPES: errors += fail(f'line {n}: invalid scope {r["scope"]!r}')
        if r['evidence_level'] not in EVIDENCE: errors += fail(f'line {n}: invalid evidence {r["evidence_level"]!r}')
        if r['root_type'] not in ROOT_TYPES: errors += fail(f'line {n}: invalid root_type {r["root_type"]!r}')
        if r['demand_category'] not in DEMAND_CATEGORIES: errors += fail(f'line {n}: invalid demand_category {r["demand_category"]!r}')
        if r['primary_intent'] not in INTENTS: errors += fail(f'line {n}: invalid primary_intent {r["primary_intent"]!r}')
        if not DATE.match(r['added_at']): errors += fail(f'line {n}: invalid added_at')
        if r['last_verified_at'] and not DATE.match(r['last_verified_at']): errors += fail(f'line {n}: invalid last_verified_at')
        if r['scope']=='domain' and 'all' in {norm(x) for x in r['applicable_domains'].split(';')}: errors += fail(f'line {n}: domain-scoped root cannot use applicable_domains=all')
        if r['status'] in {'active','verified'} and not r['example_keywords'].strip(): errors += fail(f'line {n}: {r["status"]} root lacks example_keywords')
        if r['status']=='verified' and r['evidence_level'] not in {'L2','L3'}: errors += fail(f'line {n}: verified root requires L2/L3 evidence')
        if r['status']=='verified' and not r['last_verified_at'].strip(): errors += fail(f'line {n}: verified root requires last_verified_at')
        if r['evidence_level'] in {'L1','L2','L3'} and not r['evidence_ref'].strip():
            errors += fail(f'line {n}: {r["evidence_level"]} evidence requires evidence_ref')
        elif r['evidence_ref'].strip():
            for ref in [x.strip() for x in r['evidence_ref'].split(' | ') if x.strip()]:
                err=validate_local_evidence_ref(ref, a.file.resolve().parents[1])
                if err: errors += fail(f'line {n}: {err}')
        if r['evidence_level'] in {'L2','L3'} and not r['validation_basis'].strip(): errors += fail(f'line {n}: {r["evidence_level"]} evidence requires validation_basis')

    # Aliases must not collide with a different canonical root.
    for n,r in enumerate(rows, start=2):
        for alias in [norm(x) for x in r['aliases'].split(';') if norm(x)]:
            if alias in roots and alias != norm(r['root']):
                errors += fail(f'line {n}: alias {alias!r} collides with canonical root on line {roots[alias]}')

    if errors:
        print(f'FAILED: {errors} issue(s) across {len(rows)} roots')
        return 1
    print(f'OK: {len(rows)} roots; schema, enums, lifecycle, provenance, aliases, patterns, and dates valid')
    return 0

if __name__=='__main__': raise SystemExit(main())
