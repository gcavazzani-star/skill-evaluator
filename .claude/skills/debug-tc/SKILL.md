---
name: debug-tc
description: >
  Use esta skill para diagnosticar por que um test case está falhando.
  Ative quando o usuário mencionar um TC com score baixo, um TC que falhou,
  ou pedir para entender o que está errado com um resultado de eval.
  Funciona com qualquer skill do framework.

negative_triggers: >
  NÃO ative esta skill se:
  - O usuário quer criar um novo TC (use /add-tc).
  - O usuário quer rodar o eval (use run_eval.py diretamente).
  - O usuário quer ajustar a rubrica sem analisar um TC específico.
  - O usuário quer melhorar o SKILL.md sem contexto de falha.
---

# Skill: Debug TC

**Versão:** 1.0.0

---

## Objetivo

Diagnosticar a causa raiz de um test case com score baixo ou veredicto FAIL/ERROR,
identificando se o problema está no output da skill, na rubrica ou no input,
e entregando recomendações concretas e priorizadas.

---

## Pré-condições

Antes de executar, identifique:

1. **Nome da skill** — pasta em `evals/<skill>/`
2. **ID do TC** — ex: TC05

Se algum dos dois estiver ausente, pergunte ao usuário antes de prosseguir.
Não invente valores. Se o usuário disse apenas "o TC5 falhou", confirme se é TC05.

---

## Raciocínio Encadeado

Execute obrigatoriamente nesta ordem. Não pule etapas.

### Passo 1 — Coletar definição do TC

```
Read("evals/<skill>/test_cases.json")
```

Extraia do TC identificado:
- `type` — generate ou reject
- `input_file` ou `prompt`
- `expected_behavior`
- `expected_file` (se presente)
- `scoring_blocks` — quais blocos/critérios serão avaliados

### Passo 2 — Ler o output gerado

```
Read("evals/<skill>/generated/<TC_ID>_output.md")
```

Se o arquivo não existir: o TC ainda não foi executado. Informe ao usuário e
sugira: `python run_eval.py --skill <skill> --tc <TC_ID> --no-browser --no-summary`

### Passo 3 — Ler o input real (se TC usa input_file)

```
Read("evals/<skill>/inputs/<input_file>")
```

Isso permite avaliar se o output faz sentido dado o input.

### Passo 4 — Ler o expected (se existir)

```
Read("evals/<skill>/expected/<expected_file>")
```

Se não houver `expected_file`, use o campo `expected_behavior` do TC como referência.

### Passo 5 — Ler a rubrica para entender os critérios aplicados

```
Read("evals/<skill>/rubric.json")
```

Foque nos blocos listados em `scoring_blocks` do TC.
Para TCs de rejeição, foque no critério em `reject_criteria`.

### Passo 6 — Verificar histórico de scores

```
Read("evals/<skill>/history.jsonl")
```

Se o arquivo existir, compare o score atual do TC com runs anteriores:
- Score caiu em relação ao último run? → possível regressão introduzida por mudança recente
- Score sempre foi baixo? → problema estrutural no SKILL.md ou rubrica

### Passo 7 — Ler o SKILL.md para cruzar com o output

```
Read(".claude/skills/<skill>/SKILL.md")
```

Verifique se o output segue o formato de saída definido na skill.
Para TCs de rejeição, verifique o `negative_triggers` e as pré-condições (DoR) da skill.

---

## Diagnóstico

Com base nos dados coletados, produza o diagnóstico no formato abaixo.

### Formato de saída

```
## Diagnóstico — <SKILL> / <TC_ID>

**Score:** <score>/100  |  **Veredicto:** <PASS/FAIL/ERROR>
**Tipo:** <generate/reject>

---

### O que falhou

[Para cada critério com score baixo, uma linha:]
- **<ID do critério>** (<score>/10) — <o que estava sendo avaliado> → <o que o output fez de errado>

[Para TCs de rejeição:]
- **<criterion-id>** — a skill <gerou / não recusou / respondeu parcialmente> quando deveria <recusar / redirecionar>

---

### Causa raiz provável

[Uma das três:]
- **Problema no output da skill** — o SKILL.md não instrui claramente o comportamento X
- **Problema na rubrica** — o critério X é ambíguo ou exige algo que o input não permite avaliar
- **Problema no input** — o input sintético não cobre o cenário que o TC pretende testar

---

### Recomendações

[Máximo 3, ordenadas por impacto:]

1. [Ação concreta — ex: "Adicionar ao SKILL.md, seção Passo 3, a instrução explícita de que..."]
2. [Ação concreta — ex: "Reformular critério X2 da rubrica de '...' para '...' para reduzir ambiguidade"]
3. [Ação concreta — ex: "Adicionar ao input a informação Y que está ausente e impede a avaliação correta do critério X"]

---

**Para re-testar após aplicar as correções:**
```
python run_eval.py --skill <skill> --tc <TC_ID> --no-browser --no-summary
```
```

---

## Regras do diagnóstico

- Nunca culpe o judge sem evidência de que o output estava correto
- Se o output parece correto mas o score é baixo, o problema pode ser a rubrica — diga isso explicitamente
- Se o TC é de rejeição e a skill gerou conteúdo, priorize isso acima de qualquer outra falha
- Se o arquivo `generated/` não existe, não faça diagnóstico — peça ao usuário para rodar o TC primeiro
- Se history.jsonl mostrar que o TC passou em runs anteriores, inclua "possível regressão" no diagnóstico
