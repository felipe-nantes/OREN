# Evidence Hierarchy and Human Authority

Este documento governa como o ARGOS/OREN transforma fontes, comportamento observado e inferências em decisões de engenharia. Ele não cria alegações clínicas.

## Hierarquia obrigatória L1–L6

1. **L1 — standard ou documentação normativa/oficial aplicável**: seção e versão identificáveis. Uma documentação oficial de biblioteca é autoritativa somente sobre a API/semântica daquela biblioteca; um paper é referência metodológica, não cria por si só política do projeto.
2. **L2 — scientific contract explicitamente aprovado/documentado pelo projeto**: decisão ratificada, versionada, com fonte, responsável e racional.
3. **L3 — specification/invariant test explicitamente aprovado**: implementação executável de um contrato identificado.
4. **L4 — implementação e documentação atuais**: evidência do estado do sistema e de claims declarados, não prova automática de correção.
5. **L5 — characterization test**: comportamento observado congelado temporariamente, possivelmente defeituoso.
6. **L6 — inferência do agente**: hipótese a verificar; nunca promove a si própria.

Um nível inferior não pode sobrescrever silenciosamente um nível superior. Papers e livros entram como referências especializadas com autoridade declarada nos cartões, mas não constituem um sétimo nível nem substituem decisão L2.

Norma legal/regulatória aplicável, quando identificada por autoridade competente, deve ser tratada acima de contratos internos. Ela não é inventada pelo agente.

## Classes semânticas obrigatórias

- `OBSERVED_BEHAVIOR`: o código atual faz isto; pode estar errado.
- `SOFTWARE_CONTRACT`: regra de API, estado, atomicidade, integridade ou erro.
- `GEOMETRIC_CONTRACT`: regra sobre espaço físico, coordenadas, grade ou transformação.
- `SCIENTIFIC_CONTRACT`: decisão metodológica congelada e aprovada.
- `DOMAIN_POLICY`: decisão operacional pertencente ao responsável científico.
- `CLINICAL_CLAIM`: diagnóstico, prognóstico, tratamento, segurança ou validade clínica; fora da autoridade do agente.

Nunca converter `OBSERVED_BEHAVIOR` em `SCIENTIFIC_CONTRACT` porque existe um assert ou snapshot.

## Resolução de conflito

1. Cite a fonte, URL/seção, contrato e comportamento atual.
2. Verifique se as fontes falam da mesma camada: padrão, API, método, política interna ou clínica.
3. Uma documentação de biblioteca não pode sobrescrever DICOM; um teste existente não pode sobrescrever um contrato aprovado; um paper não escolhe automaticamente a política do produto.
4. Se a correção exigir alterar semântica científica, interrompa a aplicação, produza testes e opções e solicite decisão humana.
5. Registre a decisão, o responsável, a data, o racional e os testes afetados.

## Gates de autoridade

| Risco | Exemplos | Autoridade do agente | Gate |
|---|---|---|---|
| Baixo | nomes locais, helpers puros, typing, imports mortos, duplicação mecânica, código inalcançável demonstrado | pode aplicar em branch | suíte focal + global |
| Médio | cache, serialização, I/O, retry, concorrência, performance, interfaces, troca equivalente de API | somente proposta até aprovação | operador + integração + mutação |
| Alto científico | seleção DICOM, orientação, registration, resampling, interpolação, máscaras, preprocessing, folds, thresholds, denominadores, labels, métricas e cleanup 3D quantitativo | diagnóstico, testes e patch proposto | aprovação explícita + scientific regression |
| Fora da autoridade | diagnóstico, prognóstico, terapia, threshold clínico, segurança/validade clínica e mudança da pergunta científica | nunca decide | especialista/autoridade humana |

## Contracts-before-refactoring

Antes de alterar qualquer módulo:

1. identificar inputs, outputs e efeitos colaterais;
2. classificar o risco;
3. listar comportamento observado e contratos separadamente;
4. escrever characterization tests quando necessários;
5. escrever testes de especificação, invariantes e negativos;
6. usar property tests para propriedades gerais;
7. usar integração para geometria, I/O e pipeline;
8. executar branch coverage, análise estática e mutation testing quando viável;
9. demonstrar que os testes discriminam defeitos;
10. propor uma única mudança semântica;
11. cumprir o gate humano;
12. executar suíte focal/global, regressão e benchmark pertinente;
13. registrar evidências e decisão.

## Proteção de thresholds e constantes

Thresholds, mappings, labels, agrupamentos, inclusão/exclusão, revisão de modelo, dimensão, normalização, espaço de busca, agregação, denominadores, bootstrap e cleanup quantitativo são contratos de alto risco quando afetam o desenho científico.

O agente pode informar localização, valor atual, efeito, evidência, alternativas e testes afetados. Não pode alterar o valor porque “parece melhor” ou melhora uma métrica. A decisão pertence ao operador.

## Pacote mínimo de evidências por patch

- `CHANGE_ID`;
- módulo e rotas afetadas;
- risco;
- comportamento atual;
- IDs e classes de contrato;
- fontes e seções;
- testes antes/depois;
- branch coverage pertinente;
- mutation survivors relevantes;
- benchmark quando aplicável;
- mudança aplicada ou apenas proposta;
- impacto científico possível;
- decisão necessária;
- responsável pela aprovação.

## Regra final

O papel do agente é reduzir incerteza e produzir evidência reproduzível. A aprovação humana não é formalidade: ela é a autoridade semântica para políticas científicas e a única rota para decisões clínicas.
