# Comparação A/B de vistas 3D salvas

## Objetivo

Permitir a comparação visual entre duas composições técnicas do mesmo modelo,
como segmentos versus vasos ou candidato isolado versus contexto hepático.

## Fluxo

1. preparar e salvar pelo menos duas vistas;
2. marcar uma vista como **A** e outra como **B**;
3. inspecionar as miniaturas lado a lado;
4. clicar em A ou B para restaurar integralmente essa cena.

Uma terceira vista não pode entrar na comparação enquanto A ou B não for
removida. Excluir uma vista também a remove automaticamente da comparação.

## Privacidade e persistência

As miniaturas:

- são geradas localmente por `renderer.domElement.toDataURL("image/png")`;
- contêm apenas o canvas do modelo 3D;
- não incluem a referência 2D da RM;
- permanecem somente na memória do navegador;
- não são incluídas no payload de aprovação.

O backend persiste apenas `compared_saved_view_ids`, permitindo auditar quais
marcadores foram comparados sem armazenar pixels adicionais.

## Validação real

No caso `c2424a1dd2e1` foram criadas:

```text
A = Vista 1 · Segmentos
B = Vista 2 · Vasos
```

As duas miniaturas foram renderizadas. Ao clicar em A, o visualizador restaurou
a vista Segmentos com câmera, corte, opacidades e oito regiões de Couinaud. Não
houve erro no console.

Validação automatizada:

```text
testes focados: 92 passed
suíte completa: 1530 passed, 3 skipped
```

Evidência visual:

```text
experiments/couinaud_diagnostic_c2424a1dd2e1_v3/
viewer_saved_views_ab_comparison_job_c2424a1dd2e1.png
```

## Segurança do contrato

O backend aceita no máximo dois IDs, exige que sejam distintos e verifica se
ambos pertencem à lista de vistas salvas no mesmo estado de revisão.
