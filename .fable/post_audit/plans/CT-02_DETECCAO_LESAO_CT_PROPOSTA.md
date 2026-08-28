# CT-02 — PROPOSTA FORMAL: detecção de lesão hepática em TC no OREN

Data: 2026-08-25 · Autor: Fable 5 · Status: **PROPOSTA AGUARDANDO GATE —
nada aqui executa sem ratificação do operador** (HG-05 + HG-06/07; HG-12
nas fronteiras de claim). Pedido de origem: "benchmark de acertividade na
detecção de lesão e classificação para CT" (Felipe, 2026-08-25).

## 1. Por que isto é uma PROPOSTA e não um benchmark

O modo CT do OREN (CT-01) **não possui** detector nem classificador de
lesão — por decisão de desenho ratificada: a triagem MedSigLIP/MedGemma é
RM-only (bundles congelados; D4) e a localização de candidato foi
desabilitada em TC porque o TotalSegmentator **não tem task de tumor
hepático em CT** (D7 — o análogo CT de `liver_lesions_mr` não existe no
motor atual). Não há capacidade para medir; é preciso CRIÁ-LA primeiro —
mudança científica gated, nos termos do pack.

## 2. O que é honestamente alcançável (e o que não é)

| alvo | viável? | com quê |
|---|---|---|
| **Detecção/localização de lesão em CT** (região candidata, advisory) | SIM, com modelo novo | modelo pré-treinado em MSD Task03/LiTS (máscaras de fígado+tumor, n=131 TCs) |
| Benchmark de detecção (sensibilidade por lesão, FP/caso, Dice de tumor) | SIM | held-out do MSD + 3D-IRCADb; referência humana existente |
| **Classificação do tipo de lesão em TC** (HCC vs benignas, como na RM) | **NÃO com dados públicos disponíveis** | MSD/LiTS rotulam MÁSCARA de tumor, sem diagnóstico por lesão; não existe coorte pública de TC com subtipo confirmado equivalente à LLD/OpenSwiss | 
| Volumetria hepática CT vs referência (fase F do CT-01) | SIM, imediato | CHAOS-CT n=20 (JÁ LOCAL) + braço tumoral do MSD |

A parte "classificação" do pedido fica declarada INVIÁVEL nesta proposta —
prometê-la seria fabricar um estimando sem dado de referência. Se surgir
coorte de TC com diagnósticos, reabre-se em proposta própria.

## 3. Desenho proposto (execução SOMENTE após ratificação)

### CT-02-A — Adoção do detector candidato (HG-05)
Adotar um modelo público pré-treinado de segmentação de tumor hepático em
CT (candidatos, em ordem de preferência: bundle MONAI/nnU-Net treinado no
MSD Task03; alternativa nnU-Net LiTS). Papel no OREN: **exatamente o mesmo
contrato do `localizacao_candidata` de RM** — região candidata ADVISORY,
gerada após o fluxo, nunca alimenta classificador nenhum, revisão humana
obrigatória, `research_only`, atrás de flag própria
(`WEBAPP_CT_CANDIDATE_ENABLED`) e de `validado: false` até o CT-02-B.
Integração espelha o padrão do perfil (bloco `localizacao_candidata` do
figado_ct.yaml ganha motor/task quando o modelo for adotado).

### CT-02-B — Benchmark de detecção (o pedido original, agora executável)
Sobre held-out do MSD (casos NÃO usados em qualquer ajuste) + 3D-IRCADb:
- **Primários**: sensibilidade por lesão (critério de acerto: sobreposição
  com a máscara de referência acima de limiar pré-registrado), FP por caso.
- **Secundários**: Dice da máscara de tumor; estratos por tamanho de lesão
  (o Volyrics mediu que tumor volumoso é o regime frágil); volumetria do
  fígado nos mesmos casos (fecha a fase F tumoral do CT-01).
- Protocolo pré-registrado ANTES de rodar (endpoints, limiares, splits),
  no padrão dos contratos congelados; resultados entram como docs
  numerados + evidence.

### CT-02-C — Gate de revisão (HG-06/07)
Números apresentados ao operador; promoção do candidato a "habilitado por
padrão" só via gate; nenhuma promoção automática por números bons (mesma
regra do `validado` do CT-01).

## 4. Dados (autorizado em 2026-08-25; download público de pesquisa)

- **CHAOS-CT n=20** (fígado saudável + referência): já local
  (Downloads/CHAOS_Train_Sets.zip) → extraído para `D:\datasets_ct\CHAOS_CT`.
- **MSD Task03_Liver** (131 TCs, máscaras fígado+tumor, CC-BY-SA 4.0):
  download em curso para `D:\datasets_ct\Task03_Liver.tar` (~27 GB, fonte
  AWS Open Data do Medical Segmentation Decathlon).
- **3D-IRCADb-01** (20 TCs, 15 com tumor): requer registro no site do
  IRCAD — fica para o operador se quiser o braço de comparação direta com
  os n do Volyrics.
- Tudo é dado público desidentificado de pesquisa; fora do Git; herda a
  política de retenção classe C (evidência) do ROB-11.

## 5. O que esta proposta NÃO autoriza fazer

Rodar os classificadores de RM em TC; treinar modelo próprio; qualquer
claim de sensibilidade/especificidade clínica; promoção a CLINICO;
mexer em qualquer contrato ou artefato congelado de RM.

## 6. Decisões pedidas ao operador

1. Ratificar CT-02-A (adoção de detector pré-treinado como candidato
   advisory, atrás de flag)?
2. Ratificar o protocolo CT-02-B (com pré-registro dos endpoints antes de
   qualquer execução)?
3. Aceitar a declaração de inviabilidade da CLASSIFICAÇÃO em TC com os
   dados públicos existentes (fica fora do escopo até haver coorte)?
4. (Opcional) Autorizar também a fase F volumétrica imediata do CT-01 com
   o CHAOS-CT local — independente desta proposta e sem gate científico.
