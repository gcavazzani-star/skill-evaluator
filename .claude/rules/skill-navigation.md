# Rule: Skill Navigation

**Trigger:** sempre que o usuário mencionar uma skill pelo nome, pedir para trabalhar
com SKILL.md, examples.md, patterns.md, ou sugerir mudanças no comportamento de uma skill.

---

## Como descobrir os arquivos de uma skill

```
Glob(".claude/skills/<nome-da-skill>/*")
```

Arquivos esperados:
- `SKILL.md` — definição principal: objetivo, pré-condições (DoR), raciocínio encadeado, formato de saída
- `examples.md` — exemplos few-shot que calibram o comportamento (entradas ricas, parciais, ambíguas)
- `patterns.md` — guard rails e comportamentos de borda (o que é proibido, o que fazer em situações inesperadas)

Se algum dos três estiver ausente, o hook `post_write_checks.py` já avisa.
Se ainda não existir, crie-o antes de rodar qualquer eval.

---

## Ordem obrigatória de leitura

1. `Read(".claude/skills/<skill>/SKILL.md")`
   → Extraia: pré-condições (DoR = Definition of Ready), `negative_triggers`, formato de saída, passos do raciocínio encadeado

2. `Read(".claude/skills/<skill>/examples.md")`
   → Calibra o comportamento para inputs ricos, parciais e ambíguos
   → Define o que é um output "bom" na prática

3. `Read(".claude/skills/<skill>/patterns.md")`
   → Lista os comportamentos proibidos e as respostas corretas para situações inesperadas

**Regra:** nunca propor mudança em SKILL.md sem ter lido examples.md e patterns.md primeiro.
Os três arquivos são projetados para trabalhar juntos — uma mudança em SKILL.md pode
contradizer um exemplo ou um guard rail.

---

## Verificar se o eval está configurado

```
Glob("evals/<nome-da-skill>/")
```

Se o diretório existir:
```
Glob("evals/<nome-da-skill>/*")
```
→ Verifique se rubric.json e test_cases.json estão presentes.

Se o eval não existir e o usuário quiser criar um, use `/setup-skill-eval`.

---

## Skills disponíveis neste projeto

```
Glob(".claude/skills/*/SKILL.md")
```

Cada resultado é uma skill configurada. Habilite `eval-navigation.md` para navegar
nos arquivos de avaliação correspondentes.
