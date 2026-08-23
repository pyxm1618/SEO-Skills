#!/usr/bin/env python3
"""Audit breadth and evidence balance of the keyword root library.

This script never mutates the library. It reports where the bootstrap library is
thin so future research can target gaps instead of blindly adding more roots.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_LIBRARY = Path(__file__).resolve().parents[1] / 'references' / 'root-library.csv'
USABLE = {'active', 'verified'}


def split_values(value):
    return [x.strip().lower() for x in (value or '').split(';') if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--library', type=Path, default=DEFAULT_LIBRARY)
    ap.add_argument('--format', choices=['json', 'tsv'], default='json')
    ap.add_argument('--weak-category-total', type=int, default=5)
    ap.add_argument('--weak-category-usable', type=int, default=3)
    ap.add_argument('--weak-domain-total', type=int, default=5)
    ap.add_argument('--weak-domain-usable', type=int, default=3)
    args = ap.parse_args()

    with args.library.open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))

    status = Counter(r['status'] for r in rows)
    evidence = Counter(r['evidence_level'] for r in rows)
    scope = Counter(r['scope'] for r in rows)
    intent = Counter(r['primary_intent'] for r in rows)

    by_cat = defaultdict(lambda: Counter(total=0, usable=0, verified=0, active=0, candidate=0))
    for r in rows:
        c = by_cat[r['demand_category']]
        c['total'] += 1
        c[r['status']] += 1
        if r['status'] in USABLE:
            c['usable'] += 1

    by_domain = defaultdict(lambda: Counter(total=0, usable=0, verified=0, active=0, candidate=0))
    for r in rows:
        for d in split_values(r['applicable_domains']):
            if d == 'all':
                continue
            c = by_domain[d]
            c['total'] += 1
            c[r['status']] += 1
            if r['status'] in USABLE:
                c['usable'] += 1

    weak_categories = []
    for name, c in by_cat.items():
        reasons = []
        if c['total'] < args.weak_category_total:
            reasons.append(f"total<{args.weak_category_total}")
        if c['usable'] < args.weak_category_usable:
            reasons.append(f"usable<{args.weak_category_usable}")
        if c['verified'] == 0:
            reasons.append('verified=0')
        if reasons:
            weak_categories.append({'demand_category': name, **dict(c), 'reasons': reasons})
    weak_categories.sort(key=lambda x: (x['usable'], x['verified'], x['total'], x['demand_category']))

    weak_domains = []
    for name, c in by_domain.items():
        reasons = []
        if c['total'] < args.weak_domain_total:
            reasons.append(f"total<{args.weak_domain_total}")
        if c['usable'] < args.weak_domain_usable:
            reasons.append(f"usable<{args.weak_domain_usable}")
        if c['verified'] == 0:
            reasons.append('verified=0')
        if reasons:
            weak_domains.append({'domain': name, **dict(c), 'reasons': reasons})
    weak_domains.sort(key=lambda x: (x['usable'], x['verified'], x['total'], x['domain']))

    tool_share = (intent.get('tool', 0) / len(rows)) if rows else 0.0
    candidate_share = (status.get('candidate', 0) / len(rows)) if rows else 0.0

    result = {
        'summary': {
            'total_roots': len(rows),
            'usable_roots': sum(1 for r in rows if r['status'] in USABLE),
            'verified_roots': status.get('verified', 0),
            'active_roots': status.get('active', 0),
            'candidate_roots': status.get('candidate', 0),
            'universal_roots': scope.get('universal', 0),
            'domain_roots': scope.get('domain', 0),
            'tool_intent_share': round(tool_share, 4),
            'candidate_share': round(candidate_share, 4),
        },
        'status_counts': dict(sorted(status.items())),
        'evidence_counts': dict(sorted(evidence.items())),
        'intent_counts': dict(sorted(intent.items())),
        'demand_category_counts': {k: dict(v) for k, v in sorted(by_cat.items())},
        'domain_counts': {k: dict(v) for k, v in sorted(by_domain.items())},
        'weak_demand_categories': weak_categories,
        'weak_domains': weak_domains,
        'interpretation': {
            'is_complete_universe': False,
            'note': 'Coverage flags are research-priority heuristics, not proof that a category/domain lacks SEO opportunity.'
        }
    }

    if args.format == 'json':
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print('section\tname\ttotal\tusable\tverified\treasons')
        for x in weak_categories:
            print('demand_category\t{}\t{}\t{}\t{}\t{}'.format(
                x['demand_category'], x['total'], x['usable'], x['verified'], ','.join(x['reasons'])))
        for x in weak_domains:
            print('domain\t{}\t{}\t{}\t{}\t{}'.format(
                x['domain'], x['total'], x['usable'], x['verified'], ','.join(x['reasons'])))


if __name__ == '__main__':
    main()
