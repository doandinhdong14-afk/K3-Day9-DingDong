"""Delivery Agent.

Owns: the promised delivery date versus the actual delivery to the customer.

It answers only "was this delivered, and was it late?" — attributing the delay to
a seller or to the carrier is the Policy Agent's job, and needs the Order &
Seller Agent's handoff evidence as well.
"""

from __future__ import annotations

from typing import Any, Dict

from ..protocol import CaseContext, Handoff
from .base import Agent

SYSTEM = """You are the Delivery Agent in an e-commerce dispute investigation team.
You compare the promised delivery date with the actual delivery to the customer.

Rules you must follow:
- Timestamps are plain strings "YYYY-MM-DD HH:MM:SS" (or "YYYY-MM-DD 00:00:00") and compare
  chronologically as written. Do not convert timezones.
- Late means order_delivered_customer_date is strictly later than order_estimated_delivery_date.
- If order_delivered_customer_date is empty, the order was never delivered: delivered=false and
  delivered_after_estimate=false. Do not guess a delivery that is not recorded.
- Olist has no per-item tracking checkpoints. Never invent one.

Answer with a single JSON object and nothing else."""

USER_TEMPLATE = """{facts}

Step 1. Copy order_delivered_customer_date into "actual_delivery" and
order_estimated_delivery_date into "promised_delivery". Copy them exactly.

Step 2. Rewrite each date as a plain integer YYYYMMDD (drop the time part), then
compare the two integers. Set delivered_after_estimate = true ONLY when
actual_ymd > promised_ymd. Delivery earlier than promised is ON TIME, not late.
Most orders in this dataset arrive early, so do not assume the complaint is correct.

Worked examples:
  actual "2018-01-31 21:34:47" -> 20180131 ; promised "2018-02-09 00:00:00" -> 20180209
    20180131 < 20180209 -> delivered_after_estimate = false (arrived early)
  actual "2018-06-20 13:52:47" -> 20180620 ; promised "2018-07-04 00:00:00" -> 20180704
    20180620 < 20180704 -> delivered_after_estimate = false (arrived early)
  actual "2018-03-25 14:02:00" -> 20180325 ; promised "2018-03-22 00:00:00" -> 20180322
    20180325 > 20180322 -> delivered_after_estimate = true (3 days late)
  actual "" -> no delivery recorded
    -> delivered = false and delivered_after_estimate = false

Step 3. days_late = whole days from promised to actual, and 0 whenever
delivered_after_estimate is false. days_late is never negative.

Return exactly this JSON shape:
{{
  "actual_delivery": "<copied, or empty string>",
  "promised_delivery": "<copied>",
  "actual_ymd": <integer YYYYMMDD, or 0 if never delivered>,
  "promised_ymd": <integer YYYYMMDD>,
  "delivered": <true|false>,
  "delivered_after_estimate": <true|false>,
  "days_late": <int>,
  "carrier_handoff_recorded": <true|false>,
  "reasoning": "<one short sentence naming both dates>"
}}"""


class DeliveryAgent(Agent):
    name = "delivery_agent"
    emits = "delivery_finding"

    def run(self, context: CaseContext) -> Handoff:
        self._begin(context)
        timeline = self.data.get_delivery_timeline(context.order_id)

        # Withhold the derived boolean so the model does the comparison itself.
        facts = {
            k: v
            for k, v in timeline.items()
            if k not in ("delivered_after_estimate", "has_delivery_record")
        }
        fallback = self._deterministic(timeline)
        raw = self._ask(
            context,
            SYSTEM,
            USER_TEMPLATE.format(facts=self.facts_block("DELIVERY FACTS", facts)),
            fallback,
        )

        # Self-consistency check inside the agent: the model reports both the two
        # dates as YYYYMMDD integers and its own verdict. When those contradict
        # each other, the integers it extracted are the more reliable of its two
        # answers — comparing them is bookkeeping over the model's own output.
        stated = self.as_bool(raw.get("delivered_after_estimate"), fallback["delivered_after_estimate"])
        actual_ymd = self.as_int(raw.get("actual_ymd"), 0)
        promised_ymd = self.as_int(raw.get("promised_ymd"), 0)
        after_estimate = stated
        if actual_ymd and promised_ymd:
            derived = actual_ymd > promised_ymd
            if derived != stated:
                self.tracer.emit(
                    "self_inconsistency",
                    context.case_id,
                    self.name,
                    stated_delivered_after_estimate=stated,
                    actual_ymd=actual_ymd,
                    promised_ymd=promised_ymd,
                    resolved_to=derived,
                )
            after_estimate = derived

        payload = {
            "order_id": context.order_id,
            "order_status": timeline.get("order_status", "unknown"),
            "delivered": self.as_bool(raw.get("delivered"), fallback["delivered"]),
            "delivered_after_estimate": after_estimate,
            "days_late": max(0, self.as_int(raw.get("days_late"), fallback["days_late"])),
            "carrier_handoff_recorded": self.as_bool(
                raw.get("carrier_handoff_recorded"), fallback["carrier_handoff_recorded"]
            ),
            "order_delivered_customer_date": timeline.get("order_delivered_customer_date", ""),
            "order_estimated_delivery_date": timeline.get("order_estimated_delivery_date", ""),
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
    def _deterministic(timeline: Dict[str, Any]) -> Dict[str, Any]:
        delivered_at = timeline.get("order_delivered_customer_date", "")
        estimated = timeline.get("order_estimated_delivery_date", "")
        late = timeline.get("delivered_after_estimate", False)
        days_late = 0
        if late:
            from datetime import datetime

            fmt = "%Y-%m-%d %H:%M:%S"
            try:
                days_late = (
                    datetime.strptime(delivered_at, fmt) - datetime.strptime(estimated, fmt)
                ).days
            except ValueError:
                days_late = 0
        return {
            "delivered": bool(delivered_at),
            "delivered_after_estimate": bool(late),
            "days_late": max(0, days_late),
            "carrier_handoff_recorded": bool(timeline.get("order_delivered_carrier_date")),
            "reasoning": "deterministic fallback",
        }
