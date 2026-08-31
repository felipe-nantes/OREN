# CT-03 — Método dedicado de análise de TC (meta ≥75% detecção e ≥75% tipo)

Data: 2026-08-28 · Autor: Fable 5 · Status: **PLANO APROVADO pelo operador
em 2026-08-28** (plan mode; substitui o CT-02 com premissas atualizadas).
Ordem de origem: "trabalhar em um metodo especifico para analise de CT,
tendo em vista a baixa acertividade do benchmark anterior, a meta é 75% no
minimo, tanto na deteccao de lesao quanto na definicao de tipo".

Decisões do operador (AskUserQuestion, 2026-08-28):
1. Dados de treino para o SSD D: (escrita verificada por sha256 antes).
2. Métrica de tipo CONDICIONAL: ≥75% de acerto de tipo entre os casos
   detectados, com detecção ≥75% medida à parte (duas metas de 75%).
3. Benignos exigidos → fase própria GATED por aquisição de dados (fase G).

## Premissas que mudaram desde o CT-02

- **D7 caiu**: TotalSegmentator 2.15.0 tem task `liver_lesions` de TC
  (Dataset591_ct_liver_lesions_842subj, sem licença comercial). Pesos
  baixados em 2026-08-28.
- **"Classificação de tipo inviável" caiu**: TCIA HCC-TACE-Seg (105 HCC,
  DOI 10.7937/TCIA.5FNA-0924) e Colorectal-Liver-Metastases (197
  metástase, DOI 10.7937/QXK2-QG03) dão diagnóstico por construção de
  coorte, CC-BY 4.0, download anônimo.
- CT01-F mediu o zero-shot: sens 16,2%, tipo 6,2% — motivação direta.

## Desenho (resumo; plano completo aprovado no plan file da sessão)

- Detecção: TS `liver_lesions` como candidato advisory (contrato de
  candidato de RM reutilizado; task na solicitação com allowlist
  fail-closed). Decisão de caso = volume total ≥ limiar pré-registrado
  (tunado SÓ no treino).
- Tipo: cortes axiais do fígado → embeddings MedSigLIP congelados → head
  logístico [hcc, metastase] (infra `medsiglip_multiclass_classifier` +
  `train_production_bundle`), % por classe no payload.
- Teste congelado: 40+40 TCIA (seleção pré-registrada do CT01-F) + CHAOS
  20 negativos; MSD 131 = secundário com contaminação do Dataset591
  declarada. Treino: 65 HCC + 157 CRLM restantes (D:).
- Gate: `external_bundle_evaluation.passed_75_75` + tipo condicional.
- Integração gated: `WEBAPP_CT_CANDIDATE_ENABLED` (default 0) e bundle de
  tipo via env; `validado` do perfil só muda por gate do operador.

## Fase G — benignos (gated por dados)

Sem coorte pública de TC com benignos confirmados. Caminhos: 3D-IRCADb-01
(patologia por paciente; REQUER registro do operador no site do IRCAD),
varredura TCIA/Zenodo. Interim: heurística declarada de cisto simples por
densidade HU (advisory "regra, não modelo"; fora da meta de 75%). Classe
benigna só entra no vocabulário MEDIDO com coorte rotulada.

## Gates do pack

HG-05 (adoção Dataset591 + head novo — ratificados pela aprovação do
plano), HG-06 (labels por coorte com DOI), HG-07 (splits/CV congelados),
HG-08 (thresholds antes do teste), HG-12 (claims só com números medidos).
`research_only: true` em tudo; meta 75% é GATE, não promessa — números
saem honestos com iteração declarada se não alcançada.

## Execução (iniciada 2026-08-28)

- [x] A.1 D: reconectado; escrita 150MB verificada por sha256
- [x] A.3 Pesos Dataset591 baixados
- [x] A.2 Download de treino disparado (222 séries → D:\datasets_ct\*_TRAIN;
      seleção pré-registrada em C:\datasets_ct\_ct03_selecao_treino.json)
- [x] B.1-2 candidate_region task-por-solicitação + allowlist; perfil CT
      com localizacao_candidata habilitada (motor_task liver_lesions)
- [x] B.3 process_ct_job com _localize_candidate_ct (sem gate de predição,
      decisão declarada) atrás de WEBAPP_CT_CANDIDATE_ENABLED; timeout
      próprio WEBAPP_CT_CANDIDATE_TIMEOUT=300
- [x] B.4 Testes (24 passed em test_ct_ingestion + guard)
- [x] B smoke em 2 casos HCC reais (VERDE: candidatos com componentes e
      volumes, ~2,6 min/caso pelo caminho de produção)
- [~] C benchmark de detecção RODANDO (chaos → train → teste → msd + 2
      varreduras; JSONL em evidence/CT03/; work preservado em
      D:\datasets_ct\_ct03_work)
- [~] D pipeline de tipo:
      - [x] D.1 labels protegidos por coorte: 222 treino + 80 teste
            congelado (casos/qualification/ct03_v1/; proveniência DOI)
      - [x] D.3 protocolo CONGELADO antes de extração supervisionada:
            ct03_ct_type_protocol_v1.lock.json + splits aninhados 5x4
            por paciente, seed 20260828, assinatura b1c2f21c...
      - [x] D.5-config medsiglip_ct_axial_type_v1.yaml validada pelo
            load_multiclass_config (cenário ct_medsiglip_type)
      - [ ] D.2 slices (ct03_build_slices.py pronto; GATED pelas
            máscaras da campanha C — dataset imutável, roda 1x com os
            222 completos)
      - [ ] D.4 embeddings (GPU livre exigida: parar gateway MedGemma)
      - [ ] D.5 OOF + train_production_bundle
- [ ] E avaliação congelada gate 75/75
- [ ] F integração UI com % por classe
- [ ] G benignos (gated)
