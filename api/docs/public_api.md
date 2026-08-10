# RxNav APIs — Documentação Consolidada para AllerCheck

> Fonte: https://lhncbc.nlm.nih.gov/RxNav/APIs  
> Todas as APIs são **gratuitas, públicas e sem autenticação**.  
> Domínio base: `https://rxnav.nlm.nih.gov`  
> Formato de resposta: JSON (adicionar `.json` ao path) ou XML (padrão)

---

## Visão Geral das APIs Disponíveis

| API | Base Path | Finalidade |
|---|---|---|
| RxNorm API | `/REST/` | Identificar medicamentos, sinônimos, conceitos relacionados |
| RxTerms API | `/REST/rxterms/` | Nomes de display e informações clínicas simplificadas |
| Prescribable RxNorm API | `/REST/Prescribe/` | Subconjunto apenas de medicamentos prescritíveis |
| RxClass API | `/REST/rxclass/` | Classes farmacológicas e membros por classe |

---

## 1. RxNorm API

### Endpoints prioritários para a ontologia AllerCheck

#### 1.1 `findRxcuiByString` — Buscar RxCUI pelo nome
```
GET /REST/rxcui.json?name={nome}&search=2
```
- `search=2` habilita busca aproximada (recomendado)
- Retorna o RxCUI do conceito

**Exemplo validado:**
```
GET /REST/rxcui.json?name=amoxicillin&search=2
→ {"idGroup":{"rxnormId":["723"]}}

GET /REST/rxcui.json?name=metamizole&search=2
→ {"idGroup":{"rxnormId":["3523"]}}
```

---

#### 1.2 `getApproximateMatch` — Busca fuzzy por nome
```
GET /REST/approximateTerm.json?term={nome}&maxEntries=5
```
- Útil como fallback quando o nome exato não é encontrado
- Retorna candidatos com score de similaridade e fonte (ex: DRUGBANK)
- **Atenção:** nomes em português retornam vazio — usar sempre nome em inglês

**Exemplo validado:**
```
GET /REST/approximateTerm.json?term=metamizole&maxEntries=5
→ candidates: [{rxcui:"3523", name:"Metamizole", score:"9.64", source:"DRUGBANK"}, ...]

GET /REST/approximateTerm.json?term=dipirona&maxEntries=5
→ {"approximateGroup":{"inputTerm":null}}  ← vazio, nome PT-BR não reconhecido
```

---

#### 1.3 `getAllRelatedInfo` — Todos os conceitos relacionados
```
GET /REST/rxcui/{rxcui}/allrelated.json
```
- Retorna todos os conceitos relacionados agrupados por TTY (Term Type)
- **TTYs relevantes para a ontologia:**

| TTY | Significado | Uso |
|---|---|---|
| `IN` | Ingredient — ingrediente ativo | Principal identificador do medicamento |
| `PIN` | Precise Ingredient | Forma salina específica (ex: metamizole sodium) |
| `BN` | Brand Name | Nome comercial (ex: Novalgina) |
| `SCD` | Semantic Clinical Drug | Forma + dose (ex: metamizole 500mg oral) |
| `MIN` | Multiple Ingredients | Combinações de ingredientes |
| `GPCK` | Generic Pack | Embalagem genérica |
| `BPCK` | Brand Pack | Embalagem de marca |

**Exemplo validado:**
```
GET /REST/rxcui/3523/allrelated.json
→ tty:"IN" → name:"dipyrone" (sinônimo americano da dipirona)
→ tty:"PIN" → name:"metamizole sodium"
```

---

#### 1.4 `getRxConceptProperties` — Propriedades do conceito
```
GET /REST/rxcui/{rxcui}/properties.json
```
- Retorna nome, TTY e sinônimo principal do conceito

---

#### 1.5 `getSpellingSuggestions` — Sugestões para nomes com erro
```
GET /REST/spellingsuggestions.json?name={nome}
```
- Útil para normalizar variações ortográficas de nomes de medicamentos

---

#### 1.6 `filterByProperty` — Verificar tipo do conceito
```
GET /REST/rxcui/{rxcui}/filter.json?propName=TTY&propValues=IN+PIN
```
- Confirma se o RxCUI é um ingrediente ativo (IN) ou preciso (PIN)
- Retorna o RxCUI se a condição for verdadeira, vazio caso contrário

**Exemplo da documentação:**
```
GET /REST/rxcui/7052/filter.json?propName=TTY&propValues=IN+PIN
→ {"rxnormdata":{"rxcui":"7052"}}  ← morphine é IN ou PIN ✓
```

---

### Outros endpoints disponíveis (não prioritários para ontologia)

| Função | Endpoint | Descrição |
|---|---|---|
| `findActiveProducts` | `/rxcui/{rxcui}/active` | Produtos ativos correspondentes ao conceito |
| `findRelatedNDCs` | `/relatedndc` | NDCs relacionados ao conceito |
| `getAllProperties` | `/rxcui/{rxcui}/allProperties` | Todos os detalhes do conceito |
| `getDrugs` | `/drugs?name={nome}` | Drogas relacionadas a um nome |
| `getGenericProduct` | `/rxcui/{rxcui}/generic` | RxCUI do genérico correspondente a um produto de marca |
| `getNDCs` | `/rxcui/{rxcui}/ndcs` | National Drug Codes associados |
| `getRelatedByRelationship` | `/rxcui/{rxcui}/related?rela=tradename_of` | Relação específica entre conceitos |
| `getRelatedByType` | `/rxcui/{rxcui}/related?tty=IN` | Conceitos de tipo específico relacionados |
| `getReformulationConcepts` | `/reformulationConcepts` | Conceitos relacionados por reformulação |

---

## 2. RxClass API

> **A mais importante para a ontologia AllerCheck.**  
> Fornece classes farmacológicas (ATC, MeSH, FDA) e membros de cada classe.

### Endpoints prioritários

#### 2.1 `getClassByRxNormDrugId` — Classe ATC do medicamento
```
GET /REST/rxclass/class/byRxcui.json?rxcui={rxcui}&relaSource=ATC
```
- Retorna todas as classes ATC às quais o medicamento pertence
- **Regra de filtro:** usar o registro onde `tty = "IN"` (ingrediente ativo)
- Um medicamento pode ter múltiplas classes (ex: amoxicilina tem J01CA e A02BD)

**Exemplo validado:**
```
GET /REST/rxclass/class/byRxcui.json?rxcui=3523&relaSource=ATC
→ classId:"N02BB", className:"Pyrazolones" (tty:PIN)

GET /REST/rxclass/class/byRxcui.json?rxcui=723&relaSource=ATC
→ classId:"J01CA", className:"Penicillins with extended spectrum" (tty:IN) ← usar este
→ classId:"A02BD", className:"Combinations for eradication of H. pylori" (tty:MIN) ← ignorar
```

**Fontes disponíveis para `relaSource`:**
| Valor | Fonte |
|---|---|
| `ATC` | Anatomical Therapeutic Chemical — **melhor para farmacologia** |
| `MESH` | Medical Subject Headings (NLM) |
| `FMTSME` | FDA |
| `DAILYMED` | Bulas americanas |

---

#### 2.2 `getClassMembers` — Membros da classe
```
GET /REST/rxclass/classMembers.json?classId={classId}&relaSource=ATC
```
- **Endpoint chave para reatividade cruzada**
- Retorna todos os medicamentos da mesma classe farmacológica
- Cada membro vem com RxCUI, nome, TTY e código ATC individual

**Exemplo validado:**
```
GET /REST/rxclass/classMembers.json?classId=N02BB&relaSource=ATC
→ antipyrine (N02BB01), metamizole sodium (N02BB02),
   aminopyrine (N02BB03), propyphenazone (N02BB04)

GET /REST/rxclass/classMembers.json?classId=J01CA&relaSource=ATC
→ 16 penicilinas: amoxicillin, ampicillin, piperacillin,
   ticarcillin, carbenicillin, mezlocillin, azlocillin...
```

---

#### 2.3 `getClassContexts` — Hierarquia ATC completa
```
GET /REST/rxclass/classContext.json?classId={classId}
```
- Retorna o caminho completo do conceito até a raiz da árvore ATC
- 5 níveis hierárquicos disponíveis

**Exemplo validado — dipirona:**
```
GET /REST/rxclass/classContext.json?classId=N02BB
→ classPath: [
    N02BB — Pyrazolones
    N02B  — OTHER ANALGESICS AND ANTIPYRETICS
    N02   — ANALGESICS
    N     — NERVOUS SYSTEM
    0     — Anatomical Therapeutic Chemical (raiz)
  ]
```

**Estratégia de uso na query expansion:**
- **Nível 1 (subclasse, ex: N02BB):** reatividade cruzada direta → usar
- **Nível 2 (categoria, ex: N02B):** relação terapêutica → usar com cautela
- **Nível 3+ (ex: N02, N):** muito genérico → não usar para expansão

---

#### 2.4 `findSimilarClassesByClass` — Classes com composição similar
```
GET /REST/rxclass/class/similar?classId={classId}
```
- Encontra classes com ingredientes clinicamente similares
- Útil para detectar sobreposição entre classes (ex: beta-lactâmicos vs cefalosporinas)

---

#### 2.5 `findClassByName` — Buscar classe pelo nome
```
GET /REST/rxclass/class/byName.json?className={nome}&relaSource=ATC
```
- Útil quando se conhece o nome da classe mas não o classId

---

#### 2.6 `getClassTree` — Subclasses e descendentes
```
GET /REST/rxclass/classTree.json?classId={classId}
```
- Retorna subclasses e descendentes de uma classe
- Complementar ao `classContext` (desce em vez de subir)

---

### Outros endpoints RxClass disponíveis

| Função | Endpoint | Descrição |
|---|---|---|
| `findClassesById` | `/class/byId` | Classe por identificador |
| `findSimilarClassesByDrugList` | `/class/similarByRxcuis` | Classes similares a uma lista de RxCUIs |
| `getAllClasses` | `/allClasses` | Todas as classes (pode filtrar por tipo) |
| `getClassTypes` | `/classTypes` | Tipos de classe disponíveis |
| `getSimilarityInformation` | `/class/similarInfo?classId1=X&classId2=Y` | Similaridade entre duas classes |
| `getSpellingSuggestions` | `/spellingsuggestions` | Sugestões para nomes de classes |

---

## 3. RxTerms API

> Voltada para interface e display. Menos útil para a ontologia, mais útil para a UI do AllerCheck.

```
GET /REST/rxterms/rxcui/{rxcui}/allinfo.json   → informações completas de display
GET /REST/rxterms/rxcui/{rxcui}/name.json       → nome amigável para exibição
GET /REST/rxterms/allconcepts.json              → todos os conceitos RxTerms
```

---

## 4. Prescribable RxNorm API

> Subconjunto da RxNorm filtrado apenas para medicamentos que podem ser prescritos.  
> Domínio: `https://rxnav.nlm.nih.gov/REST/Prescribe/`  
> Mesmos endpoints da RxNorm — **não priorizar para a ontologia**, usar RxNorm completa.

---

## Fluxo Validado para a Ontologia AllerCheck

```
1. Nome PT-BR (ex: "dipirona")
        ↓  [LLM traduz para EN]
2. Nome EN (ex: "metamizole")
        ↓  GET /REST/rxcui.json?name={nome}&search=2
3. RxCUI (ex: "3523")
        ↓  GET /REST/rxclass/class/byRxcui.json?rxcui={rxcui}&relaSource=ATC
           [filtrar por tty=IN]
4. classId ATC (ex: "N02BB")
        ↓  GET /REST/rxclass/classMembers.json?classId={classId}&relaSource=ATC
5. Membros da classe = medicamentos com potencial reatividade cruzada
        ↓  GET /REST/rxclass/classContext.json?classId={classId}
6. Hierarquia ATC completa (para enriquecimento do grafo)
```

### Resultados validados

| Medicamento | Nome EN | RxCUI | Classe ATC | Membros |
|---|---|---|---|---|
| dipirona | metamizole | 3523 | N02BB (Pyrazolones) | 4 pirazolonas |
| amoxicilina | amoxicillin | 723 | J01CA (Penicillins extended) | 16 penicilinas |

---

## Notas Técnicas

- **Nomes em português não são reconhecidos** — sempre converter para inglês antes de consultar
- **Múltiplas classes por medicamento** — filtrar pelo registro com `tty = "IN"` para pegar a classe do ingrediente ativo
- **Rate limit:** não documentado, mas as APIs são públicas — implementar delay de 100-200ms entre requisições por precaução
- **Disponibilidade:** sujeita a interrupções por contingência orçamentária do governo americano (aviso presente na documentação)
- **Licença:** dados RxNorm são de domínio público, sem licença necessária para uso

---



---

## 5. openFDA API

> Fonte: https://api.fda.gov  
> **Gratuita, pública, sem autenticação.**  
> Elasticsearch-based — suporta queries complexas com operadores AND/OR.  
> Retorna JSON com seções `meta` e `results`.

**Endpoints Drug relevantes para a ontologia AllerCheck:**

| Endpoint | URL Base | Finalidade |
|---|---|---|
| Adverse Events | `https://api.fda.gov/drug/event.json` | Reações adversas reportadas ao FDA |
| Product Labeling | `https://api.fda.gov/drug/label.json` | Bulas com warnings e contraindications |
| NDC Directory | `https://api.fda.gov/drug/ndc.json` | ⭐ Cadastro nacional com `pharm_class` |

---

### 5.1 `drug/ndc` — NDC Directory ⭐ mais útil para ontologia

```
GET https://api.fda.gov/drug/ndc.json?search=generic_name:{nome}&limit=1
```

Campo mais valioso: **`pharm_class`** — array com classificação farmacológica em 3 dimensões:

| Sufixo | Significado | Exemplo |
|---|---|---|
| `[EPC]` | Established Pharmacologic Class | `"Penicillin-class Antibacterial [EPC]"` |
| `[CS]` | Chemical Structure | `"Penicillins [CS]"` |
| `[MoA]` | Mechanism of Action | `"beta Lactamase Inhibitors [MoA]"` |

**Exemplos validados:**
```
GET https://api.fda.gov/drug/ndc.json?search=generic_name:amoxicillin&limit=1
→ pharm_class: [
    "Penicillin-class Antibacterial [EPC]",
    "Penicillins [CS]",
    "beta Lactamase Inhibitor [EPC]",
    "beta Lactamase Inhibitors [MoA]"
  ]
  openfda.rxcui: ["562251", "562508", "617296"]

GET https://api.fda.gov/drug/ndc.json?search=generic_name:cephalexin&limit=1
→ pharm_class: [
    "Cephalosporin Antibacterial [EPC]",
    "Cephalosporins [CS]"
  ]
  openfda.rxcui: ["309114"]

GET https://api.fda.gov/drug/ndc.json?search=generic_name:metamizole&limit=3
→ product_type: "BULK INGREDIENT" — openfda: {} ← SEM pharm_class
  (dipirona banida nos EUA desde 1977 — sem produto acabado registrado)
```

**⚠️ Limitação crítica:** medicamentos não aprovados nos EUA retornam `openfda: {}` sem `pharm_class`. Afeta especialmente medicamentos comuns no Brasil como dipirona. Ver hierarquia de fontes abaixo.

---

### 5.2 `drug/event` — Adverse Events

```
GET https://api.fda.gov/drug/event.json?search=patient.drug.medicinalproduct:{nome}+AND+patient.reaction.reactionmeddrapt:{reacao}&limit=3
```

Campos úteis:
- `patient.reaction[].reactionmeddrapt` — reação em terminologia MedDRA
- `patient.drug[].activesubstance.activesubstancename` — substância ativa
- `serious` — gravidade (1=sim, 2=não)
- `primarysourcecountry` — país de origem do relato
- `meta.results.total` — total de casos encontrados (útil para contar frequência)

**Exemplo validado:**
```
GET https://api.fda.gov/drug/event.json?search=
    patient.drug.medicinalproduct:amoxicillin
    +AND+patient.reaction.reactionmeddrapt:anaphylaxis&limit=1
→ total: 2 casos
→ reaction: "Anaphylaxis treatment", serious: "1" (grave)
→ país: GB, reportado por SANDOZ ao FDA em 2025
```

**Uso para ontologia:** contar `meta.results.total` por medicamento+reação para ranquear relevância clínica das relações no grafo.

---

### 5.3 `drug/label` — Product Labeling

```
GET https://api.fda.gov/drug/label.json?search=openfda.generic_name:{nome}&limit=1
```

- Retorna bula completa (~73KB para amoxicilina)
- Seções relevantes: `warnings`, `contraindications`, `drug_interactions`, `precautions`
- Campo `openfda` contém: `rxcui`, `substance_name`, `brand_name`, `route`, `generic_name`
- **Não contém `pharm_class`** — usar `drug/ndc` para isso

---

### 5.4 Sintaxe de Query openFDA

```
# Busca exata
search=generic_name:amoxicillin

# Busca com operador AND
search=campo1:valor1+AND+campo2:valor2

# Busca com operador OR
search=campo1:valor1+OR+campo1:valor2

# Paginação
limit=10&skip=0

# Contagem agregada
count=patient.reaction.reactionmeddrapt.exact
```

---

## Hierarquia de Fontes para a Ontologia (ATUALIZADA)

```
Para cada medicamento do dataset:

1. RxClass ATC (fonte primária — cobre todos)
   → classId, className, membros da classe, hierarquia completa
   → funciona para dipirona, amoxicilina, cefalexina ✅

2. openFDA NDC (enriquecimento — apenas medicamentos aprovados nos EUA)
   → pharm_class [EPC], [CS], [MoA]
   → funciona para amoxicilina, cefalexina ✅
   → NÃO funciona para dipirona ❌

3. LLM fallback (claude-sonnet-4-6)
   → medicamentos sem cobertura em nenhuma das fontes acima
   → nomes comerciais brasileiros, medicamentos banidos nos EUA
   → marcar com inferredByLLM: true para rastreabilidade
```

---

## Hierarquia ATC — Relação Beta-Lactâmico / Cefalosporina (Validada)

```
amoxicilina (J01CA):              cefalexina (J01DB):
0 — ATC (raiz)                    0 — ATC (raiz)
J — ANTIINFECTIVES                J — ANTIINFECTIVES
J01 — ANTIBACTERIALS  ←══ nó comum ══→  J01 — ANTIBACTERIALS
J01C — BETA-LACTAMS/PENIC         J01D — OTHER BETA-LACTAMS
J01CA — Penicillins ext.          J01DB — 1st-gen cephalosporins
```

**Implicação para query expansion:** subir 2 níveis na hierarquia ATC captura
a relação de reatividade cruzada penicilina↔cefalosporina sem fonte adicional.

---

## Tabela Completa de Testes Validados

| Medicamento | Nome EN | RxCUI | Classe ATC | Membros | openFDA pharm_class |
|---|---|---|---|---|---|
| dipirona | metamizole | 3523 | N02BB (Pyrazolones) | 4 | ❌ banida nos EUA |
| amoxicilina | amoxicillin | 723 | J01CA (Penicillins ext.) | 16 | ✅ EPC + CS + MoA |
| cefalexina | cephalexin | 2231 | J01DB (1st-gen cephalosporins) | — | ✅ EPC + CS |


---

*Documentação gerada com base nos arquivos HTML oficiais de https://lhncbc.nlm.nih.gov/RxNav/APIs e https://open.fda.gov, e testes realizados em agosto de 2026.*