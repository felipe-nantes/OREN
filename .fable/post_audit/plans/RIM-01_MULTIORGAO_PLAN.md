# RIM-01 — OREN multi-órgão: fluxo completo para o RIM (RM+TC)

Data: 2026-08-28 · Autor: Fable 5 · Status: **PLANO APROVADO pelo operador
em 2026-08-28** (plan mode). Fases A-E EXECUTADAS e testadas/provadas com
smoke real; fase F (validação estatística) e G (benignos) pendentes.

## Contexto

O OREN é dirigido por perfis (fígado RM/TC) com motor teoricamente
agnóstico. O operador quer o fluxo aplicável a um segundo órgão: o RIM.
A exploração confirmou que `dtwin/core.py`, `dtwin/engine.py` e ~90% de
`dtwin/stages.py` são genéricos, mas identificou 7 bloqueadores duros e
uma superfície cosmética grande.

Decisões do operador (2026-08-28):
1. **Par como um todo**: perfil "rins" — órgão = união L+R; cada lado é
   estrutura separada no viewer com volumetria por lado + total (TKV).
2. **RM + TC** no v1.
3. **Escopo v1**: volumetria + 3D/XR + candidato de cistos (TC via task
   `kidney_cysts`); **sem laudo automático** (não há classificador renal;
   laudo MedGemma renal fica para um v2 com benchmark próprio).
4. **Contrato versionado com alias**: chaves genéricas novas
   (`organ_summary`, `percent_of_organ`); fígado emite ambas; rim só as
   novas.

Ativos: TS 2.15.0 dá `kidney_left/right` em `total`/`total_mr` (sem
licença) e `kidney_cysts` (CT, task 789, grátis). Ground truth p/ validação
(fase F): CHAOS-MR (rins rotulados, ~1,3GB) e KiTS (CT, maior).

## Desenho (resumo — ver plano completo no histórico da sessão)

- Motor: `rotulo_alvo` no perfil aceita string (byte-idêntico) OU lista
  (união lógica — órgão par). `dtwin/stages.py::stage3_segment_organ`.
- Eixo órgão×modalidade: `webapp/server.py::PROFILES[(organ, modality)]`,
  com `MODALITY_PROFILES`/`_profile_path_for` (CT-01) preservados
  intocados como alias figado-only.
- Flag: `WEBAPP_KIDNEY_ENABLED` (default 0), mesmo padrão do
  `WEBAPP_CT_ENABLED`.
- Worker novo `process_organ_job` (webapp/jobs.py): espelha o desenho
  D3/D4 do CT-01 (sem triagem/laudo), mas genérico a qualquer
  (organ, modality) ≠ figado.
- Candidato de cistos renal (TC): GATED para a fase D — a união de
  múltiplos arquivos de saída (`kidney_cyst_left`/`kidney_cyst_right`)
  em `dtwin/candidate_region.py` não foi feita ainda, deliberadamente,
  para não mexer nesse módulo enquanto a campanha do CT-03 o usa ao vivo.
- Contrato de volumetria v2 (`organ_summary` com alias `whole_liver_summary`
  para fígado) e generalização do viewer/XR (labels por manifesto):
  **fase C, ainda não feita** — hoje o rim usa a MESMA chave
  `whole_liver_summary` do fígado (nome cosmético, dado correto).

## Fases

- **[x] A — Motor multi-rótulo**: `stages.py` aceita lista em
  `rotulo_alvo`; testes dedicados (união, lado ausente aborta, tipo
  inválido aborta) + teste com o perfil REAL `rins.yaml` via fake
  TotalSegmentator. `tests/test_gates_extra.py`.
- **[x] B — Perfis + plumbing órgão×modalidade**: `profiles/rins.yaml`
  (MR) e `profiles/rins_ct.yaml` (CT) — candidato **desabilitado**
  nesta fase; `PROFILES`/`ORGANS_SUPORTADOS`/`KIDNEY_ENABLED` em
  `server.py`; `/api/analyze` aceita `organ` (default `figado`, 100%
  compatível); recusa explícita de campos figado-específicos
  (`scenario`, `medgemma_backend`, `enhanced_3d=1`, `modality=AUTO`)
  quando `organ=rins`; `process_organ_job` despacha por órgão. UI:
  seletor de órgão ao lado do de modalidade (visível só com a flag),
  `renderOrganResult` no card de resultado. Testes:
  `tests/test_rim_ingestion.py` (12 casos: perfis, tabela, dispatch,
  rejeições, worker MR/CT, falha graciosa) + guard de rotas atualizado.
  Suíte completa verde: **1848 passed / 4 skipped / 0 failed**.
  Verificação manual no browser: seletor renderiza, texto correto,
  toggle de picks exclusivos de fígado confirmado via DOM.
- **[x] C — Contrato volumetria v2 + viewer/XR genéricos**: `dtwin/volumetry.py`
  ganha `contract_v2`/`organ`/`organ_summary`/`percent_of_organ` como
  ALIAS aditivo (toda chave v1 permanece; fígado tem as duas, cópia
  exata); `measurement_class` do agregado vira `whole_organ` p/
  não-fígado (a função pura `measurement_class()` continua
  byte-idêntica — a correção é só na fronteira do manifesto, onde o
  órgão é conhecido). `nome_exibicao` do perfil chega ao
  `viewer_manifest.json` (`organ_label`) e ao `label` do mesh do órgão
  (`dtwin/stages.py`, default "Fígado" preserva o caminho histórico).
  Testes: `tests/test_volumetry.py` (2 casos novos: alias exato p/
  fígado, `whole_organ` p/ rim) — 11/11 verdes.
- **[x] D — Candidato de cistos TC**: `dtwin/candidate_region.py` ganha
  `TASK_OUTPUT_FILES` (task→arquivo(s)) e `ALLOWED_TASKS +=
  {kidney_cysts}`; quando a task produz 2 arquivos (par), une por OR
  voxel-a-voxel antes de `validate_and_store_candidate` — caminho de 1
  arquivo (fígado) byte-idêntico. `profiles/rins_ct.yaml` habilitado.
  `process_organ_job` reusa `_localize_candidate_ct` (já organ-agnóstico
  apesar do nome, herdado do CT-01/CT-03) quando o perfil habilita o
  bloco. Testes: união com esferas disjuntas (prova matemática) + aborto
  com lado faltante — `tests/test_rim_ingestion.py`, 14/14 verdes.
- **[x] E — Smoke real (Engine de produção, sem mocks)**: script
  `.fable/post_audit/analysis/rim_smoke_e2e.py`.
  **TC** (TCIA HCC_001, série DICOM real de abdome): rim esquerdo
  164,1mL + direito 162,7mL (organ_summary 326,9mL); candidato de cisto
  rodou e retornou `no_candidate_detected` honestamente (paciente sem
  cisto visível — não é falso positivo forçado); 3 meshes publicadas.
  **RM** (CHAOS-MR sujeito 1, T1DUAL InPhase): rim esquerdo 131,4mL +
  direito 145,1mL (organ_summary 277,3mL, sem candidato — task não
  existe em RM, como desenhado); 3 meshes. Volumes nos dois casos
  fisiologicamente plausíveis (rim adulto ~120-200mL/lado).
  `organ_label` correto nos dois ("Rins"/"Rins (TC)"),
  `measurement_class` correto (`whole_organ`) nos dois.
- **[x] F — Validação ENCERRADA (2026-09-02)**: CHAOS-MR (rim RM) 20/20
  sem falha técnica; **razão mediana 0,665, Dice 0,78** — sub-segmentação
  real via `total_mr` (não erro de execução), zero trocas de
  lateralidade nos 20 casos. KiTS (rim TC) 40/40; **razão mediana 0,847,
  Dice 0,913** — TC bem melhor que RM para rim; correlação
  erro×carga tumoral significativa (rho 0,51, p=0,0007), mesmo padrão
  qualitativo do CT01-F/CT03 fígado. **Ablação do refino (2026-09-02,
  3 piores casos): HIPÓTESE DE ERO SÃO REFUTADA COM DADOS** — a máscara
  BRUTA do total_mr (sem qualquer refino) já sai em razão 0,53-0,58;
  o refino de produção (opening radius=2) muda isso em só ~0,01-0,015
  (ruído). A sub-segmentação é do MODELO total_mr do TotalSegmentator
  para rim em RM, não do refino do OREN — recalibrar radius não
  resolveria. Evidência: `evidence/RIM-F/ablacao_refino_chaos_mr.json`.
  **Veredito honesto: melhorar rim em RM exigiria modelo dedicado (não
  existe task específica no TS 2.15.0); o braço de TC já está em faixa
  razoável.** `validado` permanece `false` nos dois perfis — decisão de
  promoção é gate do operador.
  Evidência: `evidence/RIM-F/rimf_{chaos_mr,kits}_resultados.json`.
- (histórico da fase, antes da execução) runner escrito e validado sem GPU:
  `rim_f_benchmark.py` (+ `rim_f_ts_um_caso.py`) — protocolo pré-registrado
  no docstring; achado de formato ANTES de gastar GPU (CHAOS-MR sujeito 1
  tem InPhase truncada 24/35 vs Ground — fase escolhida por caso batendo
  contagem de cortes; 19/20 sujeitos são InPhase==OutPhase==Ground) e
  sanity check dos 40 KiTS (shapes imagem/label, 40/40 ok). GATED por
  GPU: a campanha CT-03 (detecção) ainda roda (~145 casos CRLM
  restantes); lição registrada de crash nativo por contenção de GPU
  (RTX 4060 8GB) — o runner de validação está encadeado para disparar
  sozinho só quando os processos do CT-03 encerrarem (checagem
  programática, não estimativa de tempo).
  datasets PRONTOS e verificados localmente — CHAOS-MR 20/20 sujeitos
  (`C:\datasets_ct\CHAOS_MR`, re-extraído direto do zip fonte após uma
  corrupção de extração via D: — ver nota abaixo) e KiTS 40/40 casos
  com imagem+label (`C:\datasets_ct\KiTS`, via Hugging Face
  `neheller/KiTS-Challenge-Imaging`). Falta escrever o runner de
  benchmark (razão/Dice por lado, molde do `ct01_f_volumetric`) e rodar
  antes de `validado: true`. Não bloqueia A-E.

### Nota — corrupção de extração via D: (2026-08-28/09-01)

A primeira extração do CHAOS-MR foi para `D:\datasets_rim` durante uma
janela em que o SSD externo (exFAT sem journaling) estava se corrompendo
(mesmo incidente que afetou o CT-03 nesta sessão). Os bytes NASCERAM
corrompidos na extração (arquivos com `0xFF` puro desde o byte ~0x70) —
uma verificação superficial (listagem + até uma primeira leitura GDCM)
não pegou porque foi feita ANTES da corrupção se manifestar; uma
segunda verificação, minutos depois, falhou 100% dos sujeitos. Um
`robocopy` D:→C: copiou fielmente os bytes já ruins (contagem/bytes
batiam, mas o conteúdo era lixo). Correção: reextraído DIRETO do zip
fonte (`Downloads/CHAOS_Train_Sets.zip`, íntegro) para C:, pulando o D:
inteiramente — verificado 20/20 por leitura GDCM real. Lição
permanente: **para qualquer dado que passe pelo D:, uma verificação
antes de "parecer ok" não é garantia — reverificar profundamente depois
de qualquer intervalo, e preferir nunca usar o D: como destino
intermediário nesta máquina.**
- **[ ] Strings da UI**: dicionário `ORGAN_LABELS` para parametrizar
  títulos/etapas por órgão em todo o webapp (hoje só o card de
  resultado do rim tem texto próprio; o resto do fluxo usa strings
  genéricas o suficiente para não confundir, mas não foi auditado
  string a string).

## Governança

- HG-01: este documento espelha o plano aprovado em plan mode.
- HG-05 não dispara (tasks nativas TS via perfil, sem modelo novo
  adotado nesta fase). HG-12 protegido: rim `validado:false` +
  `research_only` + sem laudo em toda a fase B.
- Nenhum contrato científico ou artefato de RM tocado; suíte completa +
  guard de rotas são o oráculo (1848/4/0 após a fase B).
- Fora de escopo v1: laudo MedGemma renal, classificador renal, Bosniak,
  multifásico renal, textura realista de rim (follow-ups documentados).

## Verificação (fase B)

1. Suíte completa verde (1848 passed / 4 skipped / 0 failed).
2. `tests/test_gates_extra.py` — motor multi-rótulo (perfil sintético +
   perfil real `rins.yaml`).
3. `tests/test_rim_ingestion.py` — perfis, tabela órgão×modalidade,
   dispatch do `/api/analyze`, recusas explícitas, worker
   `process_organ_job` (MR e CT, mocks sem GPU).
4. `tests/test_server_route_inventory.py` — guard de rotas/patch-points
   inalterado (nenhuma rota nova; símbolos novos pinados).
5. Verificação manual no browser (`webapp-rim01-preview`,
   `WEBAPP_CT_ENABLED=1` + `WEBAPP_KIDNEY_ENABLED=1`): seletor de órgão
   presente, texto correto, toggle de campos exclusivos de fígado
   (3-D aprimorado/backend MedGemma) confirmado corretamente escondido
   quando `organ=rins` é selecionado.
