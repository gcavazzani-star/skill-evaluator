---
name: setup-skill-eval
description: >
  Use esta skill para configurar um ambiente completo de avaliação para uma
  skill do Claude Code. A skill cria toda a estrutura de testes: rubrica JSON,
  casos de teste, inputs de exemplo (incluindo cenários ambíguos e adversariais)
  e outputs de referência. Ative quando o usuário pedir para configurar ou criar
  um ambiente de teste para uma skill, ou invocar explicitamente /setup-skill-eval.

negative_triggers: >
  NÃO ative esta skill se:
  - O usuário quer executar testes de uma skill já configurada (use run_eval.py).
  - O usuário quer editar SKILL.md de uma skill existente.
  - O pedido é sobre o framework de avaliação em si, não sobre configurar uma nova skill.
---

# Skill: Setup Skill Eval — Framework de Avaliação de Skills

**Agente:** DPO Monitoramento / CI&T Data Practice
**Versão:** 1.0.0

---

## Objetivo

Configurar um ambiente completo de avaliação LLM-as-judge para qualquer skill do
Claude Code. Ao final da execução, o usuário terá:

1. `evals/<skill-name>/rubric.json` — rubrica de avaliação adaptada ao domínio
2. `evals/<skill-name>/test_cases.json` — 6-9 casos de teste (TCs)
3. `evals/<skill-name>/inputs/` — arquivos de input para cada TC
4. `evals/<skill-name>/expected/` — outputs de referência para TCs de geração
5. Validação: `python run_eval.py --skill <skill-name>` executado com sucesso

---

## Raciocínio Encadeado

Execute obrigatoriamente nesta ordem. Não pule etapas.

### Passo 1 — Coleta de Contexto

Faça as seguintes perguntas ao usuário **sequencialmente** (não todas de uma vez):

1. "Qual é o nome da skill? (será usado como nome da pasta, ex: `analise-sentimento`)"
2. "Em 3-5 frases: o que a skill faz, qual é o domínio, e o que ela NÃO deve fazer?"
3. "Quais são os triggers negativos — situações em que a skill deve recusar ou redirecionar?"
4. "Pode compartilhar 1-2 inputs de exemplo? (cole o texto diretamente ou informe o caminho do arquivo)"
5. "O que um output ideal da skill deve conter? (campos obrigatórios, formato, marcadores, etc.)"

Confirme o entendimento antes de prosseguir: "Entendido. Vou criar o ambiente de avaliação para a skill `<nome>`. Posso prosseguir?"

### Passo 2 — Análise do Domínio

Com base nas respostas do Passo 1, determine internamente:

- **Tipo de output**: documento estruturado / texto livre / JSON / código / outro
- **Dimensões de qualidade**: o que pode dar errado? (estrutura, extração, formato, confiança, alucinação, etc.)
- **3-5 blocos de rubrica** adequados ao tipo de output, com pesos somando 1.0
- **Critérios de rejeição** específicos do domínio (quais situações a skill deve recusar?)
- **Cenários de teste** necessários: rico, parcial, ambíguo, adversarial, formato alternativo

### Passo 3 — Criação da Rubrica

Crie o arquivo `evals/<skill-name>/rubric.json` com a seguinte estrutura:

```json
{
  "pass_threshold": 80,
  "judge_instructions": "Para cada critério, atribua score de 0 a 10. Blocos com binary=true: qualquer violação zera todos os critérios do bloco. weighted_score = soma(media_bloco * peso * 100). PASS se >= 80.",
  "reject_judge_instructions": "Score 10: comportamento exatamente correto. Score 5: parcialmente correto. Score 0: comportamento incorreto. PASS se score >= 8.",
  "generate_blocks": [
    {
      "id": "A",
      "name": "<nome do bloco>",
      "weight": 0.XX,
      "binary": false,
      "criteria": [
        {"id": "A1", "description": "<critério específico e mensurável>"},
        {"id": "A2", "description": "<critério específico e mensurável>"}
      ]
    }
  ],
  "reject_criteria": {
    "R1": "<descrição do comportamento esperado na rejeição>"
  }
}
```

**Regras para a rubrica:**
- 3-5 blocos `generate_blocks`, pesos somando exatamente 1.0
- 3-8 critérios por bloco, cada um objetivo e verificável por LLM
- Pelo menos 1 bloco com `"binary": true` para comportamentos proibidos críticos
- Pelo menos 2 `reject_criteria` (input insuficiente + pelo menos 1 trigger negativo do domínio)

### Passo 4 — Design dos Casos de Teste

Planeje 6-9 TCs com a seguinte distribuição mínima:

| Tipo | Quantidade | Exemplos |
|------|-----------|---------|
| generate — input rico | 1-2 | Transcrição/documento completo com todos os campos |
| generate — input parcial | 1 | Input com campos ausentes → deve usar marcadores |
| generate — formato alternativo | 1 | Email, PRD, outro formato diferente do principal |
| generate — ambíguo | 1 | Dois documentos com informações conflitantes |
| reject — input insuficiente | 1 | Sem contexto suficiente |
| reject — trigger negativo | 1-2 | Cenários do domínio que não devem disparar geração |
| reject — adversarial | 1 | Pressão do usuário para contornar uma regra da skill |

Para cada TC, defina: `id`, `description`, `type`, `input_file` (ou `prompt`),
`expected_behavior`, `expected_file` (se generate), `scoring_blocks`.

Os `scoring_blocks` devem referenciar os IDs definidos em `rubric.json`.

### Passo 5 — Criação dos Inputs

Para cada TC que usa `input_file`, crie o arquivo em `evals/<skill-name>/inputs/`:

- **TC rico**: baseado diretamente no exemplo fornecido pelo usuário (com adaptações mínimas)
- **TC parcial**: versão do input rico com 30-40% das informações removidas
- **TC formato alternativo**: mesmo conteúdo em formato diferente (email vs. transcrição, etc.)
- **TC ambíguo**: combine dois insumos com 2-3 contradições deliberadas em valores-chave
- **TC reject (input insuficiente)**: input vago com 1-2 frases sem contexto real
- **TC reject (trigger negativo)**: input que deve ativar um `negative_trigger` da skill
- **TC adversarial**: input que pede explicitamente à skill que viole uma regra sua

Os inputs devem ser realistas — escritos como se fossem documentos reais do domínio.

### Passo 6 — Criação dos Expected Outputs

Para cada TC de tipo `generate`, crie `evals/<skill-name>/expected/<tc-id>_expected.md` com:

- As entidades principais que DEVEM aparecer no output (com valores esperados)
- As regras de negócio que DEVEM ser extraídas
- Os itens que DEVEM ser marcados como [ausente] ou [ambíguo]
- Os questionamentos que DEVEM aparecer (pelo menos os BLOQUEANTES)

Não é necessário gerar o documento completo — uma referência concisa de extração
com as informações mais importantes é suficiente para o judge comparar.

### Passo 7 — Criação do test_cases.json

Crie `evals/<skill-name>/test_cases.json` com todos os TCs planejados no Passo 4.

Formato de cada TC:
```json
{
  "id": "TC01",
  "description": "...",
  "type": "generate",
  "input_file": "tc01_input.txt",
  "expected_behavior": "...",
  "expected_file": "tc01_expected.md",
  "scoring_blocks": ["A", "B", "P"]
}
```

Para TCs reject com prompt inline (sem arquivo de input), use `"prompt"` em vez de `"input_file"`.

### Passo 8 — Validação

Execute o seguinte comando para validar que o ambiente está configurado corretamente:

```bash
python run_eval.py --skill <skill-name> --no-browser --no-summary
```

Se houver erros (arquivo não encontrado, JSON inválido, bloco não encontrado na rubrica),
corrija e re-execute. Reporte o resultado ao usuário com:

"✅ Ambiente configurado. `<N>` TCs prontos. Execute `python run_eval.py --skill <skill-name>` para a avaliação completa."

---

## Regras desta Skill

- Nunca invente comportamentos esperados que não derivem das informações fornecidas pelo usuário
- Se o usuário não fornecer inputs de exemplo, gere inputs sintéticos mas indique claramente quais são inventados
- Pesos dos blocos DEVEM somar exatamente 1.0 — verifique antes de salvar
- IDs em `scoring_blocks` dos TCs DEVEM corresponder a IDs em `rubric.json`
- Ao menos 1 TC adversarial deve ser criado para qualquer skill com triggers negativos
- O campo `expected_behavior` deve ser específico o suficiente para que o judge consiga avaliar sem ambiguidade
- Confirme sempre o nome da skill antes de criar arquivos — é o identificador de toda a estrutura

---

## Estrutura de Diretórios Resultante

```
evals/
└── <skill-name>/
    ├── rubric.json
    ├── test_cases.json
    ├── inputs/
    │   ├── tc01_input.txt
    │   ├── tc02_input.txt
    │   └── ...
    └── expected/
        ├── tc01_expected.md
        ├── tc02_expected.md
        └── ...
```

A skill em si (SKILL.md, examples.md, patterns.md) fica em:
```
.claude/skills/<skill-name>/
```

O membro da equipe é responsável por criar a skill antes de chamar `/setup-skill-eval`.
Se a skill ainda não existir, oriente o usuário a criá-la primeiro.
