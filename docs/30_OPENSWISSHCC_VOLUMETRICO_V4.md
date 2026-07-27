# OpenSwissHCC v4 — cobertura volumétrica para revisão

Data: 14 de julho de 2026  
Estado: aguardando revisão humana; nenhuma inferência v4 executada

## Objetivo

Aumentar a evidência visual fornecida aos modelos sem usar máscara de lesão,
ground truth, RAG ou treino. A coorte `uniform_9` v3 permanece imutável.

## Implementação

Foram adicionadas configurações separadas para:

- cobertura multifásica RGB completa;
- fallback venoso com cobertura completa;
- fallback venoso de alto contraste com cobertura completa.

Todas usam:

- `panel.strategy=volumetric_blocks`;
- até nove cortes axiais por painel;
- `choice_classification` para futura pontuação contínua;
- zero retry;
- timeout interno máximo de 120 s;
- RAG desligado;
- modo pesquisa e revisão humana obrigatória.

O novo builder:

- exige a revisão v3 assinada como fonte;
- roteia 68 casos para RGB multifásico e 20 para fallback venoso;
- reutiliza somente inputs neutros, máscaras automáticas de fígado e
  alinhamentos já auditados;
- nunca lê labels ou máscaras de lesão;
- exige `covered_liver_voxels == total_liver_voxels`;
- rejeita índices axiais ausentes ou duplicados;
- calcula SHA-256 de cada PNG e da coleção ordenada;
- publica a coorte de forma atômica;
- mantém `eligible_for_inference=false`.

## Resultado da construção

```text
casos: 88
painéis: 561
painéis por caso: mínimo 4, mediana 6, máximo 9
multifásicos RGB: 68 casos / 437 painéis
fallbacks venosos: 20 casos / 124 painéis
metadados PNG: 0
bytes totais: 600.338.548
cohort_signature: f44b7daf5d6f996ff1f45d6de3e18de92a2a6d017f4542652fc3ef94fa1f38ab
```

Dimensões autorizadas:

- RGB: 1536×1152;
- venoso: 1280×960.

Ambas representam grade 4×3 com tiles quadrados e ficam abaixo de quatro
milhões de pixels por painel.

## Galeria

```text
casos/qualification/openswisshcc_v1/prepared/
development_review_gallery_v4_volumetric/index.html
```

Assinatura da galeria:

```text
0c9ce7f2507c18b544c221bd6c3012993eb34d67a38b2d7c38f3abacca393e19
```

A galeria possui 88 seções recolhíveis e 561 imagens com carregamento lazy.
Ela é explicitamente `authoritative_approval=false`.

## O que revisar

Não é necessário julgar presença de HCC ou emitir opinião médica. Em cada
caso, verificar somente qualidade técnica:

1. todos os painéis abrem;
2. o fígado é identificável nos cortes reais;
3. a sequência de painéis parece percorrer o fígado sem salto grosseiro;
4. não há painel inteiramente preto, vazio ou corrompido;
5. no RGB, não há desalinhamento grosseiro entre canais;
6. não há PHI visível gravada nos pixels;
7. espaços vazios no último painel parcial são esperados e não constituem
   falha por si só.

Se houver problema, registrar:

```text
case_id - painel N/M - codigo - observacao
```

Códigos sugeridos:

- `M`: desalinhamento multifásico grosseiro;
- `C`: enquadramento/corte do fígado inadequado;
- `Q`: qualidade/contraste insuficiente;
- `P`: PHI visível;
- `I`: imagem ausente ou corrompida.

## Testes

A etapa terminou com 423 testes aprovados. Os testes novos cobrem:

- cobertura exata e dois painéis para uma máscara de 14 cortes;
- hash e ordem de toda a coleção;
- detecção de alteração em painel não-preview;
- rejeição de ground truth no manifesto neutro;
- reuso somente de cache completo e íntegro;
- publicação atômica da coorte;
- galeria não autoritativa com todos os links;
- preservação dos candidatos baseline e fallbacks `uniform_9`.

## Próximo gate

Depois da revisão humana:

1. gerar manifesto volumétrico assinado com todos os hashes;
2. congelar configs, prompts e regra de agregação;
3. executar primeiro scores MedSigLIP e MedGemma sem labels;
4. validar tempo total por exame, com teto de 180 s;
5. somente então anexar labels do desenvolvimento aberto;
6. não baixar nem abrir o holdout enquanto a regra não estiver estável.

