#!/usr/bin/env python3
"""Deterministic domain anchor pooling and Rising-only radar traversal."""

from __future__ import annotations

import re
from collections import deque
from typing import Any, Callable


class HumanInterventionRequired(RuntimeError):
    def __init__(
        self,
        message: str,
        blocker_type: str = "captcha_or_unusual_traffic",
        url: str = "",
        stage: str = "",
        keyword: str = "",
    ) -> None:
        super().__init__(message)
        self.blocker_type = blocker_type
        self.url = url
        self.stage = stage
        self.keyword = keyword


def canonical_keyword(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _tokens(value: Any) -> set[str]:
    return {token for token in re.findall(r"[^\W_]+", canonical_keyword(value), flags=re.UNICODE) if len(token) > 1}


# These terms describe a generic search mechanic or temporal/news modifier.  An
# overlap on one of them is not evidence that two queries belong to the same
# demand domain.  This is deliberately small and deterministic rather than a
# new semantic/agent framework.
GENERIC_RELATION_TOKENS = frozenset(
    {
        "finder",
        "find",
        "search",
        "lookup",
        "tool",
        "tools",
        "guide",
        "generator",
        "calculator",
        "quiz",
        "test",
        "season",
        "today",
        "news",
        "best",
        "free",
        "online",
        "near",
        "how",
        "use",
        "using",
    }
)

NAVIGATION_TOKENS = frozenset(
    {"login", "signin", "sign", "official", "website", "facebook", "instagram", "youtube"}
)

# ``perfume`` is also the title of well-known books/films.  A current query
# containing one of these explicit media intents is safely excludable even
# though it contains the topical word itself.
PERFUME_MEDIA_TOKENS = frozenset(
    {
        "movie",
        "film",
        "novel",
        "book",
        "cast",
        "plot",
        "story",
        "murderer",
        "suskind",
        "imdb",
        "wikipedia",
        "trailer",
        "ending",
    }
)

# Clear unrelated ``finder`` intents seen in production drift.  Terms not in
# this set remain ``unknown`` rather than being over-rejected.
UNRELATED_FINDER_TOKENS = frozenset(
    {"people", "person", "stud", "chord", "constellation", "scale", "key", "phone", "ip", "address"}
)


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


def _is_perfume_context(domain: str, parent_anchor: str) -> bool:
    context = _tokens(domain) | _tokens(parent_anchor)
    return bool(context & {"perfume", "fragrance", "parfum", "cologne"})


def default_domain_relation(domain: str, keyword: str, parent_anchor: str) -> tuple[str, str]:
    """Return a conservative lexical/intent domain decision.

    ``in_scope`` requires a non-generic topical overlap or expression
    containment.  Generic pattern words (``finder``, ``season``...) can never
    establish scope by themselves.  Plausibly related expressions with no
    decisive evidence stay ``unknown`` so they remain reviewable instead of
    being silently discarded.
    """
    candidate_text = canonical_keyword(keyword)
    if not candidate_text:
        return "out_of_scope", "candidate keyword is empty"

    candidate_tokens = _tokens(keyword)
    if candidate_tokens & NAVIGATION_TOKENS and (
        "login" in candidate_tokens or "signin" in candidate_tokens or "official" in candidate_tokens
    ):
        return "out_of_scope", "brand_or_navigation_query"

    perfume_context = _is_perfume_context(domain, parent_anchor)
    if perfume_context and candidate_tokens & PERFUME_MEDIA_TOKENS:
        return "out_of_scope", "perfume homonym has explicit film/book/media intent"
    if perfume_context and "finder" in candidate_tokens and candidate_tokens & UNRELATED_FINDER_TOKENS:
        return "out_of_scope", "generic finder query has an explicitly unrelated subject"

    domain_text = canonical_keyword(domain)
    parent_text = canonical_keyword(parent_anchor)
    domain_tokens = _tokens(domain)
    parent_tokens = _tokens(parent_anchor)
    topical_reference_tokens = (domain_tokens | parent_tokens) - GENERIC_RELATION_TOKENS
    shared_topical = candidate_tokens & topical_reference_tokens
    if shared_topical:
        return "in_scope", "candidate shares a non-generic domain or parent-anchor term"

    # Preserve Unicode expression containment for languages where token overlap
    # may be weak, but do not let a generic English pattern become the proof.
    for reference in (domain_text, parent_text):
        if not reference or reference in GENERIC_RELATION_TOKENS:
            continue
        reference_tokens = _tokens(reference)
        if reference_tokens and reference_tokens <= GENERIC_RELATION_TOKENS:
            continue
        if reference in candidate_text:
            return "in_scope", "candidate contains a non-generic domain or parent-anchor expression"

    if candidate_tokens & (domain_tokens | parent_tokens):
        return "unknown", "only generic lexical overlap was observed; semantic review required"
    return "unknown", "lexical domain relationship is not established; semantic review required"


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
        "root_status": parent.get("root_status"),
        "root_verified": parent.get("root_verified") is True,
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
        except HumanInterventionRequired:
            raise
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
