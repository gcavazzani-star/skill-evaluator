# Rule: Before Editing Framework Code

**Trigger:** sempre que o usuário pedir para modificar `run_eval.py` ou `scorer.py`.

---

## Antes de editar run_eval.py

### 1. Mapa de funções

```
Grep("^def ", "run_eval.py", output_mode="content")
```

Funções principais e o que cada uma faz:

| Função | Responsabilidade |
|---|---|
| `build_client()` | Cria client Anthropic com API key e base_url opcionais |
| `build_system_prompt(skill)` | Concatena SKILL.md + examples.md + patterns.md |
| `load_rubric(skill)` | Lê e parseia rubric.json; falha com mensagem clara se ausente |
| `get_input_text(tc, eval_dir)` | Lê `input_file` ou retorna `prompt` diretamente |
| `get_expected_content(tc, eval_dir)` | Lê `expected_file` se declarado |
| `run_skill(client, system_prompt, input_text)` | Chama API com MODEL para gerar output |
| `_cache_key(tc_id, output, jmodel, rubric)` | Hash sha256[:16] para o judge cache |
| `_load_judge_cache(eval_dir)` | Lê `.judge_cache.json`; retorna {} se ausente |
| `_save_judge_cache(eval_dir, cache)` | Salva cache completo ao final do run |
| `_pearson(xs, ys)` | Correlação de Pearson para verbosity bias detection |
| `generate_agent_summary(client, results)` | LLM summary dos resultados usando MODEL |
| `_run_one_tc(...)` | Executa um TC: skill → cache check → judge → agrega N runs |
| `generate_html(...)` | Monta o report HTML com deltas, stddev, banner de verbosity |
| `main()` | Parse de args, workers, history, cache, verbosity, HTML, exit code |

### 2. Localizar a seção relevante

```
Grep("def _run_one_tc", "run_eval.py", output_mode="content")
Grep("def generate_html", "run_eval.py", output_mode="content")
Grep("def main", "run_eval.py", output_mode="content")
```

### 3. Parâmetros CLI disponíveis

```
Grep("add_argument", "run_eval.py", output_mode="content")
```

Argumentos: `--skill`, `--tc`, `--workers`, `--runs`, `--no-browser`, `--verbose`, `--no-summary`

### 4. Variáveis de ambiente lidas

```
Grep("os.environ", "run_eval.py", output_mode="content")
```

Variáveis: `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `SKILL_MODEL`, `JUDGE_MODEL`

---

## Antes de editar scorer.py

### 1. Leitura completa obrigatória

```
Read("scorer.py")
```

É o arquivo menor (≈ 260 linhas) — leia inteiro antes de qualquer edição.

### 2. API pública — não altere a assinatura

```python
def score(
    client,
    model: str,
    tc: dict,
    input_text: str,
    output_text: str,
    rubric: dict,
    expected_content: str = "",
) -> dict:
```

`run_eval.py` chama via alias `judge_score = score`. Qualquer mudança na assinatura
quebra o runner sem erro óbvio.

### 3. Estrutura do retorno

O dict retornado por `score()` deve sempre ter:
- `blocks` — lista de blocos com `id`, `name`, `weight`, `criteria` (cada critério: `id`, `score`, `justification`)
- `weighted_score` — float 0–100
- `verdict` — `"PASS"` | `"FAIL"` | `"ERROR"`
- `summary` — string com análise geral do judge

---

## Após qualquer edição em .py

O hook `post_write_checks.py` valida sintaxe via `py_compile` automaticamente.
Se reportar erro, corrija antes de tentar rodar o eval.

Para validar manualmente:
```
python -m py_compile run_eval.py
python -m py_compile scorer.py
```

---

## Regras críticas

- **Mudança em scorer.py invalida o judge cache** — se o prompt do judge mudou,
  delete `evals/<skill>/.judge_cache.json` para forçar re-avaliação.
- **Nunca altere MODEL padrão** — o default é `anthropic.claude-4-6-sonnet` e
  foi fixado intencionalmente. Mudanças de modelo vão via variável de ambiente.
- **O exit code 1 é CI gate** — `main()` chama `sys.exit(1)` se qualquer TC falha.
  Não remova esse comportamento.
