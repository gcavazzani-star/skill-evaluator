"""
Generic test runner for Claude Code skill evaluations.

Usage:
    python run_eval.py --skill modelagem-conceitual
    python run_eval.py --skill minha-skill --tc TC01
    python run_eval.py --skill minha-skill --workers 2 --no-browser --no-summary
"""
import os
import sys
import json
import re
import time
import threading
import concurrent.futures
import webbrowser
import argparse
from pathlib import Path
from datetime import datetime

import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv

from scorer import score as judge_score, _call_with_retry

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv()

BASE_URL = os.environ.get("ANTHROPIC_BASE_URL")
TOKEN    = os.environ.get("ANTHROPIC_API_KEY")
MODEL       = os.environ.get("SKILL_MODEL", "anthropic.claude-4-6-sonnet")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", MODEL)

BASE_DIR  = Path(__file__).parent
EVALS_DIR = BASE_DIR / "evals"
SKILL_DIR = BASE_DIR / ".claude" / "skills"


def _eval_dir(skill: str) -> Path:
    return EVALS_DIR / skill

def _skill_dir(skill: str) -> Path:
    return SKILL_DIR / skill

# ---------------------------------------------------------------------------
# Client + skill helpers
# ---------------------------------------------------------------------------

def build_client() -> Anthropic:
    kwargs = {
        "api_key": TOKEN,
        "default_headers": {"Authorization": f"Bearer {TOKEN}"},
    }
    if BASE_URL:
        kwargs["base_url"] = BASE_URL
    return Anthropic(**kwargs)


def build_system_prompt(skill: str) -> str:
    parts = []
    for fname in ("SKILL.md", "examples.md", "patterns.md"):
        path = _skill_dir(skill) / fname
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


def load_rubric(skill: str) -> dict:
    path = _eval_dir(skill) / "rubric.json"
    if not path.exists():
        print(f"ERRO: rubric.json nao encontrado em {path}")
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def build_criteria_descriptions(rubric: dict) -> dict:
    """Build {criterion_id: description} from rubric for HTML rendering."""
    desc = {}
    for block in rubric.get("generate_blocks", []):
        for c in block.get("criteria", []):
            desc[c["id"]] = c["description"]
    for bid, text in rubric.get("reject_criteria", {}).items():
        desc[bid] = text
    return desc


def get_input_text(tc: dict, eval_dir: Path) -> str:
    if "input_file" in tc:
        path = eval_dir / "inputs" / tc["input_file"]
        if path.exists():
            return path.read_text(encoding="utf-8")
        return f"[ERRO: arquivo nao encontrado: {path}]"
    return tc.get("prompt", "Quero usar esta skill.")


def get_expected_content(tc: dict, eval_dir: Path) -> str:
    ef = tc.get("expected_file")
    if ef:
        path = eval_dir / "expected" / ef
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


def run_skill(client: Anthropic, system_prompt: str, input_text: str) -> str:
    response = _call_with_retry(lambda: client.messages.create(
        model=MODEL,
        max_tokens=10000,
        system=system_prompt,
        messages=[{"role": "user", "content": input_text}],
    ))
    return response.content[0].text


# ---------------------------------------------------------------------------
# Agent summary
# ---------------------------------------------------------------------------

def generate_agent_summary(client: Anthropic, results: list) -> str:
    gen_results = [r for r in results if r["tc"]["type"] == "generate"]
    rej_results = [r for r in results if r["tc"]["type"] == "reject"]

    avg_gen  = round(sum(r["score"] for r in gen_results) / len(gen_results)) if gen_results else None
    rej_pass = sum(1 for r in rej_results if r["verdict"] == "PASS")
    passed   = sum(1 for r in results if r["verdict"] == "PASS")

    lines = []
    for r in results:
        tc     = r["tc"]
        blocks = r["scoring"].get("blocks", [])
        block_info = " ".join(
            f"{b['id']}:{round(sum(c['score'] for c in b['criteria']) / (len(b['criteria']) * 10) * 100)}"
            for b in blocks if b.get("criteria")
        )
        snippet = r["scoring"].get("summary", "")[:400]
        lines.append(
            f"- {tc['id']} ({tc['type']}): {r['verdict']} score={r['score']}/100"
            + (f" [{block_info}]" if block_info else "")
            + (f"\n  judge: {snippet}" if snippet else "")
        )

    gen_summary = (
        f"Score Geração (média): {avg_gen}/100 | corte: 80/100"
        if avg_gen is not None else "Sem TCs de geração"
    )
    rej_summary = (
        f"Rejeição Correta: {rej_pass}/{len(rej_results)} (binário pass/fail)"
        if rej_results else "Sem TCs de rejeição"
    )

    tc_lines = "\n".join(lines)
    prompt   = (
        "Você é um avaliador sênior de qualidade de sistemas de IA. "
        "Analise os resultados abaixo e gere um relatório em português brasileiro.\n\n"
        f"Resultados dos {len(results)} casos de teste:\n{tc_lines}\n\n"
        "Métricas separadas por tipo:\n"
        f"  • {gen_summary}\n"
        f"  • {rej_summary}\n"
        f"  • Aprovados (total): {passed}/{len(results)}\n\n"
        "IMPORTANTE: NÃO calcule nem cite um 'score médio geral' — as métricas de "
        "geração e rejeição são incomparáveis entre si e devem ser analisadas separadamente.\n\n"
        "Escreva uma análise com estas seções (use os títulos exatos):\n\n"
        "**Diagnóstico Geral**\n"
        "Em 2-3 frases: estado atual da skill nos dois eixos (geração e rejeição).\n\n"
        "**Pontos Fortes**\n"
        "- Liste comportamentos demonstrados consistentemente bem (máximo 4 bullets)\n\n"
        "**Pontos de Atenção**\n"
        "- Liste padrões de falha com o ID do(s) TC(s) afetado(s) (máximo 4 bullets)\n\n"
        "**Recomendações**\n"
        "- Ações concretas para melhorar a skill ou os casos de teste (máximo 3 bullets)\n\n"
        "Seja objetivo, específico e técnico. Máximo 320 palavras total."
    )

    try:
        resp = _call_with_retry(lambda: client.messages.create(
            model=MODEL,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        ))
        return resp.content[0].text
    except Exception as exc:
        return f"Não foi possível gerar a análise do agente: {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Markdown → HTML
# ---------------------------------------------------------------------------

def _md_inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+?)\*",  r"<em>\1</em>",         text)
    text = re.sub(r"`([^`]+?)`",    r"<code>\1</code>",      text)
    return text


def _md_to_html(text: str) -> str:
    lines  = text.split("\n")
    out    = []
    in_ul  = False
    in_ol  = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul: out.append("</ul>"); in_ul = False
        if in_ol: out.append("</ol>"); in_ol = False

    for line in lines:
        if line.startswith("### "):
            close_lists(); out.append(f"<h4>{_md_inline(line[4:])}</h4>")
        elif line.startswith("## "):
            close_lists(); out.append(f"<h3>{_md_inline(line[3:])}</h3>")
        elif line.startswith("# "):
            close_lists(); out.append(f"<h2>{_md_inline(line[2:])}</h2>")
        elif line.startswith("**") and line.rstrip().endswith("**") and len(line.strip()) > 4:
            inner = line.strip()[2:-2]
            close_lists(); out.append(f"<h4>{_md_inline(inner)}</h4>")
        elif re.match(r"^[-*] ", line):
            if in_ol: out.append("</ol>"); in_ol = False
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f"<li>{_md_inline(line[2:])}</li>")
        elif re.match(r"^\d+\. ", line):
            if in_ul: out.append("</ul>"); in_ul = False
            if not in_ol: out.append("<ol>"); in_ol = True
            out.append(f"<li>{_md_inline(re.sub(r'^\\d+\\. ', '', line))}</li>")
        elif not line.strip():
            close_lists()
        else:
            close_lists(); out.append(f"<p>{_md_inline(line)}</p>")

    close_lists()
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Per-TC runner
# ---------------------------------------------------------------------------

def _run_one_tc(
    tc: dict,
    client: Anthropic,
    system_prompt: str,
    rubric: dict,
    eval_dir: Path,
    gen_dir: Path,
    print_lock: threading.Lock,
    verbose: bool = False,
    judge_model: str = "",
) -> dict:
    input_text       = get_input_text(tc, eval_dir)
    expected_content = get_expected_content(tc, eval_dir)
    output           = ""
    t0               = time.monotonic()

    try:
        output = run_skill(client, system_prompt, input_text)
        (gen_dir / f"{tc['id']}_output.md").write_text(output, encoding="utf-8")
        scoring = judge_score(
            client, judge_model or JUDGE_MODEL, tc, input_text, output, rubric, expected_content
        )
    except anthropic.AuthenticationError:
        raise
    except Exception as exc:
        scoring = {
            "blocks":         [],
            "weighted_score": 0,
            "verdict":        "ERROR",
            "summary":        f"{type(exc).__name__}: {exc}",
        }

    elapsed = round(time.monotonic() - t0, 1)
    sc      = int(round(scoring.get("weighted_score", 0)))
    verdict = scoring.get("verdict", "ERROR")
    symbol  = "OK" if verdict == "PASS" else ("!!" if verdict == "ERROR" else "XX")

    with print_lock:
        print(f"  [{tc['id']}] [{symbol}] {sc:3d}/100  {verdict}  ({elapsed}s)")
        if verbose and verdict == "ERROR":
            print(f"         {scoring.get('summary', '')[:120]}")

    return {
        "tc":      tc,
        "input":   input_text,
        "output":  output,
        "scoring": scoring,
        "score":   sc,
        "verdict": verdict,
        "elapsed": elapsed,
    }


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _bar(score_pct, min_width=None):
    color = "#3fb950" if score_pct >= 80 else "#d29922" if score_pct >= 50 else "#f85149"
    style = f"width:{score_pct}%;background:{color};"
    w     = f"min-width:{min_width}px;" if min_width else ""
    return (
        f'<div class="bar-wrap">'
        f'<div class="bar-bg" style="{w}"><div class="bar-fill" style="{style}"></div></div>'
        f'<span class="bar-num" style="color:{color}">{score_pct}</span>'
        f'</div>'
    )


def _kpi_color(pct):
    if pct >= 80: return "green"
    if pct >= 50: return "yellow"
    return "red"


def _block_pct_map(blocks: list) -> dict:
    result = {}
    for b in blocks:
        criteria = b.get("criteria", [])
        if criteria:
            result[b["id"]] = round(
                sum(c["score"] for c in criteria) / (len(criteria) * 10) * 100
            )
    return result


def _mini_blocks(scoring_blocks: list, block_pct: dict) -> str:
    tiles = []
    for bid in scoring_blocks:
        pct   = block_pct.get(bid, 0)
        color = "#3fb950" if pct >= 80 else "#d29922" if pct >= 50 else "#f85149"
        bg    = "#0f2b1a" if pct >= 80 else "#2a1a00" if pct >= 50 else "#2d1010"
        tiles.append(
            f'<span class="mini-block" style="color:{color};background:{bg};" '
            f'title="{bid}: {pct}/100">{bid}</span>'
        )
    return '<div class="mini-blocks">' + "".join(tiles) + "</div>"


def _block_overview(blocks: list) -> str:
    html = ""
    for b in blocks:
        criteria = b.get("criteria", [])
        if not criteria:
            continue
        pct    = round(sum(c["score"] for c in criteria) / (len(criteria) * 10) * 100)
        color  = "#3fb950" if pct >= 80 else "#d29922" if pct >= 50 else "#f85149"
        name   = b.get("name", b["id"])
        weight = round(b.get("weight", 0) * 100)
        html  += (
            f'<div class="bov-row">'
            f'<span class="bov-label">{b["id"]}'
            f'<span class="bov-name"> — {name}</span></span>'
            f'<div class="bar-bg bov-bar">'
            f'<div class="bar-fill" style="width:{pct}%;background:{color};"></div></div>'
            f'<span class="bov-score" style="color:{color}">{pct}'
            f'<span style="color:#6e7681;font-size:0.7rem;">/100</span></span>'
            f'<span class="bov-weight">{weight}%</span>'
            f'</div>'
        )
    return html


def _render_blocks(blocks: list, criteria_descriptions: dict) -> str:
    if not blocks:
        return '<p style="color:#6e7681;font-size:0.8rem;padding:0.5rem 0;">Sem dados de scoring.</p>'
    html = ""
    for b in blocks:
        criteria = b.get("criteria", [])
        if not criteria:
            continue
        pct    = round(sum(c["score"] for c in criteria) / (len(criteria) * 10) * 100)
        weight = round(b.get("weight", 0) * 100)
        name   = b.get("name", b["id"])
        html  += (
            f'<div class="block-header">'
            f'<span class="block-title">{b["id"]} — {name}</span>'
            f'<span class="block-score">{pct}/100 '
            f'<span style="color:#484f58;font-size:0.7rem;">peso {weight}%</span></span>'
            f'</div>'
        )
        for c in criteria:
            pct_c = round(c["score"] / 10 * 100)
            color = "#3fb950" if pct_c >= 80 else "#d29922" if pct_c >= 50 else "#f85149"
            desc  = criteria_descriptions.get(c["id"], "")
            just  = c.get("justification", "").replace("<", "&lt;").replace(">", "&gt;")
            bar   = (
                f'<div class="crit-bar">'
                f'<div class="bar-bg" style="width:64px;">'
                f'<div class="bar-fill" style="width:{pct_c}%;background:{color};"></div></div>'
                f'<span class="bar-num" style="color:{color};font-size:0.7rem;width:30px;">'
                f'{c["score"]}/10</span>'
                f'</div>'
            )
            html += (
                f'<div class="crit-row">'
                f'<span class="crit-id">{c["id"]}</span>'
                f'{bar}'
                f'<div class="crit-text">'
                f'<span class="crit-desc">{desc}</span>'
                + (f'<span class="crit-just">{just}</span>' if just else "")
                + f'</div></div>'
            )
    return html


# ---------------------------------------------------------------------------
# CSS / JS (identical to run_tests.py visual style)
# ---------------------------------------------------------------------------

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0d1117; color: #e2e8f0; line-height: 1.5; }
code { font-family: 'Cascadia Code','Fira Code','Courier New',monospace; }
.header { background: linear-gradient(135deg,#161b27 0%,#0d1117 100%);
          padding: 2rem 2.5rem; border-bottom: 1px solid #21262d; }
.header h1 { font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em; color: #f0f6fc; }
.header .sub { font-size: 0.8rem; color: #6e7681; margin-top: 0.2rem; }
.kpi-row { display: flex; gap: 1rem; margin-top: 1.25rem; flex-wrap: wrap; }
.kpi { background: #161b27; border: 1px solid #21262d; border-radius: 10px;
       padding: 0.8rem 1.2rem; min-width: 115px; }
.kpi-label { font-size: 0.68rem; text-transform: uppercase;
             letter-spacing: 0.08em; color: #6e7681; }
.kpi-value { font-size: 1.5rem; font-weight: 700; margin-top: 0.1rem; }
.kpi-value.green  { color: #3fb950; }
.kpi-value.yellow { color: #d29922; }
.kpi-value.red    { color: #f85149; }
.agent-section { padding: 1.25rem 2.5rem 0; }
.agent-card { background: #161b27; border: 1px solid #30363d;
              border-left: 3px solid #58a6ff; border-radius: 10px;
              padding: 1.2rem 1.5rem; }
.agent-card-title { font-size: 0.72rem; text-transform: uppercase;
                    letter-spacing: 0.08em; color: #58a6ff; margin-bottom: 0.75rem; }
.agent-card-body { font-size: 0.84rem; color: #c9d1d9; line-height: 1.7; }
.agent-card-body h4, .agent-card-body h3, .agent-card-body h2
  { font-size: 0.84rem; font-weight: 700; color: #f0f6fc; margin: 0.8rem 0 0.3rem; }
.agent-card-body p  { margin-bottom: 0.35rem; }
.agent-card-body ul, .agent-card-body ol { padding-left: 1.2rem; margin-bottom: 0.4rem; }
.agent-card-body li { margin-bottom: 0.2rem; }
.agent-card-body strong { color: #f0f6fc; }
.agent-card-body em     { color: #a5d6ff; font-style: normal; }
.agent-card-body code   { font-size: 0.78rem; background: #0d1117;
  padding: 0.1rem 0.3rem; border-radius: 4px; color: #79c0ff; }
.agent-error { color: #6e7681; font-style: italic; font-size: 0.82rem; }
.table-wrap { padding: 1.25rem 2.5rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
thead th { padding: 0.55rem 0.9rem; background: #161b27; text-align: left;
           font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em;
           color: #6e7681; border-bottom: 1px solid #21262d; white-space: nowrap; }
tbody tr.tc-row { border-bottom: 1px solid #161b27; cursor: pointer;
                  transition: background 0.12s; }
tbody tr.tc-row:hover  { background: #161b27; }
tbody tr.tc-row.active { background: #1c2333; }
tbody td { padding: 0.6rem 0.9rem; vertical-align: middle; }
.badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 5px;
         font-size: 0.68rem; font-weight: 700; letter-spacing: 0.04em; }
.pass  { background: #0f2b1a; color: #3fb950; border: 1px solid #1a4325; }
.fail  { background: #2d1010; color: #f85149; border: 1px solid #4b1515; }
.error { background: #1f1035; color: #b083f0; border: 1px solid #3c1c6b; }
.type-gen { background: #0d2044; color: #79acf7; border: 1px solid #1a3766; }
.type-rej { background: #2a1a00; color: #e3b341; border: 1px solid #4a3000; }
.bar-wrap { display: flex; align-items: center; gap: 0.45rem; }
.bar-bg   { flex: 1; height: 5px; background: #21262d; border-radius: 3px;
            overflow: hidden; min-width: 60px; }
.bar-fill { height: 100%; border-radius: 3px; }
.bar-num  { font-size: 0.78rem; font-weight: 600; width: 38px; text-align: right;
            font-variant-numeric: tabular-nums; }
.mini-blocks { display: flex; gap: 3px; }
.mini-block  { font-size: 0.62rem; font-weight: 700; padding: 0.1rem 0.32rem;
               border-radius: 3px; letter-spacing: 0.02em; cursor: default; }
.time-chip { font-size: 0.72rem; color: #484f58; font-variant-numeric: tabular-nums; }
.detail { display: none; background: #080d17; }
.detail.open { display: block; }
.detail-inner { padding: 1.5rem 2.5rem 2rem; border-top: 1px solid #21262d; }
.expected-box { background: #101820; border: 1px solid #1e3a5f;
                border-left: 3px solid #388bfd; border-radius: 8px;
                padding: 0.7rem 1rem; margin-bottom: 1.25rem; }
.expected-label { font-size: 0.68rem; text-transform: uppercase;
                  letter-spacing: 0.06em; color: #388bfd; margin-bottom: 0.3rem; }
.expected-text  { font-size: 0.82rem; color: #9ecbff; line-height: 1.65; }
.block-overview { background: #0d1117; border: 1px solid #21262d;
                  border-radius: 8px; padding: 0.9rem 1rem; margin-bottom: 1.25rem; }
.block-overview-title { font-size: 0.68rem; text-transform: uppercase;
  letter-spacing: 0.06em; color: #6e7681; margin-bottom: 0.6rem; }
.bov-row   { display: grid; grid-template-columns: 140px 1fr 70px 36px;
             gap: 0.5rem; align-items: center; padding: 0.22rem 0; }
.bov-label { font-size: 0.76rem; font-weight: 600; color: #c9d1d9; white-space: nowrap; }
.bov-name  { font-weight: 400; color: #6e7681; }
.bov-bar   { min-width: 80px; flex: 1; }
.bov-score { font-size: 0.78rem; font-weight: 700; text-align: right;
             font-variant-numeric: tabular-nums; }
.bov-weight { font-size: 0.68rem; color: #484f58; text-align: right; }
.summary-box { background: #0d1117; border: 1px solid #21262d; border-radius: 8px;
               padding: 0.7rem 1rem; margin-bottom: 1.25rem;
               font-size: 0.82rem; color: #8b949e; line-height: 1.65; }
.sum-label   { font-size: 0.68rem; text-transform: uppercase;
               letter-spacing: 0.06em; color: #6e7681;
               display: block; margin-bottom: 0.35rem; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem;
               margin-bottom: 1.25rem; }
@media (max-width: 900px) { .detail-grid { grid-template-columns: 1fr; } }
.panel { background: #0d1117; border: 1px solid #21262d; border-radius: 8px;
         overflow: hidden; }
.panel-title { padding: 0.45rem 0.75rem; background: #161b27; font-size: 0.68rem;
               text-transform: uppercase; letter-spacing: 0.06em;
               color: #6e7681; border-bottom: 1px solid #21262d; }
.panel-body { padding: 0.75rem; }
pre.code { font-family: 'Cascadia Code','Fira Code',monospace; font-size: 0.73rem;
           white-space: pre-wrap; word-break: break-word;
           max-height: 380px; overflow-y: auto; color: #c9d1d9; line-height: 1.65; }
.criteria-panel { background: #0d1117; border: 1px solid #21262d;
                  border-radius: 8px; overflow: hidden; }
.criteria-body  { padding: 0.5rem 0.75rem 0.75rem; }
.block-header { display: flex; justify-content: space-between; align-items: center;
                padding: 0.55rem 0; margin-top: 0.4rem;
                border-bottom: 1px solid #161b27; }
.block-title { font-size: 0.78rem; font-weight: 600; color: #e2e8f0; }
.block-score { font-size: 0.75rem; color: #8b949e; }
.crit-row  { display: grid; grid-template-columns: 30px 104px 1fr;
             gap: 0.5rem; align-items: start; padding: 0.28rem 0;
             border-bottom: 1px solid #0d1117; }
.crit-id   { color: #484f58; font-family: monospace; font-size: 0.72rem; padding-top: 3px; }
.crit-bar  { display: flex; align-items: center; gap: 0.3rem; padding-top: 2px; }
.crit-text { display: flex; flex-direction: column; gap: 0.1rem; }
.crit-desc { font-size: 0.73rem; color: #c9d1d9; }
.crit-just { font-size: 0.7rem; color: #8b949e; font-style: italic; }
.delta { font-size: 0.68rem; font-weight: 700; margin-left: 0.4rem;
          padding: 0.08rem 0.3rem; border-radius: 3px; font-variant-numeric: tabular-nums; }
.delta.pos     { color: #3fb950; background: #0f2b1a; }
.delta.neg     { color: #f85149; background: #2d1010; }
.delta.neutral { color: #484f58; background: #161b27; }
.footer { text-align: center; padding: 2rem; font-size: 0.72rem; color: #21262d; }
"""

JS = """
document.querySelectorAll('tbody tr.tc-row').forEach(row => {
  row.addEventListener('click', () => {
    const id = row.dataset.tc;
    const detail = document.getElementById('detail-' + id);
    if (!detail) return;
    const isOpen = detail.classList.contains('open');
    document.querySelectorAll('.detail').forEach(d => d.classList.remove('open'));
    document.querySelectorAll('tbody tr.tc-row').forEach(r => r.classList.remove('active'));
    if (!isOpen) {
      detail.classList.add('open');
      row.classList.add('active');
      detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });
});
"""


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def generate_html(
    results: list,
    timestamp: str,
    skill: str,
    criteria_descriptions: dict,
    agent_summary: str = "",
    judge_model: str = "",
    history: dict = None,
) -> str:
    total     = len(results)
    passed    = sum(1 for r in results if r["verdict"] == "PASS")
    pass_rate = round(passed / total * 100) if total else 0

    gen_results = [r for r in results if r["tc"]["type"] == "generate"]
    rej_results = [r for r in results if r["tc"]["type"] == "reject"]
    avg_gen     = round(sum(r["score"] for r in gen_results) / len(gen_results)) if gen_results else None
    rej_pass    = sum(1 for r in rej_results if r["verdict"] == "PASS")

    if agent_summary:
        body_html = (
            f'<p class="agent-error">{agent_summary}</p>'
            if agent_summary.startswith("Não foi possível")
            else _md_to_html(agent_summary)
        )
        agent_section = f"""
<div class="agent-section">
  <div class="agent-card">
    <div class="agent-card-title">&#129302; Análise do Agente</div>
    <div class="agent-card-body">{body_html}</div>
  </div>
</div>"""
    else:
        agent_section = ""

    rows    = ""
    details = ""

    for r in results:
        tc      = r["tc"]
        verdict = r["verdict"]
        sc      = r["score"]
        elapsed = r.get("elapsed", 0)

        badge      = f'<span class="badge {verdict.lower()}">{verdict}</span>'
        type_badge = (
            '<span class="badge type-gen">generate</span>'
            if tc["type"] == "generate"
            else '<span class="badge type-rej">reject</span>'
        )
        block_pct = _block_pct_map(r["scoring"].get("blocks", []))
        mini_b    = _mini_blocks(tc.get("scoring_blocks", []), block_pct)

        prev_score = (history or {}).get(tc["id"])
        if prev_score is not None and tc["type"] == "generate":
            delta = sc - prev_score
            if delta > 0:
                delta_html = f'<span class="delta pos">+{delta}</span>'
            elif delta < 0:
                delta_html = f'<span class="delta neg">{delta}</span>'
            else:
                delta_html = '<span class="delta neutral">±0</span>'
        else:
            delta_html = ""

        rows += (
            f'<tr class="tc-row" data-tc="{tc["id"]}">'
            f'<td><strong>{tc["id"]}</strong></td>'
            f'<td>{tc["description"]}</td>'
            f'<td>{type_badge}</td>'
            f'<td>{mini_b}</td>'
            f'<td>{_bar(sc)}{delta_html}</td>'
            f'<td>{badge}</td>'
            f'<td><span class="time-chip">{elapsed}s</span></td>'
            f'</tr>'
        )

        inp_safe = r["input"].replace("<", "&lt;").replace(">", "&gt;")
        out_safe = r["output"].replace("<", "&lt;").replace(">", "&gt;")
        summary  = r["scoring"].get("summary", "").replace("<", "&lt;").replace(">", "&gt;")
        exp_text = tc.get("expected_behavior", "").replace("<", "&lt;").replace(">", "&gt;")

        expected_html = (
            f'<div class="expected-box">'
            f'<div class="expected-label">Comportamento Esperado</div>'
            f'<div class="expected-text">{exp_text}</div>'
            f'</div>'
            if exp_text else ""
        )

        bov_html = ""
        if r["scoring"].get("blocks"):
            bov_inner = _block_overview(r["scoring"]["blocks"])
            bov_html  = (
                f'<div class="block-overview">'
                f'<div class="block-overview-title">Scores por Bloco</div>'
                f'{bov_inner}</div>'
            )

        summary_html = (
            f'<div class="summary-box"><span class="sum-label">Avaliação do Judge</span>{summary}</div>'
            if summary else ""
        )

        blocks_html = _render_blocks(r["scoring"].get("blocks", []), criteria_descriptions)

        details += f"""
        <tr class="detail" id="detail-{tc['id']}">
          <td colspan="7" style="padding:0;">
            <div class="detail-inner">
              {expected_html}
              {bov_html}
              {summary_html}
              <div class="detail-grid">
                <div class="panel">
                  <div class="panel-title">Input</div>
                  <div class="panel-body"><pre class="code">{inp_safe}</pre></div>
                </div>
                <div class="panel">
                  <div class="panel-title">Output da Skill</div>
                  <div class="panel-body"><pre class="code">{out_safe}</pre></div>
                </div>
              </div>
              <div class="criteria-panel">
                <div class="panel-title">Scoring por Critério</div>
                <div class="criteria-body">{blocks_html}</div>
              </div>
            </div>
          </td>
        </tr>"""

    rej_kpi = ""
    if rej_results:
        rej_pct   = round(rej_pass / len(rej_results) * 100)
        rej_color = _kpi_color(rej_pct)
        rej_kpi   = (
            f'<div class="kpi">'
            f'<div class="kpi-label">Rejeição Correta</div>'
            f'<div class="kpi-value {rej_color}">{rej_pass}'
            f'<span style="font-size:0.9rem;color:#6e7681;">/{len(rej_results)}</span>'
            f'</div></div>'
        )

    gen_kpi = ""
    if avg_gen is not None:
        gen_color = _kpi_color(avg_gen)
        gen_kpi   = (
            f'<div class="kpi">'
            f'<div class="kpi-label">Score Geração</div>'
            f'<div class="kpi-value {gen_color}">{avg_gen}'
            f'<span style="font-size:0.9rem;color:#6e7681;">/100</span>'
            f'</div></div>'
        )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eval Report — {skill}</title>
<style>{CSS}</style>
</head>
<body>

<div class="header">
  <h1>Skill Eval Report — {skill}</h1>
  <div class="sub">Gerado em {timestamp} &nbsp;|&nbsp; Skill: {MODEL}{f' &nbsp;|&nbsp; Judge: <span style="color:#d29922">{judge_model}</span>' if judge_model and judge_model != MODEL else ''}</div>
  <div class="kpi-row">
    <div class="kpi">
      <div class="kpi-label">Aprovados / Total</div>
      <div class="kpi-value {_kpi_color(pass_rate)}">{passed}<span style="font-size:0.9rem;color:#6e7681;">/{total}</span></div>
    </div>
    {gen_kpi}
    {rej_kpi}
    <div class="kpi">
      <div class="kpi-label">TCs Executados</div>
      <div class="kpi-value" style="color:#e2e8f0;">{total}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Corte de Aprovação</div>
      <div class="kpi-value" style="color:#6e7681;">80<span style="font-size:0.9rem;">/100</span></div>
    </div>
  </div>
</div>

{agent_section}

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th style="width:60px">TC</th>
        <th>Descrição</th>
        <th style="width:80px">Tipo</th>
        <th style="width:120px">Blocos</th>
        <th style="width:180px">Score Total</th>
        <th style="width:70px">Status</th>
        <th style="width:55px">Tempo</th>
      </tr>
    </thead>
    <tbody>
      {rows}
      {details}
    </tbody>
  </table>
</div>

<div class="footer">
  Clique em qualquer linha para expandir o TC &nbsp;|&nbsp;
  Skill: <code>.claude/skills/{skill}/SKILL.md</code> &nbsp;|&nbsp;
  Rubrica: <code>evals/{skill}/rubric.json</code>
</div>

<script>{JS}</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generic skill eval runner")
    parser.add_argument("--skill",      required=True,      help="Nome da skill (ex: modelagem-conceitual)")
    parser.add_argument("--tc",         default="",         help="Rodar apenas um TC (ex: TC01)")
    parser.add_argument("--workers",    type=int, default=4, help="Workers paralelos (default: 4)")
    parser.add_argument("--no-browser", action="store_true", help="Nao abre browser ao final")
    parser.add_argument("--verbose",    action="store_true", help="Imprime detalhe de erros inline")
    parser.add_argument("--no-summary", action="store_true", help="Pula analise do agente")
    args = parser.parse_args()

    if not TOKEN:
        print("ERRO: ANTHROPIC_API_KEY nao configurada. Crie um arquivo .env baseado em .env.example")
        sys.exit(1)

    eval_dir  = _eval_dir(args.skill)
    skill_dir = _skill_dir(args.skill)
    gen_dir   = eval_dir / "generated"

    if not eval_dir.exists():
        print(f"ERRO: Diretorio de eval nao encontrado: {eval_dir}")
        print(f"Dica: rode /setup-skill-eval para configurar a skill '{args.skill}'")
        sys.exit(1)

    if not skill_dir.exists():
        print(f"ERRO: Skill nao encontrada: {skill_dir}")
        sys.exit(1)

    gen_dir.mkdir(exist_ok=True)

    rubric      = load_rubric(args.skill)
    criteria_desc = build_criteria_descriptions(rubric)
    test_cases  = json.loads((eval_dir / "test_cases.json").read_text(encoding="utf-8"))

    if args.tc:
        tc_id      = args.tc.upper()
        test_cases = [tc for tc in test_cases if tc["id"] == tc_id]
        if not test_cases:
            print(f"ERRO: TC '{tc_id}' nao encontrado em {eval_dir / 'test_cases.json'}")
            sys.exit(1)

    tc_order = {tc["id"]: i for i, tc in enumerate(test_cases)}
    workers  = min(args.workers, len(test_cases))

    # Load last run from history for delta display
    history_path = eval_dir / "history.jsonl"
    prev_scores: dict = {}
    if history_path.exists():
        try:
            last_line = history_path.read_text(encoding="utf-8").strip().splitlines()[-1]
            prev_scores = json.loads(last_line).get("tcs", {})
        except Exception:
            pass

    client        = build_client()
    system_prompt = build_system_prompt(args.skill)

    judge_label = f" | judge: {JUDGE_MODEL}" if JUDGE_MODEL != MODEL else ""
    print(f"\nSkill Eval Runner — skill: {args.skill} | {len(test_cases)} TC(s) | modelo: {MODEL}{judge_label} | workers: {workers}")
    print("-" * 70)

    results    = []
    print_lock = threading.Lock()

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_tc = {
            executor.submit(
                _run_one_tc, tc, client, system_prompt, rubric,
                eval_dir, gen_dir, print_lock, args.verbose, JUDGE_MODEL
            ): tc
            for tc in test_cases
        }
        for future in concurrent.futures.as_completed(future_to_tc):
            tc = future_to_tc[future]
            try:
                results.append(future.result())
            except anthropic.AuthenticationError as exc:
                print(f"\nERRO DE AUTENTICACAO: {exc}")
                executor.shutdown(wait=False, cancel_futures=True)
                sys.exit(1)
            except Exception as exc:
                results.append({
                    "tc":      tc,
                    "input":   get_input_text(tc, eval_dir),
                    "output":  "",
                    "scoring": {"blocks": [], "weighted_score": 0, "verdict": "ERROR", "summary": str(exc)},
                    "score":   0,
                    "verdict": "ERROR",
                    "elapsed": 0.0,
                })

    results.sort(key=lambda r: tc_order.get(r["tc"]["id"], 999))

    print("-" * 70)
    passed   = sum(1 for r in results if r["verdict"] == "PASS")
    gen_res  = [r for r in results if r["tc"]["type"] == "generate"]
    rej_res  = [r for r in results if r["tc"]["type"] == "reject"]
    avg_gen  = round(sum(r["score"] for r in gen_res) / len(gen_res)) if gen_res else None
    rej_pass = sum(1 for r in rej_res if r["verdict"] == "PASS")
    gen_part = f"score geracao: {avg_gen}/100" if avg_gen is not None else ""
    rej_part = f"rejeicao: {rej_pass}/{len(rej_res)}" if rej_res else ""
    metrics  = " | ".join(p for p in [gen_part, rej_part] if p)
    print(f"Resultado: {passed}/{len(results)} aprovados | {metrics}\n")

    agent_summary = ""
    if not args.no_summary and results:
        print("Gerando analise do agente...")
        agent_summary = generate_agent_summary(client, results)
        print("OK\n")

    ts_iso  = datetime.now().isoformat(timespec="seconds")
    ts_disp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Persist run to history.jsonl (append)
    if not args.tc:  # só salva histórico em runs completos
        history_entry = {
            "ts":          ts_iso,
            "skill_model": MODEL,
            "judge_model": JUDGE_MODEL,
            "tcs":         {r["tc"]["id"]: r["score"] for r in results},
            "avg_gen":     round(sum(r["score"] for r in gen_res) / len(gen_res)) if gen_res else None,
            "rej_pass":    rej_pass,
            "rej_total":   len(rej_res),
        }
        with history_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(history_entry, ensure_ascii=False) + "\n")
        print(f"Historico: {history_path}")

    html = generate_html(
        results, ts_disp, args.skill, criteria_desc, agent_summary,
        judge_model=JUDGE_MODEL,
        history=prev_scores if not args.tc else None,
    )
    report_path = eval_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"Relatorio: {report_path}")

    if not args.no_browser:
        webbrowser.open(report_path.as_uri())

    # Exit code non-zero for CI gates
    if passed < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
