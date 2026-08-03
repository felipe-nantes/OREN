# O segmentador não está quebrado — o problema é a fase com contraste

**Data:** 3 de agosto de 2026
**Artefatos:** `experiments/total_mr_vs_chaos_v1/`
**Script:** `tools/measure_total_mr_vs_chaos_reference.py`
**Abre:** [docs/175](175_TESTE_FRONTEND_E_VOLUME_HEPATICO.md) §6

---

## 1. A pergunta

[docs/175](175_TESTE_FRONTEND_E_VOLUME_HEPATICO.md) mediu que 76% dos 321 casos
LLD têm fígado segmentado abaixo de 900 mL, com mediana de 637 mL. Duas
explicações cabiam, e sem referência humana as duas eram igualmente plausíveis:

1. o `total_mr` sub-segmenta;
2. esses fígados são pequenos de verdade.

**Enquanto isso não fosse decidido, tanto o piso do gate quanto qualquer conserto
da máscara seriam chute.** Ninguém calibra um limiar contra um número que não sabe
se está certo.

---

## 2. A medição

O CHAOS traz máscara hepática **anotada por humano**, já na mesma grade do
`t1_in.nii.gz` preparado — então Dice e razão de volume saem sem reamostragem,
sem interpolação para contaminar o resultado.

Mesmo `total_mr`, mesma configuração full-res do exame individual, 20 casos:

| | |
|---|---:|
| **Dice mediano** | **0,908** |
| Razão volume predito / referência | **0,85** (min 0,76, máx 0,96) |
| Casos abaixo de 70% do volume de referência | **0 / 20** |
| Erros de execução | 0 / 20 |

Volume de referência humano: mediana **1446 mL**, 19/20 dentro de 900–2400 mL.
É assim que um fígado adulto se parece.

> **O `total_mr` é um bom segmentador.** Subestima de forma consistente uns 15%,
> comportamento típico de segmentação conservadora na borda, mas Dice 0,908
> contra anotação humana não é um modelo quebrado.

**A hipótese 1 está refutada na forma geral.** O problema não é o modelo.

---

## 3. Então o que explica os 637 mL do LLD?

Se a referência do LLD fosse ~1450 mL, com o viés conservador de 0,85 medido
acima esperaríamos ~1230 mL. Medimos 637 mL — **52% disso**.

Não é campo de visão, e não é o fígado sair do quadro:

| LLD preparado, 321 casos | |
|---|---:|
| FOV em z | mediana 210 mm (p10 190, p90 216) |
| Altura do fígado segmentado | mediana **126 mm** (típico adulto: 150–180) |
| Máscaras encostando na borda em z | 27 / 321 (**8%**) |

Há espaço de sobra no volume, e a máscara quase nunca é cortada pela borda. Ela é
simplesmente **fina** — curta em z *e* estreita no plano.

### O que sobra: a fase de contraste

[docs/165](165_QUALIDADE_VISUALIZADOR_3D.md) já tinha medido isso **dentro do
mesmo exame**, o que isola a fase de qualquer diferença de coorte ou de paciente:

| Fase | Volume hepático |
|---|---:|
| Arterial | 122 mL |
| **Venosa** *(a que o pipeline usa)* | 486 mL |
| Tardia | 607 mL |
| União das três | 650 mL |

Cinco vezes de variação, no mesmo paciente, mudando só a fase.

Juntando as duas medições:

> O `total_mr` alcança Dice 0,908 contra referência humana em **T1 sem
> contraste**, e recupera cerca de metade do volume esperado na **fase venosa com
> contraste** — que é exatamente o que o pipeline alimenta.

**Ressalva honesta:** CHAOS e LLD diferem em coorte, equipamento e sequência, não
só em contraste. A comparação entre os dois não isola a fase sozinha. Quem isola é
a tabela do docs/165, medida dentro do mesmo exame. As duas evidências apontam
para o mesmo lugar, e é por isso que a conclusão se sustenta — mas ela é
**fortemente apoiada**, não provada.

---

## 4. O que isso muda

**Para a apresentação.** A limitação deixa de ser "nossa segmentação falha em 76%
dos casos" — que soa como sistema quebrado — e passa a ser:

> O segmentador é validado em Dice 0,908 contra anotação humana. Ele degrada na
> fase com contraste, que é a que o pipeline usa, e por isso o modelo 3D
> subestima o volume. A causa é conhecida, localizada e tem direção de conserto.

É a mesma limitação, medida em vez de suposta.

**Para o piso de 300 mL.** Continua sem calibração possível *nesta coorte*,
porque não há referência humana de fígado no LLD. Mas agora sabe-se contra o quê
calibrar: um `total_mr` que entrega 0,85 do volume real quando as condições são
boas.

**Para o conserto da máscara.** Ganhou direção. As opções, em ordem de custo:

1. segmentar numa série **sem contraste** do próprio exame, quando existir, e
   levar a máscara para a grade venosa por registro;
2. usar a **união de fases** — mas docs/165 mediu que ela só chega a 650 mL, a
   um custo de ~5 min por exame. Não resolve;
3. trocar por um modelo robusto a contraste, o que exige validação nova.

A opção 1 é a única com chance real, e nenhuma delas é trabalho de véspera:
trocar a máscara muda os painéis, que mudam tudo que o bundle mede.

---

## 5. O que continua valendo

As métricas de classificação **não** são invalidadas por nada disto. Treino e
medição usaram exatamente estas máscaras, de forma consistente — o sistema é
coerente consigo mesmo. O que a sub-segmentação limita é o **modelo 3D** e o
quanto os painéis representam o órgão inteiro.

`clinical_use_allowed` permanece `false`.
