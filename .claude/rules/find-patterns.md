# Rule: Find Patterns — Referência de Busca

**Trigger:** sempre. Use esta tabela como ponto de partida para qualquer busca
neste projeto antes de tentar adivinhar onde algo está.

---

## Descoberta de skills e evals

| O que encontrar | Ferramenta |
|---|---|
| Todas as skills configuradas | `Glob(".claude/skills/*/SKILL.md")` |
| Skills que têm eval | `Glob("evals/*/rubric.json")` |
| Skills sem eval ainda | Compare os dois Globs acima |
| Arquivos de uma skill específica | `Glob(".claude/skills/<nome>/*")` |
| Arquivos de um eval específico | `Glob("evals/<nome>/*")` |
| Todos os inputs de um eval | `Glob("evals/<nome>/inputs/*")` |
| Todos os expected de um eval | `Glob("evals/<nome>/expected/*")` |
| Outputs do último run | `Glob("evals/<nome>/generated/*")` |

---

## Busca em test_cases.json

```
path = "evals/<skill>/test_cases.json"
```

| O que encontrar | Grep |
|---|---|
| TC específico (ex: TC05) | `Grep('"TC05"', path, output_mode="content", -C=3)` |
| Todos os TCs de geração | `Grep('"generate"', path, output_mode="content")` |
| Todos os TCs de rejeição | `Grep('"reject"', path, output_mode="content")` |
| TCs que usam bloco E | `Grep('"E"', path, output_mode="content")` |
| TCs que usam bloco B7 | `Grep('"B7"', path, output_mode="content")` |
| TCs com arquivo de input | `Grep("input_file", path, output_mode="content")` |
| TCs com prompt direto | `Grep('"prompt"', path, output_mode="content")` |
| TCs com expected_file | `Grep("expected_file", path, output_mode="content")` |

---

## Busca em rubric.json

```
path = "evals/<skill>/rubric.json"
```

| O que encontrar | Grep |
|---|---|
| IDs de todos os blocos | `Grep('"id"', path, output_mode="content")` |
| Pesos dos blocos | `Grep("weight", path, output_mode="content")` |
| Blocos binary (proibidos) | `Grep("binary", path, output_mode="content")` |
| Critérios de rejeição | `Grep("reject_criteria", path, output_mode="content", -A=10)` |
| Descrição de critério X1 | `Grep('"X1"', path, output_mode="content", -C=2)` |

---

## Busca no código do framework

| O que encontrar | Grep |
|---|---|
| Todas as funções de run_eval.py | `Grep("^def ", "run_eval.py", output_mode="content")` |
| Todas as funções de scorer.py | `Grep("^def ", "scorer.py", output_mode="content")` |
| Onde o cache é lido | `Grep("judge_cache", "run_eval.py", output_mode="content")` |
| Onde o history é gravado | `Grep("history", "run_eval.py", output_mode="content")` |
| Onde o exit code é setado | `Grep("sys.exit", "run_eval.py", output_mode="content")` |
| Argumento --runs | `Grep("runs", "run_eval.py", output_mode="content")` |
| Cálculo de verbosity | `Grep("pearson\|verbosity\|corr", "run_eval.py", output_mode="content")` |

---

## Resultados e histórico

| O que encontrar | Ferramenta |
|---|---|
| Scores do último run | `Read("evals/<skill>/history.jsonl")` → última linha |
| Output de um TC específico | `Read("evals/<skill>/generated/TC01_output.md")` |
| O que está em cache | `Read("evals/<skill>/.judge_cache.json")` |
| Último report HTML | `evals/<skill>/report.html` (abrir no browser) |

---

## Busca cross-projeto

| O que encontrar | Grep |
|---|---|
| Qualquer menção a um TC ID | `Grep("TC05", glob="evals/**/*.json", output_mode="content")` |
| Todos os arquivos .py do projeto | `Glob("*.py")` |
| Hooks configurados | `Read(".claude/settings.json")` |
| Variáveis de ambiente suportadas | `Grep("os.environ", "run_eval.py", output_mode="content")` |
