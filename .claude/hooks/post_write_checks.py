#!/usr/bin/env python3
"""
PostToolUse hook — roda após Write ou Edit.
Roteia para o validador correto com base no nome do arquivo.
"""
import sys
import json
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def validate_rubric(path: Path):
    errors, warnings = [], []
    try:
        rubric = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"JSON inválido: {e}"], []

    blocks = rubric.get("generate_blocks", [])
    if not blocks:
        errors.append("'generate_blocks' ausente ou vazio")
        return errors, warnings

    total_weight = 0.0
    for b in blocks:
        bid = b.get("id", "?")
        if not b.get("name"):
            errors.append(f"Bloco {bid}: campo 'name' ausente")
        if "weight" not in b:
            errors.append(f"Bloco {bid}: campo 'weight' ausente")
        else:
            total_weight += b["weight"]
        criteria = b.get("criteria")
        if not criteria:
            errors.append(f"Bloco {bid}: 'criteria' ausente ou vazio")
        else:
            for c in criteria:
                if not c.get("id"):
                    errors.append(f"Bloco {bid}: critério sem 'id'")
                if not c.get("description"):
                    errors.append(f"Bloco {bid}: critério '{c.get('id','?')}' sem 'description'")
        if b.get("binary") and b.get("weight", 0) > 0.15:
            warnings.append(
                f"Bloco {bid} é binary=true com peso {b['weight']:.0%} "
                f"— blocos proibidos costumam ficar em ≤ 15%"
            )

    if abs(total_weight - 1.0) > 0.001:
        errors.append(
            f"Pesos somam {total_weight:.4f}, esperado 1.0 "
            f"(diferença: {total_weight - 1.0:+.4f})"
        )

    cache_path = path.parent / ".judge_cache.json"
    if cache_path.exists():
        warnings.append(
            "rubric.json alterado — judge cache pode estar desatualizado. "
            f"Delete '{cache_path.name}' para forçar re-avaliação completa."
        )

    return errors, warnings


def check_tc_files(path: Path):
    errors, warnings = [], []
    try:
        tcs = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"JSON inválido: {e}"], []

    skill_dir    = path.parent
    inputs_dir   = skill_dir / "inputs"
    expected_dir = skill_dir / "expected"

    ids_seen = set()
    for tc in tcs:
        tid = tc.get("id", "?")
        if tid in ids_seen:
            errors.append(f"ID duplicado: {tid}")
        ids_seen.add(tid)

        if tc.get("type") not in ("generate", "reject"):
            errors.append(
                f"{tid}: 'type' deve ser 'generate' ou 'reject', "
                f"encontrado: {tc.get('type')!r}"
            )

        if not tc.get("description"):
            warnings.append(f"{tid}: campo 'description' ausente")

        if not tc.get("input_file") and not tc.get("prompt"):
            errors.append(f"{tid}: requer 'input_file' ou 'prompt'")

        if "input_file" in tc:
            f = inputs_dir / tc["input_file"]
            if not f.exists():
                errors.append(f"{tid}: input_file não encontrado → {f}")

        if "expected_file" in tc:
            f = expected_dir / tc["expected_file"]
            if not f.exists():
                errors.append(f"{tid}: expected_file não encontrado → {f}")

        if not tc.get("scoring_blocks"):
            warnings.append(f"{tid}: 'scoring_blocks' ausente — judge não saberá quais blocos avaliar")

    return errors, warnings


def check_py_syntax(path: Path):
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        msg = (result.stderr or result.stdout).strip()
        return [f"Erro de sintaxe:\n    {msg}"], []
    return [], []


def check_skill_completeness(path: Path):
    errors, warnings = [], []
    skill_dir = path.parent
    for fname in ("examples.md", "patterns.md"):
        if not (skill_dir / fname).exists():
            warnings.append(
                f"'{fname}' ausente em {skill_dir.name}/ "
                f"— o runner inclui este arquivo no system prompt"
            )
    try:
        content = path.read_text(encoding="utf-8")
        if "negative_triggers" not in content:
            warnings.append("frontmatter: campo 'negative_triggers' não encontrado")
        if not any(k in content for k in ("Pré-condições", "Pre-condicoes", "DoR")):
            warnings.append("seção de Pré-condições (DoR) não encontrada")
    except Exception:
        pass
    return errors, warnings


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    path      = Path(file_path)
    path_norm = str(path).replace("\\", "/")
    errors, warnings = [], []

    if path.name == "rubric.json" and "/evals/" in path_norm:
        e, w = validate_rubric(path)
        errors += e; warnings += w

    elif path.name == "test_cases.json" and "/evals/" in path_norm:
        e, w = check_tc_files(path)
        errors += e; warnings += w

    elif path.suffix == ".py" and path.name in ("run_eval.py", "scorer.py"):
        e, w = check_py_syntax(path)
        errors += e; warnings += w

    elif path.name == "SKILL.md" and "/.claude/" in path_norm:
        e, w = check_skill_completeness(path)
        errors += e; warnings += w

    else:
        sys.exit(0)

    label = path.name
    if warnings:
        print(f"\n⚠  [{label}]", file=sys.stderr)
        for w in warnings:
            print(f"   {w}", file=sys.stderr)

    if errors:
        print(f"\n✗  [{label}] — {len(errors)} erro(s):", file=sys.stderr)
        for e in errors:
            print(f"   {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
