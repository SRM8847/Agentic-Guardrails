#!/usr/bin/env python3
"""
Phase 0: bare agent tool-use loop. Calls the three tool servers DIRECTLY --
no proxy exists yet, that's Phase 1. Each tool server speaks plain HTTP/JSON,
shaped to mirror MCP's tools/list (-> /manifest) and tools/call (-> /call) so
swapping the transport to real MCP later is a thin adapter, not a rewrite.

Usage:
    python3 harness.py --mode mock              # no API calls, $0
    python3 harness.py --mode real               # needs ANTHROPIC_API_KEY
    python3 harness.py --mode real --task "..."  # custom task
"""
import argparse
import json
import os
import sys
import urllib.request
import uuid

# Phase 1: if PROXY_URL is set, the agent knows about exactly one
# endpoint -- the proxy -- and has no configuration path to the
# individual tool servers at all. This is what "no path to any tool
# except through the proxy" means at the harness level; the docker-compose
# network topology (tool server ports not published to the host) is what
# enforces the same thing at the infrastructure level once containerized.
PROXY_URL = os.environ.get("PROXY_URL")
if PROXY_URL:
    TOOL_SERVERS = {"proxy": PROXY_URL}
else:
    TOOL_SERVERS = {
        "fs_server": os.environ.get("FS_SERVER_URL", "http://localhost:8001"),
        "email_mock": os.environ.get("EMAIL_MOCK_URL", "http://localhost:8002"),
        "db_mock": os.environ.get("DB_MOCK_URL", "http://localhost:8003"),
    }

# Haiku by default: cheapest current model, stretches trial credit further
# for a harness where the point is testing plumbing, not model quality.
DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "claude-haiku-4-5-20251001")

# Phase 2: every call now carries a role, since the proxy's policy engine
# matches on it. Matches rules_v1.yaml's "research_agent" so the
# deny-external-reach-default rule actually has something to bite on.
AGENT_ROLE = os.environ.get("AGENT_ROLE", "research_agent")

# Phase 4: a fresh session_id per run, so trifecta signals don't leak
# between separate invocations of the harness.
SESSION_ID = os.environ.get("SESSION_ID", str(uuid.uuid4()))


def http_json(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # Phase 2 onward: a 403 (deny) or 202 (require_approval) is a
        # normal, expected policy outcome, not a transport failure -- the
        # caller needs the response body (it has {"decision": ...}), not
        # a crash.
        return json.loads(e.read())


def discover_tools():
    """Pull every server's manifest, return (tool_name -> server_url) plus
    the Anthropic tool-use schema list built from those manifests."""
    tool_to_server = {}
    anthropic_tools = []
    for server_name, base_url in TOOL_SERVERS.items():
        manifest = http_json(f"{base_url}/manifest")
        for tool_name, spec in manifest.items():
            tool_to_server[tool_name] = base_url
            anthropic_tools.append({
                "name": tool_name,
                "description": spec["description"],
                "input_schema": {
                    "type": "object",
                    "properties": {k: {"type": v} for k, v in spec["input_schema"].items()},
                    "required": list(spec["input_schema"].keys()),
                },
            })
    return tool_to_server, anthropic_tools


def call_tool(tool_to_server, tool_name, arguments):
    base_url = tool_to_server.get(tool_name)
    if base_url is None:
        return {"error": f"no server hosts tool '{tool_name}'"}
    return http_json(f"{base_url}/call", method="POST",
                      body={"tool": tool_name, "arguments": arguments,
                            "role": AGENT_ROLE, "session_id": SESSION_ID})


def run_real(task, max_turns=8):
    import anthropic
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    tool_to_server, tools = discover_tools()
    messages = [{"role": "user", "content": task}]

    for turn in range(max_turns):
        resp = client.messages.create(
            model=DEFAULT_MODEL, max_tokens=1024, tools=tools, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            text = "".join(b.text for b in resp.content if b.type == "text")
            print(f"\n[final answer after {turn + 1} turn(s)]\n{text}")
            return

        tool_results = []
        for block in tool_uses:
            print(f"[turn {turn + 1}] agent calls {block.name}({block.input})")
            result = call_tool(tool_to_server, block.name, block.input)
            print(f"           -> {result}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })
        messages.append({"role": "user", "content": tool_results})

    print("[stopped: max_turns reached without a final answer]")


def run_mock():
    """Scripted plan exercising all three servers, no API calls."""
    tool_to_server, tools = discover_tools()
    print(f"[mock] discovered {len(tools)} tools across {len(TOOL_SERVERS)} servers")

    plan = [
        ("db_query_nonpii", {"query": "select * from sales"}),        # allow
        ("fs_read", {"path": "reports/quarterly.txt"}),                # allow
        ("fs_write", {"path": "customers.99", "content": "x"}),        # require_approval
        ("fs_write", {"path": "reports/summary.txt", "content": "x"}), # deny (no rule grants general fs_write)
        ("send_email", {"to": "x@example.com", "subject": "hi", "body": "hi"}),  # deny
    ]
    for tool_name, args in plan:
        print(f"[mock] calling {tool_name}({args})")
        result = call_tool(tool_to_server, tool_name, args)
        print(f"       -> {result}")

    print("[mock] done -- no API calls made, $0 spent")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["real", "mock"], default="mock")
    parser.add_argument("--task", default=(
        "Look up our non-PII sales data, read reports/quarterly.txt, and "
        "write a one-line summary to reports/summary.txt."
    ))
    args = parser.parse_args()

    if args.mode == "real" and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Export it, or run with --mode mock.")

    run_real(args.task) if args.mode == "real" else run_mock()
