"""Deterministic data-access layer over the 9 Olist CSVs.

Design note
-----------
No agent touches a CSV directly. Every agent receives a *scoped view*
(`OlistStore.view(agent_name)`) that exposes only the tools its role is allowed
to call; calling anything else raises `AccessDenied`. That keeps the
"who may read what" story in `architecture.md` enforceable rather than
aspirational, and it makes every tool call attributable in `trace.jsonl`.

Money is summed as float then rounded to 2 decimals, exactly as the spec asks.
Timestamps are compared as the raw `YYYY-MM-DD HH:MM:SS` strings from the CSVs
(lexicographic order == chronological order for that fixed-width format), which
avoids inventing a timezone conversion the spec explicitly says not to do.
"""

from __future__ import annotations

import csv
import os
from typing import Any, Callable, Dict, List, Optional

from . import config


class AccessDenied(RuntimeError):
    """Raised when an agent calls a tool outside its granted scope."""


# Which tools each agent may call. Mirrors the table in architecture.md.
AGENT_SCOPES: Dict[str, List[str]] = {
    "order_seller_agent": ["get_order_core", "get_order_items", "get_seller_profiles"],
    "payment_agent": ["get_payments", "get_item_charge_totals"],
    "delivery_agent": ["get_delivery_timeline"],
    "policy_agent": [],          # reasons only over handoffs it receives
    "coordinator_agent": ["get_case_index"],
    "verifier_agent": [          # full read access: it must be able to re-derive everything
        "get_order_core",
        "get_order_items",
        "get_seller_profiles",
        "get_payments",
        "get_item_charge_totals",
        "get_delivery_timeline",
        "get_case_index",
        "entity_exists",
    ],
}


def _money(value: str) -> float:
    return float(value) if value not in (None, "") else 0.0


def _round2(value: float) -> float:
    return round(value + 0.0, 2)


class OlistStore:
    """Loads and indexes the CSVs once, then serves scoped read-only views."""

    def __init__(self, data_dir: str = config.DATA_DIR) -> None:
        self.data_dir = data_dir
        self.orders: Dict[str, dict] = {}
        self.items: Dict[str, List[dict]] = {}
        self.payments: Dict[str, List[dict]] = {}
        self.sellers: Dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------ load
    def _read(self, filename: str):
        path = os.path.join(self.data_dir, filename)
        with open(path, newline="", encoding="utf-8") as handle:
            yield from csv.DictReader(handle)

    def _load(self) -> None:
        for row in self._read("olist_orders_dataset.csv"):
            self.orders[row["order_id"]] = row

        for row in self._read("olist_order_items_dataset.csv"):
            self.items.setdefault(row["order_id"], []).append(row)
        for rows in self.items.values():
            rows.sort(key=lambda r: int(r["order_item_id"]))

        for row in self._read("olist_order_payments_dataset.csv"):
            self.payments.setdefault(row["order_id"], []).append(row)
        for rows in self.payments.values():
            rows.sort(key=lambda r: int(r["payment_sequential"]))

        for row in self._read("olist_sellers_dataset.csv"):
            self.sellers[row["seller_id"]] = row

    # ----------------------------------------------------------------- tools
    def get_case_index(self, order_id: str) -> Dict[str, Any]:
        """Cheap existence probe used by the coordinator before dispatching."""
        return {
            "order_id": order_id,
            "order_found": order_id in self.orders,
            "item_row_count": len(self.items.get(order_id, [])),
            "payment_row_count": len(self.payments.get(order_id, [])),
        }

    def get_order_core(self, order_id: str) -> Dict[str, Any]:
        order = self.orders.get(order_id)
        if order is None:
            return {"order_id": order_id, "found": False}
        return {
            "order_id": order_id,
            "found": True,
            "order_status": order["order_status"],
            "order_purchase_timestamp": order["order_purchase_timestamp"],
            "order_approved_at": order["order_approved_at"],
            "order_delivered_carrier_date": order["order_delivered_carrier_date"],
        }

    def get_order_items(self, order_id: str) -> Dict[str, Any]:
        rows = self.items.get(order_id, [])
        order = self.orders.get(order_id, {})
        carrier_date = order.get("order_delivered_carrier_date", "")
        items = []
        for row in rows:
            limit = row["shipping_limit_date"]
            items.append(
                {
                    "order_item_id": int(row["order_item_id"]),
                    "seller_id": row["seller_id"],
                    "shipping_limit_date": limit,
                    "price": _money(row["price"]),
                    "freight_value": _money(row["freight_value"]),
                    # Handoff is late only when a carrier pickup actually happened
                    # after the seller's contractual limit.
                    "handoff_after_limit": bool(carrier_date) and carrier_date > limit,
                }
            )
        return {
            "order_id": order_id,
            "order_delivered_carrier_date": carrier_date,
            "item_count": len(items),
            "items": items,
        }

    def get_seller_profiles(self, seller_ids: List[str]) -> Dict[str, Any]:
        profiles = []
        for seller_id in seller_ids:
            row = self.sellers.get(seller_id)
            profiles.append(
                {
                    "seller_id": seller_id,
                    "known": row is not None,
                    "seller_city": (row or {}).get("seller_city", ""),
                    "seller_state": (row or {}).get("seller_state", ""),
                }
            )
        return {"seller_count": len(profiles), "sellers": profiles}

    def get_payments(self, order_id: str) -> Dict[str, Any]:
        rows = self.payments.get(order_id, [])
        payments = [
            {
                "payment_sequential": int(r["payment_sequential"]),
                "payment_type": r["payment_type"],
                "payment_installments": int(r["payment_installments"] or 0),
                "payment_value": _money(r["payment_value"]),
            }
            for r in rows
        ]
        return {
            "order_id": order_id,
            "payment_row_count": len(payments),
            "payment_total_brl": _round2(sum(p["payment_value"] for p in payments)),
            "payments": payments,
        }

    def get_item_charge_totals(self, order_id: str) -> Dict[str, Any]:
        rows = self.items.get(order_id, [])
        item_total = _round2(sum(_money(r["price"]) for r in rows))
        freight_total = _round2(sum(_money(r["freight_value"]) for r in rows))
        return {
            "order_id": order_id,
            "item_row_count": len(rows),
            "item_total_brl": item_total,
            "freight_total_brl": freight_total,
            "expected_charge_brl": _round2(item_total + freight_total),
        }

    def get_delivery_timeline(self, order_id: str) -> Dict[str, Any]:
        order = self.orders.get(order_id)
        if order is None:
            return {"order_id": order_id, "found": False}
        delivered = order["order_delivered_customer_date"]
        estimated = order["order_estimated_delivery_date"]
        return {
            "order_id": order_id,
            "found": True,
            "order_status": order["order_status"],
            "order_purchase_timestamp": order["order_purchase_timestamp"],
            "order_delivered_carrier_date": order["order_delivered_carrier_date"],
            "order_delivered_customer_date": delivered,
            "order_estimated_delivery_date": estimated,
            "has_delivery_record": bool(delivered),
            "delivered_after_estimate": bool(delivered) and bool(estimated) and delivered > estimated,
        }

    def entity_exists(self, kind: str, *parts: str) -> bool:
        """Existence check backing evidence-ID validation in the verifier."""
        if kind == "order":
            return parts[0] in self.orders
        if kind == "item":
            order_id, item_id = parts[0], parts[1]
            return any(r["order_item_id"] == str(int(item_id)) for r in self.items.get(order_id, []))
        if kind == "payment":
            order_id, seq = parts[0], parts[1]
            return any(r["payment_sequential"] == str(int(seq)) for r in self.payments.get(order_id, []))
        if kind == "seller":
            return parts[0] in self.sellers
        return False

    # ------------------------------------------------------------------ view
    def view(self, agent_name: str, on_call: Optional[Callable[[str, dict], None]] = None) -> "ScopedStore":
        if agent_name not in AGENT_SCOPES:
            raise AccessDenied(f"unknown agent '{agent_name}' has no declared data scope")
        return ScopedStore(self, agent_name, AGENT_SCOPES[agent_name], on_call)


class ScopedStore:
    """Read-only facade exposing only the tools granted to one agent."""

    def __init__(
        self,
        store: OlistStore,
        agent_name: str,
        allowed: List[str],
        on_call: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self._store = store
        self._agent = agent_name
        self._allowed = set(allowed)
        self._on_call = on_call

    def __getattr__(self, name: str):
        if name not in self._allowed:
            raise AccessDenied(f"agent '{self._agent}' is not granted tool '{name}'")
        tool = getattr(self._store, name)

        def wrapped(*args, **kwargs):
            result = tool(*args, **kwargs)
            if self._on_call is not None:
                self._on_call(name, {"args": [str(a)[:64] for a in args]})
            return result

        return wrapped
