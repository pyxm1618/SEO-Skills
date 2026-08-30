#!/usr/bin/env python3
"""Deterministic domain anchor pooling and Rising-only radar traversal."""

from __future__ import annotations

import re
from collections import deque
from typing import Any, Callable


def canonical_keyword(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _tokens(value: Any) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", canonical_keyword(value)) if len(token) > 1}


def _root_is_relevant(root: dict[str, Any], domain: str) -> bool:
    applicable = {
        item.strip().casefold()
        for item in str(root.get("applicable_domains") or "").split(";")
        if item.strip()
    }
    normalized_domain = canonical_keyword(domain)
    if not applicable:
        return False
    if normalized_domain in applicable or "all" in applicable:
        return True
    return str(root.get("scope") or "").casefold() == "universal" and "all" in applicable


def _anchor_record(keyword: str, source: str, root: dict[str, Any] | None = None) -> dict[str, Any]:
    root = root or {}
    status = str(root.get("status") or "").strip().casefold() or None
    return {
        "keyword": keyword,
        "anchor_source": source,
        "discovery_depth": 0,
        "parent_anchor": None,
        "root_id": root.get("root_id"),
        "root_status": status,
        "root_verified": status in {"active", "verified"},
    }


def build_anchor_pool(
    domain: str,
    explicit_anchors: list[Any] | None = None,
    root_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    normalized_domain = " ".join(str(domain or "").strip().split())
    if not canonical_keyword(normalized_domain):
        raise ValueError("domain is required for an emerging radar run")

    anchors: dict[str, dict[str, Any]] = {}

    def add(keyword: Any, source: str, root: dict[str, Any] | None = None) -> None:
        text = " ".join(str(keyword or "").strip().split())
        identity = canonical_keyword(text)
        if not identity:
            return
        current = anchors.get(identity)
        if current is None:
            anchors[identity] = _anchor_record(text, source, root)
            return
        if root:
            current["root_id"] = current.get("root_id") or root.get("root_id")
            status = str(root.get("status") or "").strip().casefold() or current.get("root_status")
            current["root_status"] = status
            current["root_verified"] = status in {"active", "verified"}
        if current.get("anchor_source") == "domain" and source != "domain":
            current["anchor_source"] = source

    add(normalized_domain, "domain")
    for anchor in explicit_anchors or []:
        if isinstance(anchor, dict):
            add(anchor.get("keyword") or anchor.get("anchor"), "user_anchor", anchor)
        else:
            add(anchor, "user_anchor")

    for root in root_rows or []:
        if not isinstance(root, dict) or not _root_is_relevant(root, normalized_domain):
            continue
        status = str(root.get("status") or "").strip().casefold()
        if status not in {"active", "verified", "candidate"}:
            continue
        add(root.get("root") or root.get("keyword"), "root_bootstrap", root)

    return list(anchors.values())


def default_domain_relation(domain: str, keyword: str, parent_anchor: str) -> tuple[str, str]:
    candidate_tokens = _tokens(keyword)
    if not candidate_tokens:
        return "out_of_scope", "candidate keyword is empty"

    navigation_tokens = {
        "login",
        "signin",
        "sign",
        "official",
        "website",
        "facebook",
        "instagram",
        "youtube",
    }
    if candidate_tokens & navigation_tokens and ("login" in candidate_tokens or "signin" in candidate_tokens or "official" in candidate_tokens):
        return "out_of_scope", "brand_or_navigation_query"

    domain_tokens = _tokens(domain)
    parent_tokens = _tokens(parent_anchor)
    if candidate_tokens & (domain_tokens | parent_tokens):
        return "in_scope", "candidate shares a domain or parent-anchor term"
    return "unknown", "lexical domain relationship is not established"


def _related_rows(value: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(value, dict):
        rows = value.get("related_queries")
        context = value
    else:
        rows = value
        context = {}
    if not isinstance(rows, list):
        raise ValueError("related fetcher must return a related_queries list")
    return [row for row in rows if isinstance(row, dict)], context


def _relation_decision(
    relation_gate: Callable[[str, str, str], Any] | None,
    domain: str,
    keyword: str,
    parent_anchor: str,
) -> tuple[str, str]:
    decision = relation_gate(domain, keyword, parent_anchor) if relation_gate else default_domain_relation(domain, keyword, parent_anchor)
    if isinstance(decision, dict):
        relation = str(decision.get("domain_relation") or decision.get("relation") or "unknown")
        reason = str(decision.get("reason") or "domain relation analysis returned no reason")
        return relation, reason
    if isinstance(decision, (tuple, list)) and len(decision) >= 2:
        return str(decision[0] or "unknown"), str(decision[1] or "domain relation analysis returned no reason")
    return str(decision or "unknown"), "domain relation analysis returned no reason"


def _candidate_from_row(domain: str, parent: dict[str, Any], row: dict[str, Any], relation: str, reason: str) -> dict[str, Any]:
    candidate = {
        "keyword": " ".join(str(row.get("query") or row.get("keyword") or "").split()),
        "domain": domain,
        "root_id": parent.get("root_id"),
        "root_relation": "existing_root" if parent.get("root_verified") else "root_candidate" if parent.get("root_status") == "candidate" else "unresolved",
        "parent_anchor": parent["keyword"],
        "discovery_depth": int(parent["discovery_depth"]) + 1,
        "discovery_source": "google_trends_rising",
        "relation_type": "rising",
        "rising_value": row.get("rising_value"),
        "google_rising_label": row.get("google_rising_label"),
        "is_google_breakout": row.get("is_google_breakout") is True,
        "source_url": row.get("source_url"),
        "raw_evidence_ref": row.get("raw_evidence_ref"),
        "domain_relation": relation,
        "domain_relation_reason": reason,
    }
    for field in ("observed_at", "country", "timeframe", "screenshot_ref"):
        if row.get(field) is not None:
            candidate[field] = row[field]
    return candidate


def discover_rising_bfs(
    domain: str,
    anchors: list[dict[str, Any]],
    related_fetcher: Callable[[str], Any],
    relation_gate: Callable[[str, str, str], Any] | None = None,
    max_depth: int = 2,
    per_anchor_limit: int = 10,
    max_candidates: int = 200,
) -> dict[str, Any]:
    if not canonical_keyword(domain):
        raise ValueError("domain is required for an emerging radar run")
    if max_depth < 0 or per_anchor_limit < 1 or max_candidates < 1:
        raise ValueError("max_depth must be non-negative and limits must be positive")

    queue: deque[dict[str, Any]] = deque()
    for anchor in anchors:
        if not isinstance(anchor, dict):
            continue
        keyword = " ".join(str(anchor.get("keyword") or "").split())
        if keyword:
            queue.append(
                {
                    **anchor,
                    "keyword": keyword,
                    "discovery_depth": int(anchor.get("discovery_depth") or 0),
                }
            )

    visited: list[str] = []
    visited_set: set[str] = set()
    candidate_set: set[str] = set()
    candidates: list[dict[str, Any]] = []
    anchor_evidence: dict[str, list[dict[str, Any]]] = {}
    stops: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    while queue:
        parent = queue.popleft()
        parent_identity = canonical_keyword(parent["keyword"])
        if parent_identity in visited_set:
            stops.append({"anchor": parent["keyword"], "reason": "already_visited"})
            continue
        visited_set.add(parent_identity)
        visited.append(parent_identity)
        depth = int(parent["discovery_depth"])
        if depth >= max_depth:
            stops.append({"anchor": parent["keyword"], "reason": "max_depth"})
            continue

        try:
            fetched = related_fetcher(parent["keyword"])
            rows, context = _related_rows(fetched)
        except Exception as exc:
            blockers.append({"status": "BLOCKED", "anchor": parent["keyword"], "reason": str(exc)})
            stops.append({"anchor": parent["keyword"], "reason": "related_fetch_blocked"})
            continue

        anchor_evidence[parent_identity] = rows
        rising_rows = [row for row in rows if str(row.get("relation_type") or "").strip().casefold() == "rising"]
        if not rising_rows:
            stops.append({"anchor": parent["keyword"], "reason": "no_rising_queries"})
            continue

        for row in rising_rows[:per_anchor_limit]:
            keyword = " ".join(str(row.get("query") or row.get("keyword") or "").split())
            identity = canonical_keyword(keyword)
            if not identity:
                stops.append({"anchor": parent["keyword"], "reason": "malformed_related_row"})
                continue
            if identity in visited_set or identity in candidate_set:
                stops.append({"anchor": keyword, "reason": "already_seen", "parent_anchor": parent["keyword"]})
                continue
            if len(candidates) >= max_candidates:
                stops.append({"anchor": keyword, "reason": "max_candidates", "parent_anchor": parent["keyword"]})
                continue

            enriched_row = dict(row)
            for field in ("source_url", "raw_evidence_ref", "observed_at", "country", "timeframe", "screenshot_ref"):
                if enriched_row.get(field) is None and context.get(field) is not None:
                    enriched_row[field] = context[field]
            relation, reason = _relation_decision(relation_gate, domain, keyword, parent["keyword"])
            candidate = _candidate_from_row(domain, parent, enriched_row, relation, reason)
            candidate_set.add(identity)
            candidates.append(candidate)
            if relation == "in_scope" and int(candidate["discovery_depth"]) < max_depth:
                queue.append(candidate)
            else:
                stop_reason = (
                    "domain_relation_out_of_scope"
                    if relation == "out_of_scope"
                    else "domain_relation_unknown"
                    if relation != "in_scope"
                    else "max_depth"
                )
                stops.append({"anchor": keyword, "reason": stop_reason, "parent_anchor": parent["keyword"]})

    return {
        "domain": domain,
        "anchor_pool": anchors,
        "visited": visited,
        "visited_count": len(visited),
        "candidates": candidates,
        "discovered_unique_count": len(candidates),
        "anchor_evidence": anchor_evidence,
        "stops": stops,
        "blockers": blockers,
        "status": "BLOCKED" if blockers else "PASS",
        "recursive_edge_policy": "google_trends_rising_only",
        "max_depth": max_depth,
        "per_anchor_limit": per_anchor_limit,
        "max_candidates": max_candidates,
    }
