# EVIDENCE — TASK-2026-08-20-PH09-HRR-01 (PHASE_09, wave 1: proposta HG-03 direction-blind)

Data: 2026-08-20 · Executor: agente · Status: **DECISÃO RECEBIDA E APLICADA**
(o documento preserva a ordem cronológica: proposta → STOP no gate → decisão
A1 aprovada → aplicação; ver seção PÓS-GATE ao final).

## Inventário verificado dos sítios (correção do handoff)

| Sítio | Estado | Evidência |
|---|---|---|
| S-A `webapp/server.py:907-908` `_mesma_geometria_sitk` + call site :986 (gate da união de fases) | **direction-blind CONFIRMADO** | compara size/spacing/origin EXATOS, ignora direction; união faz OR em array space (:989) |
| S-B `dtwin/stages.py:726-730` (defesa do stage5_refine) | **direction-blind CONFIRMADO** | mesma comparação sem direction; fail-open (usa a fonte em vez de descartar) |
| S-C `dtwin/learning/multiphase_ingest.py` | **LIMPO — não é direction-blind** | `harmonize_to_reference` (195-217) faz Resample FÍSICO sobre a grade de referência; direction é tratada pela geometria física do resample; a cobertura GEO-002 opera pós-harmonização. O handoff (LONG_PLAN P0 #1) listava o arquivo; a leitura do código o INOCENTA. |

Comparadores estritos para contraste (já corretos): `segmentation_contract.same_geometry`
e `volumetry._same_geometry` (direction com atol=1e-5); `stages.py:601/878`
(direction com atol=1e-6).

## Reprodução OBSERVED do risco

`evidence/PH09/demo_direction_blind_2026-08-20.json` (script determinístico,
grade 5×5×6, spacing 1mm, máscara de fase z-flipada com mesmos
size/spacing/origin):

- `gate_webapp_aceita_flip: true` — a máscara flipada PASSA no gate.
- União em array space: **2 voxels** (z=1 e z=4); união fisicamente correta
  (resample, a mesma técnica do ingest): **1 voxel** (só z=1). O voxel da fase
  está fisicamente em z=−4, FORA da grade venosa; o OR em array space o
  materializa em z=+4 — **1 voxel fantasma a 8 mm da posição física real**.
- `defesa_stage5_descartaria_flip: false` — o stage5 usaria a união flipada
  como fonte da malha (malha espelhada silenciosa).

Characterization (PHASE_03) que fixa o comportamento atual:
`tests/test_characterization_geometry_equality.py` — mudança exige HG-03 por
declaração explícita no próprio teste.

## Raio de impacto

- Fluxo afetado: RUNTIME do produto (webapp → união de máscaras por fase →
  stage5 → malha de visualização). NENHUM caminho científico da coorte usa
  esses comparadores (metrics/volumetry/contract têm os seus, corretos) —
  os números 467/451/16 e o lock NÃO mudam.
- Cenário real de ocorrência: aquisições MR com orientação divergente entre
  fases, arquivo de união corrompido/deslocado, ou segmentador emitindo grade
  inesperada. O caso normal (máscaras derivadas da mesma venosa) tem direction
  idêntica e não é afetado.

## Proposta por sítio (decisão HG-03, uma por sítio)

### S-A (gate da união, webapp)

- **A1 (recomendada — delta mínimo, estritamente mais fail-closed):**
  adicionar `np.allclose(a.GetDirection(), b.GetDirection(), rtol=0, atol=1e-6)`
  à conjunção existente; manter size/spacing/origin EXATOS como hoje. Nada que
  hoje é rejeitado passa a ser aceito; máscara com direction divergente cai no
  bucket existente `fases_falhas["geometria_divergente"]` (degradação graciosa
  já construída: união segue com as demais fases ou cai para venosa-apenas).
- A2: alinhar o comparador inteiro ao contract (atol=1e-5 em
  spacing/origin/direction) — também passa a ACEITAR ruído float hoje
  rejeitado; delta maior, benefício especulativo.
- C: manter como risco documentado.

### S-B (defesa do stage5)

- **A1 (recomendada):** adicionar a mesma checagem de direction (atol=1e-6,
  consistente com stages.py:601/878) à condição de descarte; união flipada →
  warning existente + fallback para a venosa (caminho já presente e testado).
- C: manter como risco documentado.

### Plano de teste (se A1 aprovada em ambos)

1. Atualizar os characterization tests para o NOVO comportamento aprovado
   (flip → False no webapp; passam a ser spec tests, citando a decisão).
2. Teste novo stage5: união z-flipada em disco → fallback para venosa +
   warning (fixture sintética, sem GPU: monta case com arquivos mínimos).
3. Sondas de mutação dirigida pós-mudança (guarda desligada → KILLED).
4. Suíte completa antes/depois.

## Classificação de evidência

- OBSERVED: demo determinística; comparadores lidos nos 3 sítios.
- SOURCE_SUPPORTED: inocentação de S-C (leitura de harmonize_to_reference);
  raio de impacto (call sites únicos verificados por grep).
- INFERRED: frequência real de direções divergentes em campo (desconhecida —
  irrelevante para a decisão: o custo do A1 é ~2 linhas por sítio).

## CONTEXT_EFFICIENCY

- Inventário fechado com 3 greps + 4 leituras simbólicas; demo de 1 script.
- Handoff corrigido (S-C inocentado) ANTES de propor mudança — evita gate
  desnecessário.

## STOP

Wave termina aqui por regra da fase. Aguardando decisão HG-03 do aprovador
(formato de HUMAN_GATES.md) para S-A e S-B.

---

## PÓS-GATE: decisão recebida e aplicada (2026-08-20)

**APROVADO A1 nos dois sítios** (Felipe Nantes, via AskUserQuestion; registro
formal em HUMAN_DECISIONS.md item 13).

### Aplicação

- `webapp/server.py::_mesma_geometria_sitk`: + direction com
  `np.allclose(rtol=0, atol=1e-6)` (comentário cita a decisão).
- `dtwin/stages.py::stage5_refine`: + mesma checagem na condição de descarte.
- Characterization → spec: `tests/test_characterization_geometry_equality.py`
  atualizado (header cita HG-03 item 13; flip agora rejeitado pelos três
  comparadores; caso novo: desvio 9e-7 aceito, 9e-6 rejeitado pelo webapp —
  o atol=1e-6 aprovado é mais estrito que o 1e-5 dos comparadores de contrato).
- Teste novo: `tests/test_gates_extra.py::
  test_refino_descarta_uniao_com_direction_divergente` — união z-flipada em
  disco → warning "geometria divergente" + refino completa na venosa.

### Verificação (OBSERVED)

- Targeted: 113 passed (characterization/spec + gates_extra + test_webapp).
- Sondas de mutação: **2/2 KILLED**
  (`evidence/PH09/mutation_probes_2026-08-20.json`) — P16 guard do server
  desligado; P17 tolerância do stage5 inflada para 1e6.
- Correção de ferramenta registrada: o critério de restauração do runner
  comparava com o blob de HEAD e dava falso alarme em working tree com
  mudanças aprovadas não commitadas; v2 compara hash dos bytes pré-sonda
  (P16 re-executado: restaurado=True).
- Suíte completa: portão em execução; resultado anexado no fechamento.

### Fechamento do portão (2026-08-20)

O primeiro run do portão acusou 3 falhas; diagnóstico com saída completa:

1. `test_engine_finalize.py::test_observed_estagio5_aceita_uniao_com_direction_divergente`
   — SEGUNDO characterization test do comportamento antigo (PHASE_03 wave 4),
   não listado no plano de atualização. Quebrou COMO DESENHADO ("se quebrar,
   pare e consulte HG-03") e foi reconciliado com a decisão: invertido para
   spec (`test_estagio5_rebaixa_uniao_com_direction_divergente_para_a_venosa`
   — o resultado agora bate com a VENOSA por volume, não com a união flipada).
2. `test_property_splits_isolation.py::...nenhum_grupo_...` — flake do
   Hypothesis sob carga da suíte completa: NÃO reproduziu em 3 reexecuções
   (isolada e 2 suítes completas). Observado uma vez; sem ação, monitorar.
3. Falha ambiental conhecida da GPU (pré-existente).

Portão final: **1769 passed / 4 skipped / 1 failed ambiental** (2m26s) —
somente a falha pré-existente. Wave 1 DONE.
