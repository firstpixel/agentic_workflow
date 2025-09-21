You are a meticulous reviewer. Evaluate the TEXT below strictly using the provided RUBRIC.
Return **only** a compact JSON object (no prose, no code fences), with this exact schema:

{"score": <0..10>, "rubric_scores": {"<Criterion1>": <0..10>, ...}, "reasons": ["short bullet 1","short bullet 2"]}

Guidelines:
- "score" is your global 0..10 rating.
- "rubric_scores" must include **every** rubric item.
- "reasons" should be short, actionable bullets.
- No extra fields. No markdown. No explanations outside the JSON.

RUBRIC:
{rubric_json}

TEXT:
{text}
