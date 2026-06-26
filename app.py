import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from audit_log import append_entry, get_log
from signals.attribution import attribution_from_score, label_from_attribution
from signals.llm import llm_classify
from signals.scoring import compute_final_score
from signals.stylometric import stylometric_score

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


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@app.post("/submit")
def submit():
    data = request.get_json(silent=True)
    payload, error = _validate_submit_payload(data)
    if error:
        return jsonify({"error": error}), 400

    try:
        llm_score = llm_classify(payload["text"])
        stylo_score = stylometric_score(payload["text"])
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500

    final_score = compute_final_score(llm_score, stylo_score)
    attribution = attribution_from_score(final_score)
    confidence = final_score
    label = label_from_attribution(attribution)
    content_id = str(uuid.uuid4())

    response = {
        "content_id": content_id,
        "creator_id": payload["creator_id"],
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "llm_score": llm_score,
        "stylometric_score": stylo_score,
        "final_score": final_score,
        "status": "classified",
    }

    append_entry(
        {
            "content_id": content_id,
            "creator_id": payload["creator_id"],
            "timestamp": _utc_timestamp(),
            "attribution": attribution,
            "confidence": confidence,
            "llm_score": llm_score,
            "stylometric_score": stylo_score,
            "final_score": final_score,
            "status": "classified",
        }
    )

    return jsonify(response)


@app.get("/log")
def log():
    return jsonify({"entries": get_log()})


if __name__ == "__main__":
    app.run(debug=True)
