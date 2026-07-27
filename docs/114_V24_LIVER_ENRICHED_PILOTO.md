# V24 — leitor liver-enriched como sinal complementar

## Objetivo

Avaliar, de forma prospectivamente congelada, se um leitor MedGemma 1.5 4B com
painéis enriquecidos em fígado melhora o pior eixo do classificador v23 sem
reduzir sensibilidade ou especificidade por ajuste retrospectivo.

O v24 não substitui o v23. Ele acrescenta um único sinal contínuo:

```text
liver_enriched_max_positive_probability
```

A fusão foi fixada antes da inferência:

```text
80% família de sinais v23 + 20% leitor liver-enriched
```

Transformações ECDF, limiar e demais parâmetros devem ser aprendidos apenas nos
folds de treino. O peso não pode ser reajustado após a leitura dos resultados.

## Coorte e salvaguardas

- 132 casos OpenSwissHCC.
- 127 casos com representação multifásica RGB registrada.
- 3 casos de desenvolvimento com fallback venoso em escala de cinza replicada.
- 2 falhas técnicas anteriores permanecem falhas e contam como erro.
- Máscara hepática usada somente para localização axial grosseira.
- Sem contorno, crop guiado por lesão ou máscara de lesão.
- Labels e máscaras de lesão permanecem fechados durante preparação e inferência.

## Gate atual

Foi gerado um piloto label-blind com 10 casos e 30 painéis para revisão humana
exclusivamente técnica. A revisão deve confirmar:

1. fígado visível em todos os painéis;
2. ausência de crop ou contorno que revele candidato;
3. distribuição axial útil entre os três painéis;
4. ausência de PHI visível.

Não se deve avaliar diagnóstico, presença de lesão ou resultado esperado nessa
galeria.

## Artefatos congelados

- Protocolo: `v24_liver_enriched_protocol_v1.json`
- Assinatura do protocolo:
  `0e934cee0c9933e712f7a3d422169a6ba613d81cdf7e587e2d0d6c0c03cca04c`
- Piloto: `v24_liver_enriched_pilot10_v1`
- Assinatura do piloto:
  `f0bb3c451b501f537e2d4524e28d1c842388957525dafaf812133e64ddc5a5e8`
- Galeria: `v24_liver_enriched_gallery10_v1`
- Assinatura da galeria:
  `8aaa386e9f85749680697973c129acf6a81951db17dc49edc904db5b13b472ae`

## Próximos gates

### Concluído após aprovação técnica

- Aprovação registrada pelo revisor `jm`.
- Assinatura da revisão:
  `45bad73a8321af809c1dcb6bd2ade0cbd79d72fe9a027f6d5fb85131c06c2f88`
- Coorte completa gerada: 130 casos processáveis e 390 painéis.
- 127 casos multifásicos RGB registrados e 3 fallbacks venosos em escala de
  cinza replicada.
- Duas falhas técnicas anteriores foram mantidas e continuarão contando como
  erro, sem sinal fabricado.
- Assinatura da coorte:
  `167588c8b94d1cf964ec683c15af73f7086835bef1b995ef192e5c9c9c740078`
- Verificação independente aprovada.
- Assinatura da verificação:
  `23669e62c8f77f93137f9f61065be0f646144d89b5d37ff0143a81603cc947db`

Durante toda a geração, `labels_read=false`, `lesion_masks_read=0` e
`inference_executed=false`.

### Gates restantes

1. congelar o protocolo de inferência associado à coleção verificada;
2. executar inferência label-blind do leitor liver-enriched;
3. verificar relatórios, chamadas e limite de 180 segundos por caso;
4. congelar as predições;
5. somente então abrir os labels já autorizados e executar a avaliação
   retrospectiva multicohort;
6. aceitar o v24 apenas se sensibilidade e especificidade forem ambas pelo menos
   75%, sem falhas ocultas, e se o menor dos dois indicadores superar o v23.

Se esses critérios não forem atendidos, o candidato será rejeitado sem
recalibrar seu peso sobre os mesmos resultados.
