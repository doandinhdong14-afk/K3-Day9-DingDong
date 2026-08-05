"""Verifier Agent — the last gate before a file is written.

It runs two independent checks on the Coordinator's draft:

1. **Deterministic re-derivation** (`ground_truth.derive`). It reads the CSVs
   itself and rebuilds the answer without looking at any agent opinion. Every
   field where the draft disagrees is repaired, and the repair is written to
   `trace.jsonl` so the LLM pipeline's real accuracy stays measurable.
2. **LLM compliance sign-off.** A <=10B model reviews the repaired document
   against EC_POLICY_V1 and reports violations. Its verdict is *advisory*: it
   can lower confidence and raise flags, it cannot overrule re-derived facts.
   Facts come from data, not from a model — that ordering is deliberate.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .. import assembly, ground_truth, policy
from ..protocol import CaseContext, Handoff
from .base import Agent

SYSTEM = """You are the Verifier Agent in an e-commerce dispute investigation team.
You audit a finished resolution document against EC_POLICY_V1 before it is filed.

Check for:
- primary_issue consistent with the case_status, the root cause code and the action.
- refund amount consistent with the issue (full payment for canceled/unavailable,
  freight for late delivery, zero when no action is required).
- a responsible party present exactly when the issue assigns one.
- evidence that supports the decision.

You are auditing, not re-investigating. Answer with a single JSON object and nothing else."""

USER_TEMPLATE = """{table}

RESOLUTION DOCUMENT UNDER AUDIT:
{document}

Return exactly this JSON shape:
{{
  "compliant": <true|false>,
  "violations": ["<short description>", ...],
  "confidence_in_document": <number between 0 and 1>
}}"""


class VerifierAgent(Agent):
    name = "verifier_agent"
    emits = "verified_document"

    def run(self, context: CaseContext) -> Handoff:
        self._begin(context)
        draft_handoff = context.find("draft_document")
        draft = draft_handoff.payload["document"]

        # --- 1. deterministic re-derivation -------------------------------
        truth = ground_truth.derive(self.data, context.case_id, context.order_id)
        expected = truth["document"]
        discrepancies = assembly.diff_documents(draft, expected)
        repairs = [
            {"field": field, "draft": _trim(before), "corrected": _trim(after)}
            for field, before, after in discrepancies
            if field != "assessment.confidence"
        ]
        if repairs:
            self.tracer.emit(
                "verifier_override",
                context.case_id,
                self.name,
                repair_count=len(repairs),
                repairs=repairs,
            )

        document = json.loads(json.dumps(expected))  # authoritative copy

        # --- 2. LLM compliance sign-off (advisory) -------------------------
        raw = self._ask(
            context,
            SYSTEM,
            USER_TEMPLATE.format(
                table=policy.rule_text(document["assessment"]["primary_issue"]),
                document=json.dumps(document, ensure_ascii=False, separators=(",", ":")),
            ),
            {"compliant": True, "violations": [], "confidence_in_document": 0.9},
        )
        violations = [str(v)[:160] for v in self.as_str_list(raw.get("violations"))]
        compliant = self.as_bool(raw.get("compliant"), True)

        # --- 3. schema + referential integrity ----------------------------
        schema_errors = assembly.validate_document(document, store=self.data)
        if schema_errors:  # would be a bug in our own builder, so make it loud
            self.tracer.emit(
                "schema_violation", context.case_id, self.name, errors=schema_errors
            )

        document["assessment"]["confidence"] = assembly.confidence_for(
            document["assessment"]["primary_issue"],
            repair_count=len(repairs),
            advisory_flags=0 if compliant else len(violations) or 1,
        )

        self.tracer.emit(
            "verifier_report",
            context.case_id,
            self.name,
            deterministic_repairs=len(repairs),
            llm_compliant=compliant,
            llm_violations=violations,
            schema_errors=schema_errors,
            final_confidence=document["assessment"]["confidence"],
        )

        return self._handoff(
            context,
            receiver="coordinator_agent",
            payload={
                "document": document,
                "repairs": repairs,
                "llm_compliant": compliant,
                "llm_violations": violations,
                "schema_errors": schema_errors,
                "pipeline_agreed": not repairs,
                "facts": truth["facts"],
            },
            model=raw.get("_model"),
            confidence=document["assessment"]["confidence"],
            notes=f"{len(repairs)} field(s) repaired" if repairs else "draft accepted as-is",
            grounded=True,
        )


def _trim(value: Any) -> Any:
    """Keep trace lines readable when a repaired field is a long list."""
    if isinstance(value, list) and len(value) > 6:
        return value[:6] + [f"... (+{len(value) - 6} more)"]
    if isinstance(value, str) and len(value) > 120:
        return value[:120] + "..."
    return value


def summarize_repairs(repairs: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for repair in repairs:
        head = repair["field"].split(".")[0] or "root"
        counts[head] = counts.get(head, 0) + 1
    return counts
