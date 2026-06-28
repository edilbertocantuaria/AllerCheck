"""ASBAI extraction prompt template."""

ASBAI_EXTRACTION_INSTRUCTION = """Analise o guia **"Alergia: Perguntas e Respostas" da ASBAI** e extraia uma **Matriz de Conduta Logística** para uso em um sistema de triagem automática.

Siga rigorosamente estas etapas:

**1. Mapeamento Exaustivo de Sintomas e Contextos**
Identifique **todos** os sintomas, sinais clínicos, gatilhos, cenários de risco e contextos de manejo mencionados no texto.

O agrupamento deve ser **muito detalhado** e contemplar, no mínimo, os macrotemas do guia:

* Alergia Respiratória
* Alergia e Gravidez
* Alergia Dermatológica
* Alergia Alimentar
* Anafilaxia
* Reações Adversas a Medicamentos
* Ambiente
* Métodos Diagnósticos
* Tratamento

Dentro de cada macrotema, crie subcategorias clínicas específicas sempre que houver base no texto (ex.: rinite, asma, urticária, angioedema, choque anafilático, exposição ambiental, diagnóstico diferencial, prevenção, plano terapêutico, acompanhamento).

**2. Definição de Gravidade**
Classifique os sintomas com base no conteúdo do PDF em:

* **LEVE**: reações localizadas (ex: coceira isolada, poucas manchas)
* **MODERADA**: sintomas em progressão ou presença de inchaço (ex: angioedema)
* **GRAVE/CRÍTICA**: sinais de anafilaxia ou comprometimento de órgãos vitais

**3. Extração de Condutas (com máxima granularidade)**
Para cada nível de gravidade e para cada subcategoria relevante, extraia as orientações descritas pela ASBAI, incluindo:

* Quando interromper o medicamento
* Quando observar em casa
* Quando procurar atendimento de emergência
* Sinais de alerta ("red flags")

Além disso, sempre que o texto trouxer, explicite:

* Estratégias de prevenção
* Critérios de encaminhamento para especialista
* Condutas em populações especiais (ex.: gestantes, crianças)
* Cuidados de seguimento após evento agudo

---

**Formato de saída obrigatório:**

Uma tabela em Markdown com a seguinte estrutura:

| Categoria | Sintomas/Palavras-chave | Gravidade | Conduta Recomendada (Texto Amigável) |
| :-------- | :---------------------- | :-------- | :----------------------------------- |

**Regras de detalhamento da tabela:**

* Gere uma tabela **extensa e prolixa**, priorizando cobertura total do conteúdo.
* Use categorias compostas quando útil, no formato: `Macrotema > Subcategoria`.
* Evite consolidar excessivamente: prefira várias linhas específicas em vez de poucas linhas genéricas.
* Não omita tópicos de ambiente, diagnóstico e tratamento; converta-os em linhas operacionais para triagem logística.

---

**Saída adicional obrigatória:**

Ao final, forneça um resumo com exatamente **3 frases** descrevendo o **tom de voz utilizado pelos médicos da ASBAI**, focando em como transmitem calma, clareza e segurança ao paciente.

---

**Requisitos técnicos adicionais:**

* O PDF deve ser processado integralmente antes do envio ao modelo
* Não resumir, truncar ou selecionar trechos do documento
* Garantir que a resposta seja determinística e estruturada (ideal para uso em sistema automatizado)
"""
