"""Order & Seller Agent.

Owns: order status, item rows, seller identity, and the seller's contractual
handoff deadline (`shipping_limit_date`) versus the actual carrier pickup.

The prompt deliberately withholds the store's precomputed `handoff_after_limit`
flag so the model performs the timestamp comparison itself; that judgement is
what the verifier later scores.
"""

from __future__ import annotations

from typing import Any, Dict

from ..protocol import CaseContext, Handoff
from .base import Agent

SYSTEM = """You are the Order & Seller Agent in an e-commerce dispute investigation team.
You examine one order's status, its item rows and each seller's contractual handoff deadline.

Rules you must follow:
- Timestamps are plain strings "YYYY-MM-DD HH:MM:SS" and compare chronologically as written.
- A seller handed off LATE only if order_delivered_carrier_date exists AND is strictly later
  than that seller's shipping_limit_date. An empty carrier date is NOT a late handoff.
- Report only what the data shows. Never invent items, sellers or timestamps.

Answer with a single JSON object and nothing else."""

USER_TEMPLATE = """{facts}

Step 1. For EVERY item row, copy that item's shipping_limit_date and copy the order's
order_delivered_carrier_date into the answer, then compare them chronologically:
compare the year first, then the month, then the day, then the time.
Set handoff_after_limit = true only when the carrier date is strictly LATER than that
item's limit. If order_delivered_carrier_date is empty, handoff_after_limit is false.

Worked examples of the comparison:
  carrier "2017-05-04 09:00:00" vs limit "2017-04-28 18:30:00"
    -> month 05 is later than month 04 -> handoff_after_limit = true
  carrier "2017-05-04 09:00:00" vs limit "2017-05-09 18:30:00"
    -> day 04 is earlier than day 09 -> handoff_after_limit = false
  carrier "" vs limit "2017-05-09 18:30:00"
    -> no carrier pickup recorded -> handoff_after_limit = false

Step 2. item_total_brl = sum of every item price; freight_total_brl = sum of every
freight_value. Round both to 2 decimals.

Step 3. seller_handoff_late = true if ANY item row has handoff_after_limit = true.

Return exactly this JSON shape:
{{
  "order_status": "<status string>",
  "has_item_rows": <true|false>,
  "item_count": <int>,
  "item_checks": [
    {{
      "order_item_id": <int>,
      "seller_id": "<seller_id>",
      "shipping_limit_date": "<copied from the item row>",
      "carrier_date": "<copied from the order>",
      "handoff_after_limit": <true|false>
    }}
  ],
  "seller_ids": ["<seller_id>", ...],
  "item_total_brl": <number>,
  "freight_total_brl": <number>,
  "seller_handoff_late": <true|false>,
  "late_seller_ids": ["<seller_id>", ...],
  "reasoning": "<one short sentence>"
}}"""


class OrderSellerAgent(Agent):
    name = "order_seller_agent"
    emits = "order_seller_finding"

    def run(self, context: CaseContext) -> Handoff:
        self._begin(context)
        core = self.data.get_order_core(context.order_id)
        items_view = self.data.get_order_items(context.order_id)
        seller_ids = list(dict.fromkeys(i["seller_id"] for i in items_view["items"]))
        profiles = self.data.get_seller_profiles(seller_ids)

        # Strip the derived flag: the model must reason from raw timestamps.
        prompt_items = [
            {k: v for k, v in item.items() if k != "handoff_after_limit"}
            for item in items_view["items"]
        ]
        facts = {
            "order_id": context.order_id,
            "order_status": core.get("order_status", "unknown"),
            "order_purchase_timestamp": core.get("order_purchase_timestamp", ""),
            "order_delivered_carrier_date": core.get("order_delivered_carrier_date", ""),
            "item_rows": prompt_items,
            "sellers": profiles["sellers"],
        }

        fallback = self._deterministic(core, items_view, seller_ids)
        raw = self._ask(
            context,
            SYSTEM,
            USER_TEMPLATE.format(facts=self.facts_block("ORDER FACTS", facts)),
            fallback,
        )

        # Aggregate the model's own per-item verdicts. This is bookkeeping over
        # what the model decided, not a correction of it: an 8B model is far more
        # reliable at one date comparison at a time than at an OR across rows.
        checks = raw.get("item_checks") if isinstance(raw.get("item_checks"), list) else []
        checked_late = [
            str(c.get("seller_id", ""))
            for c in checks
            if isinstance(c, dict) and self.as_bool(c.get("handoff_after_limit"))
        ]
        late_flag = self.as_bool(raw.get("seller_handoff_late"), fallback["seller_handoff_late"])
        if checks:
            late_flag = late_flag or bool(checked_late)

        late_ids = [s for s in checked_late if s] or self.as_str_list(raw.get("late_seller_ids"))

        payload = {
            "order_id": context.order_id,
            "order_status": str(raw.get("order_status", fallback["order_status"])),
            "has_item_rows": self.as_bool(raw.get("has_item_rows"), fallback["has_item_rows"]),
            "item_count": self.as_int(raw.get("item_count"), fallback["item_count"]),
            "item_ids": fallback["item_ids"],  # identifiers are structural, not inferred
            "seller_ids": self.as_str_list(raw.get("seller_ids")) or fallback["seller_ids"],
            "item_total_brl": self.as_float(raw.get("item_total_brl"), fallback["item_total_brl"]),
            "freight_total_brl": self.as_float(
                raw.get("freight_total_brl"), fallback["freight_total_brl"]
            ),
            "seller_handoff_late": late_flag,
            "late_seller_ids": list(dict.fromkeys(late_ids)),
            "item_checks": checks,
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
    def _deterministic(core: Dict[str, Any], items_view: Dict[str, Any], seller_ids) -> Dict[str, Any]:
        items = items_view["items"]
        late = [i["seller_id"] for i in items if i["handoff_after_limit"]]
        return {
            "order_status": core.get("order_status", "unknown"),
            "has_item_rows": bool(items),
            "item_count": len(items),
            "item_ids": [f"{items_view['order_id']}:{i['order_item_id']}" for i in items],
            "seller_ids": list(seller_ids),
            "item_total_brl": round(sum(i["price"] for i in items), 2),
            "freight_total_brl": round(sum(i["freight_value"] for i in items), 2),
            "seller_handoff_late": bool(late),
            "late_seller_ids": list(dict.fromkeys(late)),
            "reasoning": "deterministic fallback",
        }
