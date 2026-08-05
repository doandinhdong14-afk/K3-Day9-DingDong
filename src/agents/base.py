"""Shared plumbing for every agent in the pipeline."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

from ..llm import LLMClient, LLMError
from ..olist_store import OlistStore
from ..protocol import CaseContext, Handoff
from ..tracing import Tracer


class Agent:
    """Base class: scoped data access, tool-call tracing, LLM-with-fallback."""

    name = "agent"
    receives: List[str] = []
    emits = "finding"

    def __init__(self, store: OlistStore, llm: LLMClient, tracer: Tracer) -> None:
        self._store = store
        self.llm = llm
        self.tracer = tracer
        # One agent instance serves several cases concurrently, so the tool log
        # has to be per-thread or provenance from different cases interleaves.
        self._local = threading.local()
        self.data = store.view(self.name, on_call=self._record_tool)

    # ------------------------------------------------------------------ util
    @property
    def _tool_log(self) -> List[str]:
        if not hasattr(self._local, "tools"):
            self._local.tools = []
        return self._local.tools

    def _record_tool(self, tool_name: str, meta: Dict[str, Any]) -> None:
        self._tool_log.append(tool_name)

    def _begin(self, context: CaseContext) -> None:
        self._local.tools = []
        self.tracer.emit("agent_start", context.case_id, self.name, order_id=context.order_id)

    def _ask(
        self,
        context: CaseContext,
        system: str,
        user: str,
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        """One structured LLM turn. On hard failure, degrade to `fallback`."""
        started = time.time()
        try:
            parsed, meta = self.llm.chat_json(system, user)
            self.tracer.emit(
                "llm_call",
                context.case_id,
                self.name,
                model=meta["model"],
                json_repaired=meta["json_repaired"],
                latency_ms=int((time.time() - started) * 1000),
                response=parsed,
            )
            parsed["_model"] = meta["model"]
            return parsed
        except LLMError as exc:
            self.tracer.emit(
                "llm_failure",
                context.case_id,
                self.name,
                error=str(exc)[:300],
                latency_ms=int((time.time() - started) * 1000),
                degraded_to="deterministic_fallback",
            )
            out = dict(fallback)
            out["_model"] = None
            out["_degraded"] = True
            return out

    def _handoff(
        self,
        context: CaseContext,
        receiver: str,
        payload: Dict[str, Any],
        model: Optional[str],
        confidence: float = 1.0,
        notes: str = "",
        grounded: bool = True,
    ) -> Handoff:
        handoff = Handoff(
            case_id=context.case_id,
            sender=self.name,
            receiver=receiver,
            intent=self.emits,
            payload=payload,
            tools_used=list(dict.fromkeys(self._tool_log)),
            model=model,
            confidence=confidence,
            notes=notes,
            grounded=grounded,
        )
        context.add(handoff)
        envelope = {k: v for k, v in handoff.to_dict().items() if k not in ("case_id", "sender")}
        self.tracer.emit("handoff", context.case_id, self.name, **envelope)
        return handoff

    # -------------------------------------------------------------- coercion
    @staticmethod
    def as_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "yes", "1", "y")
        if isinstance(value, (int, float)):
            return bool(value)
        return default

    @staticmethod
    def as_float(value: Any, default: float = 0.0) -> float:
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def as_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def as_str_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v) for v in value if isinstance(v, (str, int)) and str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    @staticmethod
    def facts_block(title: str, facts: Dict[str, Any]) -> str:
        return f"{title}:\n{json.dumps(facts, ensure_ascii=False, indent=2, sort_keys=True)}"

    def run(self, context: CaseContext) -> Handoff:  # pragma: no cover - interface
        raise NotImplementedError
