# OpenSwissHCC v9 — exclusão técnica e resultados multissequência

Data: 15 de julho de 2026  
Modelo: MedGemma 1.5 4B Instruction-Tuned  
Uso: pesquisa, com revisão humana obrigatória

## 1. Revisão técnica cega

A galeria multissequência foi revisada antes da inferência e antes da abertura do
ground truth. O revisor `jm` aprovou 87 dos 88 casos para a coorte primária.

O caso de índice 72 na galeria,
`anon-openswiss-cb2c5c63fc28b8ee`, foi excluído tecnicamente por degradação
multissequência severa. A exclusão não foi baseada no diagnóstico, na classe ou
em máscara de lesão.

- motivo: `severe_multisequence_quality_degradation`;
- status: `technical_quality_exclusion`;
- assinatura da revisão: `f4eb8e03b435820ef8d00656e332de7f9e84438301a0d68201ed59a7f58596d8`;
- SHA-256 do arquivo de revisão: `9110be9589e561cdb5ef17888f4a25c4987df5335549308d3ee5aca5ff6fa79b`;
- coorte primária: 87 casos;
- coorte de estresse técnico: 1 caso.

O avaliador exige que os casos aprovados na revisão assinada sejam exatamente os
casos inferidos e que qualquer label adicional corresponda exatamente a uma
exclusão técnica documentada. Assim, a linha excluída não foi apagada do ground
truth original e seu hash permaneceu auditável.

## 2. Execução cega

A inferência foi dividida deterministicamente em 11 chunks e consolidada somente
depois da validação de todos os casos, hashes e assinaturas.

- casos: 87/87;
- painéis T1 venoso/T2/TRACE/ADC: 2.130;
- falhas técnicas: 0;
- tempo médio por caso: 59,20 s;
- maior tempo por caso: 89,17 s;
- casos acima de 180 s: 0;
- ground truth lido durante inferência: não;
- decisão final emitida durante inferência: não;
- holdout aberto: não.

O gate temporal foi aprovado com margem. Os scores cegos foram persistidos antes
da abertura controlada dos labels de desenvolvimento.

## 3. Avaliação pós-inferência

A coorte primária contém 39 casos positivos e 48 negativos. A melhor feature
selecionada pelo protocolo foi `v9_panel_mean`.

| Métrica LOOCV | Resultado |
|---|---:|
| Verdadeiros positivos | 21 |
| Falsos negativos | 18 |
| Verdadeiros negativos | 29 |
| Falsos positivos | 19 |
| Sensibilidade | 53,85% |
| Especificidade | 60,42% |
| Acurácia balanceada | 57,13% |
| IC95% da sensibilidade | 38,57%–68,43% |
| IC95% da especificidade | 46,31%–72,98% |
| Repetições 5-fold aprovadas em 75%/75% | 0/50 |
| Validações aninhadas aprovadas em 75%/75% | 0/50 |

Status: `development_only_not_qualified`.

## 4. Diagnóstico do sinal

O resultado não pode ser corrigido por simples ajuste de threshold. A melhor AUC
entre as features v9 foi apenas 0,565. Para `v9_panel_mean`, a média foi 0,2747
nos positivos e 0,2724 nos negativos, uma separação muito pequena.

Nenhum caso teve `v9_fraction_over_050` diferente de zero. Isso mostra colapso
das probabilidades pairwise abaixo de 0,5: o modelo apresentou preferência
linguística estável pela frase negativa, mas quase nenhuma modulação associada à
classe real. O scorer de duas frases longas mediu mais a probabilidade textual
das continuações do que evidência visual discriminativa de HCC.

A inclusão de T1, T2, DWI TRACE e ADC resolveu cobertura e qualidade de entrada,
mas não forneceu ao MedGemma 4B, nesse formato de saída, sinal suficiente para
75% de sensibilidade e 75% de especificidade.

## 5. Decisão metodológica

- Não declarar 75% de acurácia.
- Não abrir o holdout.
- Não selecionar uma regra usando o holdout.
- Não repetir somente variações de frases ou thresholds sobre os mesmos scores.
- Preservar v9 como experimento negativo completo e reproduzível.

## 6. Próximo experimento defensável

O próximo candidato deve mudar a fonte de evidência, mantendo o MedGemma 4B como
leitor final:

1. produzir candidatos/ROIs de lesão em alta resolução por processamento 3D ou
   modelo público de localização, sem usar a máscara de lesão do benchmark;
2. mostrar ao 4B o contexto anatômico e crops focais ampliados, não apenas o plano
   completo;
3. registrar sensibilidade do localizador e cobertura das regiões propostas;
4. medir segmentação/localização + MedGemma dentro do teto end-to-end de 180 s;
5. executar piloto cego pequeno e persistir scores antes de acessar labels;
6. promover para a coorte de desenvolvimento somente se houver AUC e separação
   claramente superiores às do v9;
7. abrir o holdout apenas se LOOCV e validações repetidas atingirem 75%/75%.

Uma alternativa paralela é usar a interface volumétrica nativa do MedGemma 1.5
4B, desde que seja confirmada e implementada conforme o contrato oficial do
modelo, com gate de memória e tempo. Ambas as hipóteses devem ser testadas em
piloto técnico antes de uma nova execução completa.

## 7. Validação de software

Após a integração da exclusão assinada ao avaliador:

- 476 testes passaram;
- nenhum teste falhou;
- os avisos restantes são de depreciação de dependências e não alteraram o
  resultado do benchmark.

