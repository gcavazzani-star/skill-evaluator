# Rule: Reading Eval Results

**Trigger:** sempre que o usuário perguntar sobre scores, resultados, tendências,
regressões, outputs gerados, ou pedir para interpretar o que aconteceu em um eval.

**Regra fundamental:** nunca reportar scores de memória. Sempre ler `history.jsonl`
ou rodar um eval fresco com `python run_eval.py --skill <nome>`.

---

## Scores históricos — history.jsonl

```
Read("evals/<skill>/history.jsonl")
```

Cada linha é um JSON de um run completo. Estrutura:

```json
{
  "ts":          "2026-08-19T14:30:00",
  "skill_model": "anthropic.claude-4-6-sonnet",
  "judge_model": "anthropic.claude-4-6-sonnet",
  "runs":        1,
  "tcs": {
    "TC01": 87,
    "TC02": 91,
    "TC03": 95
  },
  "avg_gen":   89,
  "rej_pass":  4,
  "rej_total": 7
}
```

Para ver o estado atual: leia a **última linha**.
Para ver tendências: leia todas as linhas e compare o dict `tcs` entre runs.
Para detectar regressão em um TC: ache o TC nas linhas anteriores e compare com a última.

O arquivo só existe após o primeiro run completo (sem `--tc`).
Runs com `--tc` (TC único) não são gravados no histórico.

---

## Output gerado de um TC específico

### Descobrir quais outputs existem

```
Glob("evals/<skill>/generated/*")
```

Nomeação: `TC01_output.md`, `TC02_output.md`, etc.
Contém o output da skill do **melhor run** quando `--runs N > 1`.

### Ler o output de um TC

```
Read("evals/<skill>/generated/TC01_output.md")
```

Para comparar com o esperado:
```
Read("evals/<skill>/expected/<expected_file_do_tc>")
```

O `expected_file` de cada TC está em `test_cases.json` — use `eval-navigation.md`
para localizar.

---

## Judge cache — o que foi avaliado vs reavaliado

```
Read("evals/<skill>/.judge_cache.json")
```

Cada chave é um hash de 16 chars de `sha256(judge_model|tc_id|rubric_sig|output)`.
O valor é o dict de scoring completo (mesmo formato retornado por `scorer.py`).

Um TC aparece no cache se:
- Seu output não mudou desde o último run
- O judge_model não mudou
- A rubrica (IDs dos blocos) não mudou

Se o cache existe mas os scores parecem desatualizados após edição da rubrica:
```
# deletar o cache para forçar re-avaliação completa
# (avisar o usuário antes — não deletar sem confirmar)
```

---

## Interpretar métricas separadamente

Os dois tipos de TC têm métricas incomparáveis — nunca calcule uma média geral:

| Tipo | Métrica | Corte |
|---|---|---|
| `generate` | `avg_gen` (0–100, média ponderada pelos blocos) | ≥ 80 = PASS |
| `reject` | `rej_pass / rej_total` (binário) | ≥ 8/10 = PASS |

Um score de geração alto com taxa de rejeição baixa significa: a skill gera bem
mas não se recusa quando deveria — problema de negative triggers.

O contrário (rejeição perfeita, geração baixa) significa: a skill é cautelosa
demais mas não produz output de qualidade.

---

## Rodar um eval rápido para atualizar resultados

```powershell
# Run completo
python run_eval.py --skill <nome> --no-browser

# TC específico (não grava no histórico)
python run_eval.py --skill <nome> --tc TC05 --no-browser --no-summary

# Com múltiplos runs para medir variância
python run_eval.py --skill <nome> --runs 3 --no-browser
```
