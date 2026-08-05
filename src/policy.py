"""EC_POLICY_V1 as data.

Single source of truth for the rule table, shared by the Policy Agent's prompt
and by the Verifier's independent re-derivation. Keeping it in one place means
the two paths can disagree about a *case* but never about the *policy*.
"""

from __future__ import annotations

from typing import Any, Dict

# Ordered by the precedence the README mandates. First match wins.
ISSUE_ORDER = [
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
]

ISSUE_SPEC: Dict[str, Dict[str, Any]] = {
    "canceled_order_paid": {
        "root_cause": "ORDER_CANCELED_AFTER_PAYMENT",
        "party_type": "platform",
        "party_id": "OLIST_PLATFORM",
        "refund_basis": "payment_total",
        "action": "issue_full_refund",
        "case_status": "action_required",
        "base_confidence": 0.97,
        "condition": "order_status = canceled and payment total > 0",
    },
    "unavailable_order_paid": {
        "root_cause": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
        "party_type": "platform",
        "party_id": "OLIST_PLATFORM",
        "refund_basis": "payment_total",
        "action": "issue_full_refund",
        "case_status": "action_required",
        "base_confidence": 0.97,
        "condition": "order_status = unavailable and payment total > 0",
    },
    "late_delivery_seller": {
        "root_cause": "SELLER_HANDOFF_AFTER_LIMIT",
        "party_type": "seller",
        "party_id": None,  # the violating seller_id
        "refund_basis": "freight_total",
        "action": "refund_freight",
        "case_status": "action_required",
        "base_confidence": 0.95,
        "condition": "delivered after estimated date AND carrier picked up after shipping_limit_date",
    },
    "late_delivery_logistics": {
        "root_cause": "CARRIER_DELIVERED_AFTER_ESTIMATE",
        "party_type": "logistics_provider",
        "party_id": "LOGISTICS_PROVIDER",
        "refund_basis": "freight_total",
        "action": "refund_freight",
        "case_status": "action_required",
        "base_confidence": 0.95,
        "condition": "delivered after estimated date AND carrier picked up no later than shipping_limit_date",
    },
    "valid_split_payment": {
        "root_cause": "MULTIPLE_PAYMENTS_RECONCILED",
        "party_type": None,
        "party_id": None,
        "refund_basis": "none",
        "action": "explain_valid_split_payment",
        "case_status": "no_action",
        "base_confidence": 0.93,
        "condition": ">= 2 payment rows and payment total matches item + freight within 0.10 BRL",
    },
    "unsupported_late_claim": {
        "root_cause": "DELIVERY_WITHIN_ESTIMATE",
        "party_type": None,
        "party_id": None,
        "refund_basis": "none",
        "action": "reject_late_refund",
        "case_status": "no_action",
        "base_confidence": 0.91,
        "condition": "delivered no later than estimated date and payment reconciles",
    },
}

VALID_ROOT_CAUSES = {spec["root_cause"] for spec in ISSUE_SPEC.values()}
VALID_ACTIONS = {spec["action"] for spec in ISSUE_SPEC.values()}
VALID_CASE_STATUS = {"action_required", "no_action"}


def rule_text(issue: str) -> str:
    """Just the one rule, for prompts that already know the classification.

    The Verifier audits a decision that has already been made, so shipping the
    whole table there wastes a scarce tokens-per-minute budget.
    """
    spec = ISSUE_SPEC.get(issue)
    if spec is None:
        return f"Unknown primary_issue '{issue}'. Any document claiming it is non-compliant."
    party = spec["party_id"] or (spec["party_type"] or "nobody")
    if issue == "late_delivery_seller":
        party = "the seller_id that handed off late"
    refund = {
        "payment_total": "the full payment total",
        "freight_total": "the freight total",
        "none": "0",
    }[spec["refund_basis"]]
    return (
        f"EC_POLICY_V1 rule for '{issue}':\n"
        f"  condition:       {spec['condition']}\n"
        f"  root_cause_code: {spec['root_cause']}\n"
        f"  responsible:     {party}\n"
        f"  refund:          {refund}\n"
        f"  action:          {spec['action']}\n"
        f"  case_status:     {spec['case_status']}"
    )


def policy_table_text() -> str:
    """Human-readable rule table injected into the Policy Agent prompt."""
    lines = ["EC_POLICY_V1 - evaluate in this exact order, first match wins:"]
    for index, issue in enumerate(ISSUE_ORDER, start=1):
        spec = ISSUE_SPEC[issue]
        party = spec["party_id"] or (spec["party_type"] or "none")
        if issue == "late_delivery_seller":
            party = "the seller_id that handed off late"
        refund = {
            "payment_total": "the full payment total",
            "freight_total": "the freight total",
            "none": "0",
        }[spec["refund_basis"]]
        lines.append(
            f"{index}. {issue}\n"
            f"   condition: {spec['condition']}\n"
            f"   root_cause_code: {spec['root_cause']}\n"
            f"   responsible: {party}\n"
            f"   refund: {refund}   action: {spec['action']}   case_status: {spec['case_status']}"
        )
    return "\n".join(lines)
