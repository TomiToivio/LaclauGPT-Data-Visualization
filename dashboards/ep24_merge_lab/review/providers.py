"""Model clients for the independent review pass (#311).

Every review is attributable: the ledger records the model, the prompt version, the run id and
the time, and nothing is written when a model fails or returns something that is not the agreed
schema. A review that did not happen is never recorded as if it had.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

PROMPT_VERSION = "ep24-review-v1"

SYSTEM = """You are one of three independent reviewers of a legacy political-discourse corpus.
You judge whether labels name the same thing, and you give the exact English Wikipedia article
title when a genuinely equivalent article exists.

Rules:
- Answer with JSON only, no prose, no code fences.
- "decision": "merge" if the labels denote the same referent, "split" if the cluster contains
  more than one referent, "keep" if they are different things that must stay apart.
- "canonical": the exact English Wikipedia article title when one exists, otherwise a concise,
  specific English label. Never invent a title; never use a merely related article.
- Preserve meaning: distinct people, distinct parties (a Dutch Christian Democrat is not the
  German CDU), broader/narrower concepts, opposing sentiments and different stances must not merge.
- "wikipedia_title": the exact title you verified exists, or null.
- "confidence": your calibrated probability that the decision is right, 0.0-1.0.
- "rationale": at most 200 characters, naming the evidence you used.
"""

SCHEMA_HINT = """Reply exactly like:
{"decision":"merge|split|keep","canonical":"...","wikipedia_title":null,"confidence":0.0,"rationale":"..."}"""


@dataclass
class Reviewer:
    """One attributable reviewer: a model plus the prompt variant it uses."""

    name: str
    host: str
    model: str
    temperature: float = 0.0
    #: Different reviewers get differently worded instructions, so agreement is not one prompt
    #: asking itself the same question three times.
    style: str = "plain"
    extra: dict[str, Any] = field(default_factory=dict)

    def prompt_style(self) -> str:
        if self.style == "evidence-first":
            return (
                "Before deciding, name silently the evidence that would change your mind, then "
                "decide. Prefer keeping labels apart when the evidence is thin."
            )
        if self.style == "skeptical":
            return (
                "You are the skeptic of the panel: assume the merge is wrong until the labels "
                "clearly denote one referent across languages and countries."
            )
        return "Weigh the labels, their countries and their languages, then decide."


def _post(host: str, path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://{host}{path}", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _first_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a reply, tolerating fences and stray prose."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _validate(payload: dict[str, Any]) -> dict[str, Any]:
    decision = str(payload.get("decision", "")).strip().lower()
    if decision not in {"merge", "split", "keep"}:
        raise ValueError(f"decision must be merge/split/keep, got {decision!r}")
    canonical = str(payload.get("canonical", "")).strip()
    if not canonical:
        raise ValueError("canonical must not be empty")
    title = payload.get("wikipedia_title")
    if title is not None and not isinstance(title, str):
        raise ValueError("wikipedia_title must be a string or null")
    confidence = float(payload.get("confidence", 0.0))
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return {
        "decision": decision,
        "canonical": canonical[:200],
        "wikipedia_title": (title or "").strip()[:200] or None,
        "confidence": round(confidence, 3),
        "rationale": str(payload.get("rationale", "")).strip()[:300],
    }


def review(
    unit: dict[str, Any], reviewer: Reviewer, *, timeout: int = 90, attempts: int = 3
) -> dict[str, Any]:
    """Ask one reviewer about one unit. Raises on anything that is not a usable review."""
    labels = unit.get("labels", [])
    context = {
        "category": unit.get("category"),
        "labels": labels,
        "countries": unit.get("countries", []),
        "proposed_canonical": unit.get("canonical"),
        "proposed_alternatives": unit.get("alternatives", []),
        "matcher_confidence": unit.get("confidence", 0.0),
        "occurrences": unit.get("occurrences", 0),
    }
    prompt = (
        f"{SYSTEM}\n{reviewer.prompt_style()}\n\n"
        f"Unit:\n{json.dumps(context, ensure_ascii=False, indent=1)}\n\n{SCHEMA_HINT}"
    )
    payload = {
        "model": reviewer.model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": reviewer.temperature, "num_predict": 800},
    }
    started = time.time()
    last_error: Exception | None = None
    response: dict[str, Any] = {}
    text = ""
    for attempt in range(1, attempts + 1):
        try:
            payload["options"]["num_predict"] = 800 * attempt
            response = _post(reviewer.host, "/api/generate", payload, timeout)
            text = response.get("response", "")
            if response.get("done_reason") == "length":
                # The reply was cut off mid-JSON; retrying with more room is the honest fix.
                raise ValueError("response truncated at the token cap")
            if not text.strip():
                raise ValueError("empty response (the model returned nothing)")
            parsed = _validate(_first_json(text))
            break
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                raise
            time.sleep(1.5 * attempt)
    else:  # pragma: no cover - the loop always breaks or raises
        raise last_error or RuntimeError("review failed")
    parsed.update(
        {
            "reviewer": reviewer.name,
            "model": reviewer.model,
            "prompt_version": PROMPT_VERSION,
            "latency_s": round(time.time() - started, 2),
            "model_digest": response.get("model", ""),
            "created_at_unix": response.get("created_at", ""),
        }
    )
    return parsed


def adjudicate(
    unit: dict[str, Any],
    reviews: list[dict[str, Any]],
    reviewer: Reviewer,
    *,
    timeout: int = 90,
) -> dict[str, Any]:
    """A fourth model decides when the three reviewers disagree, on the record."""
    panel = [
        {
            "reviewer": item["reviewer"],
            "decision": item["decision"],
            "canonical": item["canonical"],
            "wikipedia_title": item.get("wikipedia_title"),
            "confidence": item["confidence"],
            "rationale": item.get("rationale", ""),
        }
        for item in reviews
    ]
    prompt = (
        f"{SYSTEM}\nYou are the adjudicator. Three reviewers disagreed; decide, and say why the "
        f"minority was wrong. Do not average votes.\n\n"
        f"Unit:\n{json.dumps(unit, ensure_ascii=False, indent=1)}\n\n"
        f"Reviews:\n{json.dumps(panel, ensure_ascii=False, indent=1)}\n\n{SCHEMA_HINT}"
    )
    payload = {
        "model": reviewer.model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_predict": 400},
    }
    started = time.time()
    response = _post(reviewer.host, "/api/generate", payload, timeout)
    parsed = _validate(_first_json(response.get("response", "")))
    parsed.update(
        {
            "reviewer": reviewer.name,
            "model": reviewer.model,
            "prompt_version": f"{PROMPT_VERSION}-adjudication",
            "latency_s": round(time.time() - started, 2),
            "adjudicated": True,
        }
    )
    return parsed


def ping(reviewer: Reviewer, *, timeout: int = 30) -> tuple[bool, str]:
    """Is this reviewer reachable and able to answer at all?"""
    try:
        response = _post(
            reviewer.host,
            "/api/generate",
            {
                "model": reviewer.model,
                "prompt": 'Reply with JSON: {"ok": true}',
                "stream": False,
                "format": "json",
                "options": {"temperature": 0, "num_predict": 16},
            },
            timeout,
        )
        return True, (response.get("response") or "")[:60]
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


BATCH_SYSTEM = """You are one of three independent reviewers of a legacy political-discourse corpus.
You are given several units; judge each one on its own.

Rules:
- Answer with a JSON array only, one object per unit, in the same order, each carrying its "unit_id".
- "decision": "merge" if the labels denote the same referent, "split" if the cluster holds more
  than one referent, "keep" if they are different things that must stay apart.
- "canonical": the exact English Wikipedia article title when a genuinely equivalent article
  exists, otherwise a concise specific English label. Never invent a title, never use a merely
  related article.
- Distinct people, distinct parties (a Dutch Christian Democrat is not the German CDU), broader
  or narrower concepts, opposing sentiments and different stances must not merge.
- "wikipedia_title": the exact title you verified exists, or null. "confidence": 0.0-1.0.
- "rationale": at most 200 characters.
"""

BATCH_HINT = 'Reply exactly like: [{"unit_id":"...","decision":"merge|split|keep","canonical":"...","wikipedia_title":null,"confidence":0.0,"rationale":"..."}]'


def review_batch(
    units: list[dict[str, Any]],
    reviewer: Reviewer,
    *,
    timeout: int = 240,
    attempts: int = 3,
) -> dict[str, dict[str, Any]]:
    """Ask one reviewer about several units in one call, and return only validated verdicts.

    Batching keeps a full-corpus panel inside a night's compute without weakening the rule the
    issue sets: every *unit* still gets its own verdict from this reviewer, and a unit missing
    from the reply is treated as not reviewed rather than guessed.
    """
    compact = [
        {
            "unit_id": unit["unit_id"],
            "category": unit.get("category"),
            "labels": unit.get("labels", []),
            "countries": unit.get("countries", []),
            "proposed_canonical": unit.get("canonical"),
            "proposed_alternatives": unit.get("alternatives", []),
            "occurrences": unit.get("occurrences", 0),
        }
        for unit in units
    ]
    prompt = (
        f"{BATCH_SYSTEM}{reviewer.prompt_style()}\n\n"
        f"Units:\n{json.dumps(compact, ensure_ascii=False)}\n\n{BATCH_HINT}"
    )
    payload = {
        "model": reviewer.model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        # Room for every verdict plus the models' own preamble; the retry grows it further.
        "options": {"temperature": reviewer.temperature, "num_predict": 400 * len(units) + 600},
    }
    started = time.time()
    response: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        payload["options"]["num_predict"] = (400 * len(units) + 600) * attempt
        try:
            response = _post(reviewer.host, "/api/generate", payload, timeout)
            if response.get("done_reason") == "length":
                raise ValueError("batch reply truncated")
            parsed = _first_json(response.get("response", ""))
            items = parsed if isinstance(parsed, list) else parsed.get("reviews", [])
            verdicts: dict[str, dict[str, Any]] = {}
            for item in items:
                unit_id = str(item.get("unit_id", ""))
                if not unit_id:
                    continue
                try:
                    verdict = _validate(item)
                except ValueError:
                    continue
                verdict.update(
                    {
                        "reviewer": reviewer.name,
                        "model": reviewer.model,
                        "prompt_version": f"{PROMPT_VERSION}-batch",
                        "latency_s": round(time.time() - started, 2),
                    }
                )
                verdicts[unit_id] = verdict
            if not verdicts:
                raise ValueError("no usable verdict in the batch reply")
            return verdicts
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(1.5 * attempt)
    raise RuntimeError("batch review failed")
