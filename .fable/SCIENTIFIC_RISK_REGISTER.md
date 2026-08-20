# Registro de riscos científicos

Este registro contém riscos que podem alterar população, labels, geometria, representação, experimento, resultado, denominador ou interpretação. Eles não são dívida técnica comum e não autorizam correção automática.

## Convenções

- **STATUS:** `OPEN`, `AWAITING_HUMAN`, `DOCUMENTED_LIMITATION` ou `CLOSED`. Nenhum item desta primeira auditoria está `CLOSED`.
- **CONFIDENCE:** confiança de que a divergência/risco existe, não probabilidade de dano clínico.
- **RISK:** segue `.fable/RISK_AUTHORITY_MATRIX.md`.
- **HUMAN_GATE:** segue `.fable/HUMAN_GATES.md`.
- Uma alegação de uso clínico, normalidade anatômica, diagnóstico, segurança ou planejamento cirúrgico é `OUT_OF_AUTHORITY`, mesmo se o código tiver um threshold.

## SR-001 — Resultados centrais não são reproduzíveis a partir deste checkout

- **ID:** SR-001
- **LOCATION:** `configs/training/hybrid_v1_protocol.lock.json:35-53`; `configs/training/hybrid_v1_protocol.yaml:5-12`; `docs/121_IMPLEMENTACAO_CLASSIFICADOR_VISUAL_LOG.md`; manuscrito pp. 11–14.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** Os paths de labels protegidos referenciados pelo lock não existem neste checkout. Os documentos preservam números, mas os dados e artefatos OOF necessários para recalculá-los não estão disponíveis.
- **EVIDENCE:** `casos/qualification/openswisshcc_v1/prepared/development_v1/protected_ground_truth/development_labels.jsonl`, `casos/qualification/openswisshcc_v1/prepared/holdout_v21_protected_labels/holdout_labels.jsonl` e `casos/qualification/lld_mmri_v23/prepared/external_protocol_v1/protected_ground_truth/labels.jsonl` foram verificados como ausentes; o lock registra seus hashes.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Impede reprodução independente de 467/451/16, Etapa C, baseline, LoRA, probes e comparações por coorte.
- **ROUTE:** REPRODUCIBILITY + ML_CLASSIFICATION + METRICS_STATISTICS + PROVENANCE
- **RECOMMENDED_PHASE:** PHASE_00_FREEZE e PHASE_06_SCIENTIFIC_REGRESSION
- **HUMAN_GATE:** HG-06, HG-07, HG-08
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Definir pacote de dados/artefatos verificável, licença, hashes, acesso e comando de reprodução sem colocar PHI ou ground truth no Git.

## SR-002 — Ledger executável incompleto para 467/451/16

- **ID:** SR-002
- **LOCATION:** manuscrito pp. 2–3, 6, 11 e 22; `configs/training/hybrid_v1_protocol.lock.json:11-27`; `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:32-77`.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** O repositório congela 467 e 220/247, além de 335+88+44, mas não há um único ledger versionado neste checkout que derive 451 computáveis e 16 falhas com motivo e estágio por caso.
- **EVIDENCE:** O contrato v23 explicita 14 falhas LLD e 321 processáveis; o manuscrito adiciona duas falhas OpenSwiss, mas essa reconciliação não aparece no mesmo lock operacional.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Mudança silenciosa do denominador ou dupla contagem entre OpenSwiss dev/holdout altera sensibilidade, especificidade e coverage.
- **ROUTE:** COHORT + METRICS_STATISTICS + AUDIT + PROVENANCE
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS
- **HUMAN_GATE:** HG-06, HG-08
- **STATUS:** AWAITING_HUMAN
- **DECISION_REQUIRED:** Aprovar um ledger por caso com recebido/elegível/computável/falha/exclusão, sem expor labels protegidos.

## SR-003 — Denominadores mistos no liver-enriched

- **ID:** SR-003
- **LOCATION:** manuscrito p. 11, §3.2 e p. 22, Tabela 2; `dtwin/benchmark/lld_mmri_v23_liver_enriched_evaluation.py:192-220,520-610`.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** A tabela apresenta `n=321 comp.`, mas sensibilidade/especificidade penalizam falhas no denominador de 335; AUC exclui falhas e usa apenas computáveis.
- **EVIDENCE:** O código incrementa FN/FP para falha técnica, valida 157/178 e registra `roc_auc_scope: inference_eligible_cases_only`.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Um leitor pode recalcular proporções com 321, comparar AUC e proporções como se compartilhassem população ou eliminar falhas.
- **ROUTE:** METRICS_STATISTICS + REPORTING
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS
- **HUMAN_GATE:** HG-08
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Fazer a legenda declarar separadamente `n` de cada estimando e confirmar os numeradores congelados.

## SR-004 — Ledger TCGA-LIHC contraditório

- **ID:** SR-004
- **LOCATION:** manuscrito p. 6, §2.2; p. 22, Tabela 1; p. 27, Figura 2.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** A Tabela 1 registra 11 recebidos e 11 computáveis; a Figura 2 mostra 12 solicitados, uma exclusão/falha e 11 incluídos.
- **EVIDENCE:** Contradição visual interna no PDF; TCGA-LIHC não integra o contrato principal atual em `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:32-77`.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Altera fluxo de inclusão, taxa de falha e denominador da sensibilidade 5/11.
- **ROUTE:** COHORT + REPORTING + PROVENANCE
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS
- **HUMAN_GATE:** HG-06, HG-08
- **STATUS:** AWAITING_HUMAN
- **DECISION_REQUIRED:** Reconciliar solicitado/recebido/elegível/computável e corrigir tabela ou figura com ledger de aquisição.

## SR-005 — `n` ausente em experimentos LLD secundários

- **ID:** SR-005
- **LOCATION:** manuscrito pp. 8, 12 e 23; `dtwin/learning/radiomics_features.py`; `dtwin/learning/localized_candidate_features.py`; `dtwin/learning/multi_signal_fusion.py`.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** Descritores, ROI correta, concatenação e fusão T2/DWI são reportados sem um denominador explícito por análise.
- **EVIDENCE:** A Tabela 3 informa apenas “LLD”; disponibilidade de sequência, ROI e falha técnica pode diferir entre módulos.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Deltas entre métodos podem refletir mudança de população, não ganho de representação.
- **ROUTE:** COHORT + LOCALIZATION + ML_CLASSIFICATION + METRICS_STATISTICS
- **RECOMMENDED_PHASE:** PHASE_01_CARTOGRAPHY e PHASE_06_SCIENTIFIC_REGRESSION
- **HUMAN_GATE:** HG-06, HG-07, HG-08
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Vincular cada resultado a IDs de casos, disponibilidade de modalidade, falhas e comparador no mesmo estimando.

## SR-006 — Seleção do bundle final não é a estimativa nested-OOF

- **ID:** SR-006
- **LOCATION:** `dtwin/learning/medsiglip_multiclass_classifier.py:1216-1225,1268-1309`; `docs/123_ETAPA_C_PRODUCAO_E_BENCHMARK_VISUAL.md:21-42`; manuscrito §§2.5.2, 2.6 e 3.5.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** O modelo servível escolhe C, agregação e threshold por CV sobre os folds externos e ajusta todos os casos. A métrica dessa seleção é otimista e não substitui a nested-OOF.
- **EVIDENCE:** O próprio código/doc 123 registra `generalization_estimate_source: nested_oof_etapa_c` e proíbe reportar seleção/in-sample como generalização.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Uma interface ou relatório pode atribuir ~79/80% ou resultado in-sample ao desempenho honesto de 75,91/76,11%.
- **ROUTE:** ML_CLASSIFICATION + CROSS_VALIDATION + METRICS_STATISTICS + FRONTEND
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS e PHASE_04_INVARIANTS
- **HUMAN_GATE:** HG-07, HG-08
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Exigir campo de proveniência do estimando em toda apresentação e teste negativo contra promoção da métrica de seleção.

## SR-007 — Forte separabilidade de coorte e possível shortcut

- **ID:** SR-007
- **LOCATION:** manuscrito pp. 13, 16–17 e 23; `docs/131_FRENTE1_RESULTADO.md:21,85`; `docs/134_PLANO_META_75_75.md:53`; `dtwin/learning/robustness.py`.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** Embeddings e medidas físicas codificam origem quase perfeitamente; a Etapa C também usa classes `positive_unspecified`/`negative_unspecified` específicas de OpenSwiss.
- **EVIDENCE:** Probes documentadas em 100% e 98,75%; performance varia por coorte e transferência LLD→OpenSwiss cai.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Métrica agregada pode explorar diferenças de aquisição/coorte e não transferir para um terceiro domínio.
- **ROUTE:** ML_CLASSIFICATION + CROSS_VALIDATION + STATISTICS + DOMAIN_SHIFT
- **RECOMMENDED_PHASE:** PHASE_06_SCIENTIFIC_REGRESSION
- **HUMAN_GATE:** HG-06, HG-07
- **STATUS:** DOCUMENTED_LIMITATION
- **DECISION_REQUIRED:** Manter claims restritos; definir coorte realmente independente e testes LODO/temporal antes de promoção.

## SR-008 — Dois gates geométricos não equivalentes entre fases

- **ID:** SR-008
- **LOCATION:** `dtwin/benchmark/openswisshcc_alignment.py:60-92,432-457`; `dtwin/learning/multiphase_ingest.py:61-63,194-216,308-317`; manuscrito pp. 7, 14 e 24.
- **CATEGORY:** GEOMETRIC_CONTRACT
- **DESCRIPTION:** O benchmark OpenSwiss usa Dice mínimo 0,80 entre máscaras para escolher alinhamento; a ingestão DICOM bruta usa coverage mínimo 0,50 da grade venosa. O manuscrito não delimita essas rotas.
- **EVIDENCE:** Ambos os valores estão implementados e testados, mas medem objetos diferentes; a união LLD reporta Dice 0,64 em outro contexto.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Troca silenciosa de gate muda exclusões, intensidade dos painéis, geometria e resultado de classificação/volume.
- **ROUTE:** GEOMETRY + REGISTRATION + RESAMPLING + DICOM
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS e PHASE_05_INTEGRATION
- **HUMAN_GATE:** HG-02, HG-04, HG-08
- **STATUS:** AWAITING_HUMAN
- **DECISION_REQUIRED:** Aprovar contrato por rota, declarar métrica/unidade/reference grid e impedir reutilização fora do contexto.

## SR-009 — Resolver DICOM automático é heurístico e documentação está obsoleta

- **ID:** SR-009
- **LOCATION:** `dtwin/learning/raw_dicom_phase_resolver.py:45-57,233-290`; `dtwin/learning/multiphase_ingest.py:8-14,245-273`; `docs/123_ETAPA_C_PRODUCAO_E_BENCHMARK_VISUAL.md:52-69`.
- **CATEGORY:** DOMAIN_POLICY
- **DESCRIPTION:** O código atual resolve fases por semântica DICOM ou ordem pós-contraste, mas docstring e doc 123 ainda afirmam que a identificação automática não existe.
- **EVIDENCE:** `build_multiphase_case` chama `resolve_raw_dicom_phases` quando não há pastas nomeadas; o resolver falha fechado em ambiguidades conhecidas.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Operador/Fable pode assumir requisito de curadoria manual inexistente ou confiar em automação sem confirmação clínica de timing.
- **ROUTE:** DICOM + PIPELINE + DOCUMENTATION
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS e PHASE_05_INTEGRATION
- **HUMAN_GATE:** HG-02
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Definir se o produto aceita resolução automática, quais tags/métodos são autorizados e quando revisão humana é obrigatória.

## SR-010 — DICOM original e PHI podem persistir em artefatos de trabalho

- **ID:** SR-010
- **LOCATION:** `dtwin/learning/raw_dicom_phase_resolver.py:294-326`; `dtwin/stages.py:386-408`; `webapp/server.py:15-17,3200-3244`.
- **CATEGORY:** DOMAIN_POLICY
- **DESCRIPTION:** O resolver hardlinka ou copia os bytes DICOM originais para `resolved_raw_phases`, enquanto o manifesto declara `phi_persisted:false`. A conversão posterior a NIfTI descarta headers, mas não limpa os DICOM materializados nem detecta burned-in PHI.
- **EVIDENCE:** `_materialize` usa `os.link`/`shutil.copy2`; `stage1_ingest` documenta que PHI em pixel exige revisão; o demo autoassume essa confirmação.
- **CONFIDENCE:** HIGH
- **RISK:** OUT_OF_AUTHORITY
- **IMPACT:** Exposição de identificadores, datas/private tags ou texto queimado em disco, logs, backup ou pacote de evidências.
- **ROUTE:** DEIDENTIFICATION + PRIVACY + DICOM + ARTIFACTS
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS e PHASE_07_ADVERSARIAL
- **HUMAN_GATE:** HG-11
- **STATUS:** AWAITING_HUMAN
- **DECISION_REQUIRED:** Aprovar política de storage/retention/de-ID e revisar artefatos reais sem inserir PHI no pack ou Git.

## SR-011 — Validação de geometria da máscara de união omite direction

- **ID:** SR-011
- **LOCATION:** `dtwin/stages.py:717-735`; comparação completa usada para candidatos em `dtwin/stages.py:855-880`.
- **CATEGORY:** GEOMETRIC_CONTRACT
- **DESCRIPTION:** Antes de usar `mask_organ_union` como fonte 3D, `stage5_refine` compara size, spacing e origin, mas não `GetDirection()`. Outras rotas comparam direction explicitamente.
- **EVIDENCE:** A condição em `dtwin/stages.py:726-730` não contém direction; `tests/test_engine_finalize.py:177-255` cobre divergência de spacing, não matriz de direção.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Máscara com eixos/orientação divergentes pode produzir malha e volume espacialmente incorretos sem fallback.
- **ROUTE:** GEOMETRY + SEGMENTATION + RECONSTRUCTION_3D
- **RECOMMENDED_PHASE:** PHASE_03_CHARACTERIZATION e PHASE_04_INVARIANTS
- **HUMAN_GATE:** HG-03, HG-05, HG-10
- **STATUS:** RESOLVED (2026-08-20, PHASE_09 wave 1 — HG-03 HUMAN_DECISIONS item 13)
- **RESOLUTION:** `stage5_refine` e `webapp/server._mesma_geometria_sitk` passaram a exigir direction (`np.allclose(rtol=0, atol=1e-6)`); risco reproduzido com demo determinística (voxel fantasma a 8 mm, `evidence/PH09/`); characterization invertida para spec em 2 arquivos; teste de fallback novo; 2/2 mutantes KILLED; `multiphase_ingest` verificado e INOCENTADO (resample físico já tratava direction).

## SR-012 — Deriva de fonte de segmentação entre classificação e visualização

- **ID:** SR-012
- **LOCATION:** `profiles/figado.yaml:26-70`; `configs/segmentation_visualization_v2.yaml:1-43`; `dtwin/stages.py:140-155,714-765`.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** A máscara primária continua `total_mr`, mas visualização pode preferir shadow aprovada, união entre fases e anatomia opcional. O manuscrito descreve principalmente `total_mr` e uma união piloto.
- **EVIDENCE:** Config v2 declara `visualization_only` e `may_change_classification_input:false`; `_fonte_da_malha_do_orgao` prefere shadow/união.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Usuário pode atribuir métricas do classificador à máscara de visualização, ou comparar volumes provenientes de fontes diferentes sem provenance.
- **ROUTE:** SEGMENTATION + PIPELINE + VOLUMETRY + RECONSTRUCTION_3D
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS e PHASE_05_INTEGRATION
- **HUMAN_GATE:** HG-05, HG-10
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Tornar a origem de cada máscara/volume obrigatória no artefato e proibir promoção shadow→classificação sem experimento aprovado.

## SR-013 — Métricas do localizador histórico não pertencem ao localizador atual

- **ID:** SR-013
- **LOCATION:** `profiles/figado.yaml:61-70`; `docs/185_SUPERVISAO_LOCALIZADA_MONOFASICA_RESULTADOS.md:25-64`; manuscrito pp. 13 e 23.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** O produto atual configura TotalSegmentator `liver_lesions_mr`; o experimento de 32/37, 37/37 e AUC 0,5464 usou pipeline de caixas/supervisão localizada distinto.
- **EVIDENCE:** Não foi localizado teste/artefato de equivalência entre os dois algoritmos.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Herdar recall ou discriminação histórica criaria claim sem evidência para a implementação atual.
- **ROUTE:** LOCALIZATION + SEGMENTATION + METRICS_STATISTICS + FRONTEND
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS e PHASE_06_SCIENTIFIC_REGRESSION
- **HUMAN_GATE:** HG-05, HG-06, HG-08
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Identificar algoritmo/versão por artefato e executar avaliação própria do localizador atual antes de citar métricas.

## SR-014 — Faixa hepática “típica” 900–2400 mL sem fonte aprovada

- **ID:** SR-014
- **LOCATION:** `webapp/server.py:625-637,676-719`; `docs/175_TESTE_FRONTEND_E_VOLUME_HEPATICO.md:29,96-145`; manuscrito pp. 14 e 24.
- **CATEGORY:** CLINICAL_CLAIM
- **DESCRIPTION:** O webapp usa 900–2400 mL para aviso de fígado adulto, mas o repositório não identifica uma norma/paper, população, sexo, superfície corporal, condição hepática ou validação que justifique os limites.
- **EVIDENCE:** O doc 175 chama o piso de não calibrado e observa que 76% da coorte LLD fica abaixo de 900 mL por subsegmentação.
- **CONFIDENCE:** HIGH
- **RISK:** OUT_OF_AUTHORITY
- **IMPACT:** Pode rotular anatomia real como anormal ou mascarar erro de segmentação; não pode ser tratado como threshold clínico.
- **ROUTE:** VOLUMETRY + FRONTEND + CLINICAL_CLAIM
- **RECOMMENDED_PHASE:** PHASE_09_HIGH_RISK_REVIEW
- **HUMAN_GATE:** HG-08, HG-12
- **STATUS:** AWAITING_HUMAN
- **DECISION_REQUIRED:** Especialista deve aprovar/remover/reformular o aviso e fornecer fonte, população e finalidade; Fable não escolhe limites.

## SR-015 — Parâmetros numéricos 3D parcialmente justificados

- **ID:** SR-015
- **LOCATION:** `profiles/figado.yaml:91-119`; `dtwin/stages.py:212-356`; `dtwin/viewer_artifacts.py:89-179`.
- **CATEGORY:** GEOMETRIC_CONTRACT
- **DESCRIPTION:** Isovalue 0,5, 30 iterações Taubin, passband 0,1, grade 0,8 mm, sigma 2,0 mm, 160.000 triângulos, erro de volume 2% e p95 de superfície de 1 voxel afetam malha/QC. Parte possui rationale em comentários, mas não há um único contrato aprovado com dataset, comparador e tolerâncias.
- **EVIDENCE:** Valores estão no perfil e são consumidos pelo pipeline; `tests/test_stages_units.py` protege apenas preservação de volume <5% num fixture e não todos os parâmetros/tolerâncias.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Alterações podem suavizar lesões, mudar topologia, volume aparente, performance do viewer e aprovação de QC.
- **ROUTE:** RECONSTRUCTION_3D + GEOMETRY + PERFORMANCE
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS, PHASE_04_INVARIANTS e PHASE_06_SCIENTIFIC_REGRESSION
- **HUMAN_GATE:** HG-10
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Para cada parâmetro, registrar hipótese, fonte, faixa testada, efeito, tolerância e autoridade; não promover os números sem isso.

## SR-016 — Threshold 0,90 de limpeza altera volume/topologia

- **ID:** SR-016
- **LOCATION:** `dtwin/stages.py:158-208,714-765`; `docs/188_DIAGNOSTICO_E_PLANO_VISUALIZACAO_3D.md:122-125,287-297`; manuscrito pp. 9, 14, 18 e 24.
- **CATEGORY:** DOMAIN_POLICY
- **DESCRIPTION:** O código define “volume relevante” por fração do maior componente ≥0,90, valor ausente do manuscrito.
- **EVIDENCE:** Doc 188 relata 20/321 abaixo de 0,90 e risco de perder >10%; testes exercitam ilha pequena e fígado partido, mas não uma regressão de coorte versionada.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Mudar o piso modifica quais voxels aparecem, volume medido, corpo único e narrativa de QC.
- **ROUTE:** SEGMENTATION + VOLUMETRY + RECONSTRUCTION_3D
- **RECOMMENDED_PHASE:** PHASE_06_SCIENTIFIC_REGRESSION
- **HUMAN_GATE:** HG-05, HG-10
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Aprovar formalmente o contrato e preservar uma regressão por casos de fronteira antes de alteração.

## SR-017 — Volumetria mede máscara, não volume hepático verdadeiro

- **ID:** SR-017
- **LOCATION:** `dtwin/volumetry.py:151-210,425-460`; `dtwin/stages.py:1197-1201`; manuscrito pp. 14, 18–19 e 24.
- **CATEGORY:** CLINICAL_CLAIM
- **DESCRIPTION:** A fórmula física é correta para a máscara, mas a máscara LLD não possui referência humana e mostra subsegmentação importante. Volume de máscara não é automaticamente volume anatômico do órgão.
- **EVIDENCE:** O manifesto nega acurácia anatômica; docs 175/176 documentam mediana 637 mL e discrepância de fase; CHAOS é a única referência humana do manuscrito.
- **CONFIDENCE:** HIGH
- **RISK:** OUT_OF_AUTHORITY
- **IMPACT:** Relatórios podem induzir decisão clínica ou comparação longitudinal inválida se omitirem fonte, qualidade e revisão.
- **ROUTE:** VOLUMETRY + SEGMENTATION + CLINICAL_CLAIM
- **RECOMMENDED_PHASE:** PHASE_06_SCIENTIFIC_REGRESSION e PHASE_09_HIGH_RISK_REVIEW
- **HUMAN_GATE:** HG-05, HG-10, HG-12
- **STATUS:** DOCUMENTED_LIMITATION
- **DECISION_REQUIRED:** Manter linguagem “volume da máscara segmentada” até validação clínica/reader study apropriada.

## SR-018 — Volume de candidato não é volume tumoral

- **ID:** SR-018
- **LOCATION:** `dtwin/volumetry.py:52-55,185-207,425-460`; `profiles/figado.yaml:61-70`; `tests/test_volumetry.py:77-97`.
- **CATEGORY:** CLINICAL_CLAIM
- **DESCRIPTION:** A região candidata automática é deliberadamente não confirmada e pode conter tecido não lesional; seu volume não pode ser rotulado como volume tumoral.
- **EVIDENCE:** Código e testes usam `automatic_unconfirmed_candidate` e exigem revisão.
- **CONFIDENCE:** HIGH
- **RISK:** OUT_OF_AUTHORITY
- **IMPACT:** Pode produzir falsa quantificação de carga tumoral e alterar conduta se a semântica for encurtada na UI/export.
- **ROUTE:** LOCALIZATION + VOLUMETRY + FRONTEND
- **RECOMMENDED_PHASE:** PHASE_04_INVARIANTS
- **HUMAN_GATE:** HG-05, HG-12
- **STATUS:** DOCUMENTED_LIMITATION
- **DECISION_REQUIRED:** Preservar o label completo em JSON, CSV, UI e exports; qualquer promoção exige referência humana e aprovação clínica.

## SR-019 — “Assinatura” do bundle é checksum sem identidade

- **ID:** SR-019
- **LOCATION:** `dtwin/learning/visual_inference.py:75-95`; `tests/test_learning_visual_inference.py:30-73`; manuscrito p. 10, p. 16 e p. 25.
- **CATEGORY:** SOFTWARE_CONTRACT
- **DESCRIPTION:** `bundle_signature` é SHA-256 canônico sem chave. Detecta alteração, mas não autentica produtor, não fornece não repúdio nem cadeia de confiança.
- **EVIDENCE:** O verificador recomputa hash do corpo e do modelo; nenhum keystore/chave/certificado participa.
- **CONFIDENCE:** HIGH
- **RISK:** MEDIUM
- **IMPACT:** Auditor pode interpretar “assinado” como garantia criptográfica/regulatória inexistente.
- **ROUTE:** SECURITY + ARTIFACTS + PROVENANCE + DOCUMENTATION
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS
- **HUMAN_GATE:** HG-01
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Renomear conceitualmente para checksum/integrity hash ou aprovar arquitetura real de assinatura; não alterar sem decisão de segurança.

## SR-020 — Gate de revisão humana não é uniforme

- **ID:** SR-020
- **LOCATION:** manuscrito p. 7 e p. 25; `webapp/server.py:15-17,1041,1090,1226-1228`; `dtwin/stages.py:1226-1233`.
- **CATEGORY:** DOMAIN_POLICY
- **DESCRIPTION:** O manuscrito exige revisão antes de qualquer interpretação; viewer/candidato registram requisito, mas o demo autoassume confirmação de PHI e existe saída com `requires_human_review:false`.
- **EVIDENCE:** Divergência explícita entre docstring do servidor e manifests/regras por rota.
- **CONFIDENCE:** HIGH
- **RISK:** OUT_OF_AUTHORITY
- **IMPACT:** Saída pode parecer aprovada, PHI pode ser processada sem inspeção e fronteira pesquisa/clínica pode desaparecer entre endpoints.
- **ROUTE:** PIPELINE + FRONTEND + PRIVACY + CLINICAL_CLAIM
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS e PHASE_05_INTEGRATION
- **HUMAN_GATE:** HG-11, HG-12
- **STATUS:** AWAITING_HUMAN
- **DECISION_REQUIRED:** Definir matriz de revisão por artefato/endpoint e proibir autoassunção fora de fixture/demo explicitamente isolado.

## SR-021 — CHAOS não transfere validade para LLD ou DCE

- **ID:** SR-021
- **LOCATION:** manuscrito pp. 14, 18–19 e 24; `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:61-68`; `docs/189_SOLUCAO_VISUALIZACAO_UNIAO_DE_FASES.md:54-77`.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** CHAOS tem 20 máscaras humanas e sustenta comparação separada, mas não possui as mesmas fases dinâmicas nem população da coorte principal.
- **EVIDENCE:** O contrato marca CHAOS incompatível com v23 e proíbe métrica de qualificação; o manuscrito limita explicitamente a transferência.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Dice ~0,91 e ganho de união podem ser apresentados indevidamente como acurácia da segmentação LLD/produção.
- **ROUTE:** SEGMENTATION + SCIENTIFIC_REGRESSION + REPORTING
- **RECOMMENDED_PHASE:** PHASE_06_SCIENTIFIC_REGRESSION
- **HUMAN_GATE:** HG-05, HG-06, HG-08
- **STATUS:** DOCUMENTED_LIMITATION
- **DECISION_REQUIRED:** Preservar dataset, sequência, variante, denominador e referência em todo claim; obter referência DCE independente para generalizar.

## SR-022 — Figura 6 não é evidência visual final

- **ID:** SR-022
- **LOCATION:** manuscrito pp. 26, 31 e 32; `dtwin/stages.py:1189-1239`; `dtwin/viewer_artifacts.py`.
- **CATEGORY:** DOMAIN_POLICY
- **DESCRIPTION:** A Figura 6 é template; o código gera assets do viewer, mas não existe exemplo editorial final com fonte, autorização, transformações e referência documentadas.
- **EVIDENCE:** O próprio manuscrito manda não submeter o template.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Privacidade/licença e narrativa visual podem ser violadas; imagem bonita pode sugerir anatomia verdadeira.
- **ROUTE:** RECONSTRUCTION_3D + PRIVACY + REPORTING
- **RECOMMENDED_PHASE:** PHASE_10_CONSOLIDATION
- **HUMAN_GATE:** HG-10, HG-11, HG-12
- **STATUS:** AWAITING_HUMAN
- **DECISION_REQUIRED:** Selecionar exemplos autorizados/desidentificados, registrar proveniência e obter revisão humana antes da submissão.

## SR-023 — Ambiente final e commit do manuscrito estão incompletos

- **ID:** SR-023
- **LOCATION:** manuscrito pp. 6–7, §2.3 e p. 32, pendências L001/L002.
- **CATEGORY:** SOFTWARE_CONTRACT
- **DESCRIPTION:** Driver NVIDIA, build do Windows, CUDA/cuDNN efetivos, commit e ambiente completo não foram congelados na versão de trabalho.
- **EVIDENCE:** O manuscrito declara esses itens pendentes; os tempos/VRAM foram medidos em módulos/versões diferentes.
- **CONFIDENCE:** HIGH
- **RISK:** MEDIUM, promovido a HIGH quando altera numericamente embeddings/segmentação/malha.
- **IMPACT:** Resultados e performance podem não reproduzir em outro hardware/release.
- **ROUTE:** BUILD_ENVIRONMENT + REPRODUCIBILITY + PERFORMANCE
- **RECOMMENDED_PHASE:** PHASE_00_FREEZE
- **HUMAN_GATE:** HG-09 quando modelo/representação for afetado
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Capturar manifest de ambiente e commit vinculados aos artefatos publicados; não inferir versões ausentes.

## SR-024 — Inferência estatística é majoritariamente descritiva

- **ID:** SR-024
- **LOCATION:** manuscrito pp. 9–10, 12 e 19; `configs/benchmark/v23_retrospective_multicohort_contract_v1.json:123-145`; `dtwin/learning/robustness.py`.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** Não há IC de AUC nem comparação pareada completa entre variantes; diversos experimentos diferem em população, endpoint e partição.
- **EVIDENCE:** Limitação explicitamente declarada no manuscrito; contrato marca AUC como secundária.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Ranking por AUC ou linguagem de superioridade/equivalência excede a evidência.
- **ROUTE:** METRICS_STATISTICS + REPORTING
- **RECOMMENDED_PHASE:** PHASE_06_SCIENTIFIC_REGRESSION
- **HUMAN_GATE:** HG-08
- **STATUS:** DOCUMENTED_LIMITATION
- **DECISION_REQUIRED:** Pré-especificar comparação pareada e estimando antes de qualquer claim comparativo novo.

## SR-025 — TCGA-LIHC positivo-only não estima especificidade

- **ID:** SR-025
- **LOCATION:** manuscrito pp. 6, 13, 19, 22–23 e 29.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** O recorte tem apenas positivos; especificidade, acurácia balanceada e uma métrica binária completa são não estimáveis.
- **EVIDENCE:** O manuscrito registra sensibilidade 5/11 e marca demais métricas como N/E; o contrato geral proíbe combinar fontes single-class em métrica primária.
- **CONFIDENCE:** HIGH
- **RISK:** HIGH_SCIENTIFIC_GEOMETRIC
- **IMPACT:** Pode ser apresentado indevidamente como validação externa completa ou combinado com negativos de outro dataset, confundindo classe e origem.
- **ROUTE:** COHORT + METRICS_STATISTICS + REPORTING
- **RECOMMENDED_PHASE:** PHASE_02_CONTRACTS
- **HUMAN_GATE:** HG-06, HG-08
- **STATUS:** DOCUMENTED_LIMITATION
- **DECISION_REQUIRED:** Manter apenas sensibilidade positiva-only com denominador explícito e não fabricar especificidade cross-dataset.

## SR-026 — Volume piloto 568/569 mL sem regra de reconciliação

- **ID:** SR-026
- **LOCATION:** `docs/188_DIAGNOSTICO_E_PLANO_VISUALIZACAO_3D.md:351`; `docs/189_SOLUCAO_VISUALIZACAO_UNIAO_DE_FASES.md:27`; manuscrito pp. 14 e 24.
- **CATEGORY:** SCIENTIFIC_CONTRACT
- **DESCRIPTION:** Duas fontes internas adjacentes registram 568 e 569 mL para a mesma mediana aparente; nenhuma declara alteração de população ou regra de arredondamento.
- **EVIDENCE:** Valores verificados nos dois documentos; manuscrito usa 569 mL.
- **CONFIDENCE:** HIGH
- **RISK:** MEDIUM
- **IMPACT:** Enfraquece rastreabilidade do resultado e pode ocultar cálculo/fonte diferentes.
- **ROUTE:** VOLUMETRY + PROVENANCE + REPORTING
- **RECOMMENDED_PHASE:** PHASE_01_CARTOGRAPHY
- **HUMAN_GATE:** HG-08, HG-10
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Recuperar artefato e método de arredondamento; não escolher um valor por conveniência.

## SR-027 — Segmentos Couinaud atuais não possuem validação anatômica no manuscrito

- **ID:** SR-027
- **LOCATION:** `profiles/figado.yaml:32-54`; `dtwin/volumetry.py:217-270`; `tests/test_volumetry.py:99-150`; manuscrito pp. 9, 14 e 24.
- **CATEGORY:** CLINICAL_CLAIM
- **DESCRIPTION:** O produto atual pode gerar oito segmentos Couinaud e volumes por segmento; o manuscrito não avalia sua acurácia anatômica. O teste existente confirma apenas partição algébrica da máscara hepática.
- **EVIDENCE:** `require_complete:true` e gate de partição existem, mas não há referência humana/reader study dos limites segmentares no material auditado.
- **CONFIDENCE:** HIGH
- **RISK:** OUT_OF_AUTHORITY
- **IMPACT:** Volumes segmentares podem ser confundidos com anatomia cirúrgica válida.
- **ROUTE:** SEGMENTATION + VOLUMETRY + RECONSTRUCTION_3D + CLINICAL_CLAIM
- **RECOMMENDED_PHASE:** PHASE_06_SCIENTIFIC_REGRESSION e PHASE_09_HIGH_RISK_REVIEW
- **HUMAN_GATE:** HG-05, HG-10, HG-12
- **STATUS:** OPEN
- **DECISION_REQUIRED:** Rotular como experimental/técnico e obter validação anatômica humana antes de qualquer uso clínico ou cirúrgico.

## Stop rules derivados

O Fable deve parar e gerar `STOP_REPORT` quando uma task tocar qualquer item `AWAITING_HUMAN`, ou quando exigir:

- escolher entre Dice 0,80 e coverage 0,50;
- alterar 467/451/16, labels, folds, thresholds ou política de falha;
- promover máscara shadow, união, localizador ou Couinaud a output clínico;
- usar 900–2400 mL como verdade clínica;
- remover/reter componentes com outro threshold;
- persistir DICOM real sem política de PHI aprovada;
- chamar checksum de assinatura autenticada;
- publicar resultado sem ledger/artefato reproduzível;
- afirmar anatomia verdadeira, diagnóstico, segurança, utilidade clínica ou planejamento cirúrgico.
