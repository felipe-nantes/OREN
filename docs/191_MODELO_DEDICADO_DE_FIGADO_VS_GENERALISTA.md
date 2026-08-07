# 191 — Modelo dedicado de fígado (`liver_segments_mr`) vs generalista (`total_mr`)

## Origem

docs/190 fechou a questão da fragmentação: 19/20 casos extremos já viravam
corpo único pelo caminho real de produção, e as duas tentativas de correção
adicional reprovaram nos gates. Mas ao medir os volumes, apareceu o problema
que a fragmentação escondia — **sub-segmentação**:

| | |
|---|---|
| Volume mediano (20 casos LLD selecionados) | 993 mL |
| Abaixo da faixa adulta (900–2400 mL) | 9/20 |
| Abaixo de 600 mL | 7/20 |
| Pior caso | 148 mL (12% de um fígado) |

Um fígado de 212 mL renderizado como corpo único e liso continua sendo uma
visualização ruim — só deixou de estar *visivelmente* errada.

Contra a referência humana do CHAOS (docs/176,
`experiments/total_mr_vs_chaos_v1`), o `total_mr` captura só ~84% do fígado
verdadeiro. A união de 3 fases (docs/189) compensa parte disso, mas está
compensando uma limitação do modelo, não corrigindo-a — e a 4ª fase já rendeu
só +4,5%, sinal de que essa via se esgotou.

## Hipótese

O `total_mr` é um modelo generalista de RM (50 estruturas,
`Dataset850/851/852`, 1088 sujeitos). O `liver_segments_mr` é **específico de
fígado** (`Dataset576_mri_liver_segments_120subj`), livre de licença, com
pesos já baixados localmente. A união dos seus 8 segmentos de Couinaud dá uma
máscara hepática — e a função já existia no repo desde antes
(`liver_segments_mr_union_segmenter`,
`dtwin/benchmark/lld_mmri_v23_preparation.py:338`), nunca medida.

Especialista com base pequena (120) contra generalista com base grande (1088):
podia ganhar ou perder. Por isso se mede.

## Desenho do teste — isolado da produção por construção

Exigência explícita: o teste não podia quebrar o produto atual.

- Zero modificação em `dtwin/`, `webapp/`, `profiles/`, `viewer/` — só leitura.
- Nada escrito em `casos/` (onde vivem os exames de produção).
- Saída exclusivamente em `experiments/liver_segments_mr_vs_chaos_v1/`
  (gitignorado, como todos os experimentos).
- `liver_segments_mr_union_segmenter` usado **sem modificação**.
- Subprocesso isolado com timeout de 900 s.
- Consequência: reprovando o gate, não haveria nada a reverter.

## Gate pré-especificado (escrito antes de rodar)

Baseline `total_mr` vs CHAOS, n=20: Dice mediano 0,9082 | recall mediano
0,8375 | razão de volume 0,8515.

O problema a resolver é recall (fígado faltando), então o gate exigiu ganho de
recall **sem** perder acurácia global:

| | critério |
|---|---|
| (a) | recall mediano ≥ 0,8875 (baseline +5 pontos) |
| (b) | Dice mediano ≥ 0,8982 (baseline −1 ponto de tolerância) |
| (c) | nenhum caso com Dice < 0,80 |

O critério (a) sozinho não bastaria: um modelo que vaza para o estômago também
sobe recall. (b) e (c) são a trava contra isso.

## Resultado — GATE PASSA nos três critérios

Head-to-head, mesma referência humana, mesmos 20 casos, mesma entrada
(`t1_in.nii.gz`), ambos em resolução plena:

| métrica | `total_mr` | `liver_segments_mr` | delta |
|---|---|---|---|
| Dice mediano | 0,9082 | **0,9256** | +0,0174 |
| recall mediano | 0,8375 | **0,8915** | +0,0540 |
| razão de volume mediana | 0,8515 | **0,9086** | +0,0572 |
| Dice mínimo | 0,8650 | **0,8957** | +0,0307 |

**Análise pareada — o ponto mais forte:**

| | |
|---|---|
| Dice melhorou em | **20/20 casos** (min +0,0072, max +0,0356) |
| Recall melhorou em | **20/20 casos** (min +0,0141, max +0,0643) |
| Wilcoxon pareado (Dice) | p < 0,00001 |
| Wilcoxon pareado (recall) | p < 0,00001 |

Nenhum caso piorou em nenhuma das duas métricas. Não é ganho de mediana puxado
por poucos casos — é uniforme.

A razão de volume subindo de 0,8515 para 0,9086 significa recuperar cerca de
**40% do volume que faltava**, sem perda de precisão (o Dice subiu junto).

## Ressalvas que precisam acompanhar qualquer uso deste número

1. **O CHAOS é T1 SEM contraste; a produção segmenta a fase venosa COM
   contraste.** É comparação justa entre os dois modelos sob a mesma regra,
   mas não prova que o ganho se transfere para realce dinâmico. docs/165 já
   mostrou que a fase muda o resultado. **Esta é a ressalva mais importante.**
2. n=20, um único dataset público.
3. O `liver_segments_mr` foi treinado em 120 sujeitos. Vencer aqui não garante
   generalização para a diversidade da coorte LLD.
4. Custo: ~36 s por caso, e o modelo **não aceita o modo `--fast`**
   (`python_api.py:444`) — sempre resolução plena.
5. Não diz nada sobre **vasos**: o `liver_segments_mr` só produz fígado. A
   fragmentação vascular de docs/190 continua aberta.

## Estado

Nenhuma mudança em produção. O gate passou, o que justifica um plano próprio
de adoção — não a adoção em si. O passo que falta antes de qualquer troca é
medir na fase venosa com contraste, que é o regime real de operação; sem isso,
a ressalva nº 1 permanece decisiva.

## Arquivos

- `tools/measure_liver_segments_mr_vs_chaos_reference.py` — a medição.
- `tools/liver_segments_mr_worker.py` — worker isolado.
- `experiments/liver_segments_mr_vs_chaos_v1/results.json` — resultado por caso.
- `experiments/total_mr_vs_chaos_v1/results.json` — baseline (docs/176).
