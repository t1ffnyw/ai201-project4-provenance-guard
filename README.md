# Provenance Guard

A small Flask service that classifies whether a piece of text is likely human-written or AI-generated. It returns a transparency label with a confidence score, records every decision to a structured audit log, lets creators appeal a classification for human review, and rate-limits the public endpoint.

## How it works

Each submission runs through two independent detection signals, which are combined into a single `final_score` in `[0, 1]` (0 = human, 1 = AI). The score maps to one of three transparency labels and is written to an append-only audit log.

```
text --> llm_classify ----\
                           >-- final_score --> label --> response + audit log
text --> stylometric_score-/
```

## Detection signals

### Signal 1: LLM-based classification (`signals/llm.py`)

A Groq-hosted model (`llama-3.3-70b-versatile`) rates the text from `0` (clearly human) to `1` (clearly AI).

**Why this signal.** Modern AI text is defined by *semantic* patterns which the model can detect. It is the stronger of the two signals because it reads meaning, not just shape.

**Design choices.** The prompt forces a single decimal and an explicit three-band rubric so the model uses the full range rather than collapsing to 0/1. The rubric deliberately states that **tone is not a signal**: formal/academic register is not an AI tell, and casual register is not proof of humanity. The model is told to judge specificity and substance. `temperature=0` keeps scoring reproducible.

**What I'd change for a real deployment.** A single model call is a single point of failure and a cost/latency centre. In production I'd (a) cache by content hash, (b) add a cheaper local fallback model for when Groq is unavailable, (c) calibrate the model's raw scores against a labeled dataset instead of trusting the rubric's self-reported bands, and (d) log prompt/model versions so score drift is traceable.

### Signal 2: Stylometric heuristics (`signals/stylometric.py`)

Two deterministic surface metrics, each mapped to `0`–`1` (higher = more AI-like) and averaged:

- **Sentence-length variance** — coefficient of variation of words-per-sentence. Human writing tends to mix long and short sentences; uniform rhythm reads as machine-smoothed.
- **Punctuation density** — punctuation characters over total characters, scored by distance from a typical-prose band.

**Why this signal.** It is cheap, fully deterministic, needs no network, and catches a *different* failure mode than the LLM: surface regularity. It also acts as a cross-check so the system does not depend entirely on one model's judgment.

**What I'd change for a real deployment.** These heuristics are weak on short inputs and easily gamed (add one long rambling sentence and the variance metric flips). For real use I'd add burstiness and function-word distribution, compute metrics over a sliding window so short text degrades gracefully, and fit the mapping constants on a real corpus rather than hand-tuning them.

## Confidence scoring (and why)

The two signals are merged with a weighted sum (`signals/scoring.py`):

```
final_score = 0.7 * llm_score + 0.3 * stylometric_score
```

**Why a weighted sum, and why 0.7 / 0.3.** A linear blend is explainable and every input's contribution is legible, which matters for a tool whose whole point is transparency. The LLM is weighted more heavily because it is content-aware and empirically the better discriminator while the stylometric signal is a lighter, noisier surface check whose main job is to nudge and to guard against the LLM over-trusting tone. Equal weighting let the noisy stylometric metrics drag clearly-AI text down into the uncertain band, so 0.7/0.3 reflects measured trust, not a guess.


### Example submissions (real Milestone 4 scores)

**High-confidence case — clearly human:**

> "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after..."

| llm_score | stylometric_score | final_score | label |
|---|---|---|---|
| 0.10 | 0.11 | **0.10** | Likely Human |

Both signals agree and the score sits deep in the Likely Human band with high confidence.

**Lower-confidence case — lightly edited AI:**

> "I've been thinking a lot about remote work lately. There are genuine tradeoffs — flexibility and no commute on one side, isolation and blurred work-life boundaries on the other. Studies show productivity varies widely by individual and role type."

| llm_score | stylometric_score | final_score | label |
|---|---|---|---|
| 0.50 | 0.19 | **0.41** | Mixed/Uncertain |

The signals disagree (the LLM is on the fence at 0.50, stylometrics leans human at 0.19), so the blended score lands in the Mixed/Uncertain band at low confidence.

The gap between `0.10` and `0.41` (and, in the full suite, `0.65` for clearly-AI text) is the evidence that scoring produces real variation across inputs.

## Transparency labels: the three variants

`final_score` maps to exactly one label (`signals/attribution.py`). The `label` field in the `/submit` response displays one of these three exact strings:

| Variant | Condition | Exact displayed text |
|---|---|---|
| High-confidence AI | `final_score > 0.6` | **`Likely AI`** |
| High-confidence human | `final_score < 0.4` | **`Likely Human`** |
| Uncertain | `0.4 <= final_score <= 0.6` | **`Mixed/Uncertain`** |

Written description of each:

- **High-confidence AI — `Likely AI`**: shown when the blended score exceeds 0.6, i.e. both the model and/or surface statistics strongly indicate machine generation. Communicates that the text most likely was AI-generated.
- **High-confidence human — `Likely Human`**: shown when the blended score is below 0.4, indicating the text reads as genuinely human-written. Communicates a low likelihood of AI involvement.
- **Uncertain — `Mixed/Uncertain`**: shown in the 0.4–0.6 middle band, used when the signals are weak or disagree (e.g. lightly edited AI, or human writing with AI-like regularity). Communicates that the system cannot make a confident call and the result should not be treated as definitive.

The label is computed from the score on every request, so all three are reachable depending on input.

## Endpoints

### `POST /submit`

Classifies text. Rate limited to **10 per minute; 100 per day** per IP.

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "The sun dipped below the horizon...", "creator_id": "test-user-1"}' | python -m json.tool
```

Response:

```json
{
  "content_id": "048ba75e-89f3-4462-a940-e4c5e1a52530",
  "creator_id": "test-user-1",
  "attribution": "likely_human",
  "confidence": 0.218,
  "label": "Likely Human",
  "llm_score": 0.1,
  "stylometric_score": 0.49,
  "final_score": 0.218,
  "status": "classified"
}
```

Save the `content_id` — it is required to file an appeal.

### `POST /appeal`

Files an appeal against a prior classification. Accepts `content_id` and `creator_reasoning`. It sets the content's status to `under_review`, logs the appeal alongside the original classification decision, and returns a confirmation. No automated re-classification is performed; appeals are queued for a human reviewer.

```bash
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "PASTE-CONTENT-ID-HERE", "creator_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical."}' | python -m json.tool
```

Response:

```json
{
  "content_id": "PASTE-CONTENT-ID-HERE",
  "status": "under_review",
  "message": "Appeal received and queued for human review."
}
```

Validation: missing/empty `content_id` or `creator_reasoning` returns `400`; an unknown `content_id` returns `404`.

### `GET /log`

Returns the most recent audit log entries as JSON: `{"entries": [...]}`.

## Audit log

Every submission and appeal is appended as one JSON object per line to `data/audit.jsonl` (structured JSON Lines, not console output). Each entry captures the timestamp, content ID, attribution result, confidence score, both individual signal scores, and whether an appeal has been filed.

Sample submission entry:

```json
{
  "content_id": "c8c3b63c-5a62-4375-8d46-5ab6fb4c49f7",
  "creator_id": "ratelimit-test",
  "timestamp": "2026-06-28T20:34:04.761149Z",
  "event": "submission",
  "attribution": "likely_ai",
  "confidence": 0.700,
  "llm_score": 0.8,
  "stylometric_score": 0.468,
  "final_score": 0.700,
  "status": "classified",
  "appeal_filed": false
}
```

Sample appeal entry (status flips to `under_review`, original decision carried alongside):

```json
{
  "content_id": "048ba75e-89f3-4462-a940-e4c5e1a52530",
  "creator_id": "appeal-tester",
  "timestamp": "2026-06-28T20:33:24.748136Z",
  "event": "appeal",
  "status": "under_review",
  "appeal_filed": true,
  "appeal_reasoning": "I wrote this myself; I am a non-native English speaker.",
  "attribution": "likely_human",
  "confidence": 0.218,
  "llm_score": 0.1,
  "stylometric_score": 0.495,
  "final_score": 0.218,
  "original_status": "classified"
}
```

## Rate limiting

`POST /submit` is limited with Flask-Limiter (in-memory storage) to **10 per minute; 100 per day** per client IP.

**Reasoning.** A genuine writer checking their own drafts works in bursts of a few submissions and rarely exceeds a handful per minute, so `10/min` sits comfortably above realistic human use while stopping a script from flooding the endpoint. `100/day` caps sustained abuse from a single IP without blocking even a heavy but legitimate day of editing. The limits are intentionally generous for one person and restrictive for automation.


## Known limitations

The system will get some content reliably wrong, and the failures trace to specific properties of the two signals rather than to "needs more data."

**Very short submissions (one or two sentences).** The stylometric sentence-length-variance metric is undefined when there is only one sentence, so `sentence_length_variance_score` returns a hardcoded `0.7` (AI-leaning) in that case (`signals/stylometric.py`). A genuine one-line human note therefore receives an artificial nudge toward "AI" purely because there are too few sentences to measure rhythm — the metric is reporting an artifact, not a real signal. Short text also gives the LLM very little to judge, so the combined result is unstable and can flip on minor edits.

**Poetry and other deliberately uniform writing.** The variance metric treats low sentence-length variance as AI-like, and poems, song lyrics, or list-like prose with even line lengths and sparse punctuation push *both* stylometric metrics toward "AI." A human-written poem can therefore be flagged as machine-generated, because the heuristic mistakes an intentional stylistic choice (regular meter) for the machine-smoothed uniformity it was designed to detect.

In both cases the LLM signal partially compensates, but because stylometrics contributes 30% of the score it can still drag a genuinely human piece into or across the uncertain boundary.

## Spec reflection

**Where the spec helped.** The "uncertainty representation" table in `planning.md` defined exact numeric thresholds (`< 0.4`, `0.4–0.6`, `> 0.6`). Those concrete boundaries removed all ambiguity from the label-mapping code and made it directly testable — they became `attribution_from_score()` plus boundary unit tests (`0.39 → human`, `0.40 → uncertain`, `0.60 → uncertain`, `0.61 → ai`). Having the contract pinned down in the plan meant the implementation and its tests fell out almost mechanically.

**Where the implementation diverged, and why.** `planning.md` specified three stylometric heuristics — sentence-length variance, type-token ratio (TTR), and punctuation density. The implementation **dropped TTR**. During Milestone 4 calibration, TTR returned `0.0` for every realistic short submission: these texts all had TTR above the metric's high cutoff (few repeated words in ~50 words), so it never discriminated and only diluted the average. Keeping a metric that contributes no signal would have made the stylometric score worse, so I removed it and averaged the two remaining metrics. (A second, smaller divergence: the appeal status string is `under_review` and the field is `appeal_reasoning`, where `planning.md` had written `appeal_pending`; the API contract from the assignment took precedence.)

## AI usage

**1. Generating and then correcting the stylometric signal.** I directed an AI tool to implement `signals/stylometric.py` and `signals/scoring.py` from the detection-signals spec. It produced three metrics (including TTR) combined as an equal average. On running the calibration suite, two problems showed up that I overrode: TTR scored `0.0` for all four reference inputs (so I removed it), and the punctuation-density mapping (originally centered around `0.085`) scored ordinary prose as AI-like, so I re-tuned the band to center on `0.03`. The AI's structure was a fine starting point, but its constants were not calibrated and one whole metric was dead weight.

**2. Verifying AI-generated threshold logic against the spec.** I asked an AI tool to write the score-to-label mapping. Because AI commonly gets boundary conditions subtly wrong (e.g. `<= 0.4` for "human", or excluding the endpoints of the uncertain band), I did not accept it blindly — I added explicit boundary unit tests pinned to the spec's exact ranges and confirmed `0.40` and `0.60` both resolve to `Mixed/Uncertain`. The generated code happened to be correct, but the tests were the thing I trusted, not the generation.

**3. Iterating on the LLM prompt.** I directed the AI to draft the classification prompt, then refined it through testing. Its first version defaulted casual text to "human" and flagged formal human prose (a monetary-policy paragraph) as AI at `0.80`. I overrode this by adding explicit guidance that **tone is not a signal** and that scoring should reflect specificity and substance; that change dropped the formal-human false positive to `0.20` while keeping the clearly-AI and clearly-human cases correct.
