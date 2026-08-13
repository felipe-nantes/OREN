# Identificação interativa das estruturas 3D

## Objetivo

Permitir que o revisor identifique diretamente uma estrutura visível no modelo, sem depender apenas da lista lateral e sem transformar a visualização em diagnóstico automático.

## Funcionamento

- Um clique curto sobre uma superfície visível seleciona a malha atingida.
- Arrastar para rotacionar não seleciona estruturas.
- A estrutura recebe destaque emissivo verde temporário, preservando sua cor anatômica.
- Um clique no espaço vazio ou o botão **Limpar seleção** remove o destaque.
- Troca de preset, ocultação ou isolamento incompatível também limpa a seleção.
- Com o fígado sólido, estruturas internas ocluídas não podem ser selecionadas através da superfície.
- Ao reduzir a opacidade hepática, o raycast pode alcançar a primeira estrutura interna visível.

## Painel de identificação

O painel mostra somente dados já presentes no `viewer_manifest.json`:

- nome;
- categoria anatômica ou funcional;
- volume da máscara fonte;
- área de superfície;
- número de triângulos;
- desvio p95 da reconstrução para a máscara;
- condição fechada/manifold;
- alertas técnicos.

O painel declara explicitamente que essas métricas medem fidelidade à máscara fonte, não acurácia anatômica. Candidato, lesão e região classificada recebem ainda o aviso de que a camada não confirma diagnóstico.

## Compatibilidade com a régua

O clique de seleção e o clique de medição usam modos mutuamente definidos:

- régua desligada: clique identifica estrutura;
- régua ligada: clique marca pontos de medição e não muda a seleção atual.

Na validação real, a veia porta/esplênica permaneceu selecionada enquanto uma distância era medida.

## Auditoria

O campo opcional `viewer_state.selected_role` é persistido na revisão. O backend aceita somente identificadores simples com até 64 caracteres, rejeitando caminhos ou valores arbitrários.

## Validação

Caso `c2424a1dd2e1`:

- clique selecionou corretamente `Veia porta e esplênica`;
- painel exibiu 27,2 mL, 98,9 cm², 46.548 triângulos, p95 de 1,48 mm e malha fechada;
- destaque visual aplicado e removível;
- régua permaneceu independente;
- backend reiniciado com o novo contrato;
- **129 testes aprovados**.

Captura:

`experiments/couinaud_diagnostic_c2424a1dd2e1_v3/viewer_direct_structure_selection_job_c2424a1dd2e1.png`

## Escopo

Não há nova inferência, leitura de máscara, alteração de segmentação ou decisão clínica. A feature é exclusivamente de exploração e auditoria humana.
