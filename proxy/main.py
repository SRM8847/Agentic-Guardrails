from flask import Flask, request, jsonify
import requests
import os
import policy_client

app = Flask(__name__)

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


def refresh_manifest():
    aggregated = {}
    _tool_to_downstream.clear()
    for server_name, base_url in DOWNSTREAM.items():
        resp = requests.get(f"{base_url}/manifest", timeout=5)
        resp.raise_for_status()
        manifest = resp.json()
        for tool_name, spec in manifest.items():
            _tool_to_downstream[tool_name] = base_url
            aggregated[tool_name] = spec
    return aggregated


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

    # Phase 2: the policy decision happens here, BEFORE anything is
    # forwarded. deny and require_approval both stop the call right here --
    # neither ever reaches the downstream tool server.
    role = body.get("role", DEFAULT_ROLE)
    arguments = body.get("arguments", {})
    resource_key = RESOURCE_ARG.get(tool)
    resource = arguments.get(resource_key, "") if resource_key else ""

    decision = policy_client.decide(role, tool, resource)

    if decision == "deny":
        return jsonify({"decision": "deny", "error": "blocked by policy"}), 403

    if decision == "require_approval":
        return jsonify({"decision": "require_approval",
                         "error": "blocked pending human approval (not yet implemented)"}), 202

    # decision == "allow" -- forward unchanged, same as Phase 1.
    downstream_resp = requests.post(f"{base_url}/call", json=body, timeout=10)
    resp_body = downstream_resp.json()
    resp_body["decision"] = "allow"
    return jsonify(resp_body), downstream_resp.status_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
