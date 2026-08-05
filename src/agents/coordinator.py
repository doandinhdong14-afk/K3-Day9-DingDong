"""Coordinator Agent — dispatch, merge, draft, escalate to the verifier.

Flow for one case:

    coordinator --(case brief)--> order_seller | payment | delivery   (parallel)
              <--(3 findings)---
    coordinator --(3 findings)--> policy_agent
              <--(decision)-----
    coordinator  builds the draft document from the findings + decision
    coordinator --(draft)-------> verifier_agent
              <--(verified doc)-- written to output/<case_id>.json

The coordinator holds no data scope beyond an existence probe: everything it
knows about the order arrives through handoffs.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from .. import assembly, config
from ..protocol import CaseContext, Handoff
from .base import Agent
from .delivery_agent import DeliveryAgent
from .order_seller_agent import OrderSellerAgent
from .payment_agent import PaymentAgent
from .policy_agent import PolicyAgent
from .verifier_agent import VerifierAgent


class CoordinatorAgent(Agent):
    name = "coordinator_agent"
    emits = "draft_document"

    def __init__(self, store, llm, tracer) -> None:
        super().__init__(store, llm, tracer)
        self.order_seller = OrderSellerAgent(store, llm, tracer)
        self.payment = PaymentAgent(store, llm, tracer)
        self.delivery = DeliveryAgent(store, llm, tracer)
        self.policy = PolicyAgent(store, llm, tracer)
        self.verifier = VerifierAgent(store, llm, tracer)

    # ------------------------------------------------------------------ main
    def handle_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        context = CaseContext(
            case_id=case["case_id"],
            order_id=case["customer_request"]["claimed_order_id"],
            opened_at=case.get("opened_at", ""),
            customer_message=case["customer_request"].get("message", ""),
            policy_version=case.get("policy_version", config.POLICY_VERSION),
        )
        self._begin(context)
        index = self.data.get_case_index(context.order_id)
        self.tracer.emit("case_start", context.case_id, self.name, **index)

        if not index["order_found"]:
            # Not reachable for the official 50 cases, but the pipeline must not
            # fabricate an investigation for an order that does not exist.
            self.tracer.emit("order_not_found", context.case_id, self.name, order_id=context.order_id)

        # --- fan out to the three domain specialists ----------------------
        with ThreadPoolExecutor(max_workers=config.AGENT_WORKERS) as pool:
            futures = [
                pool.submit(self.order_seller.run, context),
                pool.submit(self.payment.run, context),
                pool.submit(self.delivery.run, context),
            ]
            for future in futures:
                future.result()

        # --- policy classification ----------------------------------------
        decision = self.policy.run(context)

        # --- draft assembled from what the agents reported ------------------
        draft = self._draft(context, decision)
        self._handoff(
            context,
            receiver="verifier_agent",
            payload={"document": draft},
            model=None,
            confidence=decision.payload["confidence"],
            notes="draft built from agent findings, unverified",
        )

        # --- verification gate ---------------------------------------------
        verified = self.verifier.run(context)
        document = verified.payload["document"]

        self.tracer.emit(
            "case_complete",
            context.case_id,
            self.name,
            primary_issue=document["assessment"]["primary_issue"],
            case_status=document["assessment"]["case_status"],
            confidence=document["assessment"]["confidence"],
            recommended_refund_brl=document["financial_resolution"]["recommended_refund_brl"],
            pipeline_agreed=verified.payload["pipeline_agreed"],
            repair_count=len(verified.payload["repairs"]),
            handoff_count=len(context.handoffs),
        )
        return {
            "document": document,
            "draft": draft,
            "context": context,
            "verification": verified.payload,
        }

    # ----------------------------------------------------------------- draft
    def _draft(self, context: CaseContext, decision: Handoff) -> Dict[str, Any]:
        order = context.find("order_seller_finding").payload
        payment = context.find("payment_finding").payload
        call = decision.payload

        parties: List[Dict[str, str]] = []
        party_type = call.get("responsible_party_type", "none")
        party_id = call.get("responsible_party_id", "")
        if party_type in ("seller", "logistics_provider", "platform") and party_id:
            parties.append({"party_type": party_type, "party_id": party_id})

        return assembly.build_document(
            case_id=context.case_id,
            order_id=context.order_id,
            primary_issue=call["primary_issue"],
            case_status=call["case_status"],
            confidence=call["confidence"],
            item_ids=order.get("item_ids", []),
            seller_ids=order.get("seller_ids", []),
            payment_ids=payment.get("payment_ids", []),
            root_cause=call["root_cause_code"],
            responsible_parties=parties,
            item_total=order.get("item_total_brl", 0.0),
            freight_total=order.get("freight_total_brl", 0.0),
            payment_total=payment.get("payment_total_brl", 0.0),
            refund=call.get("recommended_refund_brl", 0.0),
            actions=[call["resolution_action"]],
        )
