# OpenSwissHCC — resultados MedGemma 4B v3–v5

Data: 14 de julho de 2026  
Modo: pesquisa, com revisão humana obrigatória

Este documento continua o registro de
`28_OPENSWISSHCC_REMEDIACAO_TECNICA_V2.md`. O documento anterior não foi
alterado porque sua ACL local impediu a edição segura.

## 1. Inferência e avaliação oficial v3

A inferência MedGemma 1.5 4B foi executada nos 88 painéis aprovados. Antes
da abertura dos rótulos, o avaliador oficial confirmou:

- 88 casos únicos e exatamente iguais à coorte congelada;
- 88 relatórios com status `success_pending_human_review`;
- hashes, assinatura do freeze e assinatura da revisão íntegros;
- `ground_truth_read=false` e `metrics_calculated=false`;
- nenhuma falha, timeout, staging parcial ou artefato ausente;
- tempo médio de 4,632 s, mediana de 4,550 s, p95 de 4,969 s e máximo
  de 9,341 s por caso.

Somente depois desse gate o ground truth de desenvolvimento foi aberto uma
única vez. O resultado oficial foi:

```text
TP=39  TN=0  FP=49  FN=0
sensibilidade: 100,0% (IC95% 91,0%–100,0%)
especificidade: 0,0% (IC95% 0,0%–7,3%)
acurácia: 44,3%
gate de tempo: PASS
gate simultâneo 75%/75%: FAIL
```

O modo `prefilled_label` classificou todos os casos como `POSITIVA`. Ele
resolveu latência e validade do schema, mas não demonstrou discriminação
clínica. Os artefatos autoritativos estão em:

```text
casos/qualification/openswisshcc_v1/runs/dev_v3_4b/
casos/qualification/openswisshcc_v1/evaluation/dev_v3_4b/
```

O holdout de 44 casos continua fechado e não foi baixado nem avaliado.

## 2. Calibração exploratória v4 — escolha balanceada

Os mesmos 88 painéis foram pontuados sem rótulos por escolha balanceada em
quadrado latino. O artefato de scores foi fechado antes de anexar o ground
truth e possui SHA-256:

```text
1c93917d1eaf46ee979e6c117463626d0b390722d98bfe7ba6ab0bbe43e17a9d
```

O argmax produziu sensibilidade de 23,1% e especificidade de 83,7%. Nenhuma
função simples dos três scores, nenhum limiar global e nenhum par de limiares
separado por tipo de painel alcançou 75%/75%. O melhor compromisso entre os
sinais simples permaneceu aproximadamente em 64%/63%. Portanto, a escolha
balanceada não foi promovida como decisão final.

## 3. Segundo leitor v5 — MedSigLIP

O ensemble pré-declarado `v5_mimic_aware` do MedSigLIP oficial foi executado
sem rótulos, decisão final ou máscara de lesão. Os 88 painéis foram pontuados
em 88,868 s no total; após o carregamento inicial, cada painel levou cerca de
0,67 s. SHA-256 do lote:

```text
5213f1343bb1eb09918aca3ffaa8f054f9e75bec74ae240b5c4fd1423244e669
```

Nenhuma agregação MedSigLIP isolada atingiu o gate. O melhor compromisso
simples ficou em 61,5% de sensibilidade e 61,2% de especificidade.

## 4. Fusão determinística exploratória

Uma fusão por percentis entre dois sinais independentes alcançou, no
desenvolvimento completo, 30/39 positivos e 37/49 negativos:

```text
sensibilidade: 76,9% (IC95% Wilson 61,7%–87,4%)
especificidade: 75,5% (IC95% Wilson 61,9%–85,4%)
AUC: 0,765
```

A regra combina `P(INCONCLUSIVA)-P(NEGATIVA)` da escolha balanceada MedGemma
com o score sagital invertido do MedSigLIP, após transformação por ECDF de
desenvolvimento. Entretanto, a estabilidade foi insuficiente:

- leave-one-out: sensibilidade 74,4%, especificidade 75,5%;
- em 50 repetições de validação cruzada estratificada 5-fold, somente 7
  mantiveram simultaneamente os dois gates;
- o limiar válido foi único entre as combinações exploradas.

Por isso a fusão permanece candidata exploratória, não uma configuração
qualificada. O próximo experimento deve aumentar a evidência visual com
cobertura volumétrica completa antes de considerar a abertura do holdout.

## 5. Próxima etapa

O gerador multifásico já implementa `volumetric_blocks` e cobertura axial
exata. A próxima implementação deve:

1. criar candidatos volumétricos sem sobrescrever a coorte `uniform_9`;
2. reutilizar os alinhamentos, volumes e máscaras hepáticas já auditados;
3. manter fallback venoso nos casos sem representação multifásica adequada;
4. provar cobertura de 100% e hashes de todos os painéis;
5. gerar uma nova galeria, sem inferência automática;
6. exigir revisão humana antes de qualquer chamada aos modelos;
7. medir tempo por exame incluindo todos os painéis;
8. usar somente o desenvolvimento aberto para selecionar a regra;
9. congelar tudo antes de baixar ou abrir o holdout.

