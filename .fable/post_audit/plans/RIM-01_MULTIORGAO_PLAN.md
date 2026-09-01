# RIM-01 — OREN multi-órgão: fluxo completo para o RIM (RM+TC)

Data: 2026-08-28 · Autor: Fable 5 · Status: **PLANO APROVADO pelo operador
em 2026-08-28** (plan mode). Fase B EXECUTADA e testada; fases C-G pendentes.

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
- **[ ] C — Contrato volumetria v2 + viewer/XR genéricos**: alias
  `organ_summary`/`percent_of_organ` em `dtwin/volumetry.py`; labels do
  viewer vindos do manifesto (`organ.label`) em vez de "Fígado"
  hardcoded; payloads enums. Bateria fígado deve permanecer
  byte-compatível (chaves antigas presentes e idênticas).
- **[ ] D — Candidato de cistos TC**: `ALLOWED_TASKS` +=
  `kidney_cysts`; união dos dois arquivos de saída
  (`kidney_cyst_left.nii.gz` + `kidney_cyst_right.nii.gz`) antes de
  `validate_and_store_candidate`; habilitar no perfil `rins_ct.yaml`;
  `process_organ_job` ganha a chamada de candidato (mesmo padrão do
  `_localize_candidate_ct`); teste. Fazer SÓ depois que a campanha do
  CT-03 não estiver mais usando `candidate_region.py` ao vivo.
- **[ ] E — Smoke real**: 2-3 casos de TC locais (as séries TCIA do
  CT-03 têm rins no campo de visão) fluxo completo rim: segmentação →
  volumetria por lado → 3D no viewer → cistos; 1 caso de RM real
  (CHAOS-MR, a baixar).
- **[ ] F — Validação (GATED)**: CHAOS-MR (benchmark volumétrico RM,
  razão/Dice por lado, molde do `ct01_f_volumetric`); KiTS para TC.
  Só depois `validado: true` e remoção da flag. Não bloqueia A-E.
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
