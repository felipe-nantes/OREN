# OpenSwissHCC v19 e v20 — resultados protegidos

## Autorização e integridade

Foi autorizada explicitamente a abertura exclusiva de `development_labels.jsonl`
para os protocolos:

```text
v19: f42ee0009c5c65fd7cb92d05bf8d605d78bd31c9ac3c04cd3ebcdec425229a1e
v20: be8652b3a96070b3821c8780fef3985a4f2be26f0d10cc93443de8e924fa6750
```

O holdout permaneceu fechado. Nenhum prompt, peso, score, transformação, limiar
ou regra de agregação foi alterado depois da autorização.

```text
casos: 87
positivos: 39
negativos: 48
SHA-256 dos labels: 406a746124c10bf6b8a43d4a2b500d9582f22a6dc01529ccb7b27769c8e32020
holdout aberto: não
```

## V19 — atlas axial com RAG textual

### Resultado primário LOOCV

| Métrica | Resultado |
|---|---:|
| Verdadeiros positivos | 17 |
| Falsos negativos | 22 |
| Verdadeiros negativos | 22 |
| Falsos positivos | 26 |
| Sensibilidade | **43,59%** |
| Especificidade | **45,83%** |
| Acurácia balanceada | 44,71% |
| Meta 75%/75% | **reprovada** |

Intervalos de Wilson de 95%:

```text
sensibilidade: 29,30% a 59,02%
especificidade: 32,58% a 59,71%
```

Diagnósticos secundários:

```text
ROC-AUC aparente: 0,4143
argmax bruto:
  sensibilidade: 28,21%
  especificidade: 62,50%
  inconclusivos: 27, contados como erro
```

O máximo observado do leitor sobre o atlas pré-computado foi 19,0979 segundos.
O gate parcial de tempo passou, mas o tempo DICOM end-to-end não foi demonstrado
para o v19.

### Interpretação

O contexto RAG melhorou a diversidade categórica em relação ao v17, mas não
produziu um score discriminativo. A AUC abaixo de 0,5 e as métricas próximas do
acaso mostram que o RAG textual não corrige a limitação visual do leitor 4B.

## V20 — fusão v11 + RAG v19

### Resultado primário LOOCV

| Métrica | Resultado |
|---|---:|
| Verdadeiros positivos | 27 |
| Falsos negativos | 12 |
| Verdadeiros negativos | 37 |
| Falsos positivos | 11 |
| Sensibilidade | **69,23%** |
| Especificidade | **77,08%** |
| Acurácia balanceada | 73,16% |
| Meta 75%/75% | **reprovada** |

Intervalos de Wilson de 95%:

```text
sensibilidade: 53,58% a 81,43%
especificidade: 63,46% a 86,69%
```

Resultado aparente, não elegível para substituir o primário:

```text
sensibilidade: 71,79%
especificidade: 75,00%
```

Robustez estratificada 5-fold, 50 repetições:

```text
repetições passando 75%/75%: 0/50
mediana da sensibilidade: 69,23%
mediana da especificidade: 72,92%
menor sensibilidade: 66,67%
menor especificidade: 66,67%
```

O tempo conservador pré-declarado foi 104,4465 segundos, abaixo de 180 segundos.
Ele soma os maiores tempos dos componentes, mas não substitui uma medição DICOM
end-to-end do candidato final.

### Comparação com o v11

| Protocolo | Sensibilidade LOOCV | Especificidade LOOCV |
|---|---:|---:|
| v11 | **74,36%** | 75,00% |
| v19 | 43,59% | 45,83% |
| v20 | 69,23% | **77,08%** |

O v20 aumentou a especificidade em 2,08 pontos percentuais em relação ao v11,
mas reduziu a sensibilidade em 5,13 pontos. Portanto, o novo leitor RAG adicionou
ruído ao melhor candidato em vez de recuperar o verdadeiro positivo que faltava.

## Decisão

```text
v19 promovido: não
v20 promovido: não
melhor candidato 4B preservado: v11
meta simultânea 75%/75% atingida: não
holdout autorizado: não
holdout aberto: não
qualificação final: não
```

Não é metodologicamente defensável procurar novos pesos ou limiares usando os
mesmos 87 labels. Depois de múltiplas hipóteses adaptativas, isso elevaria o risco
de sobreajuste e não provaria generalização.

## Próximo caminho defensável

Para continuar buscando 75%/75% no 4B, é necessária uma nova fonte de informação:

1. nova coorte pública independente para desenvolvimento, mantendo o holdout
   atual fechado;
2. detector/localizador de lesão hepática em RM já treinado e publicamente
   disponível, validado sem usar as máscaras na inferência do MedGemma;
3. avaliação dos mesmos protocolos congelados no 27B do Mac para isolar se o
   gargalo é capacidade do leitor — esse teste não substitui a meta específica
   do 4B;
4. somente após um candidato passar o gate de acurácia, medir novamente o fluxo
   DICOM end-to-end e exigir todos os casos abaixo de 180 segundos.

O uso continua exclusivamente em pesquisa, com revisão humana obrigatória.

## Artefatos e hashes

```text
v19 evaluation.json:
54d28657be96b1bc82a638faba185d16ff086c7b722fc903995e501207d0c7d4

v19 case_scores.csv:
e27a46da734bfa3ce034a8969a9f9568e28891f49ef373cae50acd7823ae1192

v20 evaluation.json:
68a4c23a405e9c483c4d892916a847eec5ab8f18d54ef46dc3b891b5f313e240

v20 case_features.csv:
bd3b6047d5acb0e38cecc48e8c8d42bb0d7a5840813be27352970c2ab6230929
```
