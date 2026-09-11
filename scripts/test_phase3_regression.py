#!/usr/bin/env python3
"""
Phase 3 regression check. Requires OPA to already be running (use
run_phase3.sh). Runs the same set of (role, tool, resource) cases through
both engines and asserts they produce identical decisions -- this is the
actual proof that OPA reproduces Phase 2, not just a claim.
"""
import sys

sys.path.insert(0, "proxy")
import policy_client  # noqa: E402
import opa_client     # noqa: E402

CASES = [
    ("research_agent", "fs_read", "reports/quarterly.txt"),
    ("research_agent", "send_email", ""),
    ("any_role", "fs_write", "customers.99"),
    ("any_role", "fs_write", "logs.txt"),
    ("research_agent", "db_query_nonpii", ""),
    ("research_agent", "totally_unknown_tool", ""),
    ("some_other_role", "fetch_url", ""),          # role=any covers this
    ("some_other_role", "s3_put_object", ""),      # no rule for this role -> default deny
    ("research_agent", "s3_put_object", ""),       # matches deny-external-reach-default exactly
]

mismatches = []
for role, tool, resource in CASES:
    py_decision = policy_client.decide(role, tool, resource)
    opa_decision = opa_client.decide(role, tool, resource)
    match = py_decision == opa_decision
    status = "PASS" if match else "FAIL"
    print(f"{status}: ({role!r}, {tool!r}, {resource!r}) -> python={py_decision!r} opa={opa_decision!r}")
    if not match:
        mismatches.append((role, tool, resource, py_decision, opa_decision))

print()
if mismatches:
    print(f"{len(mismatches)}/{len(CASES)} MISMATCHES -- OPA does not reproduce Phase 2 yet")
    sys.exit(1)
else:
    print(f"{len(CASES)}/{len(CASES)} cases agree -- OPA reproduces Phase 2 exactly")
    sys.exit(0)
