#!/usr/bin/env python3
"""
Phase 4 trifecta check. Assumes tool servers + OPA (guardrail_phase4.rego)
+ proxy are already running (use run_phase4.sh). Walks a single session
through a sequence designed to move trifecta_state none -> partial ->
tripped, and proves the override changes outcomes that role-based policy
alone would have allowed. Also checks session isolation.
"""
import json
import sys
import urllib.request
import uuid

PROXY = "http://localhost:8000"
SESSION_ID = f"test-{uuid.uuid4()}"


def http_json(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def call(tool, arguments, session_id=SESSION_ID):
    return http_json(f"{PROXY}/call", method="POST",
                      body={"tool": tool, "arguments": arguments,
                            "role": "research_agent", "session_id": session_id})


checks = []


def check(name, condition, detail=""):
    checks.append((name, condition))
    print(f"{'PASS' if condition else 'FAIL'}: {name}" + (f" ({detail})" if detail else ""))


# Step 1: read a sensitive file. No prior signals on this session yet,
# so role-based policy (which always allows fs_read) is what decides.
status, body = call("fs_read", {"path": "customers.db.txt"})
check("step 1: fs_read(customers.db.txt) allowed, no prior trifecta signal",
      status == 200 and body.get("decision") == "allow", f"got {body.get('decision')}")

# Step 2: fetch an untrusted URL. Prior state has only touched_sensitive
# (1 of 3) -> trifecta_state is still "none" -> still allowed.
status, body = call("fetch_url", {"url": "http://example.com"})
check("step 2: fetch_url allowed, trifecta still 'none' (1 of 3 signals so far)",
      status == 200 and body.get("decision") == "allow", f"got {body.get('decision')}")

# Step 3: an ordinary fs_read. Prior state now has 2 signals
# (touched_sensitive + ingested_untrusted) -> "partial" -> this call,
# which role-based policy alone would always allow, must now require
# approval instead.
status, body = call("fs_read", {"path": "reports/quarterly.txt"})
check("step 3: plain fs_read forced to require_approval by partial trifecta",
      status == 202 and body.get("decision") == "require_approval", f"got {body.get('decision')}")

# Step 4: attempt external reach. Still "partial" going INTO this call
# (step 3 added no new signal type) -> still require_approval, not yet a
# hard deny. But this call's own external_reach signal completes all
# three, so trifecta becomes "tripped" for whatever comes after it.
status, body = call("send_email", {"to": "x@example.com", "subject": "hi", "body": "hi"})
check("step 4: send_email still require_approval (partial going in)",
      status == 202 and body.get("decision") == "require_approval", f"got {body.get('decision')}")

# Step 5: all three signals are now true. A plain fs_read -- normally an
# automatic allow -- must be hard denied.
status, body = call("fs_read", {"path": "reports/quarterly.txt"})
check("step 5: plain fs_read hard-denied once trifecta is fully tripped",
      status == 403 and body.get("decision") == "deny", f"got {body.get('decision')}")

# Step 6 (session isolation): a completely different session_id must not
# inherit this session's tripped state.
other_session = f"other-{uuid.uuid4()}"
status, body = call("fs_read", {"path": "reports/quarterly.txt"}, session_id=other_session)
check("step 6: a different session_id is unaffected by this session's tripped state",
      status == 200 and body.get("decision") == "allow", f"got {body.get('decision')}")

print()
passed = sum(1 for _, ok in checks if ok)
print(f"{passed}/{len(checks)} checks passed")
sys.exit(0 if passed == len(checks) else 1)
