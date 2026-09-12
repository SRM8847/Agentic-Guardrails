"""
Phase 3 policy engine: same decide(role, tool, resource) -> str signature
as policy_client.py, but the actual matching happens inside OPA via
guardrail_phase3.rego, not in this process.
"""
import os
import requests

OPA_URL = os.environ.get("OPA_URL", "http://localhost:8181")


def decide(role, tool, resource="", trifecta_state="none"):
    try:
        resp = requests.post(
            f"{OPA_URL}/v1/data/guardrail/decision",
            json={"input": {"role": role, "tool": tool, "resource": resource,
                             "trifecta_state": trifecta_state}},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("result", "deny")
    except requests.RequestException:
        # Fail closed: if OPA is unreachable, times out, or errors, treat
        # it as deny rather than crashing or silently allowing. This is
        # one of Phase 6's required fail-closed behaviors -- implementing
        # it now rather than leaving it as a gap to remember later.
        return "deny"
