#!/usr/bin/env python3
"""
Phase 2 policy check. Assumes tool servers + proxy are already running
(use run_phase2.sh). Exercises each rule in rules_v1.yaml through the
live proxy and checks both the decision AND, for the deny case, that the
downstream tool's own counter proves it never actually ran.
"""
import json
import sys
import urllib.request

PROXY = "http://localhost:8000"
EMAIL_MOCK = "http://localhost:8002"


def http_json(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def call(tool, arguments, role="research_agent"):
    return http_json(f"{PROXY}/call", method="POST",
                      body={"tool": tool, "arguments": arguments, "role": role})


checks = []


def check(name, condition):
    checks.append((name, condition))
    print(f"{'PASS' if condition else 'FAIL'}: {name}")


# Baseline: how many emails has the downstream mock actually sent so far?
_, before = http_json(f"{EMAIL_MOCK}/debug/sent_count")
sent_before = before["count"]

# 1. Read-only call should be allowed and forwarded.
status, body = call("fs_read", {"path": "reports/quarterly.txt"})
check("fs_read is allowed", status == 200 and body.get("decision") == "allow")

# 2. send_email as research_agent should be denied.
status, body = call("send_email", {"to": "x@example.com", "subject": "hi", "body": "hi"})
check("send_email is denied for research_agent", status == 403 and body.get("decision") == "deny")

# 2b. THE important check: did that denied call actually reach email_mock?
_, after = http_json(f"{EMAIL_MOCK}/debug/sent_count")
check("denied send_email never reached the downstream tool",
      after["count"] == sent_before)

# 3. fs_write to a customers.* path should require approval, not execute.
status, body = call("fs_write", {"path": "customers.99", "content": "x"})
check("fs_write to customers.* requires approval", status == 202 and body.get("decision") == "require_approval")

# 4. fs_write to a non-customers path matches no rule -> default deny.
status, body = call("fs_write", {"path": "logs.txt", "content": "x"})
check("fs_write to a non-sensitive path defaults to deny", status == 403 and body.get("decision") == "deny")

# 5. db_query_nonpii should be allowed (role=any rule).
status, body = call("db_query_nonpii", {"query": "select 1"})
check("db_query_nonpii is allowed", status == 200 and body.get("decision") == "allow")

print()
passed = sum(1 for _, ok in checks if ok)
print(f"{passed}/{len(checks)} checks passed")
sys.exit(0 if passed == len(checks) else 1)
