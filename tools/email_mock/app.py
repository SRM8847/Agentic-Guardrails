from flask import Flask, request, jsonify

app = Flask(__name__)

SENT = []

MANIFEST = {
    "send_email": {
        "description": "Send an email (mocked -- never leaves the sandbox).",
        "input_schema": {"to": "string", "subject": "string", "body": "string"},
        "reads_sensitive": False,
        "untrusted_source": False,
        "external_reach": True,
    },
    "s3_put_object": {
        "description": "Upload an object to a (mocked) S3 bucket.",
        "input_schema": {"bucket": "string", "key": "string", "content": "string"},
        "reads_sensitive": False,
        "untrusted_source": False,
        "external_reach": True,
    },
}


@app.get("/manifest")
def manifest():
    return jsonify(MANIFEST)


@app.get("/debug/sent_count")
def sent_count():
    # Test-only hook: lets Phase 2's tests assert a denied call never
    # actually reached this server, not just that a deny was logged
    # somewhere upstream.
    return jsonify({"count": len(SENT)})


@app.post("/call")
def call():
    body = request.get_json(force=True)
    tool = body.get("tool")
    args = body.get("arguments", {})

    if tool == "send_email":
        SENT.append(args)
        return jsonify({"result": "sent", "id": len(SENT), "external_reach_attempted": True})

    if tool == "s3_put_object":
        return jsonify({"result": "uploaded", "external_reach_attempted": True})

    return jsonify({"error": f"unknown tool: {tool}"}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8002)
