# 194 — MRSegmentator sobrevive ao clamp 0–255 e bate o total_mr (teste isolado)

## Origem

docs/193 reprovou o `liver_segments_mr`: apesar de vencer no CHAOS (docs/191),
ele **colapsa na preparação 0–255 do LLD** (máscara vazia). O `total_mr`
tolera o clamp mas sub-segmenta (docs/190: 7/20 fígados < 600 mL). A pergunta:
existe um modelo que **sobreviva ao clamp E segmente melhor**?

Candidato: MRSegmentator (Apache 2.0), apontado como o mais generalizável entre
os modelos de RM abdominal, segmenta 40+ estruturas incluindo fígado e vasos.

## Isolamento — não tocou a produção

Lição aprendida da forma difícil: `pip install mrsegmentator` no venv de
produção (`.venv-win`) **sobrescreveu o torch CUDA por uma build CPU** e
rebaixou o nnunetv2 — exatamente o que o `run_win.ps1` avisa. Foi **restaurado**
(torch 2.6.0+cu124, CUDA verificada com operação real na RTX 4060) e o
MRSegmentator foi reinstalado num venv **separado** (`.venv-mrseg`, gitignorado).
Todo o teste roda por lá; a produção seguiu intacta.

## Resultado

### 1. Robustez — sobrevive ao clamp que zerou o `liver_segments_mr`

Fase venosa do LLD (dado de produção, 0–255):

| caso | `total_mr` | `liver_segments_mr` | **MRSegmentator** |
|---|---|---|---|
| 0164881a | 630 mL | 0 mL | **746 mL** |
| 08c7d7e1 | 892 mL | 0 mL | **922 mL** |
| 0c4a7eb1 | **303 mL** | 0 mL | **832 mL** |

Não-vazio nos três, volumes plausíveis. O caso `0c4a7eb1` é notável: o
`total_mr` deu 303 mL (sub-segmentação severa, muito abaixo da faixa adulta),
e o MRSegmentator deu 832 mL — o tipo de caso que docs/190 identificou como o
problema real. Sugestivo de conserto, **não provado** (não há ground truth de
fígado no LLD).

### 2. Acurácia — bate o `total_mr` contra referência humana (CHAOS, n=6)

| caso | Dice | recall |
|---|---|---|
| 0a0f9ffa | 0,9241 | 0,8871 |
| 1d9c2bc7 | 0,9218 | 0,9727 |
| 1da249d0 | 0,9378 | 0,9460 |
| 2cc698a4 | 0,9196 | 0,8674 |
| 2daae03d | 0,9247 | 0,8701 |
| 2ef34906 | 0,9048 | 0,9018 |

| modelo | Dice mediano CHAOS |
|---|---|
| `total_mr` (produção) | 0,9082 |
| **MRSegmentator** | **0,9229** |
| `liver_segments_mr` | 0,9256 (mas colapsa no LLD) |

MRSegmentator supera o `total_mr` (+0,0147) e fica quase empatado com o
`liver_segments_mr` — **com a diferença decisiva de que funciona no dado de
produção**. Consistente: todos os 6 casos entre 0,90–0,94, sem colapso.

### 3. Bônus — segmenta vasos na mesma passada

Fígado (label 5) + aorta (13), veia cava inferior (14), veia porta/esplênica
(15), entre 40+ estruturas. Cobriria fígado **e** vasos de uma vez — a
fragmentação vascular de docs/190 ficou sem solução até aqui.

## Erros corrigidos no caminho (registro honesto)

O primeiro lote reportou 746/746/746 mL idêntico e Dice mediano 0,76: bug meu
— os inputs se chamam todos `t1_venous.nii.gz`/`t1_in.nii.gz` e escreveram no
mesmo arquivo de saída, então os casos 2+ liam o cache do caso 1. Corrigido com
diretório por caso; a tabela acima é do lote corrigido. O Dice também exigiu
reamostrar a predição para a grade da referência (o MRSegmentator devolve numa
grade própria).

## Ressalvas

1. CHAOS é T1 **sem** contraste (a ressalva de sempre). Mas, ao contrário do
   `liver_segments_mr`, o MRSegmentator **também** produziu resultado plausível
   na venosa **com** contraste do LLD — a preocupação de transferência é bem
   mais fraca aqui.
2. n=6 no CHAOS, 3 no LLD. Sinal forte e consistente, mas amostra pequena.
3. Sem ground truth de fígado no LLD, não dá para afirmar que 746/922/832 são
   **mais corretos** que os do `total_mr` — só que são plausíveis e não-vazios.
4. Rodou em CPU (~7 min/caso). Em produção precisaria de GPU no venv isolado.

## Veredito

Diferente do `liver_segments_mr`, o MRSegmentator **passa no teste que
importa**: sobrevive ao clamp 0–255 da produção, bate o `total_mr` na única
âncora de acurácia com referência humana, aparenta corrigir sub-segmentação
severa, e entrega vasos de brinde. **Justifica um plano de adoção próprio** —
não a adoção em si. O que falta antes de trocar: CHAOS completo (n=20) para o
Dice mediano firme, e idealmente uma âncora de acurácia no próprio LLD (resolver
o desalinhamento z das máscaras de lesão de docs/193).

## Estado

Produção inalterada e verificada (torch 2.6.0+cu124, CUDA OK). Teste 100%
isolado em `.venv-mrseg` (gitignorado) e `experiments/mrsegmentator_lld_test/`.

## Arquivos

- `tools/test_mrsegmentator_isolated.py` — o teste (usa só `.venv-mrseg`).
- `experiments/mrsegmentator_lld_test/results.json` — números por caso.
