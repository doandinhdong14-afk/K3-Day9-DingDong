"""Independent deterministic re-derivation of a case, owned by the Verifier.

This module never sees an agent's opinion. It reads the CSVs and applies
EC_POLICY_V1 from scratch, which is what makes the Verifier's disagreement with
the LLM pipeline meaningful: two independent paths, one arbiter.
"""

from __future__ import annotations

from typing import Any, Dict, List

from . import assembly, config, policy


def derive(store, case_id: str, order_id: str) -> Dict[str, Any]:
    core = store.get_order_core(order_id)
    items_view = store.get_order_items(order_id)
    payments = store.get_payments(order_id)
    charges = store.get_item_charge_totals(order_id)
    timeline = store.get_delivery_timeline(order_id)

    items = items_view["items"]
    item_ids = [f"{order_id}:{i['order_item_id']}" for i in items]
    seller_ids = list(dict.fromkeys(i["seller_id"] for i in items))
    payment_ids = [f"{order_id}:{p['payment_sequential']}" for p in payments["payments"]]
    late_seller_ids = list(dict.fromkeys(i["seller_id"] for i in items if i["handoff_after_limit"]))

    item_total = charges["item_total_brl"]
    freight_total = charges["freight_total_brl"]
    payment_total = payments["payment_total_brl"]
    delta = round(payment_total - charges["expected_charge_brl"], 2)
    reconciled = abs(delta) <= config.PAYMENT_TOLERANCE_BRL

    facts = {
        "order_found": core.get("found", False),
        "order_status": core.get("order_status", ""),
        "has_item_rows": bool(items),
        "item_count": len(items),
        "payment_row_count": len(payments["payments"]),
        "is_split_payment": len(payments["payments"]) >= 2,
        "reconciled": reconciled,
        "delta_brl": delta,
        "delivered": bool(timeline.get("order_delivered_customer_date")),
        "delivered_after_estimate": bool(timeline.get("delivered_after_estimate")),
        "carrier_handoff_recorded": bool(core.get("order_delivered_carrier_date")),
        "seller_handoff_late": bool(late_seller_ids),
        "late_seller_ids": late_seller_ids,
    }

    issue = _classify(facts, payment_total)
    spec = policy.ISSUE_SPEC[issue]
    refund = {
        "payment_total": payment_total,
        "freight_total": freight_total,
        "none": 0.0,
    }[spec["refund_basis"]]

    responsible_parties: List[Dict[str, str]] = []
    if spec["party_type"] == "seller":
        for seller_id in (late_seller_ids or seller_ids)[: config.MAX_RESPONSIBLE_PARTIES]:
            responsible_parties.append({"party_type": "seller", "party_id": seller_id})
    elif spec["party_type"]:
        responsible_parties.append({"party_type": spec["party_type"], "party_id": spec["party_id"]})

    document = assembly.build_document(
        case_id=case_id,
        order_id=order_id,
        primary_issue=issue,
        case_status=spec["case_status"],
        confidence=spec["base_confidence"],
        item_ids=item_ids,
        seller_ids=seller_ids,
        payment_ids=payment_ids,
        root_cause=spec["root_cause"],
        responsible_parties=responsible_parties,
        item_total=item_total,
        freight_total=freight_total,
        payment_total=payment_total,
        refund=round(refund, 2),
        actions=[spec["action"]],
    )
    return {"document": document, "facts": facts}


def _classify(facts: Dict[str, Any], payment_total: float) -> str:
    """EC_POLICY_V1 precedence, first match wins."""
    if facts["order_status"] == "canceled" and payment_total > 0:
        return "canceled_order_paid"
    if facts["order_status"] == "unavailable" and payment_total > 0:
        return "unavailable_order_paid"
    if facts["delivered_after_estimate"]:
        return "late_delivery_seller" if facts["seller_handoff_late"] else "late_delivery_logistics"
    if facts["is_split_payment"] and facts["reconciled"]:
        return "valid_split_payment"
    return "unsupported_late_claim"
