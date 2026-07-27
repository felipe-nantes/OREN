# OpenSwissHCC v16 — galeria técnica full87

Data: 2026-07-16  
Estado: geração e validação técnica concluídas; revisão humana pendente  
Holdout: fechado

## 1. Objetivo

Construir o material de entrada de todos os 87 casos de desenvolvimento autorizados pelo protocolo v16, sem ler os labels e sem executar inferência, para auditoria humana anterior ao scoring cego com o MedGemma 1.5 4B.

## 2. Conteúdo gerado

Diretório:

`casos/qualification/openswisshcc_v1/prepared/development_v16_full87_v1`

- 87 casos;
- 229 stacks candidatos;
- 6.626 frames que serão fornecidos ao modelo;
- 229 contact sheets exclusivos para auditoria humana;
- 9 páginas de galeria, com até 10 casos por página;
- 84 casos com registro espacial;
- 3 casos processados pelo fallback não registrado previamente aprovado.

Os contact sheets não são entradas do modelo e não aparecem nos manifestos dos casos usados pelo scoring.

## 3. Validação técnica

O validador reabriu todos os frames e contact sheets e conferiu:

- schema e completude da coorte;
- número e ordem dos casos e candidatos;
- hashes, formato, dimensões e integridade dos arquivos;
- correspondência entre stacks e contact sheets;
- isolamento dos arquivos de auditoria em relação às entradas do modelo;
- hashes do índice e das nove páginas da galeria;
- ausência de inferência, ground truth e holdout.

Resultados:

- hash da coorte: `5a204e930fc0c2b329f29d52b9c318930975242ca8adb2b8925bd4ddc3758a2e`;
- assinatura da galeria: `2e8a8efc9539ba216e5628fe7f8ca5348476d52292d89dd675bcdf07c507dd40`;
- ground truth lido: não;
- holdout aberto: não;
- inferência executada: não;
- status da revisão técnica humana: pendente.

## 4. Revisão humana requerida

O revisor deve percorrer as nove páginas e verificar, em cada candidato:

1. se o fígado está reconhecível e suficientemente enquadrado;
2. se o contorno amarelo acompanha tecido hepático, sem deslocamento grosseiro;
3. se o candidato contém evidência temporal útil, sem troca anatômica evidente;
4. se crop, orientação, contraste ou artefatos tornam o material impróprio;
5. se os casos fallback permanecem dentro do padrão já aprovado.

Problemas devem ser registrados por página, caso e candidato. A aprovação deve identificar o revisor.

## 5. Próximo gate

Somente após aprovação humana integral serão permitidos:

1. assinatura da revisão full87;
2. congelamento do protocolo de scoring cego;
3. execução do MedGemma 1.5 4B sem labels;
4. validação e congelamento das 87 predições;
5. abertura exclusiva dos labels de desenvolvimento para cálculo das métricas;
6. manutenção do holdout fechado.

Nenhuma conclusão de acurácia pode ser emitida nesta etapa.
