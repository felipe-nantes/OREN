# Teste pelo frontend, e a correção de um número que estava errado

**Data:** 3 de agosto de 2026
**Como foi feito:** os arquivos DICOM foram injetados no `startAnalysis` da própria
página — a mesma função que o seletor de pasta chama. É o caminho real do
frontend, não a API por fora.
**Casos:** benchmark cego interno `ARGOS_INTERNAL_BLIND_BENCHMARK_120_V1`.

---

## 1. Os três casos

| Caso | Referência | Resultado | Subtipo | Tempo |
|---|---|---|---|---:|
| `ARGOS-BLIND-0046` | HCC | **POSITIVA** (0,633 / limiar 0,475) | **HCC** — correto | 114 s |
| `ARGOS-BLIND-0048` | hemangioma | **NEGATIVA** (0,104) | **hemangioma** — correto | 127 s |
| `ARGOS-BLIND-0026` | HCC | **recusado pelo gate anatômico** | — | 51 s |

Nos dois que concluíram o pipeline acertou tudo: a decisão binária, o subtipo, e
o `subtype_is_screening_target` (verdadeiro só no HCC). A massa nas classes
nomeadas foi 99,5% e 96,5%, muito acima do piso de 50%.

Também funcionaram: resolução das três fases dinâmicas a partir de DICOM bruto
(`t1_arterial`/`t1_venous`/`t1_delayed`, por metadados explícitos), o
visualizador 3D, a localização candidata pós-inferência (`pending_human_review`)
e o cartão gracioso no caso recusado — sem nenhum achado fabricado.

**O aviso de volume disparou sozinho** no caso 0046: fígado segmentado de 485 mL
contra a faixa típica de 900–2400 mL. O sistema avisou contra o próprio
resultado, que é o comportamento desejado.

---

## 2. O gate está em um caminho só

`_mask_quality` é chamado em `webapp/server.py:736`, dentro de
`process_visual_job` — **o caminho individual**. O caminho de benchmark não o
aplica.

Consequência, verificada com os mesmos 8 arquivos do mesmo exame:

> `ARGOS-BLIND-0026` é **recusado** ao ser enviado pela página de exame
> individual e é **aceito e contado como acerto** ao ser enviado pela página de
> benchmark.

Aplicando o gate do caminho individual às 25 máscaras que o benchmark do
[docs/171](171_RESULTADO_BENCHMARK_FRONTEND_PATOLOGIA_VARIACAO.md) guardou:

| | |
|---|---:|
| Reprovados pelo gate | **2 / 25 (8%)** |
| Quais | `ARGOS-BLIND-0077` (204 mL) e `ARGOS-BLIND-0026` (283 mL) |
| Ambos são | **HCC — 2 dos 5 positivos da coorte** |

A sensibilidade de 100% do docs/171 foi medida sobre 5 positivos, dois dos quais
o sistema no ar teria recusado.

---

## 3. O docs/171 é integralmente in-sample — agora provado

O veredito exibido para esses casos é `unknown`, e isso está **correto**: o
identificador cego (`ARGOS-BLIND-…`) vem de um namespace que não é comparável ao
do treino (`anon-…`), e `in_sample_status` se recusa a chamar de
`out_of_sample` o que apenas não conseguiu comparar.

Resolvendo a proveniência pelo `original_case_id` do CSV privado e comparando
contra o manifesto do próprio bundle:

> **25 / 25 `in_sample`.**

Os 100% binários e os 96,43% de subtipo do docs/171 são inteiramente sobre casos
que o modelo viu no treino. O documento já sinalizava isso; agora está
verificado contra o artefato, não afirmado.

---

## 4. Correção: o volume hepático do docs/165 estava errado

[docs/165](165_QUALIDADE_VISUALIZADOR_3D.md) registrou "mediana 1601 mL, p10 419
mL" nos 321 casos LLD, e concluiu que a segmentação "falha numa cauda de 10–15%".
**Esse número não se reproduz.**

Medido sobre `liver_mask_venous.nii.gz`, nos três conjuntos preparados, com
resultado idêntico nos três:

| | docs/165 | **medido** |
|---|---:|---:|
| p10 | 419 mL | **164 mL** |
| **mediana** | **1601 mL** | **637 mL** |
| p90 | — | 1126 mL |

| Faixa | Casos |
|---|---:|
| Abaixo de 300 mL — reprovaria no gate | 56 / 321 (**17%**) |
| Abaixo de 900 mL — piso adulto do próprio webapp | 244 / 321 (**76%**) |
| Dentro de 900–2400 mL | 77 / 321 (24%) |

**Não é uma cauda de 10–15%. Em três quartos da coorte principal o volume
segmentado fica abaixo do piso que o próprio sistema usa para avisar.**

Isso não invalida as métricas de classificação — elas foram treinadas e medidas
sobre exatamente estas máscaras, de forma consistente. O que muda é o tamanho da
ressalva sobre o modelo 3D e sobre o quanto os painéis representam o órgão
inteiro.

### Uma hipótese que foi testada e refutada

Suspeitei que o caminho de DICOM bruto segmentasse pior que o preparado, o que
seria um descasamento treino/produção. Comparação pareada, mesmos 25 pacientes
nos dois caminhos:

| | |
|---|---:|
| Mediana, caminho bruto | 552 mL |
| Mediana, caminho preparado | 637 mL |
| **Razão mediana bruto/preparado** | **0,97** |

**Os dois caminhos são equivalentes. Não há descasamento.** O volume baixo é
propriedade da segmentação nesta coorte, não da ingestão nova.

### Não é corte de campo de visão

Nos 25 casos o FOV mediano em z é 210 mm — sobra para um fígado — e apenas 2/25
máscaras encostam na borda do volume. Nos piores casos o fígado segmentado ocupa
66–69 mm em z, contra 165–183 mm nos melhores. É sub-segmentação real.

---

## 5. O que isso muda para a apresentação

1. Dos três números de subtipo, o de 96,43% agora tem **duas** razões
   documentadas para não ser citado como desempenho: é in-sample (25/25,
   provado) e foi medido sem o gate que está no ar (2/25 seriam recusados).
2. A ressalva de segmentação sobe de "cauda de 10–15%" para **76% abaixo do piso
   adulto**. É melhor dizer isso antes de perguntarem.
3. O pipeline ponta a ponta funciona e acerta nos casos que conclui — incluindo
   nomear a variação e avisar contra si mesmo quando a máscara é pequena.

## 6. Pendências que este teste abre

- ~~**Unificar o gate** entre o caminho individual e o de benchmark.~~
  **FEITO — ver §7.**
- **Revisar o piso de 300 mL.** Ele reprova 17% quando 76% estão abaixo da faixa
  adulta: pega desastres, não sub-segmentação moderada.
- **Investigar a sub-segmentação do `total_mr` nesta coorte.** Trocar a máscara
  invalidaria as métricas congeladas (os painéis saem dela), então isso é
  trabalho planejado, não conserto de véspera.

---

## 7. Correção aplicada: o gate agora é um ponto único

`_segmentar_figado_com_gate` passa a ser a **única** forma de obter uma máscara
hepática nos dois fluxos visuais. `process_visual_job` e
`_run_visual_benchmark_case` chamam essa função; nenhum dos dois chama `_segment`
direto.

Falhar ali é o comportamento correto, não efeito colateral: os painéis são
recortados da máscara, então classificar sobre meio fígado é acertar por sorte.
No benchmark a exceção vira falha técnica, que a política de métricas já conta
como erro.

### Verificação ponta a ponta, pela página de benchmark

Os dois casos HCC, enviados pelo botão real da página:

| Caso | Antes | Depois |
|---|---|---|
| `ARGOS-BLIND-0026` | `decisive`, contado como **acerto** | **`failed`** — "a segmentação do fígado não ficou anatomicamente plausível" |
| `ARGOS-BLIND-0046` | `decisive` | `decisive`, POSITIVA, agora com `liver_mask_quality` registrado (484,8 mL) |

A sensibilidade desse lote de dois caiu de 1,00 para **0,50**, porque a falha
técnica passou a contar como erro. **Essa queda é o conserto, não uma
regressão:** o número antigo vinha de aceitar um exame que a página individual
recusava.

Efeito colateral útil: o benchmark passa a gravar `liver_mask_quality` por caso,
então o volume segmentado fica auditável em cada linha do relatório.

### Testes

Três testes novos em `tests/test_webapp.py` (1349 → **1352**, todos passando):

- o gate recusa máscara implausível e a mensagem chega ao usuário;
- o gate devolve a qualidade quando aprova, para alimentar o aviso de volume;
- **teste de regressão estrutural**: falha se qualquer um dos dois fluxos visuais
  voltar a chamar `_segment` direto, contornando o ponto único. É o que impede a
  divergência de voltar sem ninguém perceber.
