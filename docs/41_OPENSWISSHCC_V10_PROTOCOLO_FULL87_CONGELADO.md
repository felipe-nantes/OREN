# OpenSwissHCC v10 — protocolo de avaliação full87 congelado

Este documento complementa o relatório v10 do piloto e do localizador full87.

Antes de qualquer nova abertura de labels, foi congelado um protocolo estatístico em:

```text
casos/qualification/openswisshcc_v1/prepared/development_freezes_v10/
lesion_localizer_full87_evaluation_protocol.json
```

Assinatura do protocolo:

```text
e94b1bb1bc43cbb2a643515945948a5cb238e9b66473c50f365545ff8c778bbe
```

O protocolo fixa previamente:

- uma única feature primária: `log1p(total_candidate_volume_mm3)`;
- direção: valores maiores favorecem positivo;
- LOOCV como estimador primário;
- validação estratificada 5-fold repetida 50 vezes como análise secundária;
- seleção do limiar exclusivamente no conjunto de treino de cada fold;
- intervalos de Wilson de 95% sobre a matriz de confusão LOOCV;
- gate simultâneo de sensibilidade e especificidade maiores ou iguais a 75%.

O protocolo está ligado por hash ao run cego consolidado, aos 87 IDs anônimos e ao
vetor da feature. Qualquer alteração posterior invalida a verificação.

O avaliador exige o sinalizador explícito:

```text
--allow-protected-development-labels
```

Sem esse sinalizador, a execução aborta antes de chamar o leitor de labels. Um teste
automatizado verifica essa ordem. O caminho aceito deve ser especificamente
`protected_ground_truth/development_labels.jsonl`; caminhos contendo `holdout` são
rejeitados.

Estado no momento do freeze:

- casos: 87;
- ground truth lido pelo protocolo: não;
- métricas calculadas: não;
- holdout aberto: não;
- uso: pesquisa com revisão humana obrigatória.
