#!/usr/bin/env python3
"""Mine recurring root candidates from a real keyword batch.

The output is review-only. This script never mutates root-library.csv and never
assigns lifecycle/evidence status. Human/agent review must decide whether a
candidate is a reusable demand family and how evidence should be recorded.
"""
import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

DEFAULT_LIBRARY = Path(__file__).resolve().parents[1] / 'references' / 'root-library.csv'
TOKEN_RE = re.compile(r"[a-z0-9']+")
STOP_PHRASES = {
    'of the', 'in the', 'to the', 'for the', 'and the', 'what is', 'how to',
    'does it', 'when you', 'what does', 'how do', 'is the', 'on the'
}
PLACEHOLDERS = {'x', 'y', 'z'}


def norm(s):
    return ' '.join(TOKEN_RE.findall((s or '').lower()))


def tokens(s):
    return TOKEN_RE.findall((s or '').lower())


def represented_phrases(library_path):
    represented = set()
    roots = {}
    with library_path.open(encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            vals = [r.get('root', ''), r.get('canonical_pattern', '')]
            vals += [x for x in (r.get('aliases') or '').split(';') if x.strip()]
            for value in vals:
                ts = [t for t in tokens(value) if t not in PLACEHOLDERS]
                if ts:
                    phrase=' '.join(ts)
                    represented.add(phrase)
                    roots.setdefault(phrase, set()).add(norm(r.get('root','')))
    return represented, roots


def load_batch(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(data, dict) and isinstance(data.get('keywords'), list):
        return data['keywords']
    if isinstance(data, list):
        return data
    raise SystemExit('input JSON must be a list or an object containing a keywords list')


def candidate_phrases(keyword, min_tokens, max_tokens):
    ts = tokens(keyword)
    seen = set()
    nmax = min(max_tokens, len(ts))
    # Roots usually behave as stable prefixes/suffixes; mine those first.
    for n in range(min_tokens, nmax + 1):
        for part in (ts[:n], ts[-n:]):
            phrase = ' '.join(part)
            if phrase and phrase not in seen:
                seen.add(phrase)
                yield phrase
    # Also mine internal ngrams for recurring patterns such as "error code".
    for n in range(min_tokens, nmax + 1):
        for i in range(1, len(ts) - n):
            phrase = ' '.join(ts[i:i+n])
            if phrase and phrase not in seen:
                seen.add(phrase)
                yield phrase


def useful_phrase(phrase):
    ts = phrase.split()
    if phrase in STOP_PHRASES:
        return False
    if all(t.isdigit() for t in ts):
        return False
    if sum(t.isdigit() for t in ts) >= max(1, len(ts) - 1):
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--library', type=Path, default=DEFAULT_LIBRARY)
    ap.add_argument('--min-count', type=int, default=5)
    ap.add_argument('--min-tokens', type=int, default=2)
    ap.add_argument('--max-tokens', type=int, default=5)
    ap.add_argument('--limit', type=int, default=100)
    ap.add_argument('--format', choices=['json', 'tsv'], default='json')
    args = ap.parse_args()
    if args.min_count < 2:
        ap.error('--min-count must be >= 2')
    if args.min_tokens < 1 or args.max_tokens < args.min_tokens:
        ap.error('invalid token bounds')

    represented, represented_roots = represented_phrases(args.library)
    rows = load_batch(args.input)
    stats = defaultdict(lambda: {'keywords': set(), 'groups': set(), 'source_seeds': set(), 'examples': []})

    for row in rows:
        kw = norm(row.get('keyword', ''))
        if not kw:
            continue
        group = norm(row.get('group', ''))
        seed = norm(row.get('source_seed', ''))
        for phrase in candidate_phrases(kw, args.min_tokens, args.max_tokens):
            if not useful_phrase(phrase) or phrase in represented:
                continue
            s = stats[phrase]
            s['keywords'].add(kw)
            if group:
                s['groups'].add(group)
            if seed:
                s['source_seeds'].add(seed)
            if kw not in s['examples'] and len(s['examples']) < 8:
                s['examples'].append(kw)

    out = []
    for phrase, s in stats.items():
        count = len(s['keywords'])
        if count < args.min_count:
            continue
        # Recurrence across multiple seeds is valuable, but single-seed domain roots
        # are still allowed to surface for review.
        score = count + 2 * len(s['source_seeds']) + 4 * len(s['groups']) + min(len(phrase.split()), 4)
        fragment_hits=sorted({root for existing, roots in represented_roots.items() if phrase != existing and phrase in existing for root in roots if root})
        contains_hits=sorted({root for existing, roots in represented_roots.items() if phrase != existing and existing in phrase for root in roots if root})
        if fragment_hits:
            overlap_type='fragment_of_existing'
            overlap_roots=fragment_hits
        elif contains_hits:
            overlap_type='contains_existing'
            overlap_roots=contains_hits
        else:
            overlap_type='none'
            overlap_roots=[]

        seeds=sorted(s['source_seeds'])
        if phrase in seeds:
            seed_overlap_type='exact_source_seed'
        elif any(phrase in seed for seed in seeds):
            seed_overlap_type='fragment_of_source_seed'
        elif any(seed in phrase for seed in seeds):
            seed_overlap_type='contains_source_seed'
        else:
            seed_overlap_type='none'
        out.append({
            'candidate': phrase,
            'keyword_count': count,
            'distinct_groups': len(s['groups']),
            'distinct_source_seeds': len(s['source_seeds']),
            'examples': s['examples'],
            'score': score,
            'overlap_type': overlap_type,
            'overlap_roots': overlap_roots[:8],
            'seed_overlap_type': seed_overlap_type,
            'review_status': 'candidate_only',
        })

    overlap_rank={'none':0,'contains_existing':1,'fragment_of_existing':2}
    seed_rank={'none':0,'contains_source_seed':1,'fragment_of_source_seed':2,'exact_source_seed':3}
    out.sort(key=lambda x: (overlap_rank.get(x['overlap_type'],9), seed_rank.get(x['seed_overlap_type'],9), -x['score'], -x['keyword_count'], -x['distinct_source_seeds'], x['candidate']))
    out = out[:args.limit]

    if args.format == 'json':
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print('candidate\tkeyword_count\tdistinct_groups\tdistinct_source_seeds\tscore\texamples')
        for x in out:
            print('{}\t{}\t{}\t{}\t{}\t{}'.format(
                x['candidate'], x['keyword_count'], x['distinct_groups'], x['distinct_source_seeds'], x['score'], '; '.join(x['examples'])))


if __name__ == '__main__':
    main()
