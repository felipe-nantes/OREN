# OpenSwissHCC v16 — piloto temporal e gate humano

Data: 2026-07-16  
Estado: galeria temporal pronta; revisão humana pendente  
Holdout: fechado  
Classificação do desenvolvimento: exploratória

## 1. Aprovação do fallback original

A galeria fallback v16 v2 foi aprovada explicitamente pelo revisor `jm`.

Registro assinado:

`casos/qualification/openswisshcc_v1/prepared/development_reviews_v16/candidate_volume_unregistered_fallback3_v2_review.json`

Vínculo criptográfico:

- assinatura da revisão: `08d917b92328b6b237f8c8185f8c564c0adf7b1a977dfabb653855b6841227c9`;
- SHA-256 da coorte: `d4ecdf7980d46be8e59625aeaeb9b6c4f097379f757fc2bf2b222bd42ae5b5cd`;
- casos: 3;
- stacks: 6;
- ground truth lido: não;
- holdout aberto: não.

## 2. Por que não iniciar o full87 imediatamente

O plano v16 exige demonstrar primeiro que o pior cenário de execução cabe no gate de 180 segundos. Executar 87 casos antes desse teste poderia desperdiçar inferência e produzir um protocolo operacionalmente inviável.

O plano temporal assinado escolheu deterministicamente o caso com maior tempo técnico conhecido em cada cenário:

1. fallback sem candidato;
2. um candidato;
3. três candidatos;
4. cinco candidatos.

Nenhum label foi usado na seleção.

## 3. Galeria dos quatro casos críticos

Artefato:

`casos/qualification/openswisshcc_v1/prepared/development_review_gallery_v16_timing4_v1`

Propriedades:

- casos: 4;
- stacks: 10, distribuídos como 1/1/3/5;
- frames: 290;
- 29 frames por stack;
- arquivos publicados: 306;
- maior caminho absoluto: 218 caracteres;
- assinatura da galeria: `ae2be4a1869dcd771e6c473dc9dab3242ba0efd651d697db37d79fc035602b03`;
- SHA-256 da coorte: `99025d639bd78117a6a240960a3ec08431424a885a57ce531e5a3b0095829cf6`;
- modo dinâmico: `registered_to_venous`;
- inferência executada: não;
- ground truth lido: não;
- holdout aberto: não;
- revisão humana: pendente.

Casos e cenários:

- `anon-openswiss-3ccae581c20d8685`: fallback, 1 stack;
- `anon-openswiss-0b899ac38ea25c6d`: um candidato, 1 stack;
- `anon-openswiss-bd571089c6a5d00f`: três candidatos, 3 stacks;
- `anon-openswiss-5e91365aca1943ec`: cinco candidatos, 5 stacks.

## 4. Reuso visual comprovado

O caso `anon-openswiss-bd571089c6a5d00f` já fazia parte do piloto v16 aprovado. O hash do manifesto mudou porque foram acrescentados campos explícitos de modo de alinhamento, mas a comparação técnica mostrou:

- 87 frames antes e depois;
- nomes e SHA-256 de todos os PNGs idênticos;
- papéis e fontes idênticos;
- seleção candidata idêntica;
- hashes das fontes idênticos.

Mesmo assim, a galeria temporal completa continuará exigindo aprovação vinculada ao bundle de quatro casos.

## 5. O que avaliar

Para cada stack:

1. o ROI contém fígado e não está deslocado;
2. os cortes início/centro/fim têm continuidade;
3. T1 nativo, arterial registrado, venoso e tardio registrado correspondem à mesma região;
4. T2, DWI trace e ADC são anatomicamente comparáveis;
5. há contraste suficiente;
6. não há PHI, texto clínico, contorno ou máscara de lesão;
7. o fallback no centro hepático é tecnicamente utilizável;
8. os candidatos adicionais dos cenários 3 e 5 não apresentam crop/FOV quebrado.

Esta é uma revisão técnica, não diagnóstica. Não se deve procurar ou inferir o ground truth.

## 6. Próximo passo após aprovação

Após uma aprovação explícita:

1. registrar revisão assinada vinculada ao bundle temporal;
2. congelar o protocolo de scoring 4B;
3. regenerar cada caso em diretório temporário e exigir igualdade dos hashes com o bundle aprovado;
4. executar exatamente uma chamada por stack, sem retry automático;
5. medir renderização, scoring e tempo ponta a ponta;
6. invalidar qualquer caso acima de 180 segundos ou com falha parcial;
7. somente se todos passarem, construir e revisar o bundle full87.

Nenhuma acurácia é calculada nesta etapa.

## 7. Validação de código

Após adicionar o construtor, a CLI e os testes do bundle temporal, a suíte completa do ARGOS reportou:

- `637 passed`;
- `0 failed`;
- `389 warnings` de depreciação já conhecidos;
- duração: `40.78 s`.