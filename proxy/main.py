from flask import Flask, request, jsonify
import requests
import os
import policy_client
import opa_client
import session_state

app = Flask(__name__)

# Phase 3: which engine actually decides. Defaults to opa now that it
# exists; set POLICY_ENGINE=yaml to fall back to the Phase 2 engine for
# comparison. Both stay in the codebase -- this is what makes the
# regression test meaningful, since it can call either one directly.
POLICY_ENGINE = os.environ.get("POLICY_ENGINE", "opa")


def decide(role, tool, resource, trifecta_state="none"):
    if POLICY_ENGINE == "yaml":
        # Phase 2's engine was never trifecta-aware and stays that way --
        # it's the regression baseline, not something we keep extending.
        return policy_client.decide(role, tool, resource)
    return opa_client.decide(role, tool, resource, trifecta_state)


# Which argument on each tool call counts as its "resource" for policy
# matching. Tools not listed here have no resource concept (resource="").
RESOURCE_ARG = {
    "fs_read": "path",
    "fs_write": "path",
}
DEFAULT_ROLE = os.environ.get("DEFAULT_ROLE", "research_agent")

DOWNSTREAM = {
    "fs_server": os.environ.get("FS_SERVER_URL", "http://localhost:8001"),
    "email_mock": os.environ.get("EMAIL_MOCK_URL", "http://localhost:8002"),
    "db_mock": os.environ.get("DB_MOCK_URL", "http://localhost:8003"),
}

# Populated by refresh_manifest(). Maps each tool name to the downstream
# server that actually hosts it, so /call knows where to forward.
_tool_to_downstream = {}
# Full manifest spec per tool (description, input_schema, and the three
# static signal flags), so Phase 4 can derive this call's own trifecta
# contribution without needing the downstream server to have run yet.
_tool_manifest = {}


def refresh_manifest():
    aggregated = {}
    _tool_to_downstream.clear()
    _tool_manifest.clear()
    for server_name, base_url in DOWNSTREAM.items():
        resp = requests.get(f"{base_url}/manifest", timeout=5)
        resp.raise_for_status()
        manifest = resp.json()
        for tool_name, spec in manifest.items():
            _tool_to_downstream[tool_name] = base_url
            _tool_manifest[tool_name] = spec
            aggregated[tool_name] = spec
    return aggregated


def signals_for_call(tool, resource):
    """This call's own contribution to the three trifecta signals, BEFORE
    knowing whether it will be allowed. Most tools have a fixed answer
    (fetch_url is always untrusted, send_email is always external reach);
    fs_read/fs_write's reads_sensitive is None in the manifest because it
    genuinely depends on which resource is being touched, decided here by
    the same customers.* convention the rule table itself uses."""
    spec = _tool_manifest.get(tool, {})
    reads_sensitive = spec.get("reads_sensitive")
    if reads_sensitive is None:
        reads_sensitive = resource.startswith("customers")
    return (
        bool(reads_sensitive),
        bool(spec.get("untrusted_source", False)),
        bool(spec.get("external_reach", False)),
    )


@app.get("/manifest")
def manifest():
    # Refreshed on every call rather than cached once at startup, so a
    # downstream server that comes up after the proxy still gets picked up.
    return jsonify(refresh_manifest())


@app.post("/call")
def call():
    body = request.get_json(force=True)
    tool = body.get("tool")

    if not _tool_to_downstream:
        refresh_manifest()

    base_url = _tool_to_downstream.get(tool)
    if base_url is None:
        return jsonify({"error": f"unknown tool: {tool}"}), 400

    # Phase 2/3/4: the policy decision happens here, BEFORE anything is
    # forwarded. deny and require_approval both stop the call right here --
    # neither ever reaches the downstream tool server.
    role = body.get("role", DEFAULT_ROLE)
    session_id = body.get("session_id", "default-session")
    arguments = body.get("arguments", {})
    resource_key = RESOURCE_ARG.get(tool)
    resource = arguments.get(resource_key, "") if resource_key else ""

    # Phase 4: decide using the session's PRIOR state (signals from calls
    # before this one), then record this call's own contribution
    # afterward. See session_state.py's docstring for why that ordering,
    # not the other way around.
    prior_trifecta = session_state.trifecta_state(session_id)
    decision = decide(role, tool, resource, prior_trifecta)

    touched_sensitive, ingested_untrusted, external_reach = signals_for_call(tool, resource)
    session_state.update(session_id, touched_sensitive, ingested_untrusted, external_reach)

    if decision == "deny":
        return jsonify({"decision": "deny", "engine": POLICY_ENGINE,
                         "trifecta_state": prior_trifecta,
                         "error": "blocked by policy"}), 403

    if decision == "require_approval":
        return jsonify({"decision": "require_approval", "engine": POLICY_ENGINE,
                         "trifecta_state": prior_trifecta,
                         "error": "blocked pending human approval (not yet implemented)"}), 202

    # decision == "allow" -- forward unchanged, same as Phase 1.
    downstream_resp = requests.post(f"{base_url}/call", json=body, timeout=10)
    resp_body = downstream_resp.json()
    resp_body["decision"] = "allow"
    resp_body["engine"] = POLICY_ENGINE
    resp_body["trifecta_state"] = prior_trifecta
    return jsonify(resp_body), downstream_resp.status_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
