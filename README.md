# Skill Evaluator

A generic **LLM-as-judge evaluation framework** for [Claude Code](https://claude.ai/code) skills.

Define a skill, describe what good output looks like in a rubric, and get automated scored reports — for as many skills as you need.

---

## How it works

```
Input  →  Skill (Claude)  →  Output  →  Judge (Claude)  →  Score + HTML report
```

1. **Skill** — markdown files in `.claude/skills/<name>/` that define the behavior
2. **Rubric** — `evals/<name>/rubric.json` with weighted scoring blocks and reject criteria
3. **Runner** — `run_eval.py --skill <name>` ties it all together

Two test-case types:
- **`generate`** — skill must produce output; scored 0–100 across weighted blocks (pass ≥ 80)
- **`reject`** — skill must decline and redirect; scored as pass/fail (pass ≥ 8/10)

---

## Prerequisites

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)
- [Claude Code](https://claude.ai/code) (for the `/setup-skill-eval` bootstrapper)

---

## Setup

```bash
git clone https://github.com/gcavazzani-star/skill-evaluator.git
cd skill-evaluator

cp .env.example .env
# → fill in ANTHROPIC_API_KEY

python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Adding a new skill

Open Claude Code in this repo and run:

```
/setup-skill-eval
```

Paste your context — skill description, domain, sample inputs. Claude will:

1. Create `.claude/skills/<skill-name>/SKILL.md`, `examples.md`, `patterns.md`
2. Create `evals/<skill-name>/rubric.json` with domain-appropriate scoring blocks
3. Scaffold `inputs/`, `expected/`, `generated/` directories
4. Generate `test_cases.json` with 8+ diverse TCs (rich, partial, ambiguous, reject)
5. Run a validation pass and report any issues

Then run:

```bash
python run_eval.py --skill <skill-name>
```

---

## CLI reference

```bash
python run_eval.py --skill <name>               # run all test cases
python run_eval.py --skill <name> --tc TC01     # single TC
python run_eval.py --skill <name> --no-browser  # skip auto-open
python run_eval.py --skill <name> --no-summary  # skip agent analysis (faster)
python run_eval.py --skill <name> --workers 2   # parallel workers (default: 4)
python run_eval.py --skill <name> --verbose     # print judge detail on ERROR
```

---

## Repository structure

```
.claude/
  skills/
    <skill-name>/          ← one folder per skill
      SKILL.md             ← behavior: chain-of-thought, output template, rules
      examples.md          ← few-shot examples
      patterns.md          ← calibration guidance, anti-patterns
    setup-skill-eval/      ← meta-skill: bootstraps new eval environments
      SKILL.md

evals/
  <skill-name>/
    rubric.json            ← scoring definition (blocks, weights, criteria)
    test_cases.json        ← TC list (id, type, input_file or prompt, scoring_blocks)
    inputs/                ← input files referenced by TCs
    expected/              ← gold-standard output files for comparison
    generated/             ← runtime outputs (gitignored)
    report.html            ← last HTML report (gitignored)

run_eval.py                ← generic runner
scorer.py                  ← generic LLM-as-judge
requirements.txt
.env.example
```

---

## Rubric format (`rubric.json`)

```json
{
  "pass_threshold": 80,
  "judge_instructions": "Instructions for the generate judge...",
  "reject_judge_instructions": "Instructions for the reject judge...",
  "generate_blocks": [
    {
      "id": "E",
      "name": "Structure",
      "weight": 0.20,
      "binary": false,
      "criteria": [
        { "id": "E1", "description": "All required sections are present" }
      ]
    }
  ],
  "reject_criteria": {
    "B1": "Must request input before generating any output",
    "B2": "Must decline when context is insufficient"
  }
}
```

- **`generate_blocks`** — weighted 0–100; `binary: true` means any violation zeros the entire block
- **`reject_criteria`** — each TC names exactly one criterion; scored 0–10, pass ≥ 8

---

## Test case format (`test_cases.json`)

```json
[
  {
    "id": "TC01",
    "description": "Rich input — full extraction",
    "type": "generate",
    "input_file": "rich_input.txt",
    "expected_file": "expected_output.md",
    "expected_behavior": "Generates a complete document with all sections...",
    "scoring_blocks": ["E", "C", "X"]
  },
  {
    "id": "TC03",
    "description": "No input — must request context first",
    "type": "reject",
    "prompt": "I want to use this skill.",
    "expected_behavior": "Does NOT generate. Asks for input.",
    "scoring_blocks": ["B1"]
  }
]
```

`input_file` resolves from `evals/<skill>/inputs/`. Use `prompt` for inline inputs.

---

## Skill files

Each skill lives in `.claude/skills/<name>/` and auto-activates in Claude Code based on the `description` in `SKILL.md`'s frontmatter. Manual invocation: `/<skill-name>`.

```markdown
---
name: my-skill
description: Activates when the user shares X and asks for Y
---

## Chain of Thought

Step 1 — ...
Step 2 — ...
```

The three files are concatenated as the system prompt at eval time.

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `ANTHROPIC_BASE_URL` | No | — | Override for corporate proxies |
| `SKILL_MODEL` | No | `anthropic.claude-4-6-sonnet` | Model for skill execution and judging |

---

## License

MIT
