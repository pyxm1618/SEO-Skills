#!/usr/bin/env python3
"""Generate Seed hypotheses by applying universal root patterns to a domain.

Step 2 of the discovery SOP asks for natural demand-entry Seeds. The root
library already holds 197 universal roots whose `canonical_pattern` is a
demand shape with an `x` slot (`x calculator`, `free x`, ...). Filling that
slot with a domain topic produces far better Seed coverage than mechanical
letter permutation, which was measured to return mostly duplicates.

Everything this script emits is `analysis`, never `observed`. A Seed becomes a
concrete candidate only after the Google live collector observes it through
`autocomplete` or `expansions`. The output therefore carries no metrics and no
evidence reference, and callers must not promote a row without acquisition.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT_CSV = (
    Path(__file__).resolve().parents[2]
    / "keyword-root-library"
    / "references"
    / "root-library.csv"
)
LIFECYCLE_RANK = {"verified": 0, "active": 1, "candidate": 2, "deprecated": 3}


def norm(value):
    return " ".join(str(value or "").split()).strip().lower()


def domains_of(row):
    return {norm(x) for x in (row.get("applicable_domains") or "").split(";") if norm(x)}


def read_rows(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def apply_pattern(pattern, topic):
    """Fill the `x` slot of a canonical pattern with a topic.

    Patterns without a standalone `x` token are literal keywords rather than
    shapes, so they are skipped instead of being mangled into a fake phrase.
    """
    parts = norm(pattern).split()
    if "x" not in parts:
        return None
    filled = " ".join(topic if part == "x" else part for part in parts)
    filled = " ".join(filled.split())
    return filled or None


def topics_for(rows, domain, explicit):
    if explicit:
        return [norm(explicit)]
    seen = []
    for row in sorted(rows, key=lambda r: LIFECYCLE_RANK.get(r.get("status"), 9)):
        if row.get("scope") != "domain" or domain not in domains_of(row):
            continue
        topic = norm(row.get("root"))
        if topic and topic not in seen:
            seen.append(topic)
    return seen


def build(rows, domain, explicit_topic, statuses, limit):
    topics = topics_for(rows, domain, explicit_topic)
    if not topics:
        return [], []
    universal = [
        r
        for r in rows
        if r.get("scope") == "universal" and norm(r.get("status")) in statuses
    ]
    universal.sort(key=lambda r: (LIFECYCLE_RANK.get(r.get("status"), 9), norm(r.get("root"))))

    seeds = []
    seen = set()
    for row in rows:
        if row.get("scope") != "domain" or domain not in domains_of(row):
            continue
        seed = norm(row.get("root"))
        if seed and seed not in seen:
            seen.add(seed)
            seeds.append(
                {
                    "seed": seed,
                    "kind": "domain_root",
                    "source_root_id": row.get("root_id", ""),
                    "source_root": row.get("root", ""),
                    "pattern": row.get("canonical_pattern", ""),
                    "topic": "",
                    "root_status": row.get("status", ""),
                    "data_state": "analysis",
                }
            )
    for topic in topics:
        for row in universal:
            seed = apply_pattern(row.get("canonical_pattern"), topic)
            if not seed or seed in seen:
                continue
            seen.add(seed)
            seeds.append(
                {
                    "seed": seed,
                    "kind": "universal_applied",
                    "source_root_id": row.get("root_id", ""),
                    "source_root": row.get("root", ""),
                    "pattern": row.get("canonical_pattern", ""),
                    "topic": topic,
                    "root_status": row.get("status", ""),
                    "data_state": "analysis",
                }
            )
    return seeds[:limit], topics


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--domain", required=True, help="industry key as used in applicable_domains")
    parser.add_argument("--topic", help="override the topic filled into universal patterns")
    parser.add_argument(
        "--status",
        default="verified,active",
        help="universal-root lifecycle statuses to apply (default verified,active)",
    )
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--library", default=str(ROOT_CSV))
    parser.add_argument("--format", choices=["csv", "json", "tsv"], default="csv")
    parser.add_argument("--output", help="write to this path instead of stdout")
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be >= 1")
    statuses = {norm(s) for s in args.status.split(",") if norm(s)}
    rows = read_rows(args.library)
    domain = norm(args.domain)
    seeds, topics = build(rows, domain, args.topic, statuses, args.limit)
    if not seeds:
        print(
            f"BLOCKED: no roots found for domain '{domain}'; "
            "run query_roots.py --overview to see covered domains",
            file=sys.stderr,
        )
        return 2

    fields = ["seed", "kind", "source_root_id", "source_root", "pattern", "topic", "root_status", "data_state"]
    if args.format == "json":
        text = json.dumps(
            {"domain": domain, "topics": topics, "seed_count": len(seeds), "seeds": seeds},
            ensure_ascii=False,
            indent=2,
        )
    else:
        sep = "," if args.format == "csv" else "\t"
        lines = [sep.join(fields)]
        for row in seeds:
            values = [str(row.get(f, "")) for f in fields]
            if args.format == "csv":
                values = ['"' + v.replace('"', '""') + '"' if sep in v or '"' in v else v for v in values]
            lines.append(sep.join(values))
        text = "\n".join(lines)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"{len(seeds)} Seed hypotheses (analysis, not observed) -> {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
