# Materiais orgânicos das estruturas do visualizador 3D

Data: 2026-08-10
Estado: implementado e aguardando aprovação visual para se tornar o padrão fixo

## Alteração

As cores convencionais brilhantes foram substituídas, no preset Tecido realista, por materiais orgânicos com paleta dessaturada, variação tonal determinística, maior rugosidade e reflexo superficial moderado.

Paleta aplicada:

- fígado: vermelho-acastanhado;
- veia porta/esplênica: azul-esverdeado vascular;
- veia cava inferior: azul profundo dessaturado;
- vesícula: verde-oliva;
- candidato automático: ocre/âmbar orgânico;
- região classificada: azul-petróleo translúcido, exibido sob demanda;
- lesão presente no manifesto: vinho-avermelhado.

## Limite semântico

O candidato e a região classificada continuam sendo sobreposições de revisão. O tratamento reduz a aparência artificial, mas não tenta fazê-los parecer uma lesão confirmada. Isso preserva a separação entre anatomia segmentada e hipótese automática.

## Validação

- 81 testes de presets e webapp aprovados;
- sintaxe JavaScript validada;
- materiais originais continuam restauráveis;
- nenhuma leitura de máscara ou inferência foi adicionada;
- captura: `experiments/segmentation_shadow_smoke_liverhccseg_v2/viewer_realistic_organic_structures_job_c2424a1dd2e1.png`.
