# Runtime edges verificados — snapshot 9683eaa

Gerado em 2026-08-17 por TASK-2026-08-17-PH01-CARTO-03 (PHASE_01 wave 3). Método: leitura dirigida de código com evidência `file:line`; prova ESTÁTICA de fiação (o código existe e é chamado no fluxo), não prova de execução com dados. Complementa os diagramas do `SYSTEM_MAP.md`.

## Fluxo web multifásico

| Edge (SYSTEM_MAP) | Evidência | Status |
|---|---|---|
| upload → raw_dicom_phase_resolver / multiphase_ingest | `webapp/server.py:1262-1263` (`build_multiphase_case`, `RawPhaseResolutionError`); também `:950`, `:2436` | VERIFIED |
| ingest → segmentação (subprocess) | `webapp/server.py:79,486` → `dtwin/segmentation_subprocess.py:94-95` (copia `dtwin/seg_worker.py`) e `:107` (`subprocess.run`) | VERIFIED |
| segmentação → panels → classificador | `webapp/server.py:1106-1107` (`exam_to_panels`, inferência visual); bundles em `:133,141,145` | VERIFIED |
| classificador → candidate localizer (subprocess, pós-inferência) | `webapp/server.py:80,1064` → `dtwin/candidate_subprocess.py:24-27` (copia `candidate_worker.py`, `subprocess.run`) | VERIFIED |
| shadow/union opcional | `webapp/server.py:916` (`run_phase_aware_shadow`) | VERIFIED |
| → `digital_twin finalize --no-lesion` (subprocess CLI) | `webapp/server.py:888-901` (`_build_model`: `digital_twin.py finalize <case> --profile <p> --no-lesion`) | VERIFIED |
| finalize → volumetria + malha/artefatos | `dtwin/stages.py:43,51` (imports de `viewer_artifacts` e `volumetry`) | VERIFIED |
| volumetria/malha → manifest → API allowlist/hash | `webapp/server.py:789-884` (specs com `sha256`, `_model_done` valida hash por artefato via `sha256_of`) | VERIFIED |
| API → viewer desktop | `viewer/app.js:1237-2054` (consome manifesto: presets, quality, volumetry) | VERIFIED |
| API → WebXR/Quest | `viewer/xr.js` + `webapp/static/quest/` (existência verificada na wave 1; consumo de manifesto compartilha `app.js`) | VERIFIED (parcial: sessão XR real não exercitada) |
| MedGemma via HTTP | `dtwin/medgemma_client.py:148` (`MEDGEMMA_ENDPOINT_URL`), `:838` (`urlopen`); health checks `webapp/server.py:3032,3042` | VERIFIED |

## Fluxo CLI clássico

| Edge | Evidência | Status |
|---|---|---|
| CLI `digital-twin` → Engine | `digital_twin.py:30,131-143` (`Engine(profile).prepare/finalize`) | VERIFIED |
| Engine → stages 1-7 | `dtwin/engine.py:18` (`from . import stages`) | VERIFIED |

## Constantes científicas: contrato vs código/config (leitura, sem arbitrar)

| Contrato | Valor declarado | Verificado em | Status |
|---|---|---|---|
| SCI-002 | 467 = 220+247; coortes 335/88/44 | `configs/training/hybrid_v1_protocol.lock.json:11-23` | MATCH |
| SCI-003 | outer 5 / inner 4 / seed 20260724 / inner_oof_only | `hybrid_v1_protocol.lock.json:62-74` | MATCH |
| SCI-004 | falhas contam como erro; sem exclusão da métrica primária | `hybrid_v1_protocol.lock.json:24-28`, `hybrid_v1_protocol.yaml:34-37` | MATCH |
| SCI-005 | sens/spec mínimas 0,75/0,75 | `hybrid_v1_protocol.yaml:26-27`, `lock.json:8-9` | MATCH |
| SCI-007 | positivos = hcc + positive_unspecified; sem subtipo fabricado | `configs/training/medsiglip_multiclass_v1.yaml:30-32` (+comentários 8-28) | MATCH |
| SCI-008 | labels protegidos nunca ao extrator; máscaras nunca à inferência | `hybrid_v1_protocol.yaml:39-45` | MATCH |
| SCI-009 | model/revision/448/float16/batch4/pooler/L2/float32/local_only | `configs/training/medsiglip_frozen_v1.yaml:2-11`; validações `medsiglip_embeddings.py:65-76` | MATCH |
| SCI-009 (dim 1152) | output_dimensions 1152 | `medsiglip_embeddings.py:135,154` — dimensão DERIVADA do modelo, não assertada como 1152 literal; congelada transitivamente por model+revision+manifests de cache | MATCH_TRANSITIVE (candidato a spec test na fase 04) |
| SCI-010 | totalsegmentator_mri / total_mr / liver | `profiles/figado.yaml:27-30` | MATCH |
| SCI-011 | pós-inferência, sem uso no classificador, revisão humana | `profiles/figado.yaml:64-70` | MATCH |
| SCI-012 | piso 0,50 para subtipo nomeado | `dtwin/learning/visual_inference.py:49` (`NAMED_LESION_MASS_FLOOR = 0.50`) | MATCH |
| GEO-001 | linear (intensidade) + nearest (suporte), identidade em espaço físico | `dtwin/learning/multiphase_ingest.py:206,211` | MATCH |
| GEO-002 | dice ≥ 0,80 (alinhamento manuscrito) vs cobertura ≥ 0,50 (ingest bruto) | `openswisshcc_alignment.py:432,448` (0.80); `multiphase_ingest.py:63` (0.5) e `:313-317` (abort) | VERIFIED_AS_DESCRIBED — CONFLICT do contrato permanece (dois gates distintos, sem decisão de produto); decisão humana já pendente |
| GEO-003 | qualidade = fidelidade à máscara; LPS | `profiles/figado.yaml:115-122` | MATCH |
| GEO-004 | voxels × ∏spacing / 1000 → mL; geometria divergente aborta | `dtwin/volumetry.py:161-170` | MATCH |
| DOM-001 | fração mínima 0,90 p/ isolar componente; abaixo preserva tudo | `dtwin/stages.py:158-187` | MATCH |
| SW-001 | sha256 canônico do manifest + sha256 do modelo; sem assinatura com chave | `dtwin/learning/visual_inference.py:78-84` | VERIFIED_AS_DESCRIBED — CONFLICT terminológico ("assinado") permanece p/ decisão humana |

## Unknowns / limites desta verificação

- Prova é estática: nenhum edge foi exercitado com dados reais nesta task (characterization = fases 03/05).
- Sessão WebXR/Quest real não exercitada.
- SCI-001/006/013 e DOM-002 têm natureza majoritariamente de política/manuscrito; as porções verificáveis em config foram cobertas acima (lock.json e contract json); a reconciliação 451/16 do manuscrito segue pendente de reexecução por ledger (BLOCKER conhecido).
- O valor 0,80 do dice aparece como default de parâmetro, não como constante nomeada de config — sensível a call sites.
