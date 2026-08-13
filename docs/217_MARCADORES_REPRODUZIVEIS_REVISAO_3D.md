# Marcadores reproduzíveis da revisão 3D

## Objetivo

Permitir que o revisor guarde estados relevantes da inspeção e retorne a eles
sem reconstruir manualmente câmera, corte e composição.

## Estado capturado

Cada marcador registra:

- identificador e rótulo determinísticos;
- câmera e alvo orbital em milímetros;
- preset e perfil material;
- vista anatômica ativa;
- estrutura selecionada e estado de isolamento;
- estruturas visíveis e opacidade por papel;
- orientação e índice da referência 2D;
- sincronização 2D/3D;
- eixo, posição, inversão e ativação do corte.

O limite é de oito marcadores por revisão. Eles permanecem no navegador durante
a revisão e são enviados dentro de `viewer_state.saved_views` quando a decisão
humana é registrada.

## Restauração

A restauração valida os papéis contra as malhas carregadas e reaplica:

```text
materiais → opacidades/visibilidade → referência 2D → corte → câmera → seleção
```

Selecionar uma vista salva não executa inferência e não modifica os artefatos
do caso.

## Validação

No caso real `c2424a1dd2e1`:

1. a vista Segmentos foi salva;
2. a cena foi alterada para Vasos;
3. o marcador foi reaberto;
4. os oito segmentos e dois vasos foram restaurados;
5. câmera, corte e opacidades retornaram ao estado salvo;
6. o texto da vista voltou corretamente para o atlas de Couinaud;
7. nenhum erro foi registrado no console.

Validação automatizada consolidada:

```text
testes focados: 90 passed
suíte completa: 1528 passed, 3 skipped
```

Evidência visual:

```text
experiments/couinaud_diagnostic_c2424a1dd2e1_v3/
viewer_anatomical_views_and_bookmarks_job_c2424a1dd2e1.png
```

## Validação do backend

O backend rejeita:

- mais de oito marcadores;
- identificadores fora do padrão `view-NNN`;
- papéis ausentes do manifesto;
- câmera não finita ou fora do limite técnico;
- opacidades fora do intervalo `[0, 1]`;
- identificadores duplicados.
