"""Output assembly + schema validation.

Both the Coordinator (drafting from agent handoffs) and the Verifier (rebuilding
from re-derived ground truth) go through `build_document`, so the two candidate
answers are always structurally comparable and only their *content* can differ.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from . import config, policy

EVIDENCE_PATTERNS = {
    "order": re.compile(r"^order:[0-9a-f]{32}$"),
    "item": re.compile(r"^item:[0-9a-f]{32}:\d+$"),
    "payment": re.compile(r"^payment:[0-9a-f]{32}:\d+$"),
    "seller": re.compile(r"^seller:[0-9a-f]{32}$"),
    "policy": re.compile(r"^policy:[A-Z_]+$"),
}


def build_entities(
    order_id: str,
    item_ids: List[str],
    seller_ids: List[str],
    payment_ids: List[str],
) -> Dict[str, List[str]]:
    return {
        "order_ids": [order_id][: config.MAX_ENTITY_IDS],
        "item_ids": list(dict.fromkeys(item_ids))[: config.MAX_ENTITY_IDS],
        "seller_ids": list(dict.fromkeys(seller_ids))[: config.MAX_ENTITY_IDS],
        "payment_ids": list(dict.fromkeys(payment_ids))[: config.MAX_ENTITY_IDS],
    }


def build_evidence(
    order_id: str,
    item_ids: List[str],
    payment_ids: List[str],
    seller_ids: List[str],
    root_cause: str,
) -> List[str]:
    """Evidence in the order the spec's example uses, capped by priority.

    `order:` and `policy:` are always kept — they anchor the case and the rule
    applied. Item / payment / seller rows fill the remaining budget.
    """
    ordered = (
        [f"order:{order_id}"]
        + [f"item:{i}" for i in item_ids]
        + [f"payment:{p}" for p in payment_ids]
        + [f"seller:{s}" for s in seller_ids]
        + [f"policy:{root_cause}"]
    )
    deduped = list(dict.fromkeys(ordered))
    if len(deduped) <= config.MAX_EVIDENCE:
        return deduped

    anchors = [f"order:{order_id}", f"policy:{root_cause}"]
    budget = config.MAX_EVIDENCE - len(anchors)
    middle = [e for e in deduped if e not in anchors][:budget]
    return [anchors[0]] + middle + [anchors[1]]


def build_document(
    case_id: str,
    order_id: str,
    primary_issue: str,
    case_status: str,
    confidence: float,
    item_ids: List[str],
    seller_ids: List[str],
    payment_ids: List[str],
    root_cause: str,
    responsible_parties: List[Dict[str, str]],
    item_total: float,
    freight_total: float,
    payment_total: float,
    refund: float,
    actions: List[str],
) -> Dict[str, Any]:
    entities = build_entities(order_id, item_ids, seller_ids, payment_ids)
    return {
        "case_id": case_id,
        "assessment": {
            "primary_issue": primary_issue,
            "case_status": case_status,
            "confidence": round(max(0.0, min(1.0, confidence)), 2),
        },
        "affected_entities": entities,
        "root_cause_analysis": {
            "ranked_causes": [{"cause_code": root_cause, "rank": 1}][: config.MAX_ROOT_CAUSES],
            "responsible_parties": responsible_parties[: config.MAX_RESPONSIBLE_PARTIES],
        },
        "evidence_ids": build_evidence(
            order_id,
            entities["item_ids"],
            entities["payment_ids"],
            entities["seller_ids"],
            root_cause,
        ),
        "financial_resolution": {
            "currency": config.CURRENCY,
            "item_total_brl": round(item_total, 2),
            "freight_total_brl": round(freight_total, 2),
            "payment_total_brl": round(payment_total, 2),
            "recommended_refund_brl": round(refund, 2),
        },
        "resolution_actions": actions[: config.MAX_ACTIONS],
    }


def validate_document(doc: Dict[str, Any], store=None) -> List[str]:
    """Schema + policy + referential checks. Returns a list of human-readable errors."""
    errors: List[str] = []

    def need(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    need(isinstance(doc.get("case_id"), str) and doc["case_id"].startswith("EC_"), "case_id malformed")

    assessment = doc.get("assessment", {})
    need(assessment.get("primary_issue") in policy.ISSUE_SPEC, "primary_issue not in policy vocabulary")
    need(assessment.get("case_status") in policy.VALID_CASE_STATUS, "case_status invalid")
    confidence = assessment.get("confidence")
    need(isinstance(confidence, (int, float)) and 0.0 <= confidence <= 1.0, "confidence out of [0,1]")

    entities = doc.get("affected_entities", {})
    for key in ("order_ids", "item_ids", "seller_ids", "payment_ids"):
        value = entities.get(key)
        need(isinstance(value, list), f"affected_entities.{key} must be a list")
        if isinstance(value, list):
            need(len(value) <= config.MAX_ENTITY_IDS, f"affected_entities.{key} exceeds {config.MAX_ENTITY_IDS}")

    causes = doc.get("root_cause_analysis", {}).get("ranked_causes", [])
    need(0 < len(causes) <= config.MAX_ROOT_CAUSES, "ranked_causes count out of range")
    for cause in causes:
        need(cause.get("cause_code") in policy.VALID_ROOT_CAUSES, f"unknown cause_code {cause.get('cause_code')}")
        need(isinstance(cause.get("rank"), int), "cause rank must be int")

    parties = doc.get("root_cause_analysis", {}).get("responsible_parties", [])
    need(len(parties) <= config.MAX_RESPONSIBLE_PARTIES, "too many responsible_parties")
    for party in parties:
        need(
            party.get("party_type") in ("seller", "logistics_provider", "platform"),
            f"unknown party_type {party.get('party_type')}",
        )
        need(bool(party.get("party_id")), "responsible party missing party_id")

    evidence = doc.get("evidence_ids", [])
    need(len(evidence) <= config.MAX_EVIDENCE, f"evidence_ids exceeds {config.MAX_EVIDENCE}")
    need(len(evidence) == len(set(evidence)), "duplicate evidence_ids")
    for eid in evidence:
        kind = eid.split(":", 1)[0] if ":" in eid else ""
        pattern = EVIDENCE_PATTERNS.get(kind)
        if pattern is None or not pattern.match(eid):
            errors.append(f"evidence id malformed: {eid}")
            continue
        if store is not None and not _evidence_exists(store, eid):
            errors.append(f"evidence id not found in data: {eid}")

    financials = doc.get("financial_resolution", {})
    need(financials.get("currency") == config.CURRENCY, "currency must be BRL")
    for key in ("item_total_brl", "freight_total_brl", "payment_total_brl", "recommended_refund_brl"):
        value = financials.get(key)
        need(isinstance(value, (int, float)), f"financial_resolution.{key} must be numeric")
        if isinstance(value, (int, float)):
            need(round(value, 2) == value, f"financial_resolution.{key} not rounded to 2 decimals")
            need(value >= 0, f"financial_resolution.{key} negative")

    actions = doc.get("resolution_actions", [])
    need(0 < len(actions) <= config.MAX_ACTIONS, "resolution_actions count out of range")
    for action in actions:
        need(action in policy.VALID_ACTIONS, f"unknown resolution action {action}")

    # Cross-field policy coherence.
    issue = assessment.get("primary_issue")
    if issue in policy.ISSUE_SPEC:
        spec = policy.ISSUE_SPEC[issue]
        need(assessment.get("case_status") == spec["case_status"], "case_status inconsistent with primary_issue")
        need(actions[:1] == [spec["action"]], "resolution_action inconsistent with primary_issue")
        need(
            causes[:1] == [{"cause_code": spec["root_cause"], "rank": 1}],
            "root cause inconsistent with primary_issue",
        )
        refund = financials.get("recommended_refund_brl", 0)
        if spec["case_status"] == "no_action":
            need(refund == 0, "no_action case must have zero refund")
        else:
            need(refund > 0, "action_required case must have a positive refund")

    return errors


def _evidence_exists(store, eid: str) -> bool:
    parts = eid.split(":")
    kind = parts[0]
    if kind == "policy":
        return parts[1] in policy.VALID_ROOT_CAUSES
    try:
        return store.entity_exists(kind, *parts[1:])
    except (IndexError, ValueError):
        return False


def diff_documents(draft: Dict[str, Any], truth: Dict[str, Any]) -> List[Tuple[str, Any, Any]]:
    """Flat field-by-field diff used by the verifier to report repairs."""
    discrepancies: List[Tuple[str, Any, Any]] = []

    def walk(path: str, left: Any, right: Any) -> None:
        if isinstance(right, dict) and isinstance(left, dict):
            for key in right:
                walk(f"{path}.{key}" if path else key, left.get(key), right[key])
        elif isinstance(right, list) and isinstance(left, list):
            if _normalise(left) != _normalise(right):
                discrepancies.append((path, left, right))
        elif left != right:
            discrepancies.append((path, left, right))

    walk("", draft, truth)
    return discrepancies


def _normalise(values: List[Any]) -> Any:
    try:
        return sorted(values, key=repr)
    except TypeError:  # pragma: no cover
        return values


def confidence_for(issue: str, repair_count: int, advisory_flags: int) -> float:
    base: Optional[float] = policy.ISSUE_SPEC.get(issue, {}).get("base_confidence")
    if base is None:
        return 0.5
    score = base - 0.02 * repair_count - 0.01 * advisory_flags
    return round(max(0.60, min(0.99, score)), 2)
