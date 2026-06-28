Reescreva a pergunta abaixo como uma query autônoma otimizada para busca em base de farmacovigilância.

## REGRAS (aplicar nesta ordem)
1. Nome comercial → adicione o Princípio Ativo entre parênteses
2. Sintoma coloquial → adicione termo técnico entre parênteses
3. Preserve contexto clínico mencionado: idade, comorbidade, cirurgia, tempo de reação
4. Estrutura: [MEDICAMENTO (Princípio Ativo)] — [CONTEXTO] — [SINTOMA/REAÇÃO] — [PERGUNTA]

## MAPEAMENTOS RÁPIDOS
"bombinha" → "inalador (broncodilatador beta-agonista)"
"cortisona" → "corticoide sistêmico (prednisolona/prednisona)"
"falta de ar" → "dispneia"
"inchaço" → "edema"
"coceira" → "prurido"
"mal-estar súbito" → "síncope iminente ou lipotimia"

## EXEMPLOS
Entrada: "Minha mãe é alérgica ao Paracetamol, foi operada do coração, qual a alternativa?"
Saída: "Paracetamol (acetaminofeno) — alergia confirmada — contexto pós-operatório cardíaco — alternativas analgésicas seguras — risco cardiovascular"

Entrada: "Tenho filha de 5 anos alérgica a todos os antibióticos. Dessensibilização funciona?"
Saída: "Hipersensibilidade a antibióticos (raridade clínica) — contexto pediátrico 5 anos — dessensibilização medicamentosa: eficácia temporária vs permanente — indicação restrita"

Entrada: "Sou alérgico a dipirona, posso tomar Benzetacil?"
Saída: "Dipirona (metamizol sódico) — alergia confirmada — Benzetacil (benzilpenicilina) — avaliação de reatividade cruzada entre analgésico e antibiótico"

## OUTPUT OBRIGATÓRIO
Se pergunta é sobre alergia medicamentosa:
[DOMAIN_CHECK: IN_SCOPE]
Query Otimizada: [query reescrita]

Se NÃO é sobre alergia medicamentosa:
[DOMAIN_CHECK: OUT_OF_SCOPE]
Reason: [motivo]

## Histórico: {history}
## Pergunta: {question}