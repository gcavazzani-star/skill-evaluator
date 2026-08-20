# Skill Evaluator

A generic **LLM-as-judge evaluation framework** for [Claude Code](https://claude.ai/code) skills.

Define a skill, describe what good output looks like in a rubric, and get automated scored reports — for as many skills as you need.

```
Input → Skill (Claude) → Output → Judge (Claude) → Score + HTML report
```

---

## Table of Contents

- [How it works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Step-by-step: adding a new skill](#step-by-step-adding-a-new-skill)
- [Running evals](#running-evals)
- [Interpreting results](#interpreting-results)
- [Improving a skill](#improving-a-skill)
- [Reference](#reference)
  - [CLI flags](#cli-flags)
  - [Environment variables](#environment-variables)
  - [Rubric format](#rubric-format)
  - [Test case format](#test-case-format)
  - [Skill files](#skill-files)
  - [Directory structure](#directory-structure)
- [CI/CD integration](#cicd-integration)
- [How scoring works](#how-scoring-works)

---

## How it works

**Two test-case types:**

| Type | What it tests | Score | Pass threshold |
|---|---|---|---|
| `generate` | Skill must produce structured output | 0–100 (weighted blocks) | ≥ 80 |
| `reject` | Skill must decline or redirect | 0–10 (binary pass/fail) | ≥ 8/10 |

**Three layers define a skill:**

1. **Skill files** — `.claude/skills/<name>/SKILL.md`, `examples.md`, `patterns.md` — define the behavior
2. **Rubric** — `evals/<name>/rubric.json` — define what "good" looks like, with weighted scoring blocks
3. **Test cases** — `evals/<name>/test_cases.json` — define input scenarios and expected behaviors

**The runner** (`run_eval.py`) calls the skill, then calls the judge, and renders an HTML report with scores, deltas vs last run, and an agent summary.

---

## Prerequisites

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)
- [Claude Code](https://claude.ai/code) (for the skill commands)

---

## Installation

```bash
git clone https://github.com/gcavazzani-star/skill-evaluator.git
cd skill-evaluator

cp .env.example .env
# → open .env and fill in ANTHROPIC_API_KEY

python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Verify setup:

```bash
python run_eval.py --help
```

---

## Quick start

If you already have a skill in `.claude/skills/<name>/` and an eval in `evals/<name>/`:

```bash
python run_eval.py --skill <name>
```

The HTML report opens automatically in your browser.

If you're starting from scratch, follow [Step-by-step: adding a new skill](#step-by-step-adding-a-new-skill).

---

## Step-by-step: adding a new skill

### Step 1 — Open Claude Code in this repository

```bash
claude   # or open Claude Code desktop and navigate to this directory
```

Make sure you're in the `skill-evaluator/` root. The hooks and rules only activate from this directory.

### Step 2 — Run the bootstrapper

In Claude Code's **chat** (not the terminal), type:

```
/setup-skill-eval
```

> Skills are invoked in the chat interface with `/skill-name`. They are not terminal commands.

Paste your context when prompted — a description of the skill, sample inputs, what the output should look like, what the skill should refuse to do.

Claude will:
1. Create `.claude/skills/<skill-name>/SKILL.md`, `examples.md`, `patterns.md`
2. Create `evals/<skill-name>/rubric.json` with weighted scoring blocks
3. Create `evals/<skill-name>/test_cases.json` with 8+ test cases (rich, partial, ambiguous, reject)
4. Generate input files in `evals/<skill-name>/inputs/`
5. Generate expected output files in `evals/<skill-name>/expected/`
6. Run a first validation pass

### Step 3 — Run the eval

```bash
python run_eval.py --skill <skill-name>
```

The report opens in your browser. Initial scores will be imperfect — the goal is to identify what to improve.

### Step 4 — Review the report

For any TC with score < 80 or verdict FAIL, run the debug skill in Claude Code:

```
/debug-tc
```

Tell it which skill and TC to analyze. It will read the generated output, rubric, and history, and produce a diagnosis with concrete recommendations.

### Step 5 — Improve and iterate

Based on the diagnosis:
- Edit `SKILL.md` to fix unclear instructions
- Edit `rubric.json` to fix ambiguous criteria
- Edit the input file to better cover the intended scenario

Re-run after each change:

```bash
python run_eval.py --skill <skill-name> --tc TC05 --no-browser --no-summary
```

Repeat until all TCs pass consistently.

### Step 6 — Add more test cases

```
/add-tc
```

Tell Claude which behavior you want to test. It will:
1. Determine the correct TC type (generate/reject)
2. Create the input file
3. Add the TC to test_cases.json with the correct sequential ID
4. Validate everything is consistent

### Step 7 — Measure variance (optional)

To check how stable the skill's behavior is across multiple runs:

```bash
python run_eval.py --skill <skill-name> --runs 3
```

The report shows `score ± stddev` for each TC. High stddev on a TC signals nondeterministic behavior in the skill or judge.

---

## Running evals

### Full run

```bash
python run_eval.py --skill <name>
```

Runs all TCs in parallel, opens the HTML report, and saves results to `history.jsonl`.

### Single TC

```bash
python run_eval.py --skill <name> --tc TC05
```

Faster feedback loop. Does **not** write to `history.jsonl`.

### Common options

```bash
# Skip browser auto-open
python run_eval.py --skill <name> --no-browser

# Skip agent summary (faster, saves API calls)
python run_eval.py --skill <name> --no-summary

# Increase parallelism (default: 4)
python run_eval.py --skill <name> --workers 8

# Run each TC N times — reports mean ± stddev
python run_eval.py --skill <name> --runs 3

# Print judge detail on ERROR TCs
python run_eval.py --skill <name> --verbose
```

### Judge cache

Repeated runs with identical skill output skip the judge API call — results are loaded from `.judge_cache.json`. The cache is automatically invalidated when the rubric structure changes (block IDs). Delete it manually if you change judge criteria descriptions:

```bash
del evals/<name>/.judge_cache.json     # Windows
rm evals/<name>/.judge_cache.json      # macOS/Linux
```

---

## Interpreting results

### HTML report

The report opens automatically after each run. Click any row to expand the TC detail view, which shows:

- Input sent to the skill
- Output produced by the skill (best run when `--runs N > 1`)
- Score breakdown by criterion with judge justifications
- Delta vs previous run (green `+N` / red `-N`)

### Terminal output

```
[TC01] [OK]  87/100  PASS  (12.3s)
[TC03] [OK]  95/100  PASS  (3.1s)
[TC05] [XX]  62/100  FAIL  (8.7s)
```

### Score history

Every full run appends a line to `evals/<name>/history.jsonl`:

```json
{"ts": "2026-08-19T14:30:00", "tcs": {"TC01": 87, "TC03": 95, "TC05": 62}, "avg_gen": 81, "rej_pass": 4, "rej_total": 7}
```

Read it to track trends: `cat evals/<name>/history.jsonl`

### Verbosity bias warning

If the judge's scores correlate strongly with output length (Pearson > 0.7), the report shows a warning banner. This means the judge may be rewarding volume instead of quality — consider calibrating the rubric or using a separate judge model.

### Separate metrics for generate and reject

These two metrics are **incomparable** — never average them:

| Metric | Meaning | Pass |
|---|---|---|
| `avg_gen` (0–100) | Average weighted score across generate TCs | ≥ 80 |
| `rej_pass / rej_total` | Count of reject TCs correctly handled | Target: all |

High generation score + low rejection rate → skill generates well but doesn't refuse when it should.
Low generation score + high rejection rate → skill is too cautious, doesn't produce quality output.

---

## Improving a skill

### Diagnosing a failing TC

```
/debug-tc
```

In Claude Code, invoke the skill and tell it: skill name + TC ID. It reads the generated output, expected behavior, rubric criteria, and history, then delivers a root-cause diagnosis and ranked recommendations.

### Adding a test case

```
/add-tc
```

In Claude Code, invoke the skill and describe what behavior you want to cover. It creates the input file, adds the entry to `test_cases.json`, and validates everything is consistent.

### Editing SKILL.md

After changing `SKILL.md`:
1. The `post_write_checks.py` hook verifies that `examples.md` and `patterns.md` still exist
2. Re-run affected TCs to verify the change had the expected effect
3. If judge cache exists, it's still valid — the cache keys on output content, not SKILL.md

### Editing rubric.json

After changing `rubric.json`:
1. The `post_write_checks.py` hook verifies weights sum to 1.0 and all required fields are present
2. The hook warns if the judge cache may be stale (delete it to force re-evaluation)
3. Re-run all TCs to see the effect of the rubric change on scores

---

## Reference

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--skill <name>` | required | Skill to evaluate |
| `--tc <id>` | all TCs | Run a single TC (no history write) |
| `--workers <n>` | 4 | Parallel workers |
| `--runs <n>` | 1 | Runs per TC — reports mean ± stddev |
| `--no-browser` | false | Skip auto-open of HTML report |
| `--no-summary` | false | Skip agent analysis (saves API calls) |
| `--verbose` | false | Print judge detail inline on ERROR |

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `ANTHROPIC_BASE_URL` | No | — | Override for corporate proxies / Bedrock |
| `SKILL_MODEL` | No | `anthropic.claude-4-6-sonnet` | Model for skill execution |
| `JUDGE_MODEL` | No | same as `SKILL_MODEL` | Model for judging — set to a **different** model than `SKILL_MODEL` to avoid self-preference bias |

**Recommended:** use different models for skill and judge:

```env
SKILL_MODEL=claude-sonnet-5
JUDGE_MODEL=claude-opus-4-5
```

### Rubric format

```json
{
  "pass_threshold": 80,
  "judge_instructions": "For each criterion, score 0–10. Compute weighted_score = sum(block_avg * weight * 100).",
  "reject_judge_instructions": "Score 10 = exactly right. Score 0 = wrong. PASS if score >= 8.",
  "generate_blocks": [
    {
      "id": "E",
      "name": "Structure",
      "weight": 0.20,
      "binary": false,
      "criteria": [
        { "id": "E1", "description": "All required sections are present" },
        { "id": "E2", "description": "Header table has all required fields" }
      ]
    },
    {
      "id": "P",
      "name": "Prohibited behaviors",
      "weight": 0.10,
      "binary": true,
      "criteria": [
        { "id": "P1", "description": "No fabricated rules without basis in input — auto-fail if present" }
      ]
    }
  ],
  "reject_criteria": {
    "B1": "Does NOT generate output — asks for input first",
    "B7": "Does NOT merge multiple distinct products — asks which one to start with"
  }
}
```

**Key rules:**
- `generate_blocks[*].weight` must sum to exactly **1.0**
- `binary: true` blocks: any failing criterion zeros the **entire block**
- `reject_criteria`: each TC references **exactly one** key

### Test case format

```json
[
  {
    "id": "TC01",
    "description": "Rich transcript — full extraction expected",
    "type": "generate",
    "input_file": "rich_transcript.txt",
    "expected_file": "expected_output.md",
    "expected_behavior": "Generates complete document with all sections, confidence markers on every table row, and approval request at the end.",
    "scoring_blocks": ["E", "C", "X", "Q", "P"]
  },
  {
    "id": "TC05",
    "description": "No input — must request context before proceeding",
    "type": "reject",
    "prompt": "I want to model a data product.",
    "expected_behavior": "Does NOT generate. Identifies missing input and asks for a transcript or document.",
    "scoring_blocks": ["B1"]
  }
]
```

- `input_file` resolves from `evals/<skill>/inputs/`
- Use `prompt` for short inline inputs (reject TCs typically use this)
- `expected_file` resolves from `evals/<skill>/expected/` — optional, used for comparison
- `scoring_blocks` for generate: list only the blocks the scenario exercises
- `scoring_blocks` for reject: exactly one `reject_criteria` key

### Skill files

Each skill lives in `.claude/skills/<name>/` and consists of three files concatenated as the system prompt at eval time:

| File | Purpose |
|---|---|
| `SKILL.md` | Core behavior: frontmatter triggers, chain-of-thought, output template, rules |
| `examples.md` | Few-shot examples calibrating behavior for rich, partial, and ambiguous inputs |
| `patterns.md` | Guard rails: prohibited behaviors and responses for unexpected situations |

The `SKILL.md` frontmatter controls when Claude Code activates the skill:

```markdown
---
name: my-skill
description: >
  Activate when the user shares X and asks for Y.
  Also activate when the user explicitly invokes /my-skill.
negative_triggers: >
  Do NOT activate if the user already has an approved output and wants to move to the next step.
  Do NOT activate if the request is purely about SQL, pipelines, or infrastructure.
---
```

Manual invocation in Claude Code: `/<name>`

### Directory structure

```
.claude/
  skills/
    <skill-name>/
      SKILL.md             ← behavior: chain-of-thought, DoR, output template
      examples.md          ← few-shot examples
      patterns.md          ← edge cases and prohibited behaviors
    setup-skill-eval/      ← /setup-skill-eval: bootstraps a new eval from scratch
    debug-tc/              ← /debug-tc: diagnoses a failing TC
    add-tc/                ← /add-tc: guided creation of new test cases
  rules/                   ← read by Claude automatically via CLAUDE.md → Navigation Rules table
    skill-navigation.md    ← how to find and read skill files
    eval-navigation.md     ← how to navigate rubric, TCs, inputs, expected
    find-patterns.md       ← Glob/Grep/Read quick reference for this project
    before-edit-framework.md ← what to read before touching run_eval.py or scorer.py
    read-results.md        ← how to read history.jsonl and generated outputs
    ⚠ Adding a new rule file? Also add it to the Navigation Rules table in CLAUDE.md.
  hooks/
    post_write_checks.py   ← validates rubric.json, test_cases.json, .py syntax, SKILL.md
    guard_git_add.py       ← blocks git add of eval runtime outputs
  settings.json            ← hook registration

evals/
  <skill-name>/
    rubric.json            ← scoring definition
    test_cases.json        ← TC list
    inputs/                ← input files
    expected/              ← gold-standard outputs for comparison
    generated/             ← runtime outputs (gitignored)
    report.html            ← last HTML report (gitignored)
    history.jsonl          ← append-only score log (gitignored)
    .judge_cache.json      ← judge response cache (gitignored)

run_eval.py                ← generic runner
scorer.py                  ← generic LLM-as-judge
.github/workflows/
  skill-eval.yml           ← CI: runs evals on push, uploads report as artifact
requirements.txt
.env.example
```

---

## CI/CD integration

The included GitHub Actions workflow (`.github/workflows/skill-eval.yml`) runs evals automatically on every push that touches skill or eval files.

**Setup:**
1. Add `ANTHROPIC_API_KEY` to your repository secrets (`Settings → Secrets → Actions`)
2. Optionally add `SKILL_MODEL` and `JUDGE_MODEL` secrets

**Behavior:**
- Discovers all skills with a rubric in `evals/`
- Runs `run_eval.py --skill <name> --no-browser --no-summary` for each
- Uploads `report.html` as a build artifact
- **Exits with code 1 if any TC fails** — this gates PRs automatically

To trigger manually: `Actions → Skill Eval → Run workflow`

---

## How scoring works

### Generate TCs

```
weighted_score = Σ (block_avg_score × block_weight × 100)
PASS if weighted_score >= 80
```

Each block's average = mean of its criteria scores (0–10 each), scaled to 0–100.
Blocks with `binary: true`: if any criterion scores below a threshold, the entire block = 0.

### Reject TCs

```
PASS if judge_score >= 8   (out of 10)
```

The judge scores the single criterion in `scoring_blocks` on a 0–10 scale.
Reject and generate scores are never averaged together in summary metrics.

### Judge model and bias

By default, the same model acts as both skill and judge. This can introduce **self-preference bias** — the model rates its own output more favorably. To mitigate:

```env
JUDGE_MODEL=claude-opus-4-5   # different from SKILL_MODEL
```

When set, the HTML report shows both models in the header.

### Verbosity bias

The runner computes the Pearson correlation between output length and score across generate TCs. If `|correlation| > 0.7`, a warning banner appears in the HTML report — the judge may be rewarding verbosity rather than quality.

---

## License

MIT
