from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory fake filesystem. customers.* paths are the "sensitive" resource
# rules_v1.yaml's require-approval-sensitive-write rule matches against.
FAKE_FS = {
    "reports/quarterly.txt": "Q3 revenue up 12% quarter over quarter.",
    "customers.db.txt": "name,email\nAlice,alice@example.com\nBob,bob@example.com",
    "logs/app.log": "2026-09-08 INFO server started",
}

# Manifest shape mirrors MCP's tools/list: name -> description, JSON-schema-ish
# input_schema, and the three trifecta signal flags this tool sets when used.
MANIFEST = {
    "fs_read": {
        "description": "Read a file's content by path.",
        "input_schema": {"path": "string"},
        "reads_sensitive": None,   # depends on path, decided per-call below
        "untrusted_source": False,
        "external_reach": False,
    },
    "fs_write": {
        "description": "Write content to a file by path.",
        "input_schema": {"path": "string", "content": "string"},
        "reads_sensitive": None,
        "untrusted_source": False,
        "external_reach": False,
    },
    "fetch_url": {
        "description": "Fetch the (mocked) content of a URL.",
        "input_schema": {"url": "string"},
        "reads_sensitive": False,
        "untrusted_source": True,  # anything from the open web is untrusted content
        "external_reach": False,
    },
}


@app.get("/manifest")
def manifest():
    return jsonify(MANIFEST)


@app.post("/call")
def call():
    body = request.get_json(force=True)
    tool = body.get("tool")
    args = body.get("arguments", {})

    if tool == "fs_read":
        path = args.get("path", "")
        if path not in FAKE_FS:
            return jsonify({"error": f"no such file: {path}"}), 404
        return jsonify({
            "result": FAKE_FS[path],
            "touched_sensitive": path.startswith("customers"),
        })

    if tool == "fs_write":
        path = args.get("path", "")
        FAKE_FS[path] = args.get("content", "")
        return jsonify({
            "result": "ok",
            "touched_sensitive": path.startswith("customers"),
        })

    if tool == "fetch_url":
        url = args.get("url", "")
        return jsonify({
            "result": f"<mock content fetched from {url}> (this is fixture text for testing, not a real fetch)",
            "ingested_untrusted": True,
        })

    return jsonify({"error": f"unknown tool: {tool}"}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)

