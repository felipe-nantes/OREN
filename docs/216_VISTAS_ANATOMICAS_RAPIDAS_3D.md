# Vistas anatômicas rápidas no visualizador 3D

## Objetivo

Reduzir a quantidade de ajustes manuais necessários para revisar as principais
camadas do modelo, mantendo composições previsíveis e sem alterar qualquer
malha, segmentação ou resultado de inferência.

## Vistas implementadas

- **Fígado**: preset padrão, superfície hepática sólida e foco no órgão.
- **Segmentos**: Couinaud I–VIII sólidos e referências vasculares.
- **Vasos**: fígado translúcido e foco nas estruturas vasculares.
- **Candidato**: composição de triagem e foco na região automática não
  confirmada.

Cada botão verifica se a anatomia necessária existe no manifesto. Uma vista é
desabilitada quando sua estrutura não está disponível; não há fabricação de
geometria nem fallback visual enganoso.

## Comportamento

Ao aplicar uma vista:

1. o preset autorizado correspondente é aplicado;
2. o corte ortogonal de inspeção é desligado para mostrar a anatomia completa;
3. a união das malhas-alvo é calculada localmente;
4. a câmera enquadra essa união preservando a direção corrente;
5. o estado `active_anatomical_view` é registrado para auditoria.

## Validação real

No caso `c2424a1dd2e1`, a vista **Segmentos** apresentou exatamente:

```text
couinaud_i ... couinaud_viii
veia_porta_esplenica
veia_cava_inferior
```

A vista **Vasos** apresentou as estruturas vasculares com o fígado translúcido
como contexto. Não houve erros no console.

## Segurança

- Sem novas chamadas HTTP de inferência.
- Sem uso de labels ou máscaras de lesão ocultas.
- Sem modificação dos STLs ou do manifesto.
- Presets e nomes de vistas são uma enumeração fixa no código e no backend.
