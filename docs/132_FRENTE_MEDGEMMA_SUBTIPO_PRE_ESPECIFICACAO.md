# MedGemma zero-shot para subtipo (pré-especificação)

**Data:** 29 de julho de 2026
**Status ao escrever:** nenhum resultado calculado.
**Antecedentes:** [docs/129](129_FASE1_SUBTIPO_RESULTADO.md) (supervisão 52,18%) e
[docs/131](131_FRENTE1_RESULTADO.md) (zero-shot MedSigLIP 27,55%; sonda de domínio
reprova embeddings a 100,00% e radiomics a 98,75%).

---

## 1. Por que este caminho

Duas tentativas de encontrar a representação certa falharam, e a correção que eu havia
proposto — normalização por referência interna — **já estava implementada** no radiomics
([radiomics_features.py:218](../dtwin/learning/radiomics_features.py): cada fase é
normalizada pela mediana e escala robustas do próprio fígado) e mesmo assim a coorte
continua previsível a 98,75%. O que sobrevive à normalização é textura, ruído e resolução:
descritores do *scanner*, não da lesão.

Isso expõe um problema estrutural: **qualquer coisa treinada nas nossas duas coortes pode
aprender a coorte.** O MedGemma contorna isso por construção, não por engenharia — não há
treino nos nossos rótulos, logo não há mapeamento aprendido das nossas coortes e a sonda de
domínio deixa de ser a questão.

A falha do MedSigLIP não prevê a dele: similaridade de cosseno entre um painel e uma frase
é um mecanismo muito mais fraco do que um modelo generativo olhando as fases e raciocinando
sobre a diferença entre elas.

---

## 2. O que será usado, e o que não será tocado

**Não será tocado:** o gateway `/score-volume` é deliberadamente travado — o
`response_prefix` é `Literal` e o cliente não pode fornecer classes arbitrárias. Essa
proteção existe para impedir afirmação clínica arbitrária em produção e **permanece
intacta**. Este experimento carrega o modelo diretamente, no mesmo padrão já usado para o
MedSigLIP nas qualificações anteriores.

**Entrada:** os **3 painéis já renderizados** de cada caso
(`external_liver_enriched_full321_v3`), sem re-renderizar nada. Eles são
`multiphase_rgb_fusion` com mapa de canais `{red: arterial, green: portal venous,
blue: delayed}`, registrado no manifesto de cada caso.

Isso é deliberado: **a cor É a dinâmica de realce.** Uma lesão vermelha e escura no azul
é hiper-realce arterial com washout. Uma lesão escura nos três canais não realça. O prompt
informa o mapa de canais explicitamente — é informação de renderização, não de rótulo.

**Escopo:** os 321 casos LLD com subtipo, mesmo recorte dos experimentos anteriores, para
comparabilidade direta.

Nenhum rótulo entra no prompt. Nenhuma máscara de lesão é usada. O gateway será desligado
durante a execução para liberar VRAM.

---

## 3. Prompt pré-registrado

Fixado agora para não poder ser ajustado depois de ver o resultado. Não menciona
prevalência, não sugere resposta e oferece saída explícita de incerteza:

```
Você está analisando montagens de RM abdominal multifásica em modo de pesquisa.

Cada imagem é uma fusão RGB de três fases temporais do mesmo corte:
- canal VERMELHO = fase arterial
- canal VERDE    = fase portal venosa
- canal AZUL     = fase tardia

A cor de uma estrutura indica seu comportamento ao longo do tempo. Avalie apenas
o parênquima hepático.

Classifique a alteração hepática predominante em exatamente uma categoria:
- HCC: carcinoma hepatocelular
- HEMANGIOMA: hemangioma hepático
- CISTO: cisto hepático simples
- FNH: hiperplasia nodular focal
- INCERTO: as imagens não permitem distinguir com segurança

Responda com um único objeto JSON, sem Markdown:
{"subtipo": "HCC | HEMANGIOMA | CISTO | FNH | INCERTO",
 "padrao_de_realce": "string",
 "confianca": "baixa | moderada | alta"}

Isto é pesquisa, não é diagnóstico e não substitui avaliação médica.
```

Respostas não parseáveis, recusas e qualquer coisa fora do vocabulário são contadas como
**INCERTO**, nunca descartadas.

---

## 4. Gate — fixado antes de qualquer número

Âncoras de comparação: acaso **25%**, zero-shot MedSigLIP **27,55%**, supervisão
**52,18%** (que ainda por cima se beneficia do vazamento de coorte).

| Critério | Exigido |
|---|---|
| **Primário** — acurácia balanceada sobre os 321, **INCERTO contando como erro** | ≥ **40%** |
| **Secundário** — acurácia balanceada apenas entre os casos nomeados | ≥ **50%** |
| **Terciário** — taxa de abstenção (INCERTO) | ≤ **40%** |

**Os três precisam passar.** A separação entre primário e secundário existe porque um
modelo que se cala nos casos difíceis infla a acurácia entre os nomeados: o número
"entre nomeados" é sobre um subconjunto auto-selecionado e fácil. Reportar só ele seria
enganoso, exatamente como o recall de 90% do cisto em docs/131 era artefato de colapso.

### Decisão amarrada

| Resultado | Consequência |
|---|---|
| Os três passam | Caminho viável sem engenharia de features. Estruturar validação mais dura e considerar exposição com abstenção explícita. |
| Primário passa, secundário/terciário falham | Sinal real mas cobertura insuficiente. Investigar prompt e o 27B antes de decidir. |
| Primário falha | Opção barata eliminada. A Frente 2 (ingerir `C-pre`/`T2WI`/`DWI` + ROI de lesão) passa a ser justificada como o caminho caro e necessário. |

Não haverá iteração sobre o gate nem sobre o prompt após ver o resultado, em coerência com
a Etapa B, com docs/128 e com docs/130.

---

## 5. Limitações conhecidas antes de começar

1. **Um 4B pode não ter granularidade** para separar hemangioma de FNH, e pode alucinar
   subtipo com confiança. Por isso a abstenção é medida e reportada como critério, não
   como nota de rodapé.
2. **Os painéis são compostos sintéticos**, não imagens radiológicas naturais. O controle
   de sanidade de docs/131 mostrou que o MedSigLIP os reconhece como RM abdominal de
   fígado (451/451), o que é encorajador mas não garante leitura fina de realce.
3. **Faltam as sequências que definem as classes fracas.** `C-pre`, `T2WI` e `DWI` estão
   em disco e não são mostradas aqui. Um resultado negativo não prova que o MedGemma é
   incapaz — prova que ele é incapaz *com o que damos a ele hoje*.
4. Não altera produção, não expõe subtipo, `clinical_use_allowed` segue `false`.
