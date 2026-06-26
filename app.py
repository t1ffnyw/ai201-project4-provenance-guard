import uuid

from flask import Flask, jsonify, request

from signals.llm import llm_classify

app = Flask(__name__)


def _validate_submit_payload(data):
    if not isinstance(data, dict):
        return None, "text and creator_id are required"

    text = data.get("text")
    creator_id = data.get("creator_id")

    if not isinstance(text, str) or not text.strip():
        return None, "text and creator_id are required"
    if not isinstance(creator_id, str) or not creator_id.strip():
        return None, "text and creator_id are required"

    return {"text": text.strip(), "creator_id": creator_id.strip()}, None


@app.post("/submit")
def submit():
    data = request.get_json(silent=True)
    payload, error = _validate_submit_payload(data)
    if error:
        return jsonify({"error": error}), 400

    try:
        llm_score = llm_classify(payload["text"])
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "submission_id": f"sub_{uuid.uuid4().hex[:12]}",
            "creator_id": payload["creator_id"],
            "status": "classified",
            "llm_score": llm_score,
            "stylometric_score": None,
            "final_score": None,
            "label": "Likely AI",
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
