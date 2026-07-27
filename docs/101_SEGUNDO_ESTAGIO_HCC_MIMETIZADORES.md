# Segundo estágio experimental — HCC versus mimetizadores benignos

## Objetivo

O experimento externo LLD-MMRI v23 demonstrou que o MedGemma 4B liver-enriched
tem sensibilidade alta para HCC, mas chama a maioria de FNH, hemangiomas e
cistos de positivos. Este componente adiciona uma releitura independente,
centrada em diferenciar lesão focal suspeita de padrão focal benigno, sem alterar
o resultado externo já congelado.

Ele é estritamente de pesquisa, não produz diagnóstico e mantém revisão humana
obrigatória.

## Componentes

- Configuração de desenvolvimento:
  `configs/medgemma_local_4b_liver_enriched_hcc_benign_discriminator_development.yaml`.
  Ela preserva os painéis liver-enriched, usa o corpus RAG local auditável e
  força o schema pathology-target v2 compacto.
- Adjudicador:
  `dtwin/benchmark/benign_mimic_adjudication.py`.
- CLI:
  `tools/adjudicate_hcc_benign_mimic.py`.

## Regra congelada da combinação

| Primeira passagem | Releitura discriminadora | Resultado experimental |
| --- | --- | --- |
| NEGATIVA | qualquer | NEGATIVA preservada |
| INCONCLUSIVA | qualquer | INCONCLUSIVA preservada |
| POSITIVA | POSITIVA | POSITIVA |
| POSITIVA | INCONCLUSIVA | INCONCLUSIVA |
| POSITIVA | NEGATIVA, sem lesão focal e confiança moderada/alta | NEGATIVA |
| POSITIVA | NEGATIVA de baixa confiança | INCONCLUSIVA |

A releitura nunca promove uma primeira passagem negativa para positiva. A regra
é deliberadamente conservadora: desacordo não é escondido como negativo e deve
continuar contando como erro na métrica primária quando o protocolo assim exigir.

## Gates de integridade

O adjudicador recusa executar se:

- os relatórios forem de casos distintos;
- os hashes do conjunto de painéis divergirem;
- a configuração/prompt da releitura for igual à da primeira passagem;
- a releitura não trouxer o schema pathology-target v2 completo;
- o relatório violar pesquisa, revisão humana ou ausência de lesão pré-marcada.

O resultado registra hashes SHA-256 dos dois envelopes e uma assinatura canônica
da adjudicação. Ele registra explicitamente `ground_truth_read=false`,
`lesion_masks_read=0` e `lesion_masks_used=false`.

## Uso em desenvolvimento

Primeiro, executar as duas leituras sobre o mesmo conjunto de painéis aprovado.
Depois, combinar somente os dois envelopes:

```powershell
.\.venv-win\Scripts\python.exe tools\adjudicate_hcc_benign_mimic.py `
  --first-pass-report caminho\primeira\medgemma_report.json `
  --discriminator-report caminho\releitura\medgemma_report.json `
  --output caminho\benign_mimic_adjudication.json
```

O uso inicial deve ocorrer apenas em coorte de desenvolvimento já aberta. Após
escolher uma configuração e congelar a regra, uma coorte externa nova e ainda
cega deve ser usada para a avaliação final. O LLD-MMRI v23 não pode ser usado
novamente como teste independente dessa estratégia, pois seus labels já foram
abertos.
