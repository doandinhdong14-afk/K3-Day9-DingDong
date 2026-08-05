"""Policy Agent.

Has **no data access at all**: it reasons purely over the three domain handoffs
plus the EC_POLICY_V1 rule table. That is the point of the handoff protocol —
the classification must be defensible from evidence other agents surfaced, not
from a private peek at the CSVs.
"""

from __future__ import annotations

from typing import Any, Dict

from .. import policy
from ..protocol import CaseContext, Handoff
from .base import Agent

SYSTEM = """You are the Policy Agent in an e-commerce dispute investigation team.
Three specialist agents have handed you their findings. Apply EC_POLICY_V1 to classify the case.

Rules you must follow:
- Evaluate the policy conditions strictly in the listed order. The FIRST condition that matches wins.
- Base your decision ONLY on the handed-off findings. You have no database access.
- EVERY customer in this queue claims late delivery. The complaint is not evidence.
  Whether the order was late is decided by delivered_after_estimate in the Delivery
  Agent finding, and by nothing else. If that field is false, the order was NOT late,
  no matter what the customer wrote.
- Never invent refunds, transactions or events that the findings do not support.

Answer with a single JSON object and nothing else."""

USER_TEMPLATE = """{table}

CUSTOMER COMPLAINT (case {case_id}): "{message}"

{order_finding}

{payment_finding}

{delivery_finding}

responsible_party_id is never left blank when a party is assigned. Use exactly:
  - party_type "platform"           -> party_id "OLIST_PLATFORM"
  - party_type "logistics_provider" -> party_id "LOGISTICS_PROVIDER"
  - party_type "seller"             -> party_id = the late seller_id from the order finding
  - party_type "none"               -> party_id "" (only for valid_split_payment and
                                       unsupported_late_claim)

Before classifying, copy the six deciding facts out of the findings above into
"observed". Copy them exactly as reported; do not re-derive them and do not let the
customer's wording change them. Then walk the policy conditions in order against
"observed" and take the first match.

Classify this case. Return exactly this JSON shape:
{{
  "observed": {{
    "order_status": "<from the Order & Seller finding>",
    "payment_total_brl": <from the Payment finding>,
    "delivered_after_estimate": <from the Delivery finding>,
    "seller_handoff_late": <from the Order & Seller finding>,
    "is_split_payment": <from the Payment finding>,
    "reconciled": <from the Payment finding>
  }},
  "primary_issue": "<one of: {issues}>",
  "root_cause_code": "<the matching root cause code>",
  "responsible_party_type": "<seller|logistics_provider|platform|none>",
  "responsible_party_id": "<id string per the rule above>",
  "case_status": "<action_required|no_action>",
  "recommended_refund_brl": <number>,
  "resolution_action": "<the matching action>",
  "confidence": <number between 0 and 1>,
  "reasoning": "<one or two short sentences citing the deciding facts>"
}}"""


class PolicyAgent(Agent):
    name = "policy_agent"
    emits = "policy_decision"

    def run(self, context: CaseContext) -> Handoff:
        self._begin(context)
        order = context.find("order_seller_finding")
        payment = context.find("payment_finding")
        delivery = context.find("delivery_finding")

        prompt = USER_TEMPLATE.format(
            table=policy.policy_table_text(),
            case_id=context.case_id,
            message=context.customer_message,
            order_finding=self.facts_block("ORDER & SELLER AGENT FINDING", order.payload),
            payment_finding=self.facts_block("PAYMENT AGENT FINDING", payment.payload),
            delivery_finding=self.facts_block("DELIVERY AGENT FINDING", delivery.payload),
            issues=", ".join(policy.ISSUE_ORDER),
        )
        fallback = self._deterministic(order.payload, payment.payload, delivery.payload)
        raw = self._ask(context, SYSTEM, prompt, fallback)

        issue = str(raw.get("primary_issue", "")).strip()
        if issue not in policy.ISSUE_SPEC:
            issue = fallback["primary_issue"]
        spec = policy.ISSUE_SPEC[issue]

        payload = {
            "primary_issue": issue,
            "root_cause_code": str(raw.get("root_cause_code", spec["root_cause"])).strip(),
            "responsible_party_type": str(raw.get("responsible_party_type", "")).strip() or "none",
            "responsible_party_id": str(raw.get("responsible_party_id", "")).strip(),
            "case_status": str(raw.get("case_status", spec["case_status"])).strip(),
            "recommended_refund_brl": self.as_float(raw.get("recommended_refund_brl"), 0.0),
            "resolution_action": str(raw.get("resolution_action", spec["action"])).strip(),
            "confidence": max(0.0, min(1.0, self.as_float(raw.get("confidence"), 0.9))),
            "reasoning": str(raw.get("reasoning", ""))[:320],
        }
        return self._handoff(
            context,
            receiver="coordinator_agent",
            payload=payload,
            model=raw.get("_model"),
            confidence=payload["confidence"],
            notes="degraded to deterministic fallback" if raw.get("_degraded") else "",
            grounded=not raw.get("_degraded", False),
        )

    @staticmethod
    def _deterministic(order: Dict[str, Any], payment: Dict[str, Any], delivery: Dict[str, Any]) -> Dict[str, Any]:
        """Rule table applied to the handoffs — used only if the LLM call fails outright."""
        status = order.get("order_status", "")
        paid = payment.get("payment_total_brl", 0.0)
        freight = order.get("freight_total_brl", 0.0)

        if status == "canceled" and paid > 0:
            issue = "canceled_order_paid"
        elif status == "unavailable" and paid > 0:
            issue = "unavailable_order_paid"
        elif delivery.get("delivered_after_estimate"):
            issue = "late_delivery_seller" if order.get("seller_handoff_late") else "late_delivery_logistics"
        elif payment.get("is_split_payment") and payment.get("reconciled"):
            issue = "valid_split_payment"
        else:
            issue = "unsupported_late_claim"

        spec = policy.ISSUE_SPEC[issue]
        refund = {"payment_total": paid, "freight_total": freight, "none": 0.0}[spec["refund_basis"]]
        party_id = spec["party_id"] or ""
        if issue == "late_delivery_seller":
            late_ids = order.get("late_seller_ids") or order.get("seller_ids") or []
            party_id = late_ids[0] if late_ids else ""
        return {
            "primary_issue": issue,
            "root_cause_code": spec["root_cause"],
            "responsible_party_type": spec["party_type"] or "none",
            "responsible_party_id": party_id,
            "case_status": spec["case_status"],
            "recommended_refund_brl": round(refund, 2),
            "resolution_action": spec["action"],
            "confidence": spec["base_confidence"],
            "reasoning": "deterministic fallback",
        }
