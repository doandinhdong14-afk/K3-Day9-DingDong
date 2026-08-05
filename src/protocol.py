"""A2A message envelope shared by every agent.

Agents never read each other's internals. They exchange `Handoff` envelopes:
a typed payload plus the provenance needed to audit the decision later
(which agent produced it, on which model, from which tool calls, and whether
the LLM finding had to be repaired by the deterministic ground truth).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Handoff:
    """One agent-to-agent message."""

    case_id: str
    sender: str
    receiver: str
    intent: str                                   # e.g. "order_seller_finding"
    payload: Dict[str, Any]
    tools_used: List[str] = field(default_factory=list)
    model: Optional[str] = None
    confidence: float = 1.0
    notes: str = ""
    grounded: bool = True                         # False => LLM finding failed validation
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "case_id": self.case_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "intent": self.intent,
            "payload": self.payload,
            "tools_used": self.tools_used,
            "model": self.model,
            "confidence": self.confidence,
            "grounded": self.grounded,
            "notes": self.notes,
        }

    def brief(self) -> str:
        """Compact rendering handed to downstream agents as prompt context."""
        import json

        return json.dumps(self.payload, ensure_ascii=False, sort_keys=True)


@dataclass
class CaseContext:
    """Everything known about one dispute case as it moves through the pipeline."""

    case_id: str
    order_id: str
    opened_at: str
    customer_message: str
    policy_version: str
    handoffs: List[Handoff] = field(default_factory=list)

    def add(self, handoff: Handoff) -> Handoff:
        self.handoffs.append(handoff)
        return handoff

    def find(self, intent: str) -> Optional[Handoff]:
        for handoff in reversed(self.handoffs):
            if handoff.intent == intent:
                return handoff
        return None
