# OpenSwissHCC v17 — atlas axial 2×2

## Estado

O piloto técnico cego v17 foi gerado para 10 casos de desenvolvimento e aprovado
pelo revisor `jm`. O atlas full87 também foi gerado com a mesma assinatura e
passou na auditoria técnica. Ele ainda **não está liberado para inferência**:
faltam a auditoria retrospectiva de cobertura e o congelamento do leitor 4B.

Assinatura congelada do protocolo:

```text
0c7627a0fda29fdd1e95bb80213ab62da058a17d8c4283ec5b73a3fc99abd89e
```

O holdout permaneceu fechado. Labels e máscaras de lesão não foram lidos.

Registro assinado da aprovação do piloto:

```text
revisor:           jm
casos:             10
frames revisados:  148
status:            approved_for_full87_generation
review_signature:  711f1b6e37989fa91404aaa09c908ac231c1db90b1e65361757ef3b9242a5ded
observação:         itens 7 e 8 são fallback venoso esperado em escala de cinza
```

## Motivo da v17

A auditoria retrospectiva da v16 mostrou dois gargalos independentes:

1. a pilha focal v16 tornava alguma lesão visível em apenas 23 de 37 casos
   positivos com máscara venosa disponível (62,16%);
2. mesmo quando a lesão estava na evidência, o leitor 4B ainda não a classificava
   de forma confiável.

A v17 ataca primeiro o gargalo de cobertura visual. Em vez de escolher uma
região candidata, ela apresenta **todos os cortes axiais que contêm fígado**.
Cada quadro contém apenas quatro cortes, aumentando a área visual de cada corte
em comparação com o painel 4×3 original.

## Construção cega

A fonte é o coorte volumétrico v4 já aprovado visualmente. Para cada caso:

1. o hash de todo painel-fonte é verificado;
2. o manifesto deve provar cobertura hepática exata de 100%;
3. somente tiles axiais que contam para cobertura são aceitos;
4. cada tile é recortado sem interpolação e inserido, em ordem crescente, em uma
   grade 2×2;
5. cada índice axial deve aparecer exatamente uma vez;
6. quadrantes restantes do último quadro são pretos e não contam como evidência;
7. o caso inteiro deve caber no máximo congelado de 32 quadros.

Os painéis-fonte aprovados usam tiles nativos de 320×320 ou 384×384 pixels. A
v17 preserva essa resolução e, portanto, produz quadros de 640×640 ou 768×768
pixels. Não há resize, interpolação, nova segmentação nem uso de máscara de
lesão.

## Resultado técnico do piloto

```text
casos:                       10
cortes axiais:              575
quadros 2×2:                148
quadros 768×768:            117
quadros 640×640:             31
quadrantes vazios finais:    17
multifásicos RGB:              8 casos
fallback venoso:               2 casos
gates técnicos:              10/10 aprovados
erros na auditoria de hash:    0
```

## Expansão full87

A expansão foi feita somente depois da aprovação humana do piloto:

```text
casos:                       87
cortes axiais:            4.652
quadros 2×2:              1.194
máximo por caso:             20 (limite congelado: 32)
quadros 768×768:             942
quadros 640×640:             252
quadrantes vazios finais:    124
multifásicos RGB:             68 casos
fallback venoso:              19 casos
gates técnicos:              87/87 aprovados
casos piloto idênticos:       10/10 por atlas_set_sha256
erros na auditoria:            0
```

Durante a primeira tentativa do full87, um lock transitório do Windows impediu
o rename atômico do diretório de um caso. O coorte não foi publicado
parcialmente. A publicação recebeu retry exponencial limitado, coberto por
teste, e a execução completa seguinte foi aprovada sem modificar pixels ou a
assinatura do protocolo.

Artefatos:

```text
casos/qualification/openswisshcc_v1/prepared/
  development_candidate_v17_axial_atlas_pilot10_v1/
  development_review_gallery_v17_axial_atlas_pilot10_v1/
  development_reviews_v17/axial_atlas_pilot10_v1_review.json
  development_candidate_v17_axial_atlas_full87_v1/
  development_review_gallery_v17_axial_atlas_full87_v1/
```

## O que o revisor deve avaliar

Em todos os frames dos 10 casos:

1. os quatro quadrantes mostram cortes axiais consecutivos e coerentes;
2. o fígado permanece legível, sem crop novo que corte sua anatomia;
3. o contorno hepático e a fusão de fases, quando presentes, continuam coerentes;
4. os casos de fallback venoso continuam interpretáveis em escala de cinza;
5. quadrantes pretos aparecem somente no final do caso;
6. não há PHI, label diagnóstico ou contorno/marcação de lesão.

O gate humano deve registrar aprovação/reprovação e revisor. Uma reprovação
deve indicar caso e frame.

## Próximos passos

1. executar auditoria retrospectiva autorizada somente no desenvolvimento para
   confirmar que todo corte com lesão está incluído;
2. congelar prompt e schema de resposta do leitor 4B para uma única chamada
   volumétrica por caso;
3. medir latência antes de abrir novamente os labels de desenvolvimento;
4. avaliar sensibilidade e especificidade do desenvolvimento;
5. manter o holdout fechado até haver protocolo final capaz de sustentar a meta.

A autorização anterior para máscaras foi específica da auditoria v16. Para
preservar a trilha metodológica, a auditoria real v17 exige autorização explícita
separada. Até lá, o código pode ser testado apenas com dados sintéticos.

Cobertura de corte não é sinônimo de detecção. Mesmo com 100% do eixo hepático
representado, a v17 só será útil se o 4B reconhecer a lesão dentro do limite de
180 segundos. Não há declaração de ganho de acurácia nesta etapa.

## Implementação e testes

Arquivos:

```text
dtwin/benchmark/openswisshcc_axial_atlas.py
tools/build_openswisshcc_axial_atlas_v17.py
tests/test_openswisshcc_axial_atlas.py
```

A suíte específica cobre: quantidades variadas de cortes, ordem e nomes
determinísticos, resolução nativa 4×3, quadrantes vazios, adulteração de hash,
índices ausentes/duplicados, gate de cobertura-fonte, limite de frames,
publicação atômica, cegamento do coorte e integridade da galeria.
