# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Purpose

This repository is a **generic skill evaluation framework** for Claude Code skills. Define a skill, write a rubric, and run automated LLM-as-judge evaluations — for any skill you create.

---

## Setup

```powershell
cp .env.example .env   # fill in ANTHROPIC_API_KEY

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`.env` variables:
- `ANTHROPIC_API_KEY` — required
- `ANTHROPIC_BASE_URL` — optional, for corporate proxies
- `SKILL_MODEL` — model for skill execution and judging (default: `anthropic.claude-4-6-sonnet`)

---

## Running Evals

```powershell
python run_eval.py --skill <name>
python run_eval.py --skill <name> --tc TC01
python run_eval.py --skill <name> --no-browser --no-summary
python run_eval.py --skill <name> --workers 2
```

Results → `evals/<skill>/generated/<TC_ID>_output.md` and `evals/<skill>/report.html`.

**Pass threshold:** 80/100 (generate) | 8/10 (reject).

---

## Adding a New Skill

Run `/setup-skill-eval` in Claude Code and paste your context. Claude will scaffold everything and validate with a test run.

---

## Framework Architecture

### Directory Structure

```
.claude/skills/<skill-name>/     ← SKILL.md, examples.md, patterns.md
evals/<skill-name>/
  rubric.json                    ← scoring blocks, weights, criteria
  test_cases.json                ← TC definitions
  inputs/                        ← input files
  expected/                      ← gold-standard outputs
  generated/                     ← runtime outputs (gitignored)
  report.html                    ← last report (gitignored)
scorer.py                        ← generic LLM-as-judge
run_eval.py                      ← generic runner
```

### Core Components

| File | Role |
|---|---|
| `run_eval.py` | Loads rubric, runs skill, invokes judge, renders HTML report |
| `scorer.py` | Builds judge prompt from `rubric.json`, parses response, computes score |
| `evals/<skill>/rubric.json` | Rubric — generate blocks (weighted) + reject criteria (binary) |
| `evals/<skill>/test_cases.json` | TCs — `id`, `type`, `input_file` or `prompt`, `scoring_blocks` |
| `.claude/skills/setup-skill-eval/SKILL.md` | Meta-skill — bootstraps a new skill eval from scratch |

### Test Case Types

- **`generate`** — scored across weighted rubric blocks (0–100, pass ≥ 80)
- **`reject`** — scored on a single behavior criterion (pass ≥ 8/10)

### Scoring

```
# Generate
weighted_score = sum(block_avg * block_weight * 100)
PASS if weighted_score >= 80

# Reject
PASS if judge_score >= 8
```

Blocks with `binary: true` in the rubric: any criterion violation → 0 for the entire block.

Report metrics are separated by type — generation score (0–100) and rejection rate (count/total) are never averaged together.
