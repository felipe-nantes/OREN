# OpenSwissHCC v19 — atlas axial com RAG textual

## Hipótese

O v17 provou que todas as lesões públicas anotadas estavam representadas no atlas,
mas o MedGemma 4B não separou positivos de negativos. O v19 testa uma mudança de
fonte de informação: o mesmo atlas humano-aprovado recebe contexto textual
recuperado do corpus RAG já versionado.

O contexto é focalizado em:

- realce arterial, washout e cápsula no HCC;
- interpretação das fases dinâmicas;
- artefato de movimento na fase arterial;
- pseudolesões e alterações perfusionais.

Isso busca melhorar a distinção entre lesão focal e mimetizadores sem treinamento
e sem alterar imagens, segmentações ou pesos do modelo.

## Salvaguardas

```text
modelo: MedGemma 1.5 4B
entrada visual: atlas v17 aprovado
requisições por caso: 1
retry automático: 0
score: log-odds POSITIVA/NEGATIVA
tempo máximo por caso: 180 s
ground truth na inferência: não
máscara de lesão na inferência: não
holdout: fechado
uso: pesquisa com revisão humana obrigatória
```

O protocolo registra hashes do índice BM25, especificação de consultas, contexto,
trechos recuperados, configuração efetiva, prompt final, atlas e protocolo v17.
Qualquer mudança nesses componentes invalida reuso e interrompe antes da inferência.

## Avaliação predefinida

Se a inferência cega dos 87 casos for tecnicamente válida, será necessário pedir
nova autorização explícita associada à assinatura do v19 antes de abrir novamente
os labels de desenvolvimento. O estimador primário será LOOCV, com limiar ajustado
somente nos outros 86 casos. Sensibilidade e especificidade deverão ser ambas de
pelo menos 75%.

O holdout não será aberto mesmo se o desenvolvimento passar: antes será exigida
estabilidade, auditoria de tempo end-to-end e uma decisão metodológica separada.

## Congelamento e execução cega

O protocolo de inferência foi congelado com assinatura:

```text
1093b1181f7dc3bac6f1f9edce9f14d7c8bdf487013a4c1dbf504952ff2b1aff
```

Hashes principais:

```text
contexto RAG: c9ee6b580f614822ddcd052ae1420f7d4ca4adc85ced28b7773ed9234c31572e
índice BM25:  4239285a5c8a56a2ce8ab0eae6d53b7c181b24068a0b856befd8e8ad4cd2a2ab
config efetiva: 1db0c678eb31273e4bd50acba7df8cc2385ba6543d1ee09a6c0bc9053b8ef67e
```

Execução cega:

```text
casos: 87/87
requisições: 87
falhas técnicas: 0
ground truth lido: não
máscara de lesão lida: não
holdout aberto: não
```

Distribuição categórica sem interpretação clínica:

```text
POSITIVA: 29
NEGATIVA: 31
INCONCLUSIVA: 27
```

Tempos do leitor sobre o atlas pré-computado:

```text
mínimo: 5,4313 s
mediana: 8,1097 s
média: 8,2998 s
máximo: 19,0979 s
gate de 180 s: aprovado
```

O resumo cego possui SHA-256:

```text
da895bac18801773615ce8e748323001967ea0449e44d3a9d79e400ec52622cb
```

A segunda passagem validou e reutilizou as 87 predições existentes; nenhuma nova
chamada foi necessária.

## Protocolo de avaliação congelado

O vetor completo de scores foi vinculado antes de qualquer nova abertura dos
labels:

```text
assinatura da avaliação:
f42ee0009c5c65fd7cb92d05bf8d605d78bd31c9ac3c04cd3ebcdec425229a1e

SHA-256 do vetor cego:
9bd8b8efe2b99270a1ceede769b3acad148955c1764aa6aa303e1e0f26508ea1
```

O próximo gate exige autorização explícita que cite essa assinatura. Até então,
nenhuma sensibilidade, especificidade ou AUC do v19 pode ser calculada.

## Preflight do bloqueio protegido

O avaliador foi executado contra os artefatos reais sem a flag de autorização e
abortou antes de abrir o arquivo:

```text
[ABORTADO] Abertura dos labels de desenvolvimento v19 não foi autorizada.
```

Também foi testado com a flag e um caminho sintético contendo `holdout`; o
avaliador recusou o caminho antes de qualquer leitura:

```text
[ABORTADO] Avaliador v19 aceita somente development_labels.jsonl, nunca holdout.
```

Nenhum diretório de avaliação foi criado nos dois testes.

## Resultado protegido

Após autorização explícita vinculada à assinatura, o v19 obteve por LOOCV:

```text
sensibilidade: 43,59%
especificidade: 45,83%
ROC-AUC aparente: 0,4143
gate 75%/75%: reprovado
holdout aberto: não
```

O protocolo não foi promovido. A análise completa está em
`docs/79_OPENSWISSHCC_V19_V20_RESULTADOS.md`.
