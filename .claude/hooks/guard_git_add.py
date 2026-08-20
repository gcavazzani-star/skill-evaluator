#!/usr/bin/env python3
"""
PreToolUse hook — bloqueia 'git add' que incluiria outputs de eval.
Protege: generated/, report.html, history.jsonl, .judge_cache.json
"""
import sys
import json
import re

PROTECTED_PATTERNS = [
    (r"evals[/\\][^/\\]+[/\\]generated", "evals/*/generated/"),
    (r"evals[/\\][^/\\]+[/\\]report\.html", "evals/*/report.html"),
    (r"evals[/\\][^/\\]+[/\\]history\.jsonl", "evals/*/history.jsonl"),
    (r"evals[/\\][^/\\]+[/\\]\.judge_cache\.json", "evals/*/.judge_cache.json"),
    (r"\breport\.html\b", "report.html"),
    (r"\bhistory\.jsonl\b", "history.jsonl"),
    (r"\.judge_cache\.json\b", ".judge_cache.json"),
]

WILDCARD_RE = re.compile(
    r"git\s+add\s+("
    r"-A|--all"
    r"|\.(\s|$)"
    r"|evals/?(\s|$)"
    r"|evals\\?(\s|$)"
    r")",
    re.IGNORECASE,
)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not re.search(r"\bgit\s+add\b", command):
        sys.exit(0)

    hits = []
    if WILDCARD_RE.search(command):
        hits.append("wildcard (git add -A / git add . / git add evals/)")

    for pattern, label in PROTECTED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            hits.append(label)

    if not hits:
        sys.exit(0)

    print("", file=sys.stderr)
    print("✗  [guard_git_add] bloqueado — o comando incluiria arquivos de runtime:", file=sys.stderr)
    for h in hits:
        print(f"   · {h}", file=sys.stderr)
    print("", file=sys.stderr)
    print("   Adicione arquivos individualmente, por exemplo:", file=sys.stderr)
    print("     git add run_eval.py scorer.py CLAUDE.md .gitignore", file=sys.stderr)
    print("", file=sys.stderr)
    print("   Estes arquivos não devem ir para o repositório:", file=sys.stderr)
    print("     evals/*/generated/   — outputs gerados a cada run", file=sys.stderr)
    print("     evals/*/report.html  — relatório HTML (gitignored)", file=sys.stderr)
    print("     evals/*/history.jsonl — histórico de scores", file=sys.stderr)
    print("     evals/*/.judge_cache.json — cache do judge", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
