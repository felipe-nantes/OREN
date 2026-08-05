# 179 — MedSigLIP monofásico tardio

## Objetivo

Substituir o fallback MedGemma 4B + RAG por um classificador visual rápido nos
exames monofásicos em que a série selecionada possa ser identificada com
segurança como `T1_DELAYED`. Nenhuma fase é sintetizada.

## Protocolo experimental

- Encoder congelado: `google/medsiglip-448`, revisão
  `9cea28a1a1195f665105faa6e8544c112fd960a4`.
- Representação: canal tardio real do painel aprovado, replicado em R/G/B.
- Cabeça: regressão logística balanceada, seleção de C, agregação e limiar
  somente no inner CV.
- Avaliação: nested CV agrupada por paciente no LLD-MMRI.
- 335 casos: 157 positivos e 178 negativos.
- 14 falhas técnicas contadas como erros.
- Ground truth aberto somente após o congelamento das predições OOF.
- Máscaras públicas de lesão não foram lidas nem enviadas ao encoder.

## Ablação por fase

| Entrada monofásica | Sensibilidade | Especificidade | ROC-AUC | Gate 75/75 |
|---|---:|---:|---:|---|
| Arterial | 73,25% | 75,28% | 0,871 | Não |
| Portal/venosa | 74,52% | 73,60% | 0,873 | Não |
| Tardia | **77,71%** | **75,84%** | 0,851 | **Sim** |

Intervalos de confiança de 95% do braço tardio:

- sensibilidade: 70,58% a 83,51%;
- especificidade: 69,05% a 81,54%.

O resultado é uma estimativa retrospectiva interna do LLD-MMRI e não constitui
validação externa nem desempenho clínico garantido.

## Integração no exame individual

Quando o resolvedor não encontra três fases dinâmicas:

1. o OREN seleciona a melhor série MR usando somente metadados técnicos;
2. se `sequence_class == T1_DELAYED`, usa o bundle monofásico assinado;
3. gera 2 ou 3 painéis liver-enriched grayscale, sem contraste dinâmico;
4. executa MedSigLIP e a cabeça congelada;
5. só depois da decisão executa o localizador candidato para o visualizador;
6. mantém revisão humana obrigatória;
7. para arterial, venosa, fase genérica ou desconhecida, preserva o fallback
   MedGemma 4B + RAG.

O resultado expõe `monophase_reference_metrics`, `source_phase_key`, classe de
sequência selecionada, limitações e a informação explícita de que as métricas
trifásicas não se aplicam.

## Smoke tests DICOM reais

Foram executadas duas séries tardias isoladas, sem fornecer labels ao worker:

- negativo: `NEGATIVA`, score 0,125, 3 painéis, visualizador pronto, ~56 s;
- positivo: `POSITIVA`, score 0,983, 3 painéis, candidato 3D e visualizador
  prontos, ~84,5 s.

No segundo teste, a classificação terminou em aproximadamente 41,5 s; o tempo
restante correspondeu ao localizador pós-decisão e à construção do modelo 3D.

## Limites atuais

- O classificador não é independente de fase.
- O gate 75/75 só foi atingido para a representação tardia no LLD-MMRI.
- Não há estimativa válida de acurácia para um DICOM monofásico aleatório cuja
  fase seja desconhecida.
- O subtipo não é inferido por esta cabeça binária.
- O caminho continua restrito a pesquisa, com revisão humana obrigatória.

## Avaliação externa OpenSwissHCC

Depois do freeze label-blind das 132 predições, os labels públicos foram
anexados somente ao avaliador. As cinco falhas técnicas foram contadas como
erros e nenhuma máscara de lesão foi lida.

| Coorte | Sensibilidade | Especificidade | ROC-AUC |
|---|---:|---:|---:|
| OpenSwissHCC completo (132) | **25,40%** | **81,16%** | 0,655 |
| Desenvolvimento (88) | 20,51% | 79,59% | 0,684 |
| Holdout consumido (44) | 33,33% | 85,00% | 0,590 |

Conclusão: o classificador tardio treinado no LLD reconhece negativos, mas não
generaliza a sensibilidade para OpenSwissHCC. Por isso a promoção automática no
webapp fica desabilitada por padrão. O worker e o cenário permanecem disponíveis
para pesquisa reproduzível, enquanto o fallback operacional continua sendo o
MedGemma 4B + RAG.

Uma auditoria adicional escolheu o limiar usando somente os 88 casos de
desenvolvimento e o aplicou sem ajuste aos 44 casos do holdout. Nenhum limiar
atingiu 75/75 no desenvolvimento. O melhor equilíbrio foi 64,10%/61,22% e
produziu 54,17%/50,00% no holdout. Isso demonstra mudança real de domínio, não
apenas um threshold mal calibrado. O score não deve ser usado como decisão, veto
ou confirmação automática no fluxo operacional atual.

## Diagnóstico de adaptação de domínio

Foram executados dois experimentos retrospectivos adicionais, sempre com o
holdout OpenSwissHCC fora do ajuste e da seleção de limiar.

| Treino/OOF | Casos | Sensibilidade | Especificidade | ROC-AUC | Gate 75/75 |
|---|---:|---:|---:|---:|---|
| LLD + OpenSwiss-development | 423 | 74,49% | 71,81% | 0,838 | Não |
| OpenSwiss-development somente | 88 | 56,41% | 61,22% | 0,689 | Não |

No experimento combinado, o resultado agregado esconde a diferença entre os
domínios: LLD atingiu 78,98%/75,84%, enquanto OpenSwiss-development ficou em
56,41%/57,14%. Treinar somente no OpenSwiss elevou a especificidade para 61,22%,
mas não recuperou a sensibilidade.

Esses resultados descartam duas hipóteses simples:

1. recalibrar apenas o limiar não corrige a generalização;
2. separar ou misturar as cabeças por dataset não torna a representação tardia
   suficiente no OpenSwiss.

A conclusão metodológica é que o sinal dinâmico das fases, a representação
visual ou ambos precisam mudar. Não foi treinado bundle operacional com esses
experimentos, o holdout não foi usado para escolher modelo e a promoção
automática permanece desabilitada.

## Extensão hierárquica de subtipo

A implementação e o primeiro benchmark da cabeça tardia multiclasse estão
documentados em `docs/180_PLANO_MONOFASICO_HIERARQUICO_IMPLEMENTACAO.md`.
Internamente no LLD, o endpoint HCC atingiu 75,80% de sensibilidade e 77,53% de
especificidade, mas o subtipo atingiu somente 48,88% de acurácia balanceada
(56,42% top-1; 77,91% top-2). O bundle foi assinado apenas para pesquisa e não
foi promovido ao frontend.
