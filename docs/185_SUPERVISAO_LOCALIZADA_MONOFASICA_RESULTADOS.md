# Supervisao localizada de candidatos — resultado experimental

## Escopo

Esta etapa foi executada depois da autorizacao para usar as mascaras publicas
de lesao exclusivamente em desenvolvimento. As mascaras foram usadas apenas
para construir targets de treino e para auditoria retrospectiva. Elas nao
participaram da geracao de candidatos, das imagens, dos embeddings ou da
inferencia e nao foram integradas ao frontend.

## Problema corrigido

O pipeline 2.5D anterior marcava um componente automatico como positivo quando
ele tocava uma lesao em qualquer ponto, mas renderizava a imagem no centroide
do componente. Componentes extensos podiam, portanto, receber target positivo
mesmo quando a lesao nao aparecia no patch. Isso introduzia ruido sistematico
entre o target e os pixels vistos pelo classificador.

A nova implementacao separa dois artefatos imutaveis:

1. geometria label-blind, derivada somente do localizador deterministico v22;
2. targets protegidos, anexados depois pela visibilidade exata da mascara
   publica dentro da caixa e das fatias renderizadas.

## Cobertura e carga

Cobertura completa, antes do limite operacional:

```text
87 casos no protocolo
84 casos tecnicamente disponiveis
6.218 caixas automaticas
37/37 positivos com mascara visiveis em alguma caixa (100%)
media de 74,0 caixas por exame; maximo de 133
```

Configuracao operacional congelada para desenvolvimento:

```text
ordenacao: voxels automaticos na caixa (desc), rank do componente, ID
limite: 8 caixas por exame
representacao: 7 cortes axiais; arterial/venosa/tardia em RGB
672 imagens label-blind
32/37 positivos com mascara cobertos (86,49%)
77 patches positivos supervisionados
579 hard negatives supervisionados
3 falhas tecnicas mantidas no denominador
```

O top-8 foi escolhido em desenvolvimento e deve ser validado externamente; o
recall de 86,49% nao e uma estimativa independente.

## Avaliacao nested OOF por paciente

Todos os thresholds foram escolhidos nos folds internos. Cada predicao externa
foi produzida sem usar o paciente correspondente no ajuste. Falhas tecnicas
contaram como erro.

| Candidato | Sensibilidade | Especificidade | ROC-AUC | Gate 75/75 |
|---|---:|---:|---:|---:|
| MedSigLIP localizado linear | 46,15% | 54,17% | 0,5675 | falhou |
| MedSigLIP + 87 features dinamicas | 48,72% | 56,25% | 0,5436 | falhou |
| 87 features dinamicas lineares | 48,72% | 54,17% | 0,4513 | falhou |
| features dinamicas + HGB nao linear | 64,10% | 41,67% | 0,5464 | falhou |

Assinaturas das avaliacoes principais:

```text
MedSigLIP localizado: 224e1a588852df9f315c0b8304a94862f12ee8aa4ecbee38d357b200f3354d0b
fusao visual/dinamica: 0e2dd9fac61be4911c87875f571a9c99f2f225e9f254afe6c6476f6b7ea9781c
dinamica linear: a2f7a34e8318ebb5bef2014f1f721ff7de1ef84a383f0a399ebf21d855810d06
dinamica HGB: 3716941f19d0c8898c594542bbd74c2130410d685a01b6d48c77fbc306622bfd
```

## Conclusao

O gargalo de localizacao foi resolvido para esta coorte de desenvolvimento,
mas a classificacao continua sem separacao suficiente. Trocar a cabeca ou
adicionar estatisticas deterministicas nao atinge a meta. A amostra candidata
tambem e pequena: somente 77 patches positivos supervisionados.

Nenhum destes candidatos deve ser promovido ao webapp ou usado para declarar
75% de desempenho. O proximo experimento deve adaptar uma representacao
localizada/3D com uma coorte maior e targets de subtipo, preferencialmente
incluindo os casos LLD-MMRI. A validacao final precisa permanecer em uma coorte
externa sem mascaras durante inferencia.
