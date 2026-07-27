# ARGOS — panorama geral e estado atual do pipeline

**Data de consolidação:** 24 de julho de 2026  
**Repositório:** `felipe-nantes/argos`  
**Branch local:** `main`  
**Modo regulatório:** pesquisa, sem uso diagnóstico ou clínico  
**Objetivo experimental:** sensibilidade ≥ 75%, especificidade ≥ 75% e tempo ≤ 180 segundos por exame  
**Estado da meta:** **ainda não demonstrada de forma simultânea e generalizável**

---

## 1. Resumo executivo

O ARGOS já é um pipeline funcional de pesquisa para:

1. receber uma pasta DICOM de ressonância magnética;
2. selecionar uma série válida;
3. desidentificar e converter o exame;
4. segmentar automaticamente o fígado;
5. construir painéis de evidência visual;
6. consultar o MedGemma 4B ou 27B pelo contrato HTTP do projeto;
7. validar e persistir um relatório estruturado;
8. construir o modelo 3D do fígado;
9. exibir o órgão, segmentos e estruturas internas no visualizador web;
10. registrar revisão humana;
11. executar benchmarks auditáveis pelo backend, CLI ou webapp.

A infraestrutura, o webapp, o benchmark, os painéis volumétricos, o RAG textual,
o schema pathology-target, o registry de datasets, o GraphRAG de metadados, a
segmentação anatômica e o visualizador 3D estão implementados em diferentes
níveis de maturidade.

O gargalo atual não é mais fazer o sistema executar. O gargalo é a capacidade
discriminativa do MedGemma 1.5 4B:

- ele detecta alterações visuais com alta frequência;
- confunde vasos, variantes, cistos, FNH, hemangiomas, pseudolesões e outros
  mimetizadores com patologia-alvo;
- tende fortemente a responder `POSITIVA`;
- as probabilidades produzidas ficam muito próximas entre as três classes;
- novas combinações de pesos e limiares não corrigiram o problema na coorte
  OpenSwissHCC completa.

O melhor resultado histórico em 87 casos de desenvolvimento foi:

```text
v23:
sensibilidade = 82,05%
especificidade = 79,17%
```

Esse resultado é verdadeiro para aquela coorte, mas não se sustentou quando o
mesmo princípio foi avaliado nos 132 casos OpenSwissHCC:

```text
sensibilidade = 65,08%
especificidade = 60,87%
```

A recalibração aninhada mais recente, v27, também falhou:

```text
sensibilidade = 61,90%
especificidade = 55,07%
```

Portanto, o ARGOS está tecnicamente avançado e operacional como plataforma de
pesquisa, mas o classificador 4B ainda não está qualificado para a alegação
simultânea de 75%/75%.

---

## 2. Estado geral por área

| Área | Estado atual | Observação |
|---|---|---|
| Ingestão DICOM | Implementada | Seleção de série, geometria física e fail-closed |
| Desidentificação | Implementada | Conversão para NIfTI; risco de PHI queimada em pixel continua declarado |
| Segmentação hepática | Implementada | TotalSegmentator MRI; full-resolution no exame individual e modo rápido no benchmark |
| Segmentos de Couinaud | Implementados no perfil/pipeline | Task `liver_segments_mr`, oito segmentos opcionais |
| Vasos e vesícula | Implementados no perfil/pipeline | Veia porta/esplênica, VCI e vesícula |
| Painel baseline `uniform_9` | Implementado | Reproduzível e preservado |
| Cobertura `volumetric_blocks` | Implementada | Múltiplos painéis, manifesto e gate de cobertura |
| Painéis liver-enriched | Implementados e auditados | Usados em OpenSwissHCC e LLD-MMRI |
| MedGemma 4B no Windows | Implementado | Transformers, CUDA e NF4 |
| MedGemma 27B no Mac | Configs e launcher existentes | Avaliação equivalente com protocolo atual ainda pendente |
| Contrato HTTP MedGemma | Implementado | `dtwin-medgemma-v1`, uma imagem por chamada |
| Relatório clínico estruturado | Implementado | Schema base e campos pathology-target |
| RAG textual | Implementado | Corpus, chunking, índice BM25, recuperação e persistência de contexto |
| GraphRAG Neo4j | Fundação implementada | Registry → grafo de metadados; não é o decisor atual |
| Registry de datasets | Implementado | DICOM/NIfTI, validações e manifestos JSONL |
| Benchmark CLI/backend | Implementado | Ground truth isolado, métricas, hashes e falhas como erros |
| Benchmark webapp | Implementado | Cenários autorizados, sem caminhos arbitrários do navegador |
| Exame individual webapp | Implementado | Seleção entre `volumetric_rag` e `pathology_target` |
| Visualizador 3D | Implementado | STL, estruturas, materiais, toggles e aprovação |
| Persistência/retomada | Implementada em rotinas longas | Checkpoints, `fsync`, backup e publicação atômica |
| Meta 75/75 com 4B | Não atingida | Melhor resultado não generalizou |
| Gate end-to-end DICOM ≤180 s | Parcial | Inferência/painéis passam; gate completo ainda não consolidado no candidato final |
| Uso clínico | Não autorizado | Pesquisa com revisão humana obrigatória |

---

## 3. Objetivo clínico-experimental atual

O endpoint atual não é “qualquer alteração visual”. Ele foi redefinido para:

```text
positivo:
lesão focal hepática ou patologia hepática suspeita

negativo:
fígado sem achado relevante
+ variante anatômica benigna
+ pseudolesão/artefato
+ achado benigno fora do alvo
```

O modelo deveria diferenciar:

```text
1. normal sem achado relevante
2. variante anatômica ou alteração benigna
3. pseudolesão ou artefato
4. lesão focal/patologia suspeita
```

Na métrica principal:

- `POSITIVA` significa suspeita de patologia-alvo;
- `NEGATIVA` inclui normalidade e variantes benignas;
- `INCONCLUSIVA` conta como erro;
- timeout e falha técnica contam como erro;
- nenhum caso pode ser retirado depois da definição do protocolo;
- nenhuma máscara pública de lesão pode entrar na inferência.

---

## 4. Pipeline operacional atual

```text
Pasta DICOM
    │
    ▼
Seleção da melhor série de RM
    │
    ▼
Ingestão + desidentificação + NIfTI
    │
    ▼
Segmentação automática do fígado
    ├── máscara hepática
    ├── segmentos de Couinaud opcionais
    ├── veia porta/esplênica
    ├── veia cava inferior
    └── vesícula biliar
    │
    ▼
Construção dos painéis
    ├── uniform_9
    ├── volumetric_blocks
    ├── multiphase_fusion
    ├── pathology-target
    └── RAG textual opcional
    │
    ▼
MedGemma 4B/27B pelo gateway HTTP
    │
    ▼
Validação do schema + agregação entre painéis
    │
    ▼
medgemma_report.json
    │
    ├── benchmark e métricas
    │
    └── malha/STL + visualizador 3D
                         │
                         ▼
                aprovação humana
```

### 4.1 Exame individual

O fluxo individual do webapp:

- recebe DICOM;
- escolhe a melhor série;
- executa segmentação full-resolution (`fast=False`);
- tenta GPU e possui fallback explícito para CPU;
- calcula timeout conforme a quantidade de painéis;
- executa o MedGemma sequencialmente;
- exige `medgemma_report.json`;
- gera o modelo 3D;
- apresenta o relatório e o botão do visualizador;
- registra tempo até o relatório e tempo total com 3D;
- nunca transforma falha técnica em laudo.

Modos atualmente expostos na tela individual:

```text
volumetric_rag
pathology_target
```

O navegador envia somente a chave do modo. O backend resolve uma configuração
previamente autorizada dentro de `configs/`.

### 4.2 Benchmark do webapp

Modos autorizados:

```text
baseline
volumetric
rag
volumetric_rag
pathology_target
fast_pathology
```

O benchmark:

- separa o ground truth da inferência;
- segmenta cada exame;
- persiste relatório, falha e diagnóstico técnico;
- calcula sensibilidade, especificidade, precisão, F1 e matriz de confusão;
- trata inconclusivos e falhas como erros;
- registra estratégia, configuração e hashes;
- impede caminho arbitrário de configuração enviado pelo frontend.

### 4.3 Diferença de segmentação entre fluxos

```text
exame individual:
fast=False, aproximadamente 1,5 mm, maior fidelidade

benchmark webapp:
fast=True, aproximadamente 3 mm, maior throughput
```

Essa diferença é relevante. O benchmark rápido não gera a mesma qualidade
superficial do fluxo individual. Para uma comparação científica final entre
modos, a política de resolução precisa ser explicitamente congelada.

---

## 5. Segmentação e visualizador 3D

### 5.1 Fígado

O órgão é segmentado pelo TotalSegmentator MRI com:

```yaml
motor_task: total_mr
rotulo_alvo: liver
```

Não existe fallback de máscara aleatória. Se não houver máscara válida, o caso
falha.

### 5.2 Anatomia interna

O perfil do fígado já declara:

- oito segmentos de Couinaud;
- vesícula biliar;
- veia porta e esplênica;
- veia cava inferior.

As estruturas são opcionais: a ausência de uma estrutura interna não invalida
automaticamente a máscara principal ou a triagem. Cada estrutura possui nome,
cor, material e opacidade no perfil.

### 5.3 Malha e exportação

O pipeline contém:

- refino morfológico;
- remoção de pequenos fragmentos;
- marching cubes;
- suavização Taubin/windowed-sinc;
- exportação STL em coordenadas LPS;
- manifesto do visualizador;
- cores do órgão e lesão configuráveis.

### 5.4 Visualizador

O visualizador Three.js é local/offline e suporta:

- órgão principal;
- lesão manual quando disponível;
- estruturas anatômicas internas;
- materiais e opacidade;
- controles de visibilidade;
- revisão humana;
- persistência da aprovação em `approval.json`.

A segmentação da lesão continua manual pelo 3D Slicer no pipeline anatômico
tradicional. As máscaras públicas de lesão usadas em datasets de pesquisa não
entram no MedGemma.

---

## 6. Painéis de evidência visual

### 6.1 `uniform_9`

É o baseline reprodutível:

- até nove cortes axiais;
- coronal e sagital;
- grade 4×3;
- fusão/configuração fixada;
- compatível com o fluxo histórico.

### 6.2 `volumetric_blocks`

Foi implementada cobertura sistemática:

- identifica o primeiro e o último plano com fígado;
- divide os cortes em blocos;
- gera múltiplos painéis numerados;
- inclui cortes axiais reais;
- mantém coronal e sagital;
- registra metadados por tile;
- calcula hashes;
- falha antes da inferência se o gate de cobertura não for atendido;
- envia um painel por chamada para respeitar memória e contexto;
- agrega as respostas deterministicamente.

Regra de agregação:

```text
qualquer painel POSITIVA → POSITIVA
sem positiva e alguma INCONCLUSIVA → INCONCLUSIVA
todos NEGATIVA → NEGATIVA
falha técnica em qualquer painel → caso inválido
```

### 6.3 Liver-enriched

Os painéis liver-enriched foram criados para aumentar a presença efetiva do
fígado nos tiles e reduzir cortes sem órgão.

No LLD-MMRI:

- 321 casos elegíveis foram preparados;
- 949 imagens de painel foram verificadas;
- 307 casos usaram localizador automático;
- 14 casos permaneceram como falhas técnicas;
- galerias foram revisadas e aprovadas pelo revisor `jm`.

Essa representação melhorou visibilidade e tempo operacional, mas não resolveu
a diferenciação HCC versus lesões benignas.

---

## 7. MedGemma e contrato de inferência

### 7.1 Windows — MedGemma 1.5 4B

O `run_win.ps1`:

- valida ambiente virtual;
- valida CUDA;
- valida pesos locais;
- inicia o gateway na porta 8001;
- confirma o modelo esperado;
- inicia o webapp na porta 8080;
- encerra o gateway ao finalizar o webapp.

Modelo:

```text
google/medgemma-1.5-4b-it
transformers + CUDA + bitsandbytes NF4
```

### 7.2 Mac — MedGemma 27B

O repositório contém:

- `run_mac.sh`;
- configurações Ollama 27B;
- configurações 27B baseline, volumétrica, pathology-target e RAG;
- contrato HTTP compatível com o 4B.

O objetivo arquitetural é trocar somente o backend, preservando painéis,
prompts, schemas e protocolo de avaliação.

O que ainda falta é executar no Mac uma comparação formal do 27B usando o
protocolo visual e estatístico congelado. Não se pode assumir antecipadamente
que o 27B atingirá a meta.

### 7.3 Schema

Campos históricos preservados:

```text
resultado_hipotese
resumo_do_achado
localizacao_aproximada
sinais_visuais_observados
confianca
limitacoes_da_analise
necessidade_de_revisao_humana
```

Campos pathology-target disponíveis:

```text
alvo_da_triagem
ha_lesao_focal_suspeita
ha_variante_anatomica_benigna
ha_pseudolesao_ou_artefato
tipo_alteracao_nao_alvo
justificativa_da_separacao
```

Uma resposta `POSITIVA` sem `ha_lesao_focal_suspeita=true` deve ser rejeitada
ou reparada pelo validador.

---

## 8. RAG e GraphRAG

### 8.1 Corpus textual

Foram selecionadas 41 fontes autorizadas para o corpus v1, cobrindo:

- anatomia hepática;
- segmentos de Couinaud;
- HCC;
- hemangioma;
- FNH;
- cistos;
- metástases;
- colangiocarcinoma;
- DWI/ADC;
- fases dinâmicas;
- padrões de realce;
- pseudolesões;
- artefatos;
- diferenciais.

### 8.2 Fundação RAG implementada

Existem módulos para:

- construção do corpus;
- chunking;
- indexação;
- recuperação BM25;
- grounding;
- avaliação de retrieval;
- geração de documentos a partir do registry;
- persistência do contexto e proveniência.

O RAG é um eixo ortogonal à estratégia de painel:

```text
uniform_9 + sem RAG
uniform_9 + RAG
volumetric_blocks + sem RAG
volumetric_blocks + RAG
```

Na inferência atual, o contexto é anexado ao prompt e seu hash é persistido.

### 8.3 Resultado real do RAG

O RAG melhorou auditabilidade e contexto textual, mas não resolveu a detecção:

- no OpenSwissHCC v26, recuperou o desempenho do v23, sem superá-lo;
- no LLD-MMRI pós-label, os 321 casos elegíveis foram classificados como
  `POSITIVA`;
- especificidade LLD com RAG + pathology-target: **0,00%**.

Conclusão:

```text
RAG textual ajuda consistência, explicação e proveniência.
RAG textual não cria sinal visual ausente e não corrige sozinho a saturação do 4B.
```

### 8.4 GraphRAG Neo4j

Há uma fundação de GraphRAG de metadados com:

- configuração;
- schema;
- store Neo4j;
- ingestão de registry;
- consulta;
- construção de contexto;
- relações de mimetismo.

Exemplos de relações previstas:

```text
prominent_hepatic_vein CAN_MIMIC focal_liver_lesion
motion_artifact CAN_MIMIC focal_lesion
focal_fat CAN_MIMIC focal_liver_lesion
simple_cyst CAN_MIMIC hypovascular_lesion
```

O GraphRAG não é o classificador final atual e não demonstrou ganho de
sensibilidade/especificidade. Ele permanece uma camada de conhecimento e
auditoria, não a prioridade imediata.

### 8.5 Documentação RAG desatualizada

Os arquivos em `docs/rag/` ainda se descrevem como “somente planejamento”, mas
vários módulos RAG e GraphRAG já foram implementados. Essa documentação precisa
ser atualizada antes da próxima versão pública do repositório.

---

## 9. Registry e datasets

O ARGOS possui registry padronizado para datasets em DICOM e NIfTI.

Módulos:

```text
dtwin/datasets/schema.py
dtwin/datasets/dicom_utils.py
dtwin/datasets/nifti_utils.py
dtwin/datasets/registry.py
dtwin/datasets/ingest.py
dtwin/datasets/curation.py
```

Regras importantes:

- TCGA-LIHC deve aceitar somente modalidade MR;
- LLD-MMRI é NIfTI e não pode ser declarado DICOM original;
- CHAOS é controle anatômico, não “normal absoluto”;
- dados permanecem em modo pesquisa;
- UIDs e identificadores sensíveis não devem ser persistidos em texto bruto;
- labels, subtipos e phenotype tags são protegidos da inferência.

### 9.1 OpenSwissHCC

Papel:

- principal base mista;
- 132 casos;
- 63 positivos e 69 negativos;
- fases dinâmicas;
- máscaras hepáticas e de lesão públicas;
- máscaras de lesão nunca usadas na inferência.

Estado:

- antigo desenvolvimento: 88 casos, com 87 computáveis;
- antigo holdout: 44 casos, já consumido;
- coorte completa usada retrospectivamente;
- não existe holdout OpenSwissHCC ainda intacto.

### 9.2 LiverHccSeg

Papel:

- braço positivo externo pequeno;
- 14 casos HCC.

Resultado v21:

```text
sensibilidade = 78,57%
```

O ponto supera 75%, mas a amostra é pequena e não mede especificidade.

### 9.3 CHAOS

Papel:

- braço negativo externo;
- controle anatômico;
- não representa normalidade clínica absoluta.

Resultado v21:

```text
especificidade = 100,00%
```

Não pode ser combinado artificialmente com LiverHccSeg para produzir uma única
matriz, pois classe e dataset ficariam confundidos.

### 9.4 LLD-MMRI

Endpoint congelado:

```text
positivo:
HCC, 157 casos

negativo:
hemangioma + cisto + FNH, 178 casos

total:
335 casos
```

Estado técnico:

- 2.680 imagens NIfTI selecionadas;
- 321 casos elegíveis;
- 14 falhas técnicas;
- 321 relatórios MedGemma;
- 949 chamadas de painel;
- zero falhas de inferência nos elegíveis;
- persistência e verificação completas.

Resultado liver-enriched v3:

```text
TP = 148
TN = 3
FP = 175
FN = 9

sensibilidade = 94,27%
especificidade = 1,69%
ROC-AUC = 0,5145
```

Resultado RAG + pathology-target pós-label:

```text
TP = 152
TN = 0
FP = 178
FN = 5

sensibilidade = 96,82%
especificidade = 0,00%
ROC-AUC = 0,4822
```

O LLD demonstrou de forma clara o problema central: o 4B encontra “alteração”,
mas não separa HCC de mimetizadores benignos.

### 9.5 Bases locais

Diretórios usados ao longo do desenvolvimento:

```text
D:\lote_positivo_1_real
D:\rm_normais
```

Esses conjuntos são úteis para smoke tests, investigação operacional e
curadoria. Eles não substituem uma validação pública com protocolo e revisão
adequados.

---

## 10. Histórico das principais tentativas

Existem duas sequências que reutilizaram números de versão:

1. a linha histórica OpenSwissHCC v3–v23;
2. extensões geométricas e, depois, a retrospectiva multicohort v24–v27.

Por isso, o nome do experimento e a coorte são tão importantes quanto o número.

### 10.1 Resumo histórico

| Versão/linha | Ideia principal | Resultado principal | Decisão |
|---|---|---|---|
| v3 | MedGemma 4B direto | 100% sens.; 0% esp. | Saturação positiva |
| v5 | Fusão de sinais | aparente 76,9%/75,5%; LOOCV 74,4%/75,5% | Quase atingiu, não qualificou |
| v4–v8 | Painéis volumétricos, MedSigLIP e pairwise | em geral ~56%–61%; piloto v8 40%/100% | Não promover |
| v9 | Multissequência | 53,85%/60,42% | Reprovada |
| v10 | Localizador ROI | piloto bom; full87 53,85%/54,17% | Não generalizou |
| v11 | Fusão 40/40/20 | LOOCV 74,36%/75,00% | Melhor resultado limítrofe anterior |
| v13 | Entrada 3D nativa | 51,28%/31,25% | Reprovada |
| v15 | Stacks/candidatos | 56,41%/60,42% | Reprovada |
| v16 | Leitor focal | 48,72%/43,75% | Reprovada |
| v17 | Atlas axial | 41,03%/45,83% | Reprovada |
| v18 | Atlas em blocos | 41,03%/41,67% | Reprovada |
| v19 | Atlas + RAG | 43,59%/45,83% | Reprovada |
| v20 | Fusão v11 + RAG | 69,23%/77,08% | Especificidade boa, sensibilidade insuficiente |
| v21 holdout | Protocolo congelado | 83,33%/35,00% | Falha de generalização |
| v22 | Realce/exact-top5 | piloto 50%/0%; análise ampla 64,10%/80,00% | Sensibilidade insuficiente |
| v23 dev87 | Geometria vascular, 80/20 | 82,05%/79,17% | Melhor desenvolvimento; retrospectivo |
| v24 planaridade | Extensão geométrica | 82,05%/77,08% | Pior que v23 |
| v25 esfericidade | Extensão geométrica | 82,05%/79,17% | Sem ganho |
| v26 bbox fill | Extensão geométrica | 82,05%/79,17% | Peso zero; sem ganho |
| v23 full132 | Retrospectiva multicohort | 65,08%/60,87% | Não generalizou |
| v24 full132 | Liver-enriched | 61,90%/59,42% | Reprovada |
| v25 full132 | Pathology-target | 60,32%/57,97% | Reprovada |
| v26 full132 | Pathology-target + RAG | 65,08%/60,87% | Recuperou v23, sem ganho |
| v27 full132 | Recalibração aninhada | 61,90%/55,07% | Reprovada |

### 10.2 v11

O v11 foi a primeira configuração realmente próxima:

```text
aparente:
sensibilidade = 76,92%
especificidade = 77,08%

LOOCV:
sensibilidade = 74,36%
especificidade = 75,00%
```

Faltou um verdadeiro positivo para superar 75% de sensibilidade.

### 10.3 v23 em 87 casos

O v23 acrescentou linearidade ponderada de candidatos:

```text
80% família v11
20% candidate_weighted_linearity
```

Resultado:

```text
TP = 32
TN = 38
FP = 10
FN = 7

sensibilidade = 82,05%
especificidade = 79,17%
balanced accuracy = 80,61%
```

Robustez:

```text
49/50 repetições atingiram 75/75
```

Limitações:

- hipótese escolhida depois da abertura dos labels de desenvolvimento;
- uma repetição ficou abaixo de 75% de sensibilidade;
- limites inferiores dos IC95% ficaram abaixo de 75%;
- não era uma validação externa.

### 10.4 v23 na coorte completa de 132 casos

Quando os 44 casos do antigo holdout foram incorporados:

```text
TP = 41
TN = 42
FP = 27
FN = 22

sensibilidade = 65,08%
especificidade = 60,87%
ROC-AUC = 0,6866
```

O software reproduziu exatamente o resultado anterior quando restrito aos 87
casos. A queda foi causada por mudança de distribuição, não por alteração
acidental do algoritmo.

### 10.5 v24–v26 na coorte completa

```text
v24 liver-enriched:
61,90% sens. / 59,42% esp.

v25 pathology-target:
60,32% sens. / 57,97% esp.

v26 pathology-target + RAG:
65,08% sens. / 60,87% esp.
```

O RAG recuperou a perda do v24/v25, mas não adicionou separação.

### 10.6 v27 — recalibração aninhada

Foram combinados 25 sinais congelados:

- quatro sinais v23;
- probabilidades e consistência v24;
- sinais estruturados pathology-target v25;
- sinais RAG/pathology-target v26.

O protocolo usou:

- regressão logística balanceada;
- normalização somente no treino;
- regularização L2 escolhida no treino interno;
- limiar escolhido por predições internas out-of-fold;
- LOOCV externo;
- 50×5-fold para robustez.

Resultado:

```text
TP = 39
TN = 38
FP = 31
FN = 24

sensibilidade = 61,90%
especificidade = 55,07%
ROC-AUC = 0,6264
0/50 repetições atingiram 75/75
```

Conclusão: recalibrar os mesmos sinais não é suficiente.

---

## 11. O que mais funcionou

### 11.1 Em desenvolvimento

```text
v23 dev87:
82,05% sensibilidade
79,17% especificidade
```

Esse foi o melhor ponto estimado simultâneo.

### 11.2 Em coorte mista ampliada

Entre as tentativas recentes:

```text
v23 full132:
65,08% / 60,87%

v26 full132:
65,08% / 60,87%
```

### 11.3 Em braços externos separados

```text
LiverHccSeg positivo:
78,57% sensibilidade

CHAOS negativo:
100% especificidade
```

Esses braços não podem ser agrupados como prova de 75/75 porque pertencem a
datasets e classes diferentes.

### 11.4 Em mimetizadores benignos

Nenhuma configuração 4B foi satisfatória:

```text
LLD liver-enriched:
94,27% sensibilidade
1,69% especificidade

LLD RAG + pathology-target:
96,82% sensibilidade
0,00% especificidade
```

---

## 12. Problemas atuais

### 12.1 Saturação em `POSITIVA`

O 4B frequentemente classifica todos ou quase todos os casos como positivos:

- v24 OpenSwissHCC: 129/130 positivos;
- v26 OpenSwissHCC: 130/130 positivos;
- LLD liver-enriched: 314/321 positivos;
- LLD RAG/pathology-target: 321/321 positivos.

### 12.2 Probabilidades pouco separadas

As probabilidades de:

```text
POSITIVA
NEGATIVA
INCONCLUSIVA
```

ficam próximas de 1/3 em muitos casos. O argmax muda com diferenças muito
pequenas e não representa confiança clínica real.

### 12.3 Mimetizadores benignos

Principais falsos positivos:

- FNH;
- hemangioma;
- cisto;
- estruturas vasculares;
- veias calibrosas;
- alterações de perfusão;
- gordura focal;
- artefatos;
- efeitos de volume parcial.

### 12.4 Mudança de domínio

O comportamento varia entre:

- 87 casos de desenvolvimento OpenSwissHCC;
- holdout consumido;
- OpenSwissHCC completo;
- LiverHccSeg;
- CHAOS;
- LLD-MMRI;
- bases locais.

O resultado alto em uma distribuição não se transferiu para outra.

### 12.5 Ausência de sinal novo

As versões v24–v27 reorganizaram sinais existentes. Elas não introduziram um
novo leitor visual realmente independente. A recalibração não consegue criar
informação que não está presente nos sinais.

### 12.6 Falhas técnicas de segmentação

No LLD-MMRI:

```text
335 casos
321 elegíveis
14 falhas técnicas
```

As falhas permanecem no denominador. Isso é metodologicamente correto, mas
reduz o teto de desempenho e deve ser considerado no orçamento operacional.

### 12.7 Tempo end-to-end

Os tempos de inferência por painel passaram com folga:

```text
LLD liver-enriched:
média 20,61 s
máximo 22,02 s

LLD RAG/pathology-target:
média 39,69 s
máximo 42,80 s

OpenSwissHCC v26:
média 48,06 s
máximo 62,19 s
```

Entretanto, o gate final deve medir:

```text
DICOM bruto
+ seleção de série
+ conversão
+ segmentação
+ painéis
+ inferência
+ validação
+ relatório
```

Esse gate end-to-end ainda precisa ser congelado e executado no candidato que
for levado adiante.

### 12.8 Labels já consumidos

- o holdout OpenSwissHCC v21 foi consumido;
- os labels dos 132 casos OpenSwissHCC foram usados na retrospectiva;
- os labels LLD foram abertos depois do primeiro freeze;
- LLD RAG/pathology-target é exploração pós-label.

Essas bases podem continuar sendo usadas para desenvolvimento retrospectivo,
mas não como uma nova validação externa cega.

### 12.9 Revisão médica

As galerias tiveram revisão técnica humana, mas não existe validação
radiológica especializada suficiente para:

- localização segmentar;
- caracterização fina;
- confirmação do motivo do acerto;
- curadoria clínica completa das variantes.

### 12.10 Estado do repositório

Na data deste panorama:

```text
branch: main
último commit: 6ee41c58b267f9a6f1f4afb3c8487f4993eeab04
autor: Felipe Nantes
remote: https://github.com/felipe-nantes/argos.git
```

O working tree está muito distante do último commit:

```text
675 entradas no git status
34 modificadas
641 não rastreadas
```

Isso significa que grande parte do trabalho descrito neste documento ainda
precisa ser organizada, revisada e versionada. Os dados e artefatos pesados não
devem ser enviados ao Git, mas código, configs, testes e documentos precisam
ser separados dos outputs locais antes do próximo push.

Validação automatizada mais recente:

```text
166 testes focados aprovados
0 falhas
27 avisos
```

Essa execução cobriu v23/v24/v27, RAG e o screening MedGemma. A última suíte
completa documentada em fases anteriores chegou a 929 testes aprovados, mas foi
executada antes de várias alterações recentes. Portanto, ela não substitui uma
nova suíte completa sobre o estado atual.

---

## 13. Segurança, privacidade e metodologia já implementadas

O pipeline possui:

- modo `RESEARCH`;
- revisão humana obrigatória;
- resposta não diagnóstica;
- proibição de recomendação de conduta;
- validação de schema;
- abortar em falha;
- isolamento do MedGemma e segmentação em subprocessos;
- hashes SHA-256;
- manifestos;
- publicação atômica;
- checkpoints recuperáveis;
- proteção contra caminho arbitrário no webapp;
- ground truth isolado;
- máscaras de lesão excluídas da inferência;
- falhas e inconclusivos contabilizados como erros;
- distinção entre resultado exploratório, retrospectivo e externo.

O que não está resolvido:

- PHI queimada nos pixels;
- pseudonimização clínica completa;
- integração PACS;
- validação regulatória;
- validação prospectiva;
- validação médica formal.

---

## 14. O que pode e o que não pode ser afirmado

### Pode ser afirmado

- O ARGOS executa um pipeline reprodutível de pesquisa de DICOM até relatório e
  visualizador 3D.
- O MedGemma 4B foi testado em múltiplas representações e coortes públicas.
- O v23 obteve 82,05%/79,17% em uma coorte de desenvolvimento de 87 casos.
- Esse resultado não generalizou para os 132 casos OpenSwissHCC.
- O LLD demonstrou alta sensibilidade e especificidade extremamente baixa
  contra mimetizadores benignos.
- O RAG textual, nessa forma, não resolveu a especificidade.
- A recalibração v27 não resolveu o problema.

### Não pode ser afirmado

- Que o ARGOS possui sensibilidade e especificidade ≥75% de forma consolidada.
- Que 82,05%/79,17% representa desempenho externo.
- Que juntar LiverHccSeg positivo e CHAOS negativo prova 75/75.
- Que revisão humana pode ser usada para retirar casos difíceis da métrica.
- Que o RAG melhora detecção de lesões.
- Que o 27B atingirá a meta antes de ser testado.
- Que o sistema está pronto para uso clínico.

---

## 15. Próximo passo técnico recomendado

O próximo passo com maior justificativa é testar **informação nova**:

### Etapa 1 — Congelar o protocolo de transferência ao 27B

Congelar:

- coorte de desenvolvimento retrospectiva;
- painéis;
- hashes;
- prompt;
- corpus RAG, se usado;
- schema;
- política de falhas;
- métricas;
- tempo;
- regra de decisão.

Não selecionar novamente features usando os mesmos erros.

### Etapa 2 — Executar o MedGemma 27B no Mac

Comparar:

```text
4B e 27B
mesmos casos
mesmos painéis
mesmo protocolo
mesmos labels
mesma política de erros
```

O objetivo é verificar se o 27B produz:

- probabilidades menos saturadas;
- mais negativos corretos;
- melhor separação HCC versus benignos;
- ganho de AUC;
- sensibilidade e especificidade ≥75%.

### Etapa 3 — Avaliação retrospectiva honesta

Como as bases atuais já foram abertas:

- declarar a comparação como retrospectiva;
- usar predições out-of-fold quando houver calibração;
- não chamar o resultado de validação externa cega;
- não esconder falhas técnicas;
- reportar intervalos de confiança.

### Etapa 4 — Gate operacional

Se o 27B mostrar sinal:

- executar tempo DICOM bruto → relatório;
- confirmar ≤180 segundos;
- validar geração do 3D;
- validar os dois modos do exame individual;
- rodar suíte completa;
- empacotar para reprodução no Mac.

### Etapa 5 — Confirmação futura

Uma alegação forte ainda exigirá:

- nova coorte mista e independente;
- ou novos casos coletados prospectivamente;
- revisão especializada;
- protocolo congelado antes dos labels;
- reprodução do resultado.

---

## 16. Pendências de engenharia

1. Organizar o working tree e separar código de dados/artefatos.
2. Executar a suíte completa depois da organização.
3. Atualizar `README.md`, que ainda descreve partes antigas do escopo.
4. Atualizar `docs/rag/`, que ainda afirma não haver implementação.
5. Consolidar os configs experimentais e marcar claramente:
   - operacional;
   - benchmark;
   - piloto;
   - rejeitado;
   - legado.
6. Integrar ao webapp apenas um decisor que passe o protocolo.
7. Não promover a recalibração v27 para o fluxo individual.
8. Versionar código, configs, testes e documentação.
9. Criar bundle/ZIP seguro para o Mac sem imagens protegidas.
10. Reexecutar smoke test DICOM → relatório → 3D após o próximo merge.

---

## 17. Componentes que não devem ser confundidos

### Pipeline operacional do webapp

Produz relatório e 3D, usando os modos autorizados.

### Classificadores experimentais v11/v23/v27

São módulos de benchmark e avaliação. O decisor v23 que obteve 82,05%/79,17%
não está automaticamente promovido como decisor final do exame individual.

### RAG textual

É contexto para o modelo, não detector visual.

### GraphRAG

É conhecimento estruturado e recuperação de metadados, não classificador
validado.

### Visualizador 3D

Serve para revisão anatômica. Sua qualidade não implica acurácia da
classificação MedGemma.

---

## 18. Artefatos principais

### Resultados recentes

- [v23 desenvolvimento](98_OPENSWISSHCC_V23_GEOMETRIA_VASCULAR.md)
- [v23 retrospectiva completa](113_V23_RETROSPECTIVA_MULTICOHORT_FASE4.md)
- [v24 liver-enriched](115_V24_LIVER_ENRICHED_RESULTADO.md)
- [v25 pathology-target](116_V25_PATHOLOGY_TARGET_RESULTADO.md)
- [v26 pathology-target + RAG](117_V26_PATHOLOGY_TARGET_RAG_RESULTADO.md)
- [v27 recalibração aninhada](118_V27_RECALIBRACAO_ANINHADA_RESULTADO.md)
- [LLD-MMRI](100_LLD_MMRI_V23_EXECUCAO_LABEL_BLIND.md)
- [holdout v21](91_OPENSWISSHCC_HOLDOUT_V21_RESULTADO.md)

### Código central

```text
dtwin/core.py
dtwin/stages.py
dtwin/engine.py
dtwin/medgemma_client.py
dtwin/medgemma_screening.py
dtwin/medgemma_volumetric.py
dtwin/medgemma_panel_liver_enriched.py
webapp/server.py
webapp/seg_worker.py
viewer/app.js
profiles/figado.yaml
```

### RAG e datasets

```text
dtwin/rag/
dtwin/graphrag/
dtwin/datasets/
docs/rag/corpus_manifest_v1.yaml
rag/index/liver_mri_rag_v1/
```

### Avaliações recentes

```text
casos/qualification/openswisshcc_v1/evaluation/
  retrospective_multicohort_phase4_v1/
  v24_liver_enriched_v1/
  v25_pathology_target_v1/
  v26_pathology_target_rag_v1/
  v27_nested_recalibration_v1/
```

---

## 19. Critério de sucesso ainda pendente

O projeto somente poderá declarar sucesso no objetivo quando uma única
configuração demonstrar simultaneamente:

```text
sensibilidade >= 75%
especificidade >= 75%
tempo end-to-end <= 180 s
falhas e inconclusivos como erros
nenhuma máscara de lesão na inferência
predições out-of-sample
intervalos de confiança reportados
reprodução completa por hashes/config/código
revisão humana obrigatória
```

Idealmente, isso deve ocorrer em uma coorte mista independente que contenha:

- casos positivos patológicos;
- fígados normais;
- variantes anatômicas;
- pseudolesões e artefatos;
- lesões benignas que mimetizam malignidade.

---

## 20. Conclusão

O ARGOS já possui uma base de engenharia muito mais madura do que um simples
script de inferência:

- pipeline DICOM;
- segmentação;
- painéis;
- MedGemma;
- RAG;
- benchmark;
- visualizador 3D;
- auditoria;
- persistência;
- proteção metodológica.

O objetivo estatístico, porém, permanece aberto. Os experimentos mostraram que:

```text
mais painéis não bastam;
mais texto não basta;
um prompt mais específico não basta;
recalibrar os mesmos sinais não basta.
```

O próximo avanço precisa vir de um leitor visual mais capaz ou de informação
realmente nova. A transferência controlada para o MedGemma 27B é, neste
momento, o próximo teste mais lógico. Até esse teste, o v23 deve permanecer
como referência histórica de desenvolvimento, e não como sistema já
qualificado.
