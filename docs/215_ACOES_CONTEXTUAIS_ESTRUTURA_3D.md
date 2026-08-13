# Ações contextuais da estrutura 3D

## Objetivo

Dar continuidade ao plano de melhoria do visualizador sem alterar segmentação,
inferência ou os artefatos anatômicos. A estrutura selecionada diretamente no
modelo passa a oferecer ações de inspeção reproduzíveis.

## Implementação

Foram adicionadas três ações ao painel **Estrutura selecionada**:

- **Focar estrutura**: calcula o `bounding sphere` da malha em coordenadas de
  mundo e enquadra a câmera preservando a direção corrente de observação.
- **Isolar estrutura**: oculta as outras malhas e sincroniza os controles de
  visibilidade, sem criar ou alterar geometria.
- **Restaurar contexto**: recupera o preset autorizado que estava ativo antes
  do isolamento e mantém a estrutura selecionada quando ela faz parte desse
  contexto.

O estado de revisão agora registra:

- `active_view="focus"` quando a câmera foi enquadrada em uma estrutura;
- `selected_role` com o papel da malha selecionada;
- `selection_isolated` indicando se a revisão ocorreu com a estrutura isolada.

Esses campos são apenas de auditoria visual. Eles não chegam ao MedGemma, não
alteram o relatório clínico e não modificam a classificação.

## Segurança funcional

- Apenas papéis já declarados no `viewer_manifest.json` podem ser selecionados.
- O isolamento opera exclusivamente sobre as malhas já carregadas.
- A restauração usa somente presets previamente definidos no código.
- A ação de foco não faz novas requisições e não altera a geometria.
- A aprovação humana continua bloqueada até o carregamento integral do modelo.

## Validação

Validação automatizada:

```text
tests/test_viewer_presets.py + tests/test_webapp.py: 88 passed
suíte completa: 1526 passed, 3 skipped
```

Validação visual no caso real `c2424a1dd2e1`:

1. seleção direta do fígado e sincronização com a referência 2D;
2. foco com confirmação textual;
3. isolamento com somente `orgao` marcado como visível;
4. restauração do preset `default` com `orgao`, `candidato`,
   `vesicula_biliar`, `veia_porta_esplenica` e `veia_cava_inferior` visíveis;
5. nenhum erro no console do navegador.

Evidência visual:

```text
experiments/couinaud_diagnostic_c2424a1dd2e1_v3/
viewer_structure_context_actions_job_c2424a1dd2e1.png
```

## Resultado

A inspeção deixou de depender apenas dos controles extensos da lista. O revisor
agora pode selecionar uma estrutura no modelo, aproximá-la, examiná-la isolada
e retornar à composição anatômica anterior com uma ação explícita e auditável.
