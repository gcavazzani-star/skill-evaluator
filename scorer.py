"""
Generic LLM-as-judge scoring for skill evaluations.

Usage:
    from scorer import score, _call_with_retry

    result = score(client, model, tc, input_text, output_text, rubric, expected_content)
"""
import json
import re
import time

import anthropic

JUDGE_SYSTEM = (
    "Voce e um avaliador tecnico de qualidade de IA. "
    "Retorna APENAS JSON valido, sem texto adicional, sem markdown."
)

_RETRYABLE_ERRORS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
)


def _call_with_retry(fn, max_retries: int = 3, base_delay: float = 1.0):
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except anthropic.AuthenticationError:
            raise
        except _RETRYABLE_ERRORS as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(base_delay * (2 ** attempt))
    raise last_exc


# ---------------------------------------------------------------------------
# Rubric text builders
# ---------------------------------------------------------------------------

def _rubric_text(rubric: dict) -> str:
    """Build the rubric text block for the generate judge prompt."""
    lines = []
    for block in rubric["generate_blocks"]:
        pct     = int(block["weight"] * 100)
        binary  = ", binario - qualquer ocorrencia = score 0 no bloco" if block.get("binary") else ""
        lines.append(f"\nBLOCO {block['id']} - {block['name']} (peso {pct}%{binary}):")
        for c in block["criteria"]:
            lines.append(f"{c['id']}: {c['description']}")
    return "\n".join(lines)


def _json_template_generate(rubric: dict) -> str:
    """Build the empty JSON template for the generate judge prompt."""
    blocks = []
    for block in rubric["generate_blocks"]:
        criteria = [
            {"id": c["id"], "score": 0, "max": 10, "justification": ""}
            for c in block["criteria"]
        ]
        blocks.append({
            "id":       block["id"],
            "name":     block["name"],
            "weight":   block["weight"],
            "criteria": criteria,
        })
    return json.dumps(
        {"blocks": blocks, "weighted_score": 0, "verdict": "PASS", "summary": ""},
        ensure_ascii=False,
    )


def _json_template_reject(block_id: str) -> str:
    return json.dumps(
        {
            "blocks": [{
                "id": block_id,
                "name": "Comportamento de Borda",
                "weight": 1.0,
                "criteria": [{"id": block_id, "score": 0, "max": 10, "justification": ""}],
            }],
            "weighted_score": 0,
            "verdict": "FAIL",
            "summary": "",
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_generate_prompt(tc, input_text, output_text, rubric, expected_content):
    expected_section = ""
    if expected_content:
        expected_section = (
            f"\n\n## Escopo de referencia (para comparacao de extracao)\n"
            f"{expected_content[:3000]}"
        )

    instructions = rubric.get(
        "judge_instructions",
        "Para cada criterio, atribua score de 0 a 10. "
        "Calcule weighted_score = soma(media_bloco * peso_bloco * 100). "
        "Nota de corte PASS: weighted_score >= 80.",
    )

    return (
        f"Avalie o output gerado pela skill contra a rubrica abaixo.\n\n"
        f"## Comportamento esperado\n{tc['expected_behavior']}\n\n"
        f"## Input fornecido\n{input_text[:2000]}\n\n"
        f"## Output gerado pela skill\n{output_text}"
        f"{expected_section}\n\n"
        f"## Rubrica de avaliacao\n{_rubric_text(rubric)}\n\n"
        f"## Instrucoes\n{instructions}\n\n"
        f"Retorne SOMENTE este JSON (preencha os scores e justificativas):\n\n"
        f"{_json_template_generate(rubric)}"
    )


def _build_reject_prompt(tc, input_text, output_text, rubric):
    block_id       = tc["scoring_blocks"][0]
    criterion_desc = rubric.get("reject_criteria", {}).get(block_id, "Comportamento de borda")
    instructions   = rubric.get(
        "reject_judge_instructions",
        "Score 10: comportamento exatamente correto. "
        "Score 5: comportamento parcialmente correto. "
        "Score 0: comportamento incorreto. "
        "verdict: PASS se score >= 8, FAIL caso contrario.",
    )

    return (
        f"Avalie se a skill se comportou corretamente dado o input abaixo.\n\n"
        f"## Criterio avaliado ({block_id})\n{criterion_desc}\n\n"
        f"## Comportamento esperado\n{tc['expected_behavior']}\n\n"
        f"## Input fornecido\n{input_text}\n\n"
        f"## Output gerado pela skill\n{output_text}\n\n"
        f"## Instrucoes\n{instructions}\n\n"
        f"Retorne SOMENTE este JSON:\n\n"
        f"{_json_template_reject(block_id)}"
    )


# ---------------------------------------------------------------------------
# JSON extraction + scoring
# ---------------------------------------------------------------------------

def _extract_json(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _compute_weighted_score(result: dict) -> int:
    total = 0.0
    for block in result.get("blocks", []):
        criteria = block.get("criteria", [])
        if not criteria:
            continue
        block_avg = sum(c["score"] for c in criteria) / (len(criteria) * 10)
        total += block_avg * block.get("weight", 1.0)
    return round(total * 100)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score(
    client,
    model: str,
    tc: dict,
    input_text: str,
    output_text: str,
    rubric: dict,
    expected_content: str = "",
) -> dict:
    """Score a single TC output using the provided rubric."""
    if tc["type"] == "generate":
        base_prompt = _build_generate_prompt(
            tc, input_text, output_text, rubric, expected_content
        )
    else:
        base_prompt = _build_reject_prompt(tc, input_text, output_text, rubric)

    raw    = ""
    result = None

    for attempt in range(2):
        prompt = (
            base_prompt
            if attempt == 0
            else (
                "Sua resposta anterior estava incompleta ou com JSON malformado. "
                "Retorne APENAS o JSON valido e completo, sem texto adicional, "
                "sem markdown, sem truncacao:\n\n" + base_prompt
            )
        )
        try:
            response = _call_with_retry(
                lambda: client.messages.create(
                    model=model,
                    max_tokens=8000,
                    system=JUDGE_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                )
            )
        except anthropic.AuthenticationError:
            raise
        except Exception as exc:
            return {
                "blocks":         [],
                "weighted_score": 0,
                "verdict":        "ERROR",
                "summary":        f"{type(exc).__name__}: {exc}",
            }

        raw    = response.content[0].text
        result = _extract_json(raw)
        if result is not None:
            break

    if result is None:
        return {
            "blocks":         [],
            "weighted_score": 0,
            "verdict":        "ERROR",
            "summary":        f"JSON invalido apos 2 tentativas. Raw: {raw[:300]}",
        }

    if result.get("weighted_score", 0) == 0:
        result["weighted_score"] = _compute_weighted_score(result)

    pass_threshold = 80
    if result.get("verdict") not in ("PASS", "FAIL", "ERROR"):
        result["verdict"] = (
            "PASS" if result["weighted_score"] >= pass_threshold else "FAIL"
        )

    return result
