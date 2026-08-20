# Rule: Eval Navigation

**Trigger:** sempre que o usuário mencionar rubric, test cases, TCs, scoring blocks,
inputs, expected, ou pedir para criar, modificar ou revisar qualquer arquivo de eval.

---

## Sequência de leitura ao entrar em um eval

### 1. Ler a rubrica

```
Read("evals/<skill>/rubric.json")
```

O que extrair:
- `generate_blocks`: IDs dos blocos (ex: E, C, X, Q, P), pesos (`weight`), quais são `binary: true`
- `reject_criteria`: chaves dos critérios de rejeição (ex: B1, B2, B7)
- `pass_threshold`: nota de corte (padrão: 80)
- Soma dos pesos dos blocos: deve ser exatamente 1.0

### 2. Ler os test cases

```
Read("evals/<skill>/test_cases.json")
```

O que notar por TC:
- `id` — identificador (TC01, TC02 ...)
- `type` — `"generate"` (scored 0–100) ou `"reject"` (pass/fail binário)
- `input_file` vs `prompt` — TCs com `input_file` exigem o arquivo físico em `inputs/`
- `expected_file` — se presente, deve existir em `expected/`
- `scoring_blocks` — lista dos blocos da rubrica que o judge avalia para este TC

### 3. Verificar arquivos físicos

```
Glob("evals/<skill>/inputs/*")
Glob("evals/<skill>/expected/*")
```

→ Compare com os `input_file` e `expected_file` declarados em test_cases.json.
→ Arquivos referenciados mas ausentes causam erro no runner — o hook `post_write_checks.py`
  já detecta isso ao salvar test_cases.json.

---

## Inspecionar um TC específico

```
Grep('"TC05"', "evals/<skill>/test_cases.json", output_mode="content")
```

Depois leia o input:
```
Read("evals/<skill>/inputs/<input_file_do_tc>")
```

E o expected, se houver:
```
Read("evals/<skill>/expected/<expected_file_do_tc>")
```

---

## Queries úteis no test_cases.json

| O que saber | Grep |
|---|---|
| Todos os TCs de geração | `Grep('"generate"', path, output_mode="content")` |
| Todos os TCs de rejeição | `Grep('"reject"', path, output_mode="content")` |
| TCs que avaliam o bloco E | `Grep('"E"', path, output_mode="content")` |
| TCs que avaliam B7 | `Grep('"B7"', path, output_mode="content")` |
| TCs com input_file | `Grep("input_file", path, output_mode="content")` |
| TCs com prompt direto | `Grep('"prompt"', path, output_mode="content")` |
| TCs com expected_file | `Grep("expected_file", path, output_mode="content")` |

---

## Antes de criar um novo TC

1. Leia test_cases.json para ver os IDs existentes — o próximo ID deve ser sequencial.
2. Se o TC usa `input_file`, crie o arquivo em `inputs/` **antes** de declarar o TC.
3. Se o TC usa `expected_file`, crie o arquivo em `expected/` **antes** de declarar o TC.
4. Verifique que os `scoring_blocks` declarados existem na rubrica:
   ```
   Grep("\"id\"", "evals/<skill>/rubric.json", output_mode="content")
   ```

**Regra:** nunca declarar `input_file` ou `expected_file` em test_cases.json sem
verificar com Glob que o arquivo existe em disco. O runner falha silenciosamente
se o arquivo estiver ausente.
