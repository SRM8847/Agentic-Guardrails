from flask import Flask, request, jsonify

app = Flask(__name__)

TABLE = [
    {"id": 1, "product": "Widget", "units_sold": 120},
    {"id": 2, "product": "Gadget", "units_sold": 75},
]

MANIFEST = {
    "db_query_nonpii": {
        "description": "Run a read-only query against non-PII sales data.",
        "input_schema": {"query": "string"},
        "reads_sensitive": False,
        "untrusted_source": False,
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
    if tool == "db_query_nonpii":
        return jsonify({"result": TABLE})
    return jsonify({"error": f"unknown tool: {tool}"}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8003)

