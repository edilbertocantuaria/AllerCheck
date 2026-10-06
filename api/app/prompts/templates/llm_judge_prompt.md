# LLM-as-Judge: Avaliação Clínica de Respostas

Você está avaliando respostas a uma pergunta sobre alergia a medicamentos em português.

**PERGUNTA:** {question}

**RESPOSTA A:**
{response_a}

**RESPOSTA B:**
{response_b}

**RESPOSTA C:**
{response_c}

## Tarefa

Qual resposta você prefere? Escolha entre A, B ou C.

Justifique sua escolha em 1-2 frases focando em:
- Clareza clínica
- Segurança
- Utilidade para o paciente

## Resposta

Responda em JSON:
```json
{{
  "choice": "A" ou "B" ou "C",
  "confidence": 0.0 a 1.0,
  "reasoning": "sua justificativa"
}}
```
