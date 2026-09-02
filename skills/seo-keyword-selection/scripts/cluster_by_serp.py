#!/usr/bin/env python3
"""Cluster keywords by observed Google SERP overlap.

Provenance clustering (`domain x root x parent_seed`) answers where a keyword
came from. It cannot answer whether two keywords should share one page --
Google decides that, and it reveals the decision through the result set. Two
queries whose top-10 share enough URLs are being served the same intent, so one
page can rank for both; two queries that share almost nothing need separate
pages even when they came from the same root.

The threshold is a shared-URL count (default 3 of 10), the convention used by
the mainstream clustering tools. This script is `calculated`: it derives
groupings from SERP evidence that `serp_review` already collects and never
introduces a new acquisition or an AI judgement.
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def canonical_url(value):
    """Normalize a result URL so trivial differences do not break overlap.

    Scheme, `www.`, trailing slash, query and fragment are dropped: the same
    document reached two ways is one shared result, not two.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    host = (parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parts.path or "/").rstrip("/") or "/"
    return urlunsplit(("", host, path, "", "")).lstrip("/") or host


def load_serp(path):
    """Read one SERP evidence file into (keyword, ordered canonical URLs)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    keyword = " ".join(str(data.get("keyword") or "").split())
    if not keyword:
        raise ValueError(f"{path}: missing keyword")
    results = data.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError(f"{path}: missing results")
    urls = []
    for row in results:
        if not isinstance(row, dict):
            raise ValueError(f"{path}: malformed result row")
        url = canonical_url(row.get("url"))
        if url and url not in urls:
            urls.append(url)
    if not urls:
        raise ValueError(f"{path}: no usable result URLs")
    return keyword, urls, str(data.get("evidence_receipt_ref") or "")


def overlap_matrix(entries):
    pairs = {}
    keys = sorted(entries)
    for i, left in enumerate(keys):
        for right in keys[i + 1:]:
            shared = sorted(set(entries[left]["urls"]) & set(entries[right]["urls"]))
            pairs[(left, right)] = shared
    return pairs


def cluster(entries, threshold):
    """Union-find over pairs that meet the shared-URL threshold."""
    parent = {k: k for k in entries}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    pairs = overlap_matrix(entries)
    for (left, right), shared in pairs.items():
        if len(shared) >= threshold:
            union(left, right)

    groups = {}
    for key in entries:
        groups.setdefault(find(key), []).append(key)
    return pairs, [sorted(v) for v in groups.values()]


def primary_of(members, entries):
    """Pick the cluster's representative: the keyword most central to it."""
    if len(members) == 1:
        return members[0]
    scores = {}
    for member in members:
        others = [m for m in members if m != member]
        scores[member] = sum(
            len(set(entries[member]["urls"]) & set(entries[other]["urls"])) for other in others
        )
    return sorted(members, key=lambda m: (-scores[m], len(m), m))[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", nargs="+", required=True, help="serp_review evidence JSON files")
    parser.add_argument("--threshold", type=int, default=3, help="shared top-10 URLs to merge (default 3)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    if args.threshold < 1:
        parser.error("--threshold must be >= 1")

    entries = {}
    for path in args.input:
        try:
            keyword, urls, receipt = load_serp(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"BLOCKED: {exc}", file=sys.stderr)
            return 2
        if keyword in entries:
            print(f"BLOCKED: duplicate SERP evidence for '{keyword}'", file=sys.stderr)
            return 2
        entries[keyword] = {"urls": urls, "path": str(path), "evidence_receipt_ref": receipt}

    if len(entries) < 2:
        print("BLOCKED: clustering needs at least two SERP evidence files", file=sys.stderr)
        return 2

    pairs, groups = cluster(entries, args.threshold)
    groups.sort(key=lambda g: (-len(g), g[0]))
    clusters = [
        {
            "cluster_id": f"c{index + 1}",
            "primary_keyword": primary_of(members, entries),
            "members": members,
            "member_count": len(members),
            "page_recommendation": "one page" if len(members) > 1 else "own page",
        }
        for index, members in enumerate(groups)
    ]
    report = {
        "threshold_shared_urls": args.threshold,
        "keyword_count": len(entries),
        "cluster_count": len(clusters),
        "data_state": "calculated",
        "clusters": clusters,
        "pairs": [
            {"a": a, "b": b, "shared_urls": len(shared), "shared": shared}
            for (a, b), shared in sorted(pairs.items(), key=lambda kv: -len(kv[1]))
        ],
    }

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"{len(entries)} 个关键词 -> {len(clusters)} 个页面（阈值：共享 {args.threshold} 个 URL）\n")
    for item in clusters:
        print(f"[{item['cluster_id']}] {item['page_recommendation']}  主词: {item['primary_keyword']}")
        for member in item["members"]:
            if member != item["primary_keyword"]:
                print(f"      + {member}")
    print("\n两两重叠：")
    for row in report["pairs"]:
        mark = "合并" if row["shared_urls"] >= args.threshold else "分开"
        print(f"  {row['shared_urls']:>2}/10  {mark}  {row['a']}  <->  {row['b']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
