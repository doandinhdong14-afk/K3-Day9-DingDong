#!/usr/bin/env python3
"""Pre-submission gate for `output/`.

    python3 verify_output.py          # validate only
    python3 verify_output.py --zip    # validate, then build output.zip

Checks, in order:
  1. exactly EC_001.json .. EC_050.json, nothing else
  2. every document passes the full schema + policy-coherence validator
  3. every evidence ID actually resolves against the Olist CSVs
  4. case_id inside each file matches its filename
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from typing import List

from src import assembly, config
from src.olist_store import OlistStore

EXPECTED = [f"EC_{i:03d}.json" for i in range(1, 51)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", action="store_true", help="write output.zip after validation")
    args = parser.parse_args()

    present = sorted(f for f in os.listdir(config.OUTPUT_DIR) if not f.startswith("."))
    problems: List[str] = []

    missing = [f for f in EXPECTED if f not in present]
    extra = [f for f in present if f not in EXPECTED]
    if missing:
        problems.append(f"missing {len(missing)} file(s): {missing[:5]}")
    if extra:
        problems.append(f"unexpected file(s) in output/: {extra}")

    store = OlistStore()
    issues = {}
    refund_total = 0.0
    for filename in EXPECTED:
        path = os.path.join(config.OUTPUT_DIR, filename)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        if document.get("case_id") != filename[: -len(".json")]:
            problems.append(f"{filename}: case_id mismatch ({document.get('case_id')})")
        errors = assembly.validate_document(document, store=store)
        if errors:
            problems.append(f"{filename}: {errors}")
        issue = document.get("assessment", {}).get("primary_issue", "?")
        issues[issue] = issues.get(issue, 0) + 1
        refund_total += document.get("financial_resolution", {}).get("recommended_refund_brl", 0.0)

    print(f"files            : {len(present)} present, {len(EXPECTED)} expected")
    print("issue mix        :")
    for issue, count in sorted(issues.items(), key=lambda kv: -kv[1]):
        print(f"    {issue:<26} {count}")
    print(f"total refund     : {round(refund_total, 2)} BRL")

    if problems:
        print(f"\nFAILED with {len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nOK: 50/50 documents valid, every evidence ID resolves against the CSVs.")

    if args.zip:
        zip_path = os.path.join(config.REPO_ROOT, "output.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for filename in EXPECTED:
                archive.write(os.path.join(config.OUTPUT_DIR, filename), arcname=filename)
        size_kb = round(os.path.getsize(zip_path) / 1024, 1)
        print(f"wrote {zip_path} ({size_kb} KB, {len(EXPECTED)} json files, no extra entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
