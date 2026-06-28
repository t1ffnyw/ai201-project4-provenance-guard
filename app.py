import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from audit_log import append_entry, find_latest_submission, get_log
from signals.attribution import attribution_from_score, label_from_score
from signals.llm import llm_classify
from signals.scoring import compute_final_score
from signals.stylometric import stylometric_score

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


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


def _validate_appeal_payload(data):
    if not isinstance(data, dict):
        return None, "content_id and creator_reasoning are required"

    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning")

    if not isinstance(content_id, str) or not content_id.strip():
        return None, "content_id and creator_reasoning are required"
    if not isinstance(creator_reasoning, str) or not creator_reasoning.strip():
        return None, "content_id and creator_reasoning are required"

    return {
        "content_id": content_id.strip(),
        "creator_reasoning": creator_reasoning.strip(),
    }, None


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@app.post("/submit")
@limiter.limit("10 per minute;100 per day")
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
    label = label_from_score(final_score)
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
            "event": "submission",
            "attribution": attribution,
            "confidence": confidence,
            "llm_score": llm_score,
            "stylometric_score": stylo_score,
            "final_score": final_score,
            "status": "classified",
            "appeal_filed": False,
        }
    )

    return jsonify(response)


@app.post("/appeal")
def appeal():
    data = request.get_json(silent=True)
    payload, error = _validate_appeal_payload(data)
    if error:
        return jsonify({"error": error}), 400

    original = find_latest_submission(payload["content_id"])
    if original is None:
        return jsonify({"error": "content_id not found"}), 404

    append_entry(
        {
            "content_id": payload["content_id"],
            "creator_id": original.get("creator_id"),
            "timestamp": _utc_timestamp(),
            "event": "appeal",
            "status": "under_review",
            "appeal_filed": True,
            "appeal_reasoning": payload["creator_reasoning"],
            "attribution": original.get("attribution"),
            "confidence": original.get("confidence"),
            "llm_score": original.get("llm_score"),
            "stylometric_score": original.get("stylometric_score"),
            "final_score": original.get("final_score"),
            "original_status": original.get("status"),
        }
    )

    return jsonify(
        {
            "content_id": payload["content_id"],
            "status": "under_review",
            "message": "Appeal received and queued for human review.",
        }
    )


@app.get("/log")
def log():
    return jsonify({"entries": get_log()})


if __name__ == "__main__":
    app.run(debug=True)
