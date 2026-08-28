# CT01-F — Benchmark do laudo em TC (evidência)

Status: **ENCERRADO em 2026-08-28 por ordem do operador** ("nao precisa
finalizar o benchmark de volumetria") com os braços de TIPO e CHAOS
100% completos e MSD parcial (66/131 ok + 2 falhas de memória em volumes
grandes; casos restantes nunca executados — interrupção operacional, não
seleção). `research_only: true` · `clinical_use_allowed: false` · revisão
humana obrigatória sobre qualquer uso dos números.

## Resultados (ct01_laudo_metricas.json)

- **PRIMÁRIO — % acerto do TIPO: 6,2% (5/80)** — HCC 12,5% (5/40),
  CRLM 0% (0/40). Decomposição: o gargalo é DETECÇÃO (só 14/80 positivos
  de tipo receberam POSITIVA); quando o modelo detecta e nomeia, diz
  quase sempre "hcc" (5/7 no braço HCC — acertos; 5/7 no CRLM — erros;
  "metastase" nunca foi emitida). Aderência ao formato v2: 61/80 prefixo.
- Detecção geral: sensibilidade 16,2% (24/146 ok de 148 positivos),
  especificidade 60% (12/20; 5 falsos positivos + 3 INCONCLUSIVA).
  **Conclusão honesta: o laudo zero-shot portado de RM não é utilizável
  em TC** — evidência para o gate do CT-01 (flag/aviso permanecem).
- Volumetria (fase F): CHAOS razão mediana 0,9947 (IQR 0,982-1,007),
  Dice 0,9695 (mín 0,949); MSD n=66 razão 1,0208, Dice 0,9688 (mín
  0,914), sem correlação erro×carga tumoral (rho -0,14, p=0,29),
  enriquecimento de tumor no volume perdido = 1,0. **Replica localmente
  a medição do Volyrics (razão ~0,99)** — evidência da fase F pró
  `validado` do perfil CT (decisão do operador pendente).

## O que está sob teste

O braço de laudo do OREN (painéis + MedGemma 1.5 4B via gateway local,
config experimental `configs/medgemma_local_4b_ct_benchmark.yaml`) aplicado
ZERO-SHOT a TC, e a segmentação hepática do modo CT (TotalSegmentator
task=total fast=False + `dtwin.stages._refine_mask`, caminho de produção).
O classificador MedSigLIP NÃO participa (cabeça treinada/congelada sobre RM).

## Endpoints pré-registrados

Protocolo completo no docstring de
`.fable/post_audit/analysis/ct01_laudo_benchmark.py` (pré-registrado antes
de qualquer caso válido; revisão de 2026-08-27 elevou TIPO a endpoint
primário por ordem do operador; emenda v2 de 2026-08-28 documentada abaixo).

1. **PRIMÁRIO — % de acerto do TIPO** (braços TCIA, n=80): acerto =
   `resultado_hipotese == POSITIVA` E `tipo_hipotese` igual ao diagnóstico
   da coorte. Falha técnica no denominador.
2. Secundário — detecção: sensibilidade (MSD+TCIA), especificidade (CHAOS);
   INCONCLUSIVA = erro, reportada à parte.
3. Secundário — volumetria (CHAOS/MSD, que têm máscara de referência):
   razão de volume, Dice, correlação do erro com carga tumoral.

## Coortes (diagnóstico por construção; todas públicas e desidentificadas)

| braço | n | ground truth | fonte | licença |
|---|---|---|---|---|
| chaos_ct | 20 | NEGATIVA (saudáveis) | CHAOS Challenge (ISBI 2019), Train_Sets/CT | CC-BY-SA 4.0 |
| msd_task03 | 131 | POSITIVA (tumor marcado; sem tipo) | MSD Task03_Liver (AWS Open Data) | CC-BY-SA 4.0 |
| tcia_hcc | 40 | POSITIVA, tipo=hcc | TCIA **HCC-TACE-Seg** (todos HCC confirmado) | CC-BY 4.0 |
| tcia_crlm | 40 | POSITIVA, tipo=metastase | TCIA **Colorectal-Liver-Metastases** (MSKCC) | CC-BY 4.0 |

Seleção TCIA pré-registrada e cega a imagem
(`C:\datasets_ct\_tcia_selecao_40_40.json`): primeiros 40 PatientID em
ordem lexicográfica; por paciente, a série CT de maior ImageCount
(desempate por SeriesInstanceUID). Download anônimo via API NBIA v1.

Atribuições (CC-BY): HCC-TACE-Seg — Moawad et al., The Cancer Imaging
Archive, doi:10.7937/TCIA.5FNA-0924. Colorectal-Liver-Metastases — Simpson
et al., TCIA, doi:10.7937/QXK2-QG03. CHAOS — Kavur et al., Med Image Anal
2021. MSD — Antonelli et al., Nat Commun 2022.

## Limite declarado

Não existe coorte pública de TC com subtipo BENIGNO rotulado por caso: o
vocabulário benigno (hemangioma, cisto, fnh) existe no prompt para permitir
erro honesto, mas apenas hcc/metastase têm ground truth. % de acerto de
tipo é, portanto, medida sobre tipos malignos com diagnóstico de coorte.

## Emenda v2 (2026-08-28)

Com 1/80 casos do braço de tipo executados, o caso HCC_001 mostrou o 4B
emitindo tipo fora do formato ("Cisto: 1." em vez de "TIPO_HIPOTESE:
cisto."). Sem correção, o endpoint primário mediria aderência a formato,
não capacidade de tipagem. Emenda declarada ANTES do braço rodar:

- prompt passa a mostrar o formato dentro do exemplo de schema;
- parse ganha fallback (token único do vocabulário no resumo, sem acento,
  "outro" excluído por ambíguo); a via usada fica em `tipo_parse` —
  aderência ao formato é métrica secundária;
- HCC_001 anulado auditavelmente (linha `{"anulado": ...}` no JSONL) e
  reprocessado sob v2. O braço CHAOS (negativos) rodou sob v1; a diferença
  v1→v2 afeta apenas a instrução condicionada a POSITIVA.

## Artefatos

- `ct01_laudo_resultados.jsonl` — registro por caso, append-only, resumível
  (linhas `anulado` invalidam casos de forma auditável).
- `ct01_laudo_metricas.json` — agregado final
  (`.fable/post_audit/analysis/ct01_laudo_metricas.py`).
- Runner: `.fable/post_audit/analysis/ct01_laudo_benchmark.py`;
  download: `ct01_tcia_download.py` (log em
  `C:\datasets_ct\_tcia_download_log.jsonl`).
- Mudança de produção que destravou TC no gerador de painéis (modalidade
  do manifesto dirigida pela config, default RM idêntico):
  `dtwin/medgemma_panel.py` + `dtwin/medgemma_panel_multiphase.py`, pinada
  por `tests/test_medgemma_panel.py::test_manifesto_ct_rejeitado_com_config_mr_e_aceito_com_config_ct`.

## Execução do TotalSegmentator (declaração de método)

TS roda em SUBPROCESSO por caso (`ct01_ts_um_caso.py`) com os MESMOS
argumentos do stage3 de produção (task=total, fast=False, device=gpu) —
in-process, ~100 casos seguidos esgotavam o commit de memória do Windows.
Fallback declarado para volumes grandes (>250MB estouravam a RAM dos
workers nnU-Net): quando a tentativa padrão falha sem artefato, o caso é
refeito com `force_split=True` + threads mínimas (modo oficial do TS para
pouca memória; mesmo modelo/task/resolução, processamento em partes);
marcador `.ts_economico` gravado no diretório de segmentação do caso.

## Nota operacional

Dados em staging NTFS `C:\datasets_ct` (o SSD externo D:, destino final
ordenado pelo operador, desconectou em 2026-08-27); mover com robocopy
verificado e reapontar quando reconectar. PHI: nenhum dado de paciente
identificável — coortes públicas desidentificadas; manifests de caso usam
`case_id` sintético `anon-ct01f-*`.
