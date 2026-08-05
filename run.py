#!/usr/bin/env python3
"""Entry point: run the multi-agent pipeline over every case in `input/`.

    python3 run.py                 # full LLM run, writes output/, logging/, metadata.json
    python3 run.py --cases EC_001 EC_002
    python3 run.py --self-check    # deterministic engine only, no API calls, writes nothing

Requires OPENROUTER_API_KEY in `.env` (see `.env.example`) for anything but
`--self-check`.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import shutil
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from src import assembly, config, ground_truth
from src.agents import CoordinatorAgent
from src.llm import LLMClient
from src.olist_store import OlistStore
from src.tracing import Tracer


# ---------------------------------------------------------------------- io
def load_cases(case_filter: List[str]) -> List[Dict[str, Any]]:
    cases = []
    for path in sorted(glob.glob(os.path.join(config.INPUT_DIR, "EC_*.json"))):
        with open(path, encoding="utf-8") as handle:
            case = json.load(handle)
        if not case_filter or case["case_id"] in case_filter:
            cases.append(case)
    return cases


def write_output(document: Dict[str, Any]) -> str:
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    path = os.path.join(config.OUTPUT_DIR, f"{document['case_id']}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def write_metadata(payload: Dict[str, Any]) -> None:
    for path in (
        os.path.join(config.LOG_DIR, "metadata.json"),
        os.path.join(config.REPO_ROOT, "metadata.json"),
    ):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


# ------------------------------------------------------------------ modes
def self_check(cases: List[Dict[str, Any]]) -> int:
    """Validate the deterministic engine and schema without touching the API."""
    store = OlistStore()
    issues: Dict[str, int] = {}
    failures = 0
    for case in cases:
        order_id = case["customer_request"]["claimed_order_id"]
        result = ground_truth.derive(store, case["case_id"], order_id)
        document = result["document"]
        errors = assembly.validate_document(document, store=store)
        issue = document["assessment"]["primary_issue"]
        issues[issue] = issues.get(issue, 0) + 1
        if errors:
            failures += 1
            print(f"  [FAIL] {case['case_id']}: {errors}")
    print(f"\nself-check: {len(cases)} cases, {failures} schema failures")
    for issue, count in sorted(issues.items(), key=lambda kv: -kv[1]):
        print(f"  {issue:<26} {count}")
    return 1 if failures else 0


def run_pipeline(cases: List[Dict[str, Any]], workers: int) -> int:
    run_id = uuid.uuid4().hex[:12]
    started = time.time()

    store = OlistStore()
    llm = LLMClient()
    tracer = Tracer(os.path.join(config.LOG_DIR, "trace.jsonl"), run_id)
    tracer.emit(
        "run_start",
        run_start_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        case_count=len(cases),
        provider=llm.provider,
        primary_model=llm.primary_model,
        model_pool=[m["name"] for m in llm.models],
        max_params_b=config.MAX_PARAMS_B,
        workers=workers,
    )
    print(f"provider: {llm.provider}  primary model: {llm.primary_model}")

    coordinator = CoordinatorAgent(store, llm, tracer)
    results: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []

    def process(case: Dict[str, Any]) -> None:
        try:
            results[case["case_id"]] = coordinator.handle_case(case)
        except Exception as exc:  # keep one bad case from sinking the batch
            errors.append(f"{case['case_id']}: {exc}")
            tracer.emit("case_failed", case["case_id"], "coordinator_agent", error=str(exc)[:400])

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(process, cases))

    # ---- fall back to the deterministic engine for any case that crashed --
    for case in cases:
        if case["case_id"] in results:
            continue
        truth = ground_truth.derive(store, case["case_id"], case["customer_request"]["claimed_order_id"])
        results[case["case_id"]] = {
            "document": truth["document"],
            "draft": None,
            "verification": {"repairs": [], "pipeline_agreed": False, "recovered": True},
        }
        tracer.emit("case_recovered", case["case_id"], "coordinator_agent", mode="deterministic_engine")

    for case_id in sorted(results):
        write_output(results[case_id]["document"])

    # ---------------------------------------------------------- reporting --
    agreed = sum(1 for r in results.values() if r["verification"].get("pipeline_agreed"))
    repaired_fields: Dict[str, int] = {}
    for result in results.values():
        for repair in result["verification"].get("repairs", []):
            key = repair["field"]
            repaired_fields[key] = repaired_fields.get(key, 0) + 1

    schema_failures = []
    for case_id, result in results.items():
        problems = assembly.validate_document(result["document"], store=store)
        if problems:
            schema_failures.append((case_id, problems))

    duration = round(time.time() - started, 1)
    tracer.emit(
        "run_complete",
        cases=len(results),
        llm_pipeline_agreed=agreed,
        repaired_cases=len(results) - agreed,
        schema_failures=len(schema_failures),
        duration_s=duration,
        llm_calls=llm.stats["calls"],
        failed_calls=llm.stats["failed_calls"],
        json_repairs=llm.stats["json_repairs"],
    )
    trace_path = tracer.path
    tracer.close()
    shutil.copyfile(trace_path, os.path.join(config.REPO_ROOT, "trace.jsonl"))

    write_metadata(
        {
            "run_id": run_id,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "task": "K3 Day 9 - Multi-Agent E-commerce Dispute Resolution (Olist)",
            "framework": "custom multi-agent orchestration (Python standard library only, no agent framework)",
            "provider": llm.provider,
            "api_base": llm.base_url,
            "model": llm.primary_model,
            "parameter_size": f"{llm.models[0]['params_b']:g}B",
            "parameter_size_billions": llm.models[0]["params_b"],
            "constraint_max_parameter_size_billions": config.MAX_PARAMS_B,
            "model_pool": llm.models,
            "models_actually_used": llm.stats["model_calls"],
            "agents": {
                name: llm.primary_model
                for name in (
                    "coordinator_agent",
                    "order_seller_agent",
                    "payment_agent",
                    "delivery_agent",
                    "policy_agent",
                    "verifier_agent",
                )
            },
            "agent_notes": {
                "coordinator_agent": "orchestration only; no LLM call of its own",
                "verifier_agent": "deterministic re-derivation is authoritative; the LLM sign-off is advisory",
            },
            "sampling": {"temperature": config.TEMPERATURE, "max_tokens": config.MAX_TOKENS},
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "duration_seconds": duration,
                "case_workers": workers,
                "cases_processed": len(results),
                "llm_calls": llm.stats["calls"],
                "failed_llm_calls": llm.stats["failed_calls"],
                "json_repairs": llm.stats["json_repairs"],
                "prompt_tokens": llm.stats["prompt_tokens"],
                "completion_tokens": llm.stats["completion_tokens"],
            },
            "quality": {
                "cases": len(results),
                "llm_pipeline_matched_verifier": agreed,
                "cases_repaired_by_verifier": len(results) - agreed,
                "schema_failures": len(schema_failures),
                "most_repaired_fields": dict(
                    sorted(repaired_fields.items(), key=lambda kv: -kv[1])[:10]
                ),
            },
        }
    )

    print(f"\n=== run {run_id} finished in {duration}s ===")
    print(f"cases written        : {len(results)} -> {config.OUTPUT_DIR}")
    print(f"llm calls            : {llm.stats['calls']} (failed {llm.stats['failed_calls']}, "
          f"json repairs {llm.stats['json_repairs']})")
    print(f"models used          : {llm.stats['model_calls']}")
    print(f"verifier agreement   : {agreed}/{len(results)} cases needed no repair")
    if repaired_fields:
        print("most repaired fields :")
        for field, count in sorted(repaired_fields.items(), key=lambda kv: -kv[1])[:8]:
            print(f"    {field:<50} {count}")
    print(f"schema failures      : {len(schema_failures)}")
    for case_id, problems in schema_failures:
        print(f"    {case_id}: {problems}")
    if errors:
        print(f"case exceptions      : {len(errors)}")
        for error in errors:
            print(f"    {error}")
    print(f"trace                : {trace_path} ({tracer.event_count} events)")
    return 1 if schema_failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-agent EC dispute resolution")
    parser.add_argument("--cases", nargs="*", default=[], help="case ids to run (default: all)")
    parser.add_argument("--workers", type=int, default=config.CASE_WORKERS)
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="deterministic engine + schema validation only; makes no API calls and writes no output",
    )
    args = parser.parse_args()

    cases = load_cases(args.cases)
    if not cases:
        print("no cases found in input/", file=sys.stderr)
        return 1
    print(f"loaded {len(cases)} case(s) from {config.INPUT_DIR}")

    if args.self_check:
        return self_check(cases)
    return run_pipeline(cases, args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
