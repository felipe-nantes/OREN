# Manuscrito versus repositório

## Escopo da reconciliação

- `SOURCE_B`: `C:/Users/profurg/Downloads/Manuscrito_Integrado_v1_ARGOS_OREN.pdf`, versão de trabalho v1 de 9 de agosto de 2026, 33 páginas. A paginação abaixo é a impressa no PDF.
- `SOURCE_A`: checkout atual em `C:/Users/profurg/Desktop/sander/argos-main`, inspecionado em 17 de agosto de 2026.
- O PDF foi lido integralmente; tabelas e figuras das páginas 22–31 foram também conferidas visualmente.
- `CODE_EVIDENCE` significa evidência existente no repositório. Código, teste ou documento interno que repete um resultado não equivale, por si, à reprodução desse resultado.
- As fontes protegidas citadas em `configs/training/hybrid_v1_protocol.lock.json:35-53` não estão presentes neste checkout. Portanto, resultados numéricos que dependem delas são no máximo `PARTIAL_MATCH`, salvo quando o item trata apenas da regra implementada.
- Status permitidos e usados: `MATCH`, `PARTIAL_MATCH`, `CODE_ONLY`, `MANUSCRIPT_ONLY`, `CONFLICT`, `UNVERIFIED`.
- Este documento não resolve divergências e não promove `OBSERVED_BEHAVIOR` a `SCIENTIFIC_CONTRACT`.

## Claims centrais

### MVC-001

- **CLAIM_ID:** MVC-001
- **CLAIM:** O trabalho é metodológico, retrospectivo e não clínico; não sustenta diagnóstico autônomo, segurança clínica, gêmeo digital, anatomia verdadeira, uso cirúrgico ou transferibilidade universal.
- **MANUSCRIPT_SOURCE:** p. 1, “Escopo científico congelado”; pp. 5, 10, 18–19, §§2.1, 2.9, 5.6–5.7 e 6.
- **CODE_EVIDENCE:** `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:25-31,137-145`; `configs/training/hybrid_v1_protocol.yaml:40-45`; `profiles/figado.yaml:13-15`; `dtwin/stages.py:1189-1202`.
- **STATUS:** MATCH
- **NOTES:** O repositório repete de forma explícita `research_only=true`, `clinical_use_allowed=false` e limita a qualidade 3D à fidelidade à máscara fonte.
- **RISK:** OUT_OF_AUTHORITY se qualquer texto ou interface converter esse limite em alegação assistencial.

### MVC-002

- **CLAIM_ID:** MVC-002
- **CLAIM:** O denominador principal tem 467 exames, 220 positivos, 247 negativos, 451 computáveis e 16 falhas técnicas mantidas no denominador completo.
- **MANUSCRIPT_SOURCE:** pp. 2–3, resumo; p. 6, §2.2; p. 11, §3.1; p. 22, Tabela 1.
- **CODE_EVIDENCE:** `configs/training/hybrid_v1_protocol.lock.json:11-27,35-53`; `configs/training/hybrid_v1_nested_splits.json`; `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:32-77`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** O lock confirma 467, 220/247 e 335+88+44. O contrato v23 confirma 335 LLD, 321 processáveis, 14 falhas e 132 OpenSwiss. O checkout não contém um único ledger executável que reconcilie 451/16, e as fontes protegidas não estão presentes.
- **RISK:** HIGH; população e denominador afetam todas as métricas.

### MVC-003

- **CLAIM_ID:** MVC-003
- **CLAIM:** O holdout OpenSwissHCC de 44 exames foi consumido durante o desenvolvimento e não é validação externa independente.
- **MANUSCRIPT_SOURCE:** p. 6, §2.2; pp. 22–23, Tabelas 1 e 4; p. 27, Figura 2.
- **CODE_EVIDENCE:** `configs/training/hybrid_v1_protocol.lock.json:19-22,42-46`; `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:25-29,34-41`; `docs/123_ETAPA_C_PRODUCAO_E_BENCHMARK_VISUAL.md:10-17`.
- **STATUS:** MATCH
- **NOTES:** O próprio lock o nomeia `openswisshcc_consumed_holdout`; o contrato proíbe claim de validação externa cega.
- **RISK:** HIGH; descrevê-lo como externo inflaria a força inferencial.

### MVC-004

- **CLAIM_ID:** MVC-004
- **CLAIM:** A representação congelada usa `google/medsiglip-448`, revisão `9cea28a1a1195f665105faa6e8544c112fd960a4`, entrada 448, pooling visual, normalização L2, `float16` no dispositivo, saída `float32`, lote 4 e somente arquivos locais.
- **MANUSCRIPT_SOURCE:** p. 7, §2.4.
- **CODE_EVIDENCE:** `configs/training/medsiglip_frozen_v1.yaml:2-13`; `dtwin/learning/medsiglip_embeddings.py:65-76,117-130,147-179,278-289`; `tests/test_learning_medsiglip_embeddings.py:22-70,135-141`.
- **STATUS:** MATCH
- **NOTES:** A implementação valida os principais elementos antes de carregar o modelo e recusa download em runtime.
- **RISK:** HIGH; qualquer troca altera a representação científica e exige HG-09.

### MVC-005

- **CLAIM_ID:** MVC-005
- **CLAIM:** A Etapa C preserva seis rótulos de origem durante o ajuste e agrega `hcc` e `positive_unspecified` como positivos, sem fabricar subtipo para OpenSwissHCC.
- **MANUSCRIPT_SOURCE:** p. 6, §2.2; p. 8, §2.5.2.
- **CODE_EVIDENCE:** `configs/training/medsiglip_multiclass_v1.yaml:14-42`; `dtwin/learning/medsiglip_multiclass_classifier.py:1254-1266`; `tests/test_learning_medsiglip_multiclass_classifier.py:112-150,189-190`.
- **STATUS:** MATCH
- **NOTES:** O código valida a polaridade protegida das classes e recusa declaração incompleta.
- **RISK:** HIGH; alterar mapping, granularidade ou polaridade exige HG-06 e regressão científica integral.

### MVC-006

- **CLAIM_ID:** MVC-006
- **CLAIM:** A estimativa principal usa validação cruzada aninhada 5×4, agrupada por paciente, com seleção de padronização, agregação, regularização e threshold apenas no nível interno.
- **MANUSCRIPT_SOURCE:** pp. 9–10, §2.6.
- **CODE_EVIDENCE:** `configs/training/hybrid_v1_protocol.lock.json:62-73`; `dtwin/learning/splits.py:100-152,158-190`; `dtwin/learning/medsiglip_multiclass_classifier.py:1134-1143`; `tests/test_learning_splits.py:25-86`.
- **STATUS:** MATCH
- **NOTES:** Há validação explícita contra travessia de grupos e casos entre limites externos.
- **RISK:** HIGH; qualquer mudança de folds, agrupamento, seed ou fronteira de fit exige HG-07.

### MVC-007

- **CLAIM_ID:** MVC-007
- **CLAIM:** Falha técnica, timeout, não computável e inconclusivo contam como erro na análise principal em denominador completo; métricas somente entre decisões são secundárias.
- **MANUSCRIPT_SOURCE:** p. 10, §2.7; p. 25, Quadro 1.
- **CODE_EVIDENCE:** `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:123-135`; `dtwin/benchmark/metrics.py:143-287`; `tests/test_benchmark_metrics.py:4-79`; `tests/test_v23_retrospective_multicohort.py:68-79`.
- **STATUS:** MATCH
- **NOTES:** A implementação penaliza a classe verdadeira correspondente e mantém `decisions_only` explicitamente secundária.
- **RISK:** HIGH; mudar esta regra altera o estimando e o denominador.

### MVC-008

- **CLAIM_ID:** MVC-008
- **CLAIM:** Sensibilidade e especificidade mínimas de 75% formam apenas um gate operacional interno, nunca threshold clínico.
- **MANUSCRIPT_SOURCE:** pp. 8 e 10, §§2.5.1 e 2.6; pp. 22 e 28, Tabela 2 e Figura 3.
- **CODE_EVIDENCE:** `configs/training/hybrid_v1_protocol.yaml:25-31,44-45`; `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:123-139`; `dtwin/learning/medsiglip_multiclass_classifier.py:1144-1151`.
- **STATUS:** MATCH
- **NOTES:** O valor está congelado em múltiplos contratos e sempre acompanhado do limite não clínico.
- **RISK:** HIGH; mudar depois de observar resultados é proibido por `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:15-23`.

### MVC-009

- **CLAIM_ID:** MVC-009
- **CLAIM:** Proporções recebem IC95% de Wilson; a Etapa C usa bootstrap agrupado por paciente com 2.000 reamostragens; AUC é secundária e não recebeu intervalo.
- **MANUSCRIPT_SOURCE:** pp. 9–10, §2.6; p. 12, §3.5.
- **CODE_EVIDENCE:** `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:123-135`; `dtwin/benchmark/metrics.py:15-39,245-250`; `dtwin/learning/robustness.py:176-215,362-395`; `tests/test_benchmark_metrics.py:78-94`; `tests/test_learning_robustness.py:58-85`.
- **STATUS:** MATCH
- **NOTES:** O default de bootstrap é 2.000 e o reamostramento é por grupo de paciente. A ausência de IC para AUC permanece uma limitação declarada, não uma equivalência.
- **RISK:** HIGH; método de IC, unidade de reamostragem e reporting são HG-08.

### MVC-010

- **CLAIM_ID:** MVC-010
- **CLAIM:** A ingestão exclui séries derivadas identificáveis, resolve arterial/venosa/tardia e harmoniza intensidades para a grade venosa.
- **MANUSCRIPT_SOURCE:** p. 7, §2.4.
- **CODE_EVIDENCE:** `dtwin/learning/raw_dicom_phase_resolver.py:45-57,233-290`; `dtwin/learning/multiphase_ingest.py:42-63,194-216,245-321`; `tests/test_raw_dicom_phase_resolver.py:83-205`; `tests/test_learning_multiphase_ingest.py:114-190`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** A rota atual resolve DICOM bruto automaticamente e exclui SUB/MPR/MIP. Porém o docstring em `dtwin/learning/multiphase_ingest.py:8-14` e `docs/123_ETAPA_C_PRODUCAO_E_BENCHMARK_VISUAL.md:52-69` ainda dizem que a identificação automática não existe. Além disso, a produção usa coverage 0,50, enquanto o manuscrito apresenta Dice 0,80 como gate de alinhamento.
- **RISK:** HIGH geométrico e de seleção DICOM; exige HG-02/HG-04.

### MVC-011

- **CLAIM_ID:** MVC-011
- **CLAIM:** A máscara hepática primária é produzida por TotalSegmentator MRI `total_mr`, rótulo `liver`.
- **MANUSCRIPT_SOURCE:** p. 7, §2.4.
- **CODE_EVIDENCE:** `profiles/figado.yaml:26-30`; `tests/test_webapp.py:25`; `dtwin/benchmark/lld_mmri_v23_preparation.py`.
- **STATUS:** MATCH
- **NOTES:** O repositório agora também possui uma máscara shadow de visualização e anatomia opcional; esses acréscimos não devem ser confundidos com o input congelado da classificação.
- **RISK:** HIGH; trocar modelo/task ou promover a shadow altera segmentação e volumetria.

### MVC-012

- **CLAIM_ID:** MVC-012
- **CLAIM:** Localização é pós-inferência, produz candidato para revisão e não retroalimenta a decisão binária.
- **MANUSCRIPT_SOURCE:** pp. 7 e 9, §§2.4 e 2.5.5; pp. 13, 16 e 18, §§3.6, 4.7 e 5.4.
- **CODE_EVIDENCE:** `profiles/figado.yaml:61-70`; `configs/training/hybrid_v1_protocol.yaml:40-43`; `dtwin/learning/visual_inference.py:160-166`; `tests/test_learning_visual_inference.py:76-90`; `tests/test_webapp.py:730`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** A separação semântica coincide. O localizador de produção atual (`liver_lesions_mr`) não é demonstrado como sendo o mesmo algoritmo avaliado retrospectivamente no manuscrito.
- **RISK:** HIGH; métricas históricas não podem ser herdadas pelo localizador atual sem experimento de equivalência.

### MVC-013

- **CLAIM_ID:** MVC-013
- **CLAIM:** Um subtipo só é emitido quando ao menos 50% da massa pertence às classes de lesão nomeadas.
- **MANUSCRIPT_SOURCE:** p. 9, §2.5.5.
- **CODE_EVIDENCE:** `dtwin/learning/visual_inference.py:49,169-207`; `tests/test_visual_subtype.py:24-49`.
- **STATUS:** MATCH
- **NOTES:** O guard recusa renormalizar massa quase nula sobre classes nomeadas.
- **RISK:** HIGH; o piso é política científica, não threshold clínico, e exige HG-08 para mudança.

### MVC-014

- **CLAIM_ID:** MVC-014
- **CLAIM:** Bundles congelam classes, normalização, threshold, modelo e proveniência, detectando adulteração.
- **MANUSCRIPT_SOURCE:** p. 10, §2.8; p. 16, item 9; p. 25, Quadro 1 (“bundle assinado”).
- **CODE_EVIDENCE:** `dtwin/learning/visual_inference.py:75-95`; `dtwin/learning/medsiglip_multiclass_classifier.py:1216-1225`; `tests/test_learning_visual_inference.py:30-73`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** O repositório usa SHA-256 canônico do manifesto e hash do modelo. Isso fornece integridade contra alteração acidental/detectável, mas não assinatura criptográfica com chave ou identidade do signatário.
- **RISK:** MEDIUM/HIGH; chamar checksum de “assinatura” pode criar garantia de autenticidade inexistente.

### MVC-015

- **CLAIM_ID:** MVC-015
- **CLAIM:** A Etapa C obteve sensibilidade 75,91%, especificidade 76,11%, acurácia balanceada 76,01% e AUC 0,8534 no denominador de 467.
- **MANUSCRIPT_SOURCE:** pp. 2–3, resumo; p. 12, §3.5; p. 23, Tabela 4.
- **CODE_EVIDENCE:** `docs/121_IMPLEMENTACAO_CLASSIFICADOR_VISUAL_LOG.md:1464-1477`; `docs/123_ETAPA_C_PRODUCAO_E_BENCHMARK_VISUAL.md:10-17,36-42`; `dtwin/learning/medsiglip_multiclass_classifier.py:1125-1152`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** A documentação e o formato de avaliação coincidem, mas os dados protegidos e o artefato OOF completo necessário para reprodução não estão neste checkout. O código também distingue a seleção não aninhada do bundle final da estimativa nested-OOF.
- **RISK:** HIGH; resultado não deve ser promovido a validade externa ou clínica.

### MVC-016

- **CLAIM_ID:** MVC-016
- **CLAIM:** O encoder congelado + logística obteve 72,27%/73,28% e AUC 0,8014; LoRA rank 4 Q/V obteve 75,00%/70,45% e AUC 0,8187, sem superioridade pareada demonstrada.
- **MANUSCRIPT_SOURCE:** pp. 11–12, §3.3; p. 22, Tabela 2.
- **CODE_EVIDENCE:** `configs/training/medsiglip_lora_v1.yaml:1-29`; `docs/121_IMPLEMENTACAO_CLASSIFICADOR_VISUAL_LOG.md:459-486,936-960,1048-1052,1183-1184`; `docs/122_RELATORIO_CONCLUSAO_CICLO_CLASSIFICADOR_VISUAL.md:22-24`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** Configurações e números são consistentes nos documentos do repositório, mas não foram reproduzidos nesta auditoria e os dados protegidos não estão presentes.
- **RISK:** HIGH; diferenças descritivas não autorizam substituição do modelo.

### MVC-017

- **CLAIM_ID:** MVC-017
- **CLAIM:** O desempenho agregado coexistiu com forte informação de domínio: sondas atingiram 100% nos embeddings e 98,75% nas medidas físicas.
- **MANUSCRIPT_SOURCE:** p. 13, §3.5; p. 23, Tabela 4; pp. 16–17, §§4.6 e 5.3.
- **CODE_EVIDENCE:** `dtwin/learning/robustness.py`; `tests/test_learning_robustness.py`; `docs/131_FRENTE1_RESULTADO.md:21,85`; `docs/134_PLANO_META_75_75.md:53`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** A análise existe e os documentos internos repetem os resultados; o artefato de resultados e os dados necessários para reexecução não estão disponíveis neste checkout. A sonda não prova uso causal da origem pelo classificador.
- **RISK:** HIGH; risco de shortcut, transportabilidade limitada e classes específicas de coorte.

### MVC-018

- **CLAIM_ID:** MVC-018
- **CLAIM:** O localizador cobriu 32/37 positivos no top-8 e 37/37 em qualquer caixa, mas o melhor classificador de candidato permaneceu próximo ao acaso (AUC 0,5464).
- **MANUSCRIPT_SOURCE:** p. 13, §3.6; p. 23, Tabela 3; p. 30, Figura 5.
- **CODE_EVIDENCE:** `docs/185_SUPERVISAO_LOCALIZADA_MONOFASICA_RESULTADOS.md:25-64`; `dtwin/learning/localized_candidate_supervision.py`; `dtwin/benchmark/openswisshcc_candidate_localization_audit.py`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** O relatório interno explica que apenas 37 dos 39 positivos tinham máscara pública; o código atual de localização no produto não é demonstrado equivalente ao experimento.
- **RISK:** HIGH; cobertura espacial não é diagnóstico, explicação causal ou validação do candidato.

### MVC-019

- **CLAIM_ID:** MVC-019
- **CLAIM:** A camada 3D é instrumento de auditoria/visualização; métricas de máscara e malha não estabelecem acurácia anatômica ou utilidade clínica.
- **MANUSCRIPT_SOURCE:** pp. 9, 14 e 18, §§2.5.6, 3.8 e 5.5; p. 24, Tabela 6.
- **CODE_EVIDENCE:** `dtwin/stages.py:1189-1202`; `dtwin/viewer_artifacts.py:89-179`; `dtwin/volumetry.py:425-460`; `tests/test_engine_finalize.py:13-55`.
- **STATUS:** MATCH
- **NOTES:** O manifesto do viewer explicita “fidelidade à máscara fonte” e nega acurácia anatômica da segmentação.
- **RISK:** OUT_OF_AUTHORITY se a superfície for chamada de anatomia verdadeira, gêmeo digital ou modelo cirúrgico.

### MVC-020

- **CLAIM_ID:** MVC-020
- **CLAIM:** Os resultados 3D reportam, entre outros, 75% de máscaras LLD fragmentadas, 84% com Euler diferente de 1, mediana de 637 mL e, no CHAOS n=20, Dice 0,9082/0,8957/0,9168 e precisão de adição 0,8194.
- **MANUSCRIPT_SOURCE:** p. 14, §3.8; p. 24, Tabela 6.
- **CODE_EVIDENCE:** `docs/188_DIAGNOSTICO_E_PLANO_VISUALIZACAO_3D.md:41-42,122-125,233-297`; `docs/175_TESTE_FRONTEND_E_VOLUME_HEPATICO.md:90-116`; `docs/189_SOLUCAO_VISUALIZACAO_UNIAO_DE_FASES.md:27-77`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** Os documentos internos preservam os valores e mapeiam as variantes CHAOS, mas os artefatos de caso necessários para reprodução não estão versionados neste checkout. O CHAOS não valida LLD-MMRI.
- **RISK:** HIGH; resultados de QC/topologia não podem ser convertidos em acurácia anatômica.

### MVC-021

- **CLAIM_ID:** MVC-021
- **CLAIM:** Todas as saídas exigem revisão humana antes de qualquer interpretação aplicada.
- **MANUSCRIPT_SOURCE:** p. 7, §2.4; p. 25, Quadro 1.
- **CODE_EVIDENCE:** `profiles/figado.yaml:61-70`; `dtwin/stages.py:1226-1233`; `webapp/server.py:15-17,1041,1090,1226-1228`.
- **STATUS:** CONFLICT
- **NOTES:** O viewer e o candidato exigem revisão, mas o servidor declara que, no demo hands-off, a confirmação humana de PHI queimada é autoassumida e uma rota registra `requires_human_review: false`. A regra universal do manuscrito não é aplicada uniformemente.
- **RISK:** CRITICAL para privacidade e qualquer interpretação clínica; HG-11/HG-12.

### MVC-022

- **CLAIM_ID:** MVC-022
- **CLAIM:** O volume autoritativo atual é `contagem de voxels da máscara binária × volume físico do voxel`, em mL; a malha nunca é a fonte quantitativa.
- **MANUSCRIPT_SOURCE:** O manuscrito registra “volume” e métricas 3D, mas não fornece a fórmula nem declara a fonte autoritativa (pp. 9, 14 e 24).
- **CODE_EVIDENCE:** `dtwin/volumetry.py:151-210,425-460,559-590`; `tests/test_volumetry.py:33-99`; `tests/test_engine_finalize.py:23-40`.
- **STATUS:** CODE_ONLY
- **NOTES:** É um contrato geométrico explícito e bem testado no código atual; não valida a correção anatômica da máscara.
- **RISK:** HIGH; unidade, spacing, geometria ou fonte da medida não podem mudar sem HG-03/HG-10.

## Quinze ambiguidades e contradições prioritárias

### MVA-001

- **CLAIM_ID:** MVA-001
- **CLAIM:** O manuscrito apresenta Dice 0,80 como gate de alinhamento quando fases são combinadas, mas também relata mediana Dice entre fases de 0,64; a rota atual de DICOM bruto usa coverage 0,50, não Dice.
- **MANUSCRIPT_SOURCE:** p. 7, §2.4; p. 14, §3.8; p. 24, Tabela 6.
- **CODE_EVIDENCE:** `dtwin/benchmark/openswisshcc_alignment.py:60-92,432-457`; `tests/test_openswisshcc_alignment.py:19-58`; `dtwin/learning/multiphase_ingest.py:61-63,194-216,308-317`.
- **STATUS:** CONFLICT
- **NOTES:** Dice de máscaras para escolher alinhamento, Dice entre segmentações de fases e coverage da grade são quantidades distintas. O manuscrito não separa claramente os três contextos.
- **RISK:** HIGH; selecionar o gate errado muda inclusão, geometria e painéis.

### MVA-002

- **CLAIM_ID:** MVA-002
- **CLAIM:** TCGA-LIHC aparece como 11 exames recebidos na Tabela 1, enquanto a Figura 2 mostra 12 solicitados, uma falha e 11 incluídos.
- **MANUSCRIPT_SOURCE:** p. 6, §2.2; p. 22, Tabela 1; p. 27, Figura 2.
- **CODE_EVIDENCE:** O contrato principal atual não inclui TCGA-LIHC: `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:32-77`.
- **STATUS:** MANUSCRIPT_ONLY
- **NOTES:** “Recebidos” e “incluídos após falha” não podem ambos ser 11 se a figura começa em 12. É necessária correção editorial ou ledger de aquisição.
- **RISK:** HIGH; altera fluxo de inclusão e denominador de sensibilidade positiva-only.

### MVA-003

- **CLAIM_ID:** MVA-003
- **CLAIM:** O piloto 3D registra volume mediano de 568 mL em um documento e 569 mL no seguinte/manuscrito, sem declarar regra de arredondamento ou mudança de conjunto.
- **MANUSCRIPT_SOURCE:** p. 14, §3.8; p. 24, Tabela 6.
- **CODE_EVIDENCE:** `docs/188_DIAGNOSTICO_E_PLANO_VISUALIZACAO_3D.md:351`; `docs/189_SOLUCAO_VISUALIZACAO_UNIAO_DE_FASES.md:27`.
- **STATUS:** CONFLICT
- **NOTES:** A diferença pode ser arredondamento, mas a origem não está documentada; não deve ser “corrigida” por inferência.
- **RISK:** MEDIUM científico/editorial; ameaça rastreabilidade do resultado congelado.

### MVA-004

- **CLAIM_ID:** MVA-004
- **CLAIM:** O experimento generativo liver-enriched é rotulado como `LLD 321 comp.`, mas sensibilidade 94,27% e especificidade 1,69% usam os denominadores completos 157 positivos e 178 negativos, com falhas penalizadas; AUC usa apenas computáveis.
- **MANUSCRIPT_SOURCE:** p. 11, §3.2; p. 22, Tabela 2.
- **CODE_EVIDENCE:** `dtwin/benchmark/lld_mmri_v23_liver_enriched_evaluation.py:192-220,520-610`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** O código esclarece dois estimandos legítimos, mas a tabela não mostra simultaneamente `n=335` para proporções e `n=321` para AUC/decisões.
- **RISK:** HIGH; leitores podem usar o denominador errado ao reconstruir métricas.

### MVA-005

- **CLAIM_ID:** MVA-005
- **CLAIM:** O desenvolvimento OpenSwissHCC tem 39 positivos, mas o localizador é relatado em 37 positivos visíveis sem explicação no corpo principal.
- **MANUSCRIPT_SOURCE:** pp. 6 e 13, §§2.2 e 3.6; pp. 22–23, Tabelas 1 e 3.
- **CODE_EVIDENCE:** `docs/71_OPENSWISSHCC_V17_PROTOCOLO_DE_AUDITORIA.md:111-138`; `docs/185_SUPERVISAO_LOCALIZADA_MONOFASICA_RESULTADOS.md:25-51`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** O repositório explica que dois positivos públicos não tinham máscara venosa. Essa diferença de disponibilidade deve estar no manuscrito e no denominador da localização.
- **RISK:** HIGH; disponibilidade de máscara condiciona população e endpoint.

### MVA-006

- **CLAIM_ID:** MVA-006
- **CLAIM:** O manuscrito não especifica completamente como o único bundle servível da Etapa C escolhe hiperparâmetros e threshold após a avaliação nested-OOF.
- **MANUSCRIPT_SOURCE:** pp. 6, 8–10 e 12, §§2.2, 2.5.2, 2.6 e 3.5; p. 25, Quadro 1.
- **CODE_EVIDENCE:** `dtwin/learning/medsiglip_multiclass_classifier.py:1216-1230,1268-1309`; `docs/123_ETAPA_C_PRODUCAO_E_BENCHMARK_VISUAL.md:21-42`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** O bundle final seleciona C/agregação/threshold por CV sobre os folds externos congelados e depois ajusta todos os casos; essa métrica de seleção não é aninhada. A estimativa honesta continua sendo a nested-OOF, distinção ausente do método principal.
- **RISK:** HIGH; risco de reportar desempenho de seleção/in-sample como generalização.

### MVA-007

- **CLAIM_ID:** MVA-007
- **CLAIM:** LiverHccSeg é citado como material positivo complementar, mas não possui linha na Tabela 1 nem denominador explícito no corpo do manuscrito.
- **MANUSCRIPT_SOURCE:** p. 6, §2.2; p. 22, Tabela 1.
- **CODE_EVIDENCE:** `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:53-60`; `dtwin/benchmark/v23_retrospective_multicohort.py:114-121`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** O repositório congela `expected_cases: 14` e papel secundário positivo, mas o manuscrito não reconcilia quando esses casos entram ou não entram em cada experimento.
- **RISK:** HIGH; população positiva adicional pode contaminar comparações ou ser contada em duplicidade.

### MVA-008

- **CLAIM_ID:** MVA-008
- **CLAIM:** Descritores, ROI correta, concatenação global+ROI e fusão T2/DWI apresentam resultados LLD sem declarar claramente o `n` de cada análise na Tabela 3.
- **MANUSCRIPT_SOURCE:** pp. 8 e 12, §§2.5.4 e 3.4; p. 23, Tabela 3.
- **CODE_EVIDENCE:** Existem implementações em `dtwin/learning/radiomics_features.py`, `dtwin/learning/localized_candidate_features.py` e `dtwin/learning/multi_signal_fusion.py`, mas não há um ledger único versionado no checkout que associe cada número do manuscrito ao seu denominador.
- **STATUS:** UNVERIFIED
- **NOTES:** Não inferir que todos usam 321 ou 335; disponibilidade de T2/DWI, ROI e falhas pode mudar a população.
- **RISK:** HIGH; comparação sem denominador comum pode sugerir ganho inexistente.

### MVA-009

- **CLAIM_ID:** MVA-009
- **CLAIM:** O manuscrito relata volumes sem declarar fórmula, máscara fonte, geometria autoritativa ou se a malha participa da medida.
- **MANUSCRIPT_SOURCE:** pp. 9, 14 e 24, §§2.5.6, 3.8 e Tabela 6.
- **CODE_EVIDENCE:** `dtwin/volumetry.py:151-210,425-460,559-590`; `tests/test_volumetry.py:33-99`.
- **STATUS:** CODE_ONLY
- **NOTES:** O código atual resolve a lacuna com voxels × spacing e rejeita a malha como fonte, mas isso é posterior/ausente no manuscrito.
- **RISK:** HIGH geométrico; resultados antigos precisam confirmar que usaram a mesma definição.

### MVA-010

- **CLAIM_ID:** MVA-010
- **CLAIM:** “Faixa adulta de referência operacional” é usada para dizer que 6/14 volumes estavam em faixa, mas os limites não aparecem no manuscrito.
- **MANUSCRIPT_SOURCE:** p. 14, §3.8; p. 24, Tabela 6.
- **CODE_EVIDENCE:** `webapp/server.py:625-637` define atualmente 900–2400 mL; `docs/175_TESTE_FRONTEND_E_VOLUME_HEPATICO.md:29,96-145` documenta uso e ausência de calibração suficiente.
- **STATUS:** CODE_ONLY
- **NOTES:** Não há fonte normativa/peer-reviewed identificada no repositório para os dois limites; eles não são promovidos a contrato científico neste pack.
- **RISK:** HIGH/CLINICAL_CLAIM; pode rotular anatomia de paciente como anormal sem validação.

### MVA-011

- **CLAIM_ID:** MVA-011
- **CLAIM:** A “limpeza condicional” só remove componente quando não elimina volume relevante, mas o manuscrito não define “relevante”.
- **MANUSCRIPT_SOURCE:** p. 9, §2.5.6; pp. 14 e 18, §§3.8 e 5.5; p. 24, Tabela 6.
- **CODE_EVIDENCE:** `dtwin/stages.py:158-208,714-765`; `docs/188_DIAGNOSTICO_E_PLANO_VISUALIZACAO_3D.md:122-125,287-297`; `tests/test_engine_finalize.py:122-174`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** O código atual usa fração mínima 0,90 do maior componente e preserva a máscara quando o maior componente representa menos que isso. A constante deve ser explicitada no manuscrito ou vinculada a um contrato aprovado.
- **RISK:** HIGH; cleanup altera topologia e volume visível.

### MVA-012

- **CLAIM_ID:** MVA-012
- **CLAIM:** O termo “bundle assinado” pode ser entendido como assinatura criptográfica, mas o mecanismo implementado é hash SHA-256 sem chave.
- **MANUSCRIPT_SOURCE:** p. 10, §2.8; p. 16, item 9; p. 25, Quadro 1.
- **CODE_EVIDENCE:** `dtwin/learning/visual_inference.py:75-95`; `tests/test_learning_visual_inference.py:30-73`.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** Há detecção de alteração, não autenticação de autor, não repúdio ou cadeia de confiança.
- **RISK:** MEDIUM/HIGH; linguagem de segurança pode exceder a garantia real.

### MVA-013

- **CLAIM_ID:** MVA-013
- **CLAIM:** O manuscrito afirma seleção DICOM automática, remoção de identificadores antes dos artefatos e revisão humana universal, mas a implementação e a documentação atual divergem nesses três pontos.
- **MANUSCRIPT_SOURCE:** p. 7, §2.4; p. 25, Quadro 1.
- **CODE_EVIDENCE:** `dtwin/learning/multiphase_ingest.py:8-14,245-273`; `dtwin/learning/raw_dicom_phase_resolver.py:294-326`; `dtwin/stages.py:386-408`; `webapp/server.py:15-17`.
- **STATUS:** CONFLICT
- **NOTES:** Há resolver automático apesar de documentação antiga negá-lo; ele hardlinka/copia bytes DICOM originais para `resolved_raw_phases`; apenas o manifesto declara `phi_persisted:false`. Burned-in PHI não é detectada e o demo autoassume a confirmação humana.
- **RISK:** CRITICAL; seleção incorreta, PHI persistida e interpretação sem gate humano.

### MVA-014

- **CLAIM_ID:** MVA-014
- **CLAIM:** O manuscrito lista três Dices CHAOS sem associar cada valor à variante de máscara.
- **MANUSCRIPT_SOURCE:** p. 14, §3.8; p. 24, Tabela 6.
- **CODE_EVIDENCE:** `docs/189_SOLUCAO_VISUALIZACAO_UNIAO_DE_FASES.md:54-63` mapeia 0,9082 a in-phase, 0,8957 a out-phase e 0,9168 à união.
- **STATUS:** PARTIAL_MATCH
- **NOTES:** A associação existe no repositório, mas precisa ser incorporada ao manuscrito para impedir permutação dos resultados.
- **RISK:** MEDIUM científico/editorial.

### MVA-015

- **CLAIM_ID:** MVA-015
- **CLAIM:** A Figura 6 é apenas um template e ainda não contém exemplos reais anonimizados, autorizados e rastreáveis.
- **MANUSCRIPT_SOURCE:** pp. 14 e 26, §3.8 e nota das figuras; p. 31, Figura 6; p. 32, pendências editoriais.
- **CODE_EVIDENCE:** O repositório gera assets e manifesto de viewer em `dtwin/stages.py:1189-1239` e `dtwin/viewer_artifacts.py`, mas isso não constitui a figura editorial final nem comprova autorização dos exemplos.
- **STATUS:** MANUSCRIPT_ONLY
- **NOTES:** A própria versão de trabalho proíbe submeter o template.
- **RISK:** HIGH para privacidade, licença e integridade editorial.

## Regra de uso pelo Fable

1. `MATCH` não significa validade clínica; significa apenas coerência documental/implementada no escopo citado.
2. Resultado `PARTIAL_MATCH` não pode ser republicado como reproduzido enquanto os dados, hashes e artefatos de execução não forem reconciliados.
3. `CONFLICT`, `UNVERIFIED` e qualquer mudança em população, labels, geometria, threshold, denominador, modelo, representação ou 3D quantitativo acionam o human gate correspondente.
4. Nenhum item deste documento autoriza alteração do código ou do desenho científico.
