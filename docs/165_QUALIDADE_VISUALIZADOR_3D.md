# Visualizador 3D — de onde vem a "quadradice" e o que resolve

**Data:** 1 de agosto de 2026
**Escopo:** pesquisa e plano. Nada implementado ainda.

---

## 1. O que já está certo

Duas coisas que costumam ser a causa e **não são** aqui:

**O visualizador já faz *smooth shading* real.** `viewer/app.js` funde vértices
coincidentes numa geometria indexada antes de `computeVertexNormals()`. Sem isso,
o STL — que guarda normal por face, não por vértice — renderizaria facetado.
Alguém já resolveu esse problema.

**A suavização já é a correta.** `dtwin/stages.py` usa **Taubin** (windowed-sinc,
30 iterações, `pass_band=0.1`), não Laplaciano. Taubin preserva volume; o
Laplaciano encolheria o órgão a cada iteração. A literatura confirma a escolha —
o Taubin melhora a malha *preservando o volume total do órgão segmentado*.

**Resolução também não é o gargalo:**

| Malha | Vértices | Triângulos |
|---|---:|---:|
| Fígado (caso LLD) | 46.612 | 93.216 |
| Fígado (caso OpenSwiss) | 53.870 | 107.736 |

Há triângulos de sobra. Eles apenas estão traçando uma superfície em degraus.

---

## 2. A causa real, medida

O pipeline roda marching cubes **direto na grade de aquisição**, sem reamostragem
isotrópica. E a grade é fortemente anisotrópica:

| Caso | Spacing (mm) | Anisotropia Z/XY | Cortes com fígado |
|---|---|---:|---:|
| BLIND-0026 (LLD) | 0,78 × 0,78 × **3,00** | **3,84×** | **23** |
| BLIND-0003 (OpenSwiss) | 1,19 × 1,19 × **3,50** | 2,95× | 45 |

> Um fígado de ~15 cm reconstruído a partir de **23 fatias** é uma pilha de 23
> pratos. Nenhuma suavização de malha desfaz isso, porque a informação entre as
> fatias nunca existiu.

Isso é exatamente o artefato descrito na literatura: os degraus são
*limitação inerente às dimensões anisotrópicas do voxel*, e o marching cubes
segue de perto as bordas do voxel, produzindo terraços.

Segunda causa, menor: **a máscara é binária**. Marching cubes em 0/1 gera a
escada clássica de sub-voxel, porque não há gradiente para interpolar.

---

## 3. O que a literatura recomenda

| Técnica | O que resolve | Custo |
|---|---|---|
| **Interpolação antes do marching cubes** | a causa principal; reconstruir de pilha anisotrópica *sem* interpolar leva ao efeito escada, e interpolar dá reconstrução mais suave | baixo |
| **Anti-aliasing da máscara binária** (`AntiAliasBinaryImageFilter`) | a escada de sub-voxel; usa level sets e **mantém a borda a menos de 1 voxel da original** | baixo |
| **Mapa de distância com sinal** (`SignedMaurerDistanceMap`) | dá um campo contínuo para interpolar e marchar em nível 0 | baixo |
| **Suavização ciente de degraus** | identifica os degraus e suaviza **só eles**, preservando as feições reais | médio |
| **Flying Edges + MPU implicits** | híbrido: robustez do MC com rastreamento de curva implícita suave | alto |
| **Reconstrução direta por rede neural** | gera geometria suave sem passar por máscara voxelizada | muito alto |

---

## 4. Plano proposto, em ordem de retorno

### Passo 1 — Reamostragem isotrópica via campo contínuo · maior impacto

**Não** reamostrar a máscara binária com vizinho-mais-próximo: isso só cria mais
degraus. A sequência correta:

```
máscara binária (anisotrópica)
  → AntiAliasBinaryImageFilter  (vira level set contínuo, borda ≤ 1 voxel)
  → Resample para isotrópico     (interpolação linear/BSpline, ~0,8 mm)
  → marching cubes em nível 0
  → Taubin (já existe)
```

Interpolar o **level set**, e não a máscara, é o que faz a diferença: o campo
contínuo carrega a posição sub-voxel da borda, então a superfície entre duas
fatias vira uma transição suave em vez de um degrau.

Ganho esperado: elimina a maior parte dos terraços. Custo: segundos por caso.

### Passo 2 — Nível de marcha em 0, não 0,5

Com level set, o isovalor correto é **0** (a borda). Manter 0,5 depois do
anti-aliasing deslocaria a superfície para dentro do órgão.

### Passo 3 — Reavaliar a intensidade do Taubin

Hoje são 30 iterações com `pass_band=0.1`, calibradas para compensar uma entrada
em degraus. Com a entrada já suave, essa dose provavelmente **arredonda demais** e
apaga feições reais — bordas do lobo, sulcos. Provável ajuste: menos iterações ou
`pass_band` maior.

### Passo 4 — Formato, se a fluidez incomodar

STL é sopa de triângulos sem índice e sem normais: 5,4 MB para uma malha que em
**glTF com Draco** ocuparia uma fração, e já viria indexada. Só vale se o
carregamento estiver lento — não é problema de aparência.

---

## 5. O limite honesto, que precisa ser dito

Você pediu **"representação fidedigna do paciente"** e **"nada pixelizado"**. Os
dois puxam em direções opostas, e vale ser explícito sobre onde está a fronteira:

**Legítimo:** remover os degraus. O fígado real é liso; os terraços são artefato
de amostragem, não anatomia. Suavizá-los aproxima a malha da verdade.

**Não legítimo, e é onde eu pararia:** entre duas fatias separadas por 3 mm,
**qualquer** superfície é interpolação — um palpite informado, não medição. Uma
malha muito suave *parece* mais precisa do que o dado permite. Numa ferramenta que
se chama gêmeo digital cirúrgico, isso é um risco real: o cirurgião não tem como
saber, olhando, que aquela curva suave entre dois cortes foi inventada pelo
algoritmo.

**Recomendação:** aplicar os Passos 1–3, que corrigem artefato, e **registrar no
manifesto do visualizador** o spacing original e o fator de interpolação. Se o
exame tem 3,5 mm de corte, isso é uma propriedade do dado que deve viajar junto
com a malha.

Fidelidade real vem de **corte mais fino na aquisição**, não de pós-processamento.

---

## 6. Um achado colateral que afeta mais a fidelidade que qualquer render

O fígado do caso BLIND-0026 mediu **283 mL**. O projeto usa **300 mL** como piso
de plausibilidade anatômica no gate do LLD (`MINIMUM_LIVER_VOLUME_ML`, docs/158).

Esse caso passou pelo webapp, que não aplica o mesmo gate. Um fígado adulto tem
~1.500 mL — o outro caso mediu 1.508 mL. **283 mL sugere segmentação parcial**, e
nenhuma melhoria de malha corrige um órgão segmentado pela metade.

Vale investigar antes de mexer no visualizador: uma malha linda de um fígado
incompleto é pior que uma malha em degraus do fígado inteiro.

---

---

## 7. Execução — e a refutação da minha própria proposta

O plano da §4 foi testado antes de implementar. **A abordagem que propus estava
errada.**

### O que a medição mostrou

| Abordagem | Volume | Erro | Rugosidade* |
|---|---:|---:|---:|
| **A — pipeline atual** | 282 mL | **−0,2%** | 9,50 |
| **B — distância + isotrópico (minha proposta)** | 239 mL | **−15,6%** | 12,16 |
| D — B + gaussiana | 237 mL | −16,1% | **3,91** |

\* desvio-padrão do ângulo entre normais de faces vizinhas; degraus produzem
alternância 0°/90°, então valor alto = superfície em escada.

**B perde 9 a 16% do volume e nem fica mais lisa.** A interpolação linear do campo
de distância entre fatias a 3 mm cria dobras em cada plano original — mais alta
frequência, não menos. Meu raciocínio na §4 estava correto sobre a causa e errado
sobre a cura.

O que D revelou é que a suavização do campo é o que importa — rugosidade 2,4×
menor — mas ela erode a superfície de forma sistemática.

### A correção que funciona

Se a erosão é sistemática, é compensável. Em vez de fixar um deslocamento
arbitrário, o isovalor é buscado por **bisseção até a malha encerrar o volume
medido na máscara**. O critério passa a ser de fidelidade: a superfície fica tão
lisa quanto a suavização permite, mas obrigada a encerrar o volume que foi medido.

| Caso | Volume | Erro | Rugosidade (antes → depois) |
|---|---:|---:|---|
| BLIND-0026 | 283 mL | **+0,4%** | 9,50 → **4,13** |
| BLIND-0003 | 1511 mL | **+0,2%** | 6,67 → **3,29** |

**Metade da rugosidade, com fidelidade de volume igual ou melhor.**

### Custo, e como foi contido

A busca ingênua custava 6–8 s por estrutura — com uma dúzia delas, triplicaria o
tempo do exame. Duas medidas:

- **a bisseção roda numa grade 2× mais grosseira** e só a malha final na fina; o
  nível é uma distância em mm, então transfere entre resoluções;
- **decimação quadrática** com teto de 160 mil triângulos, para o STL não pesar no
  navegador.

Resultado: modelo 3D de 2,5 s para 10,0 s; exame completo de 65 s para **74 s**.

### Verificado ponta a ponta

Caso real pelo endpoint HTTP: NEGATIVA + HNF identificada, modelo 3D disponível,
74 s. Malha do fígado com 160 mil triângulos e rugosidade **4,13**. Visualmente,
os anéis concêntricos em degrau que apareciam na superfície sumiram. 1302 testes
passam.

---

## 8. O gate anatômico que faltava no webapp

Investigando o fígado de 283 mL da §6, a causa apareceu: **o webapp não aplicava
gate nenhum de plausibilidade anatômica.** `_seg_done` só checava se os arquivos
existiam.

O pipeline de pesquisa tem esse gate (`evaluate_liver_mask_quality`: volume ≥ 300
mL, extensão axial ≥ 60 mm, extensão no plano ≥ 70 mm, maior componente ≥ 90%).
Sem ele, **o webapp reportava resultados que a pesquisa contaria como falha
técnica.**

O caso media 283 mL e 69 mm de altura craniocaudal — menos da metade de um fígado
adulto — sem tocar a borda do volume, ou seja, não era corte de campo de visão e
sim sub-segmentação. Ele produziu uma classificação **correta** (POSITIVA, HCC),
mas a partir de painéis recortados de meio fígado. Acertar assim é sorte.

O mesmo gate agora roda no webapp, e o caso é recusado com mensagem explícita.

**Ressalva:** o piso de 300 mL é permissivo. Um fígado adulto tem ~1.500 mL, e um
dos casos testados passou com 511 mL. O gate pega os desastres, não as
sub-segmentações moderadas.

**Quanto é permissivo, medido depois ([docs/175](175_TESTE_FRONTEND_E_VOLUME_HEPATICO.md)):**
nos 321 casos LLD o gate reprova 17%, mas **76% ficam abaixo de 900 mL**. A
ressalva acima é maior do que parecia quando foi escrita.

---

---

## 9. Segunda rodada de apresentação, e um erro de diagnóstico meu

Depois dos prints, os ajustes seguintes:

| Item | Antes | Depois |
|---|---|---|
| Sigma do campo | 1,0 mm | **2,0 mm** — rugosidade 3,2 → 1,6, desvio da borda **inalterado** (0,71 mm) |
| Distância da câmera | 1,73× a diagonal | **1,31×** calculado pelo FOV |
| Vista inicial | `(1,1,1)` = póstero-superior-esquerda | ântero-superior direita + botões nomeados |
| Opacidade do órgão | 0,50 | **0,88** |
| Fundo | cor chapada | gradiente |

Parei o sigma em 2,0 porque acima disso o p95 do desvio passa do meio-voxel da
grade — o piso do que o exame permite saber.

**O erro:** ao subir a opacidade, o órgão ficou quase preto e passei um bom tempo
mexendo em `sheen`, `clearcoat` e `transmission`. O problema era **geometria de
iluminação**: as luzes estavam fixas em `(1, 1.2, 0.8)`, calibradas para a vista
antiga. Ao girar a vista padrão para o lado oposto, passei a mostrar o lado da
sombra. Agora o rig acompanha a câmera.

Também tentei um gradiente com esfera de céu dentro da cena; ela quebrou a
ordenação de transparência do órgão. Movido para CSS, fora da cena 3D.

---

## 10. A investigação da segmentação — onde o problema realmente está

### O que se mediu

O fígado do caso saiu com **511 mL**. Campo de visão de 380×380×198 mm, abdome
inteiro, **sem truncamento**. A vesícula saiu com **0 mL** e a veia porta com
0,5 mL — sub-segmentação severa, não corte de imagem.

Sobrepondo a máscara ao exame, o padrão fica claro: **o fígado é a grande massa
homogênea e a máscara pega bordas e ilhas, perdendo o miolo**, pior nos cortes
superior e inferior.

### O que foi descartado

| Hipótese | Teste | Resultado |
|---|---|---|
| Buracos fechados na máscara | preenchimento 3D e 2D, fechamento raio 3/5/7 | 511 → **517 mL**. Nada. O que falta não é buraco. |
| Volume 4D quebrando o modelo | `volume.nii.gz` é (512,512,76,1) | eixo singleton; o SimpleITK achata. A fase tardia é 3D e falha igual. |
| Falha sistemática do `total_mr` | volumes nos 321 casos LLD | ~~**mediana 1601 mL**, p10 419 mL. O modelo funciona na maioria; falha numa cauda de 10–15%.~~ **CORRIGIDO em [docs/175](175_TESTE_FRONTEND_E_VOLUME_HEPATICO.md): a medição estava errada.** O correto é **mediana 637 mL**, p10 164 mL, com **76% abaixo de 900 mL**. Não é cauda — é a maioria da coorte. |

### O que se confirmou

**A fase de contraste muda tudo.** Mesmo exame, mesmo modelo:

| Fase | Volume hepático |
|---|---:|
| Arterial | **122 mL** |
| Venosa *(a que o pipeline usa)* | 486 mL |
| Tardia | **607 mL** |
| União das três | **650 mL** |

Cinco vezes de variação entre fases. Mas **nenhuma chega perto dos ~1600 mL
esperados**, e a união custa duas execuções extras do TotalSegmentator (~5 min
por exame) para ainda entregar menos da metade do órgão.

### Por que não troquei a máscara

**A máscara hepática alimenta os painéis da classificação.** O bundle de produção
foi validado com painéis recortados das máscaras atuais, com todos os seus
defeitos. Trocar por uma máscara melhor é deslocamento de distribuição na entrada
do classificador — poderia degradar a acertividade que é o produto principal.

> Melhorar a máscara para o modelo 3D é seguro. Usá-la nos painéis exige
> revalidação, e essa é uma decisão de maior porte.

### O que foi feito

Faixa de plausibilidade **900–2400 mL**, com **aviso, não reprovação**:

- abaixo de 300 mL o gate anatômico reprova (implausível para adulto);
- entre 300 e 900 mL o caso passa **com aviso explícito na tela**;
- na faixa típica, o volume aparece como informação.

O aviso não vira reprovação porque **fígado pequeno existe de verdade** — cirrose
avançada, hepatectomia prévia, paciente pediátrico. Rejeitar trocaria um erro
silencioso por outro.

O ponto é que uma malha lisa e convincente de meio fígado é indistinguível, a
olho, de uma malha correta. O número precisa aparecer.

---

## 11. O que resta, em ordem

1. **Modelo de segmentação adequado a RM com contraste dinâmico.** É a causa raiz.
   O `total_mr` foi treinado sobretudo em RM sem contraste, e a variação de 5×
   entre fases mostra o quanto ele depende do realce.
2. **Se trocar a máscara, revalidar a classificação.** Não é opcional.
3. Corte mais fino na aquisição — o limite de fidelidade em Z é físico.

---

## Fontes

- [Staircase-Aware Smoothing of Medical Surface Meshes](https://www.researchgate.net/publication/220833514_Staircase-Aware_Smoothing_of_Medical_Surface_Meshes)
- [A Hybrid Method for 3D Reconstruction of MR Images](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9029689/)
- [Smooth Binary Image Before Surface Extraction — ITK](https://examples.itk.org/src/filtering/antialias/smoothbinaryimagebeforesurfaceextraction/documentation)
- [Extracting mesh from itk::AntiAliasBinaryImageFilter — ITK Discourse](https://discourse.itk.org/t/extracting-mesh-from-itk-antialiasbinaryimagefilter/574)
- [Numerical simulation of liver perfusion: from CT scans to FE model](https://arxiv.org/pdf/1412.6412)
- [MISNeR: Medical Implicit Shape Neural Representation](https://onlinelibrary.wiley.com/doi/10.1111/cgf.15222?af=R)
