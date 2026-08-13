# Sincronização bidirecional: seleção 3D para referência 2D

## Objetivo

Completar a correlação espacial entre o modelo e a RM. A sincronização anterior posicionava o corte 3D a partir de uma referência 2D; esta etapa adiciona o caminho inverso.

## Funcionamento

Ao selecionar uma estrutura visível no 3D:

1. a caixa física da geometria é calculada;
2. seu centro é obtido nas coordenadas LPS originais da malha;
3. é usado o eixo da orientação 2D atualmente ativa:
   - axial → Z;
   - coronal → Y;
   - sagital → X;
4. o visualizador procura o frame com `position_lps_mm` mais próximo;
5. a referência 2D navega para esse frame;
6. se a sincronização estiver habilitada, o corte 3D é colocado na mesma coordenada.

Não são utilizados rótulos, máscaras adicionais, inferência ou informação clínica para escolher o plano.

## Comportamento seguro

- Frames sem coordenada LPS são ignorados.
- Se nenhuma referência válida estiver disponível, a seleção 3D continua funcionando sem navegação 2D.
- A sincronização desativada permite mover apenas a referência, sem ativar o corte.
- A interface informa estrutura, centro LPS, número do plano e estado do corte.
- Os campos já existentes `reference_view` e `reference_frame_index` preservam a posição resultante na auditoria.

## Validação real

Caso `c2424a1dd2e1`, seleção da veia porta/esplênica:

- referência axial antes: índice de slider `26`, plano 27/54;
- centro da estrutura: `21,1 mm LPS` no eixo Z;
- referência selecionada: índice de slider `22`, plano 23/54, posição `21,9 mm LPS`;
- corte ortogonal ativado na mesma região;
- painel de identificação permaneceu coerente;
- **130 testes aprovados**.

Captura:

`experiments/couinaud_diagnostic_c2424a1dd2e1_v3/viewer_bidirectional_3d_to_2d_sync_job_c2424a1dd2e1.png`

## Escopo

A funcionalidade é uma ferramenta de navegação e revisão humana. Não altera a segmentação, a classificação ou a interpretação médica do exame.
