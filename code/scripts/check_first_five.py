"""Run the Identity Resolver against the first five public sample requests.

Usage from repository root:
    python code/scripts/check_first_five.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = CODE_ROOT / "src"
REPO_ROOT = CODE_ROOT.parent
sys.path.insert(0, str(SRC_ROOT))

from ghost_data_audit.csv_loader import load_dataset  # noqa: E402
from ghost_data_audit.identity_resolver import IdentityResolver  # noqa: E402


def main() -> int:
    data = load_dataset(REPO_ROOT / "dataset")
    resolver = IdentityResolver(data.user_identities, data.user_audit_log)
    sample_cases = data.sample_deletion_requests[:5]
    expected_sample = {row["case_id"]: row for row in data.sample_output}

    print("case_id | requested_email | resolved_user_ids | ambiguous | sample_status")
    print("-" * 96)
    failed = False

    for case in sample_cases:
        resolution = resolver.resolve(case["email"], case["audit_at"])
        expected = expected_sample.get(case["case_id"])
        if expected is None:
            raise RuntimeError(f"Missing public sample output for {case['case_id']}")

        # The public sample output validates the audit decision, not identity labels.
        # For this smoke test, assert the identity against the current snapshot's
        # exact email mapping and report any ambiguity rather than hiding it.
        direct_matches = sorted(
            row["user_id"]
            for row in data.user_identities
            if row["email"].strip().casefold() == case["email"].strip().casefold()
            and row["updated_at"] <= case["audit_at"]
        )
        ok = resolution.matched_user_ids == tuple(direct_matches) and not resolution.ambiguous
        failed = failed or not ok
        print(
            f"{case['case_id']} | {case['email']} | "
            f"{json.dumps(list(resolution.matched_user_ids))} | "
            f"{resolution.ambiguous} | {expected['deletion_status']} | "
            f"{'PASS' if ok else 'FAIL'}"
        )

    if failed:
        print("\nIdentity smoke test failed.", file=sys.stderr)
        return 1
    print("\nIdentity smoke test passed for the first five public sample cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
