# EVIDENCE — TASK-2026-08-24-DS-PROBE-01 (localização do sinal de domínio)

Data: 2026-08-24 · Executor: agente (Fable 5, UltraCode) · Tipo: MEDIÇÃO
(nenhuma variável do sistema alterada; outer OOF não consumido —
outer_inspection_counter permanece 0).

## Desenho executado (ajustado ao inventário real, desvio declarado)

- O plano original comparava crop/fixed_crop/enhancement/edgeonly/t2dwi —
  o inventário provou que essas variantes são **LLD-only** (probe de origem
  impossível nelas). O eixo de localização foi substituído pelo que os
  artefatos suportam: **4 famílias multi-coorte da mesma linhagem MedSigLIP**
  (stage_a global, monofase venosa, arterial, delayed; ~448-451 casos =
  321 LLD + 127-130 OpenSwiss; a stage_a cobre exatamente os 451 computáveis
  do lock).
- Condicionamento pelo LABEL verdadeiro é impossível nesta máquina
  (BLK-PROTECTED-SOURCES) e proibido pela task; fallback declarado:
  condicionamento pela PREDIÇÃO OOF congelada (proxy, sem ground truth).
- Probe: StandardScaler + LogisticRegression, StratifiedGroupKFold 5× por
  patient_group_id, seed 20260824, AUC out-of-fold agrupada; controle de
  permutação por família; 2 execuções completas com igualdade exata
  (sha256 do resultado registrado).

## OBSERVED — probe por variante de fase (probe_results_2026-08-24.json)

| Família | n | AUC origem | Controle perm. | AUC \| pred_POS | AUC \| pred_NEG |
|---|---|---|---|---|---|
| stage_a_global | 451 | **1,000** | 0,525 | 1,000 (n=215) | 1,000 (n=236) |
| monophase_venous | 451 | **1,000** | 0,531 | 1,000 | 1,000 |
| monophase_arterial | 448 | **1,000** | 0,513 | 1,000 | 1,000 |
| monophase_delayed | 448 | **1,000** | 0,495 | 1,000 | 1,000 |

Leitura: o sinal de origem SATURA em toda variante de fase, e o
condicionamento por predição não o reduz — **a pergunta "em qual fase o
sinal entra?" está respondida: em nenhuma diferencialmente; ele está a
montante da escolha de fase** (aquisição/estatística de intensidade/painel
comum a todas).

## OBSERVED — localização espectral (spectrum_results_2026-08-24.json, stage_a)

| Só top-k PCs | AUC | | Resíduo após deflacionar k direções | AUC |
|---|---|---|---|---|
| k=1 | **0,9997** | | k=1 | 0,992 |
| k=4 | 0,9999 | | k=8 | 0,954 |
| k=8 | 1,000 | | k=16 | 0,857 |
| k=64 | 1,000 | | k=32 | **0,772** |

(PCA e deflação ajustadas SÓ no treino de cada fold — sem vazamento.)

Leitura dupla e decisiva:
1. **O 1º componente principal sozinho separa as coortes (0,9997)** — origem
   é o EIXO DOMINANTE de variância da representação de produção.
2. **O sinal é difuso/redundante**: removidas 32 direções discriminantes,
   a origem ainda é lida a 0,772. Não existe "subespaço de domínio pequeno"
   para projetar fora.

## Honestidade epistêmica

- Com n=451 e d=1152 (p≫n), separabilidade linear perfeita é parcialmente
  esperada por geometria de alta dimensão; por isso as conclusões se apoiam
  nos resultados IMUNES a esse artefato: top-1 PC (1 dimensão!), a queda
  LENTA da curva de deflação e a invariância entre variantes de fase. O
  controle permutado (~0,5) descarta degenerescência da sonda.
- Números idênticos em 2 execuções (sha256
  6b56f4f0e9274a658c7d0b5ac9ed27f09021de045f9430654a19ad42b8792ea9).

## RECOMENDAÇÃO (saída da task)

1. **NÃO propor** microexperimentos de "remoção de domínio" em espaço de
   embedding (projeção/adversarial): a evidência mostra sinal dominante E
   difuso — remover 32+ direções ainda deixa 0,77 e destruiria sinal
   clínico junto. Registrar como do-not-attempt no ledger.
2. Se alguma intervenção anti-shortcut for tentada um dia, ela precisa agir
   no NÍVEL DA IMAGEM/pré-processamento (harmonização de estatística de
   intensidade), como CONTROLLED_EXPERIMENT gated com LODO como endpoint
   primário — nunca cirurgia no embedding.
3. Recalibrar o promotion gate: origin-probe AUC está saturada e NÃO
   discrimina candidatos; o endpoint discriminante real de dependência de
   domínio é LODO/transfer + por-coorte (o gate já os exige).
4. Próxima medição de maior valor no eixo: H-02 (composição das 16 falhas,
   inclui failure patterns por coorte) e H-04 (decomposição por coorte) —
   ambas baratas; H-01 está CONCLUÍDA.

## Critérios de saída

- [x] Inventário de variantes (multi vs single-coorte) registrado
- [x] Tabela comparativa determinística, 2× idêntica
- [x] Controle de degenerescência por família
- [x] Extensão espectral (concentração vs difusão) — pergunta aberta fechada
- [x] Evidence + ledger + recomendação

## CONTEXT_EFFICIENCY

- Inventário programático de 30 diretórios de embedding em 1 varredura;
  desenho ajustado ANTES de computar (evitou probe impossível nas
  variantes LLD-only).
- 2 scripts standalone versionados em post_audit/analysis/ (reutilizáveis);
  execuções em background; zero código de produção lido além do necessário.
