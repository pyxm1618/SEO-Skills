#!/usr/bin/env python3
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def load_payload(path):
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with p.open("r", encoding="utf-8", newline="") as f:
            return {"rows": list(csv.DictReader(f))}
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"rows": data}
    return data


def num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def validate(payload):
    issues = []
    ownership = defaultdict(set)
    for row in payload.get("rows", []):
        keyword = str(row.get("keyword") or "").strip()
        owner = str(row.get("ownership_page_id") or "").strip()
        if row.get("ownership_status") == "confirmed" and keyword and owner:
            ownership[keyword.casefold()].add(owner)
        if row.get("role_candidate") == "core" and row.get("ownership_status") == "confirmed":
            if row.get("serp_fast_status") != "confirmed":
                issues.append({
                    "code": "core_missing_serp_fast",
                    "keyword": keyword,
                    "page_id": row.get("page_id"),
                    "message": "Confirmed core candidate lacks confirmed SERP fast intent check",
                })
    for keyword, owners in ownership.items():
        if len(owners) > 1:
            issues.append({
                "code": "exact_ownership_collision",
                "keyword": keyword,
                "ownership_page_ids": sorted(owners),
                "message": "The same normalized keyword is confirmed for more than one page",
            })

    for item in payload.get("architecture_candidates", []):
        overlap = num(item.get("serp_overlap"))
        proposed = item.get("proposed_treatment")
        if proposed == "independent_url_candidate" and overlap is not None and overlap >= 0.6:
            issues.append({
                "code": "high_overlap_split",
                "parent_page_id": item.get("parent_page_id"),
                "child_page_id": item.get("child_page_id"),
                "serp_overlap": overlap,
                "message": "Proposed child URL has high SERP overlap with parent; prefer a module unless deeper evidence overrides",
            })

    for pair in payload.get("page_pairs", []):
        overlap = num(pair.get("serp_overlap"))
        if overlap is not None and overlap >= 0.7:
            issues.append({
                "code": "high_serp_overlap_pages",
                "page_a": pair.get("page_a"),
                "page_b": pair.get("page_b"),
                "serp_overlap": overlap,
                "message": "Two pages in the mapping universe show high SERP overlap and may cannibalize",
            })

    return {"valid": not issues, "issues": issues, "issue_count": len(issues)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--format", choices=("json",), default="json")
    args = ap.parse_args()
    print(json.dumps(validate(load_payload(args.input)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
