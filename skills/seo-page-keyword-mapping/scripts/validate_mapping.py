#!/usr/bin/env python3
import argparse
import csv
import json
import math
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


def ratio(v):
    if v in (None, ""):
        return None, "unknown"
    if isinstance(v, bool):
        return None, "invalid"
    try:
        parsed = float(v)
    except (TypeError, ValueError):
        return None, "invalid"
    if not math.isfinite(parsed) or parsed < 0 or parsed > 1:
        return None, "invalid"
    return parsed, "observed"


def validate(payload):
    issues = []
    ownership = defaultdict(set)
    for row in payload.get("rows", []):
        keyword = str(row.get("keyword") or "").strip()
        owner = str(row.get("ownership_page_id") or "").strip()
        raw_serp_fast_status = row.get("serp_fast_status")
        if raw_serp_fast_status is None or (
            isinstance(raw_serp_fast_status, str) and not raw_serp_fast_status.strip()
        ):
            serp_fast_status = "unknown"
        elif isinstance(raw_serp_fast_status, str):
            serp_fast_status = raw_serp_fast_status.strip().lower()
        else:
            serp_fast_status = "invalid"
        if serp_fast_status not in {"confirmed", "mismatch", "unknown"}:
            issues.append({
                "code": "invalid_serp_fast_status",
                "keyword": keyword,
                "page_id": row.get("page_id"),
                "message": "SERP fast status must be confirmed, mismatch, or unknown",
            })
        if row.get("ownership_status") == "confirmed" and keyword and owner:
            ownership[keyword.casefold()].add(owner)
        if row.get("role_candidate") == "core" and row.get("ownership_status") == "confirmed":
            if serp_fast_status == "mismatch":
                issues.append({
                    "code": "core_serp_mismatch",
                    "keyword": keyword,
                    "page_id": row.get("page_id"),
                    "message": "Observed SERP intent contradicts the confirmed core ownership",
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
        overlap, overlap_status = ratio(item.get("serp_overlap"))
        proposed = item.get("proposed_treatment")
        if proposed == "independent_url_candidate":
            if overlap_status == "unknown":
                issues.append({
                    "code": "independent_url_missing_serp_overlap",
                    "parent_page_id": item.get("parent_page_id"),
                    "child_page_id": item.get("child_page_id"),
                    "message": "Independent URL proposal lacks observed SERP overlap; keep it at review",
                })
            elif overlap_status == "invalid":
                issues.append({
                    "code": "independent_url_invalid_serp_overlap",
                    "parent_page_id": item.get("parent_page_id"),
                    "child_page_id": item.get("child_page_id"),
                    "message": "Independent URL proposal has invalid SERP overlap; expected a finite ratio from 0 to 1",
                })
            elif overlap >= 0.6:
                issues.append({
                    "code": "high_overlap_split",
                    "parent_page_id": item.get("parent_page_id"),
                    "child_page_id": item.get("child_page_id"),
                    "serp_overlap": overlap,
                    "message": "Proposed child URL has high SERP overlap with parent; prefer a module unless deeper evidence overrides",
                })

    for pair in payload.get("page_pairs", []):
        overlap, overlap_status = ratio(pair.get("serp_overlap"))
        if overlap_status == "invalid":
            issues.append({
                "code": "invalid_page_pair_serp_overlap",
                "page_a": pair.get("page_a"),
                "page_b": pair.get("page_b"),
                "message": "Page-pair SERP overlap must be a finite ratio from 0 to 1",
            })
        elif overlap_status == "observed" and overlap >= 0.7:
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
