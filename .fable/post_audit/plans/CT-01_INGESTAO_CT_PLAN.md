# CT-01 — Plano: ingestão de TC no fluxo completo do OREN

Data: 2026-08-25 · Autor: Fable 5 · Insumo: `OREN_CT_INGESTAO_ESPECIFICACAO.md`
(extração unilateral do Volyrics, docs/249-250 daquele repo) · Status: PLANO
— nada implementado; execução aguarda autorização (HG-01 de escopo).

## 0. Premissas da spec VERIFICADAS no lado ARGOS (OBSERVED)

A spec foi escrita sem abrir o ARGOS e pede que se verifique se o motor é
agnóstico. Verificado — **a arquitetura é a mesma** (ancestral comum):

| premissa Volyrics | lado ARGOS | veredito |
|---|---|---|
| stage1 valida contra `profile["modalidade"]` | `dtwin/stages.py:375-379` idêntico em espírito | ✅ |
| task do TotalSegmentator vem do YAML | `stage3`: `seg.get("motor_task", "total_mr")` direto p/ API | ✅ |
| Couinaud idem | `tarefas[].motor_task` lido do perfil | ✅ |
| gate de modalidade do webapp | `_expected_modalities()` JÁ deriva do perfil ativo (fallback {MR,MRI}) | ✅ |
| **único acoplamento real** | `webapp/server.py:63` — `PROFILE = "profiles/figado.yaml"` é SINGLETON: um perfil para o processo inteiro | ⚠️ é AQUI que mora o trabalho |

Diferenças estruturais relevantes vs Volyrics:
- **ARGOS tem triagem visual no fluxo completo** (MedSigLIP/MedGemma,
  treinados e CONGELADOS sobre RM — contratos científicos). Volyrics não tem
  essa camada. Esta é a fronteira de governança do porte.
- ARGOS **não tem** `_known_method_bias_note` (nem a de RM); o equivalente
  funcional é a família `_aviso_volume_figado` no webapp (e o W-038 já
  registra que a faixa 900–2400 mL de RM carece de fonte).
- Perfil único `profiles/figado.yaml` (não há par `figado_mr`/`figado_ct`).

## 1. Decisões de desenho (D1–D8)

- **D1 — Perfil novo `profiles/figado_ct.yaml`; `figado.yaml` INTOCADO.**
  Campos por diferença (§2 da spec): `modalidade: [CT]`;
  `segmentacao_orgao.motor_task: total`; Couinaud `liver_segments`;
  `segmentacao_lesao/candidata: DESABILITADA` (D7). Bloco `mesh:` copiado
  de RM com comentário "não recalibrado para espaçamento de TC" (herdando a
  honestidade da spec). Campo `validado: false` até validação local (D8).
- **D2 — Seleção de perfil POR JOB no webapp** (padrão `MODALITY_PROFILES`
  da spec §7, adaptado): dicionário `{"MR": figado.yaml, "CT": figado_ct.yaml}`
  + detecção da modalidade do upload (a infra `_modality_of` já existe) +
  perfil escolhido viaja NO JOB (estado), nunca em global mutável. Regras
  R1/R2 do REF-03 valem: config nova no server.py, módulos extraídos leem
  via `server.<nome>`; `PROFILE` legado vira o default MR (compat total —
  nenhum patch-point quebra).
- **D3 — CT entra EXCLUSIVAMENTE pela série única** (`find_best_series`),
  como na spec §3: o caminho multifásico/resolver é MR-only por validação e
  permanece assim. O roteamento do worker pula a tentativa multifásica
  quando o perfil do job é CT.
- **D4 — TRIAGEM VISUAL FICA FORA DO FLUXO CT.** Os bundles congelados são
  RM; rodá-los em TC seria claim sem lastro (HG-12 se virasse resultado).
  Cenário novo `ct_volumetric`: ingest → segmentação (`total`) → refino →
  malha → volumetria → viewer 3D → revisão/aprovação humana → XR. O payload
  de resultado declara EXPLICITAMENTE `screening_available: false` com
  motivo ("triagem visual validada apenas para RM") — ausência honesta, não
  omissão silenciosa.
- **D5 — Nota de viés de TC como AVISO CONSULTIVO no webapp** (camada
  `_aviso_volume_figado`), não em stages.py (que segue intocado — W-002 é
  gated e este plano não o abre). Números da spec §4 citados COM PROVENIÊNCIA
  EXPLÍCITA: "medição Volyrics (docs/249-250 daquele repo, n=40, razão
  mediana 0,99, rho 0,035) — NÃO replicada neste repositório".
  `correcao_aplicada: False` sempre; o volume publicado é o da máscara
  aprovada (princípio da spec, idêntico ao nosso).
- **D6 — Couinaud em TC habilitado com `require_complete: true`**: o
  fail-closed existente já descarta partições incompletas (a lacuna §6 da
  spec — `couinaud_masks_not_available` observado em caso real — degrada
  para "sem Couinaud", nunca para Couinaud errado). Amostra de validação
  local recomendada antes de confiar (fase CT-05).
- **D7 — Localização de candidato/lesão DESABILITADA em TC** (spec §6: nome
  da task não confirmado; recusa deliberada de adivinhar). O perfil CT nem
  declara o bloco; o fluxo tolera ausência (já tolera hoje).
- **D8 — `validado`/regulatório como flags INDEPENDENTES** (spec §5):
  `estado_regulatorio: PESQUISA` sempre (ARGOS é research_only por
  contrato); `validado: false` até benchmark volumétrico LOCAL (os números
  da spec são do Volyrics — evidência emprestada orienta, não valida). Com
  `validado: false`, CT roda apenas com flag de operador
  (`WEBAPP_CT_ENABLED=1`), não por padrão.

## 2. Fases de implementação

### CT-01-A — Perfil (LOW, additive)
`profiles/figado_ct.yaml` novo. Nenhum consumidor muda. Parse coberto por
teste (o perfil carrega, campos obrigatórios presentes, modalidade=[CT]).

### CT-01-B — Plumbing de perfil por job no webapp (MEDIUM)
- `MODALITY_PROFILES` + `_profile_path_for(modality)` no server.py (R1).
- `/api/analyze`: detecção de modalidade do upload → escolhe perfil → grava
  no job; uploads mistos CT+MR seguem a regra atual (`_modality_ok` filtra
  pela modalidade escolhida).
- `_expected_modalities()` ganha variante por-job (a global permanece como
  default MR — patch-points intactos).
- Guard de inventário: rotas INALTERADAS (mesma `/api/analyze`); novos
  símbolos entram no contrato da façade se algum teste/tool os patchar.

### CT-01-C — Cenário `ct_volumetric` no worker (MEDIUM-HIGH)
- Roteamento em `process_visual_job`/`process_job` (webapp/jobs.py): perfil
  CT ⇒ pula multifásico (D3) e pula triagem (D4); executa prepare+finalize
  com o perfil do job; resultado com `screening_available: false`,
  volumetria, viewer_url, aviso D5, `requires_human_review: true`.
- Timeouts: reusar os existentes; TC costuma ser mais rápida que RM na
  segmentação — sem mudança até medição dizer o contrário.

### CT-01-D — Aviso de volumetria CT (LOW)
Função nova ao lado de `_aviso_volume_figado` com o texto D5. A faixa
técnica 900–2400 mL de RM NÃO é reaproveitada para TC (W-038 já mostra que
faixa sem fonte é dívida; não criar outra).

### CT-01-E — Testes e portões (MEDIUM)
- Unit: perfil CT parseia; `_profile_path_for` mapeia MR/CT e rejeita
  desconhecida; gate de modalidade por job; cenário CT não invoca screening
  (monkeypatch em `server.process_*` prova o não-roteamento); aviso D5
  presente e `correcao_aplicada` ausente/False.
- Characterization: job CT sintético (DICOM CT mínimo gerado em teste, como
  os fixtures MR existentes) percorre ingest→…→volumetria com segmentação
  mockada — prova o encanamento sem GPU/modelo.
- Regressão MR: bateria webapp completa + suíte (baseline 1809/4/0) — o
  fluxo MR deve ficar BYTE-IDÊNTICO (nenhum artefato/contrato MR muda).
- Guards existentes (rotas, configs pinados, tools) verdes.

### CT-01-F — Validação local (GATED, fase separada; não bloqueia A–E)
Benchmark volumétrico de TC no ARGOS (equivalente local do docs/249-250)
exige datasets CT (CHAOS-CT/3D-IRCADb — presença local a confirmar; há
candidatos no D:). Só depois dela `validado: true`. Amostra Couinaud-CT
(D6) entra aqui. **Sem esta fase, CT permanece atrás da flag de operador.**

## 3. Gates e fronteiras (explícito)

- **HG-01**: aprovação deste plano (escopo/decisões D1–D8) antes de codar.
- **Nenhum contrato científico MR é tocado**: perfil MR, bundles, thresholds,
  folds, denominadores, resolver multifásico — todos intocados; a suíte e os
  guards são o oráculo disso.
- **HG-05 não dispara**: o backend de segmentação MR não muda; CT usa task
  nativa do MESMO motor via perfil novo (additive).
- **HG-12 (claims clínicos)**: D4+D8 mantêm TC como pesquisa sem triagem;
  qualquer texto de UI novo repete research_only/revisão humana.
- **O que este plano NÃO faz**: multifásico CT; correção automática de
  volume; task de lesão CT; promoção a CLINICO; recalibração de mesh
  (registrada como follow-up com o mesmo texto honesto da spec).

## 4. Riscos principais

| risco | mitigação |
|---|---|
| CT vazar para a triagem MR por um caminho não mapeado | teste negativo dedicado (CT job ⇒ zero chamadas aos process_* de screening) + `screening_available:false` no payload |
| regressão sutil no fluxo MR via plumbing de perfil | default = comportamento atual; perfil por job só diverge quando modalidade=CT; bateria MR completa como portão |
| Couinaud CT incompleto em uso real (observado no Volyrics) | require_complete já degrada fail-closed; amostra na CT-01-F |
| números do Volyrics citados como se fossem nossos | proveniência explícita no aviso + `validado:false` até CT-01-F |

## 5. Estimativa e ordem

A→B→C→D→E em sequência (E portão de cada uma acumulado), ~1 sessão de
execução disciplinada; F separada e gated pela disponibilidade de dados CT
locais + sua autorização.
