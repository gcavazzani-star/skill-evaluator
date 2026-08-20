---
name: add-tc
description: >
  Use esta skill para criar um novo test case em um eval existente.
  Ative quando o usuário pedir para adicionar um TC, testar um novo comportamento,
  criar um cenário de teste, ou expandir a cobertura de uma skill.

negative_triggers: >
  NÃO ative esta skill se:
  - O usuário quer configurar um eval do zero (use /setup-skill-eval).
  - O usuário quer editar um TC existente (edite test_cases.json e inputs/ diretamente).
  - O usuário quer debugar um TC com score baixo (use /debug-tc).
  - O usuário quer rodar o eval após criar o TC (use run_eval.py diretamente).
---

# Skill: Add TC

**Versão:** 1.0.0

---

## Objetivo

Guiar a criação de um novo test case de forma completa e consistente:
ID sequencial correto, arquivo de input adequado ao cenário, entrada em
test_cases.json validada, e raciocínio explícito sobre qual comportamento está
sendo testado e por quê.

---

## Pré-condições

Antes de executar, identifique:

1. **Nome da skill** — pasta em `evals/<skill>/`
2. **O que o TC vai testar** — comportamento específico: se não estiver claro, pergunte

Se a skill não existir em `evals/`, informe o usuário para usar `/setup-skill-eval` primeiro.

---

## Raciocínio Encadeado

Execute obrigatoriamente nesta ordem. Não pule etapas.

### Passo 1 — Ler o estado atual dos TCs

```
Read("evals/<skill>/test_cases.json")
```

Extraia:
- Maior ID numérico existente → o novo TC será o próximo (ex: se TC13 existe, o novo é TC14)
- Quais comportamentos já estão cobertos → evitar duplicatas
- Quais tipos existem (generate/reject) → para entender o balanceamento

### Passo 2 — Ler a rubrica para identificar blocos disponíveis

```
Read("evals/<skill>/rubric.json")
```

Extraia:
- IDs de todos os `generate_blocks` (ex: E, C, X, Q, P)
- Chaves de todos os `reject_criteria` (ex: B1, B2, B7)

O novo TC só pode referenciar blocos e critérios que existem na rubrica.

### Passo 3 — Verificar inputs existentes

```
Glob("evals/<skill>/inputs/*")
```

Permite reutilizar ou adaptar um input existente se for similar ao cenário desejado.

### Passo 4 — Determinar o tipo do TC

Com base no comportamento a ser testado:

**`generate`** — a skill DEVE produzir um output estruturado
- Use quando: input válido e suficiente (DoR atendida), skill deve gerar documento/análise/artefato
- Blocos: selecione os `generate_blocks` relevantes (não todos — apenas os que o cenário exercita)

**`reject`** — a skill NÃO deve gerar output
- Use quando: negative trigger ativado, DoR não atendida, input inválido
- Bloco: selecione exatamente UM critério de `reject_criteria`

### Passo 5 — Gerar o conteúdo do input

Crie o conteúdo do arquivo de input adequado ao cenário:

**Para TCs de geração:**
- O input deve ser realista — use o mesmo formato e estilo dos inputs existentes
- Controle o que está presente vs ausente vs ambíguo para exercitar os critérios selecionados
- Se o TC testa extração de entidades, garanta que as entidades estejam no input
- Se o TC testa tratamento de `[ausente]`, omita informações intencionalmente

**Para TCs de rejeição:**
- Se o input é curto (< 3 linhas), use `prompt` diretamente em test_cases.json
- Se o input é uma transcrição ou documento, crie arquivo em `inputs/`
- O input deve ativar EXATAMENTE o critério de rejeição escolhido — nem mais, nem menos

**Verificação antes de criar:**
```
Glob("evals/<skill>/inputs/*")
```
Confirme que o nome do arquivo novo é único.

### Passo 6 — Criar o arquivo de input (se necessário)

Nomeação: `<descricao_curta_sem_espacos>.txt`
Localização: `evals/<skill>/inputs/`

Escreva o arquivo com o conteúdo gerado no Passo 5.

### Passo 7 — Definir o expected_behavior

Escreva uma descrição clara do comportamento esperado da skill dado este input.

Para TCs de geração, o `expected_behavior` deve especificar:
- O que o output DEVE conter (entidades, regras, seções)
- O que o output NÃO deve conter (informações inventadas, [ausente] indevidos)
- Qualquer comportamento específico deste cenário (ex: marcação [ambíguo] para conflito X)

Para TCs de rejeição, o `expected_behavior` deve especificar:
- Que a skill NÃO gera documento
- O que a skill DEVE fazer em vez disso (pedir contexto, redirecionar, perguntar por qual produto começar)

### Passo 8 — Montar a entrada em test_cases.json

Adicione o novo TC ao array existente:

```json
{
  "id": "TC<N>",
  "description": "<descrição concisa em português — max 80 chars>",
  "type": "<generate|reject>",
  "input_file": "<nome_do_arquivo.txt>",
  "expected_behavior": "<comportamento esperado completo>",
  "scoring_blocks": ["<bloco1>", "<bloco2>"]
}
```

Para TCs sem arquivo (input inline):
```json
{
  "id": "TC<N>",
  "description": "...",
  "type": "reject",
  "prompt": "<texto do prompt inline>",
  "expected_behavior": "...",
  "scoring_blocks": ["B1"]
}
```

Regras:
- `id` deve ser sequencial e único
- `scoring_blocks` para generate: liste apenas os blocos que o cenário exercita
- `scoring_blocks` para reject: exatamente um critério B_X
- `expected_file` é opcional — adicione se criar um output de referência

### Passo 9 — Resumo para o usuário

Apresente:

```
## TC criado: <TC_ID>

**Tipo:** <generate/reject>
**Arquivo de input:** evals/<skill>/inputs/<arquivo> (ou prompt inline)
**Blocos avaliados:** <lista>

**Por que este TC é valioso:**
<1-2 frases explicando qual lacuna de cobertura ele preenche>

**Para rodar:**
python run_eval.py --skill <skill> --tc <TC_ID> --no-browser --no-summary
```

---

## Regras obrigatórias

- Nunca criar TC com `input_file` sem criar o arquivo físico primeiro
- Nunca referenciar bloco que não existe na rubrica
- Nunca duplicar um comportamento já coberto por outro TC — verificar no Passo 1
- Para TCs de rejeição, nunca usar mais de um `scoring_blocks` — o judge avalia um critério por vez
- O `description` deve ser legível no relatório HTML — evite abreviações
