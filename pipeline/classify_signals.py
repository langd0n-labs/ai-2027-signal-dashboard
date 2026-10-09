"""Ask the configured LLM to classify one signal for one month from the collected evidence."""

STATUSES = ("accelerating", "stabilizing", "unclear")
MAX_JUSTIFICATION = 400  # characters; the prompt asks for at most 300

SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": list(STATUSES)},
        "justification": {"type": "string"},
        "confidence": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
    },
    "required": ["status", "justification", "confidence"],
    "additionalProperties": False,
}

SYSTEM = """You are a signal analyst for a public dashboard that tracks whether the world is moving toward the "AI 2027" scenario (Kokotajlo et al., AI Futures Project, 2025).

You classify one signal for one calendar month:
- "accelerating": the evidence shows movement toward the scenario, as defined for this signal.
- "stabilizing": the evidence shows movement away from it, or a steady state.
- "unclear": the evidence is mixed, thin, or missing.

Rules:
- Use only the evidence provided. Do not use anything you know about events after the end of the month being classified.
- Compare this month with the month before and with the longer series where given. A level alone is not a trend.
- Counts of news stories and documents reflect attention, not outcomes. Weigh them accordingly.
- Some sources may be marked unavailable. Do not guess what they would have shown.
- Monthly economic series are published late. The latest observation is often one month before the month being classified, and JOLTS lags two months. Judge the trend from the latest observations available; a missing final month is not evidence.
- justification: one or two plain sentences, at most 300 characters, that a general reader can follow, naming the evidence that decided it.
- confidence: 1 (a guess) to 5 (strong, consistent evidence)."""


def build_prompt(signal, period, evidence):
    lines = [
        f"Signal: {signal['name']}",
        f"Month: {period}",
        f"Accelerating means: {signal['accelerating']}",
        f"Stabilizing means: {signal['stabilizing']}",
        "",
        "Evidence:",
    ]
    for part in evidence:
        lines += part["lines"]
    return "\n".join(lines)


def validate(result):
    """The schema is enforced by the API, but a different provider or a bug must not write bad data."""
    if result.get("status") not in STATUSES:
        raise ValueError(f"bad status: {result.get('status')!r}")
    if result.get("confidence") not in (1, 2, 3, 4, 5):
        raise ValueError(f"bad confidence: {result.get('confidence')!r}")
    if not isinstance(result.get("justification"), str) or not result["justification"].strip():
        raise ValueError("empty justification")
    if len(result["justification"]) > MAX_JUSTIFICATION:
        raise ValueError(f"justification longer than {MAX_JUSTIFICATION} characters")
    return {"status": result["status"], "justification": result["justification"].strip(), "confidence": result["confidence"]}


def classify(llm, prompt):
    """Return (validated result, model that served it). Only the providers below are implemented."""
    if llm["provider"] == "anthropic":
        return _anthropic(llm, prompt)
    raise ValueError(f"LLM provider {llm['provider']!r} is not implemented; add a branch in classify_signals.py")


def _anthropic(llm, prompt):
    import json

    import anthropic

    response = anthropic.Anthropic().messages.create(
        model=llm["model"],
        max_tokens=llm["max_tokens"],
        thinking={"type": "adaptive"},
        output_config={"effort": llm["effort"], "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("model declined to classify")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("response hit max_tokens")
    text = next(b.text for b in response.content if b.type == "text")
    return validate(json.loads(text)), response.model
