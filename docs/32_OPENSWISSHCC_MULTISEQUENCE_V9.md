# OpenSwissHCC — representação multissequência v9

Data da validação: 2026-07-14

## Objetivo

Avaliar uma representação nativa multissequência para o MedGemma 1.5 4B sem treinamento próprio, preservando o holdout e sem usar máscara de lesão ou ground truth durante a preparação.

Cada plano hepático projetado na série DWI TRACE produz um painel 2x2 de 896 x 896 pixels com:

1. T1 venoso, com contorno hepático apenas para localização;
2. T2 nativo;
3. última série TRACE pela ordem numérica do protocolo;
4. ADC nativo.

A última série TRACE **não é chamada de high-b**. Os sidecars JSON públicos não expõem b-values explícitos; portanto, a única afirmação reproduzível é que se trata do último run TRACE ordenado.

## Correções desta etapa

- conversão explícita dos limites de recorte NumPy para `int`, permitindo serialização JSON determinística;
- comparação geométrica de espaçamento, origem e direção com tolerâncias numéricas definidas, evitando rejeitar diferenças de arredondamento da ordem de `1e-9`;
- compatibilidade segura do scorer volumétrico com manifestos legados que informam `axial_interval`, mantendo o gate de no máximo nove cortes por painel;
- compatibilidade do runner pairwise com execução por módulo e execução direta;
- nomenclatura do auditor alterada de `high_b` para `last_ordered_trace`.

Os quatro arquivos submetidos à recriação segura foram preservados em backups temporários até a conclusão de todos os testes. Após a suíte completa passar, somente a pasta desses backups foi removida.

## Auditoria cega dos 88 casos de desenvolvimento

Resultado: `audit_complete_no_inference`.

- casos auditados: 88/88;
- ADC disponível: 88/88;
- pelo menos três runs DWI TRACE: 88/88;
- T2 BLADE: 87/88;
- fallback T2 HASTE: 1/88;
- ground truth lido: não;
- mediana de pontos físicos hepáticos dentro do FOV: 100%;
- mínimo no DWI/ADC e último TRACE ordenado: 95,6670%;
- mínimo no T2: 97,8155%;
- cosseno absoluto mínimo de orientação DWI/ADC: 0,9981348;
- cosseno absoluto mínimo de orientação T2: 0,9925513.

Em 86/88 casos, a intensidade mediana dos runs TRACE foi totalmente não crescente. Esse dado apoia a consistência da ordenação, mas não autoriza inferir b-values ausentes.

Artefato da auditoria:

`casos/qualification/openswisshcc_v1/prepared/development_multisequence_audit_v1/audit.json`

## Piloto real sem inferência

Caso público de desenvolvimento:

`anon-openswiss-04031ea54343b8db`

Resultado:

- 25 painéis gerados;
- 25/25 planos TRACE representados exatamente uma vez;
- nenhum plano ausente;
- nenhum plano duplicado;
- 99,9736% dos pontos físicos hepáticos dentro do FOV TRACE;
- gate mínimo de 95% aprovado;
- 25/25 hashes SHA-256 conferidos;
- dimensões de todos os painéis: 896 x 896;
- máscara de lesão utilizada: não;
- ground truth lido: não.

Artefato do piloto:

`casos/qualification/openswisshcc_v1/prepared/development_multisequence_candidate_v1/anon-openswiss-04031ea54343b8db/multisequence_manifest.json`

## Testes

- testes focalizados iniciais: 12 aprovados;
- repetição multissequência após ajuste de nomenclatura: 5 aprovados;
- suíte completa do ARGOS: 454 aprovados, nenhuma falha;
- avisos observados: depreciações conhecidas de SimpleITK, scikit-image, VTK e integração Starlette/httpx; nenhum aviso invalidou os resultados.

## Decisão sobre colorização

Não se deve colorir artificialmente todas as sequências como estratégia principal de acurácia. T2, DWI e ADC permanecem nativos para preservar contraste e textura diagnósticos e evitar que o modelo aprenda a interpretar uma cor de sobreposição como evidência de doença.

O contorno ciano é limitado ao T1 venoso e serve apenas como referência espacial do fígado. Mapas coloridos determinísticos podem ser testados futuramente como uma ablação separada, nunca substituindo as imagens nativas e nunca contendo informação derivada de máscara de lesão.

## Estado e próximo gate

O gerador v9 está tecnicamente validado, mas ainda não está liberado para inferência de benchmark. O próximo gate é revisão humana cega de uma galeria v9 representativa ou completa. Somente após aprovação visual devem ser executados o piloto MedGemma e a comparação com v4/v7/v8.

O holdout permanece fechado.
