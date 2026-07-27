# OpenSwissHCC v16 — stacks focais e gate humano

## Estado

A fundação cega da representação v16 foi implementada e validada. Nenhuma
inferência v16 foi executada e nenhum label de desenvolvimento ou holdout foi
lido nesta etapa.

O objetivo da v16 é substituir a leitura de um volume hepático amplo por uma
leitura focal 3D, multissequência e centrada em candidatos produzidos pelo
localizador `liver_lesions_mr` já aprovado na v10.

## Representação implementada

Para cada candidato são gerados, no máximo, 29 frames de 384 × 384 pixels:

- T1 nativo: 5 cortes;
- T1 arterial registrado ao venoso: 5 cortes;
- T1 venoso: 5 cortes;
- T1 tardio registrado ao venoso: 5 cortes;
- T2: 3 cortes;
- DWI TRACE de maior ordem disponível: 3 cortes;
- ADC: 3 cortes.

Cada grupo usa uma única janela de percentis 1–99 calculada no ROI do
candidato. O centro é propagado entre sequências por coordenadas físicas LPS.
Não há contorno, texto, máscara de lesão do dataset ou pixel sintético nos
frames enviados ao modelo.

## Seleção dos candidatos

A regra é determinística e foi definida antes da avaliação:

1. se houver até três componentes, todos são selecionados;
2. se houver mais de três, selecionar ao menos os três maiores;
3. continuar até cobrir pelo menos 75% dos voxels candidatos;
4. não ultrapassar cinco componentes;
5. abortar se os cinco maiores não cobrirem 75%;
6. quando o localizador não produzir candidato, gerar um único stack no centro
   da máscara hepática automática.

No desenvolvimento cego auditado anteriormente, a regra cobre os 80 casos com
candidatos; sete casos seguem pelo fallback hepático.

## Gates automáticos

Cada stack é recusado quando ocorrer qualquer uma destas condições:

- T1 venoso ausente ou inválido;
- menos de três grupos T1 dinâmicos utilizáveis;
- nenhuma sequência morfológica utilizável;
- quantidade de frames fora do contrato de 5 a 29;
- imagem diferente de RGB 384 × 384;
- hash, bytes ou arquivo divergente;
- uso de ground truth, máscara de lesão do dataset, PHI ou contorno candidato.

O resumo mesclado do localizador é aceito somente quando declara o schema-fonte
oficial de execução individual.

## Testes

Resultados finais em 16 de julho de 2026:

- testes específicos v16: 12 aprovados;
- suíte completa do ARGOS: 609 aprovados;
- regressões: zero;
- warnings: 380, todos não bloqueantes e já existentes nas dependências/APIs.

Os testes cobrem seleção adaptativa, cobertura insuficiente, limites axiais,
fallback, contraste, frame count, dimensões, canais sem sobreposição gráfica,
hash adulterado, schema single/merged e previews sem duplicação.

## Piloto técnico cego

Galeria autoritativa:

`casos/qualification/openswisshcc_v1/prepared/development_review_gallery_v16_candidate_volume_pilot10_v2/index.html`

Manifesto:

`casos/qualification/openswisshcc_v1/prepared/development_review_gallery_v16_candidate_volume_pilot10_v2/cohort_manifest.json`

Auditoria:

- 10 casos de desenvolvimento já aprovados na revisão pareada v10;
- 27 stacks candidatos;
- 768 PNGs gerados;
- assinatura da galeria:
  `0fcffc95fe0ed01957f8e8c5a94d2604d066e3ed7a75aaf4de4d63a76f80f838`;
- `ground_truth_read=false`;
- `dataset_lesion_mask_used=false`;
- `holdout_opened=false`;
- `inference_executed=false`.

## O que o revisor deve avaliar

Em cada candidato, verificar objetivamente:

1. o ROI contém fígado e não está cortado de forma impeditiva;
2. início, centro e fim formam uma progressão anatômica plausível;
3. nativo, arterial, venoso e tardio mostram a mesma região física;
4. T2, DWI e ADC correspondem aproximadamente à mesma região;
5. contraste permite distinguir parênquima, vasos e possível foco;
6. não há PHI, texto ou contorno embutido nas imagens;
7. no caso marcado como fallback, o centro hepático é útil para uma leitura
   negativa mesmo sem candidato focal.

Não é necessário decidir se existe câncer ou interpretar clinicamente o foco.
O gate é exclusivamente de qualidade, alinhamento, continuidade e segurança da
representação.

## Próximo passo após aprovação

Após aprovação humana, implementar e congelar o scorer 4B focal que usa o
endpoint volumétrico existente, executar pilotos críticos com 1, 3 e 5
candidatos e provar tempo total por caso menor ou igual a 180 segundos. Somente
depois disso a v16 poderá ser executada cegamente nos 87 casos.

RAG e GraphRAG permanecem fora do primeiro score visual v16. Eles poderão ser
testados depois, com contexto estático e auditado sobre mimetizadores, caso a
representação focal isolada não atinja o objetivo. Essa separação permite saber
se o ganho veio da evidência visual ou do contexto textual.
