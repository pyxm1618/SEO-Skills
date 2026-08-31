#!/usr/bin/env python3
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


def parse_num(value):
    if value in (None, ""):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return int(n) if n.is_integer() else n


def parse_ratio(value):
    if value in (None, ""):
        return None, "unknown"
    if isinstance(value, bool):
        return None, "invalid"
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return None, "invalid"
    if not math.isfinite(ratio) or ratio < 0 or ratio > 1:
        return None, "invalid"
    return ratio, "observed"


def load_payload(path):
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with p.open("r", encoding="utf-8", newline="") as f:
            return {"rows": list(csv.DictReader(f))}
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"rows": data}
    if isinstance(data, dict):
        if "rows" not in data:
            data["rows"] = []
        return data
    raise ValueError("Input must be CSV, a JSON array, or a JSON object")


def normalize_row(row):
    r = dict(row)
    r["page_id"] = str(r.get("page_id") or "").strip()
    r["keyword"] = str(r.get("keyword") or "").strip()
    r["ownership_page_id"] = str(r.get("ownership_page_id") or "").strip() or None
    r["role_candidate"] = str(r.get("role_candidate") or "unknown").strip().lower()
    r["ownership_status"] = str(r.get("ownership_status") or "unknown").strip().lower()
    raw_serp_fast_status = r.get("serp_fast_status")
    if raw_serp_fast_status is None or (
        isinstance(raw_serp_fast_status, str) and not raw_serp_fast_status.strip()
    ):
        r["serp_fast_status"] = "unknown"
    elif isinstance(raw_serp_fast_status, str):
        r["serp_fast_status"] = raw_serp_fast_status.strip().lower()
    else:
        r["serp_fast_status"] = "invalid"
    r["metric_scope_id"] = str(r.get("metric_scope_id") or "").strip() or None
    for key in ("target_scope_demand", "target_market_volume", "kd", "cpc"):
        r[key] = parse_num(r.get(key))
    r["cluster_include"] = r.get("cluster_include") in (True, 1, "1", "true", "True", "yes")
    r["eligible_core"] = (
        r["role_candidate"] == "core"
        and r["ownership_status"] == "confirmed"
        and r["ownership_page_id"] == r["page_id"]
        and r["serp_fast_status"] in {"confirmed", "unknown"}
    )
    return r


def primary_sort_key(row, cpc_tiebreak=False):
    def known(v):
        return (0, 0) if v is None else (1, v)
    key = [known(row.get("target_scope_demand")), known(row.get("target_market_volume"))]
    if cpc_tiebreak:
        key.append(known(row.get("cpc")))
    return tuple(key)


def choose_primary(rows, cpc_tiebreak=False):
    eligible = [r for r in rows if r["eligible_core"]]
    if not eligible:
        return None
    best = eligible[0]
    best_key = primary_sort_key(best, cpc_tiebreak)
    for r in eligible[1:]:
        k = primary_sort_key(r, cpc_tiebreak)
        if k > best_key:
            best, best_key = r, k
    return best


def cluster_summary(rows, primary):
    scope = primary.get("metric_scope_id") if primary else None
    included = [
        r for r in rows
        if r.get("cluster_include")
        and r.get("ownership_status") == "confirmed"
        and r.get("ownership_page_id") == r.get("page_id")
    ]
    by_kw = {}
    scope_mismatch = 0
    unknown = 0
    conflicts = 0
    if primary is None or scope is None:
        return {
            "cluster_observed_demand": None,
            "cluster_keyword_count": len({r.get("keyword", "").casefold() for r in included}),
            "cluster_unknown_keyword_count": 0,
            "cluster_scope_mismatch_count": len(included),
            "cluster_conflict_count": 0,
            "cluster_demand_complete": False,
            "cluster_metric_scope_id": None,
        }
    for r in included:
        if scope is not None and r.get("metric_scope_id") != scope:
            scope_mismatch += 1
            continue
        norm = r.get("keyword", "").casefold()
        demand = r.get("target_scope_demand")
        if norm not in by_kw:
            by_kw[norm] = demand
        elif by_kw[norm] != demand:
            conflicts += 1
            by_kw[norm] = None
    total = 0
    observed_count = 0
    for demand in by_kw.values():
        if demand is None:
            unknown += 1
            continue
        total += demand
        observed_count += 1
    if observed_count == 0:
        total = None
    keyword_count = len(by_kw)
    complete = scope_mismatch == 0 and unknown == 0 and conflicts == 0
    return {
        "cluster_observed_demand": total,
        "cluster_keyword_count": keyword_count,
        "cluster_unknown_keyword_count": unknown,
        "cluster_scope_mismatch_count": scope_mismatch,
        "cluster_conflict_count": conflicts,
        "cluster_demand_complete": complete,
        "cluster_metric_scope_id": scope,
    }


def architecture_decision(item):
    x = dict(item)
    overlap, overlap_status = parse_ratio(x.get("serp_overlap"))
    demand = parse_num(x.get("target_scope_demand"))
    x["serp_overlap"] = overlap
    x["serp_overlap_status"] = overlap_status
    x["target_scope_demand"] = demand
    task = x.get("task_divergence") is True
    independent = x.get("content_independent") is True
    if overlap_status != "observed" or x.get("task_divergence") is None or x.get("content_independent") is None:
        treatment = "review"
    elif overlap >= 0.6:
        treatment = "content_module"
    elif task and independent and demand is not None and demand > 0:
        treatment = "independent_url_candidate"
    else:
        treatment = "content_module"
    x["recommended_treatment"] = treatment
    return x


def evaluate(payload, cpc_tiebreak=False):
    rows = [normalize_row(r) for r in payload.get("rows", [])]
    groups = defaultdict(list)
    order = []
    for r in rows:
        pid = r.get("page_id")
        if pid not in groups:
            order.append(pid)
        groups[pid].append(r)

    pages = []
    for pid in order:
        rs = groups[pid]
        primary = choose_primary(rs, cpc_tiebreak)
        eligible = [r for r in rs if r["eligible_core"]]
        secondaries = [r["keyword"] for r in eligible if primary is None or r is not primary]
        summary = {
            "page_id": pid,
            "primary_keyword": primary["keyword"] if primary else None,
            "core_keyword_demand": primary.get("target_scope_demand") if primary else None,
            "target_market_volume": primary.get("target_market_volume") if primary else None,
            "secondary_core_keywords": secondaries,
        }
        summary.update(cluster_summary(rs, primary))
        pages.append(summary)

    architecture = [architecture_decision(x) for x in payload.get("architecture_candidates", [])]
    return {
        "rows": rows,
        "pages": pages,
        "architecture_candidates": architecture,
        "method": {
            "primary": "confirmed ownership + core candidate; observed SERP mismatch disqualifies",
            "cluster": "deduplicated owned observed queries within the primary metric scope",
            "cpc_tiebreak": bool(cpc_tiebreak),
        },
    }


def to_csv(data):
    fields = [
        "page_id", "primary_keyword", "core_keyword_demand", "target_market_volume",
        "cluster_observed_demand", "cluster_keyword_count", "cluster_unknown_keyword_count",
        "cluster_scope_mismatch_count", "cluster_demand_complete", "cluster_metric_scope_id",
    ]
    out = [",".join(fields)]
    for r in data["pages"]:
        vals = []
        for f in fields:
            v = r.get(f)
            if v is None:
                vals.append("")
            else:
                s = str(v).replace('"', '""')
                vals.append(f'"{s}"' if "," in s else s)
        out.append(",".join(vals))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--format", choices=("json", "csv"), default="json")
    ap.add_argument("--cpc-tiebreak", action="store_true")
    args = ap.parse_args()
    data = evaluate(load_payload(args.input), args.cpc_tiebreak)
    print(json.dumps(data, ensure_ascii=False, indent=2) if args.format == "json" else to_csv(data))


if __name__ == "__main__":
    main()
