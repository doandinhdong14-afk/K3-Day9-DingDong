"""Payment Agent.

Owns: payment rows, the paid total, and reconciliation against item + freight.

Olist stores one row per payment method, so a "split payment" is simply >= 2
rows. `payment_value` is the amount of that row, not an installment slice, so the
total is a plain sum. Reconciliation passes when |paid - (items + freight)| <= 0.10 BRL.
"""

from __future__ import annotations

from typing import Any, Dict

from .. import config
from ..protocol import CaseContext, Handoff
from .base import Agent

SYSTEM = """You are the Payment Agent in an e-commerce dispute investigation team.
You reconcile what a customer actually paid against what the order should have charged.

Rules you must follow:
- payment_value is the amount of that payment row, NOT one installment. Sum the rows as they are.
- A split payment means the order has 2 or more payment rows.
- Reconciled means |payment_total - (item_total + freight_total)| <= 0.10 BRL.
- Round every amount to 2 decimals. Never invent a payment row or a refund ledger.

Answer with a single JSON object and nothing else."""

USER_TEMPLATE = """{facts}

Step 1. List every payment_value from the rows above, then add them up into
payment_total_brl. Add the amounts exactly as written, cent by cent.

Step 2. expected_total_brl = item_total_brl + freight_total_brl.

Worked example: item_total 27.70 + freight 15.10 -> expected_total 42.80.
  A single payment row of 42.80 gives delta 0.00, so it reconciles.

Step 3. delta_brl = payment_total_brl - expected_total_brl.
Step 4. reconciled = |delta_brl| <= {tolerance}.
Step 5. is_split_payment = the order has 2 or more payment rows.

Return exactly this JSON shape:
{{
  "payment_values": [<every payment_value, copied>],
  "payment_row_count": <int>,
  "payment_total_brl": <number>,
  "expected_total_brl": <number>,
  "is_split_payment": <true|false>,
  "delta_brl": <number>,
  "reconciled": <true|false>,
  "reasoning": "<one short sentence>"
}}"""


class PaymentAgent(Agent):
    name = "payment_agent"
    emits = "payment_finding"

    def run(self, context: CaseContext) -> Handoff:
        self._begin(context)
        payments = self.data.get_payments(context.order_id)
        charges = self.data.get_item_charge_totals(context.order_id)

        facts = {
            "order_id": context.order_id,
            "payment_rows": payments["payments"],
            "item_total_brl": charges["item_total_brl"],
            "freight_total_brl": charges["freight_total_brl"],
        }
        fallback = self._deterministic(payments, charges)
        raw = self._ask(
            context,
            SYSTEM,
            USER_TEMPLATE.format(
                facts=self.facts_block("PAYMENT FACTS", facts),
                tolerance=config.PAYMENT_TOLERANCE_BRL,
            ),
            fallback,
        )

        # Self-consistency check: the model reports both totals and its own delta.
        # When they contradict, recompute the delta from the two totals it produced
        # — bookkeeping over the model's own numbers, not a correction of them.
        stated_delta = self.as_float(raw.get("delta_brl"), fallback["delta_brl"])
        paid = self.as_float(raw.get("payment_total_brl"), fallback["payment_total_brl"])
        expected = self.as_float(raw.get("expected_total_brl"), -1.0)
        delta = stated_delta
        if expected >= 0:
            derived = round(paid - expected, 2)
            if abs(derived - stated_delta) > 0.001:
                self.tracer.emit(
                    "self_inconsistency",
                    context.case_id,
                    self.name,
                    stated_delta=stated_delta,
                    payment_total=paid,
                    expected_total=expected,
                    resolved_to=derived,
                )
            delta = derived
        reconciled = abs(delta) <= config.PAYMENT_TOLERANCE_BRL

        payload = {
            "order_id": context.order_id,
            "payment_row_count": self.as_int(
                raw.get("payment_row_count"), fallback["payment_row_count"]
            ),
            "payment_sequentials": fallback["payment_sequentials"],
            "payment_ids": fallback["payment_ids"],
            "payment_total_brl": paid,
            "item_total_brl": charges["item_total_brl"],
            "freight_total_brl": charges["freight_total_brl"],
            "is_split_payment": self.as_bool(
                raw.get("is_split_payment"), fallback["is_split_payment"]
            ),
            "delta_brl": delta,
            "reconciled": reconciled,
            "reasoning": str(raw.get("reasoning", ""))[:220],
        }
        return self._handoff(
            context,
            receiver="policy_agent",
            payload=payload,
            model=raw.get("_model"),
            confidence=0.85 if raw.get("_degraded") else 0.95,
            notes="degraded to deterministic fallback" if raw.get("_degraded") else "",
            grounded=not raw.get("_degraded", False),
        )

    @staticmethod
    def _deterministic(payments: Dict[str, Any], charges: Dict[str, Any]) -> Dict[str, Any]:
        rows = payments["payments"]
        total = payments["payment_total_brl"]
        delta = round(total - charges["expected_charge_brl"], 2)
        return {
            "payment_row_count": len(rows),
            "payment_sequentials": [p["payment_sequential"] for p in rows],
            "payment_ids": [f"{payments['order_id']}:{p['payment_sequential']}" for p in rows],
            "payment_total_brl": total,
            "is_split_payment": len(rows) >= 2,
            "delta_brl": delta,
            "reconciled": abs(delta) <= config.PAYMENT_TOLERANCE_BRL,
            "reasoning": "deterministic fallback",
        }
