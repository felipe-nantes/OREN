# OpenSwissHCC v22 — fundação de realce multifásico

## Motivação

O holdout v21 atingiu 83,33% de sensibilidade e 35,00% de especificidade. A
auditoria mostrou que o problema não pode ser resolvido apenas com outro limiar:
os sinais dominantes do MedGemma e MedSigLIP ficaram próximos do acaso, e o
localizador produziu candidato em 42/44 casos.

O v22 começa por uma etapa sem inferência: verificar se o comportamento
temporal arterial/venoso/tardio contém sinal discriminativo reproduzível antes
de construir novos painéis ou gastar chamadas do 4B.

## Implementação inicial

O módulo `dtwin/benchmark/openswisshcc_enhancement_maps.py`:

- aceita somente T1 venoso, máscara hepática automática e fases arterial e
  tardia previamente registradas para a geometria venosa;
- valida tamanho, hashes, raiz, geometrias e manifestos;
- rejeita qualquer papel ou caminho com termos de label, ground truth ou lesão;
- normaliza cada fase por mediana e escala robusta dentro do fígado;
- calcula realce arterial relativo, arterial contra venoso, arterial contra
  tardio, venoso contra tardio e um mapa conjunto determinístico;
- produz quantis, frações acima de limiares predefinidos e componentes conexos;
- não recebe labels, não lê máscaras de lesão e não chama MedGemma;
- publica atomicamente `features.jsonl` e `summary.json`.

Os 87 casos do full87 permanecem na ordem congelada. Os 84 casos registrados
são elegíveis para features; os três fallbacks não registrados são mantidos
explicitamente como indisponíveis, nunca excluídos silenciosamente.

## Próximo gate

1. executar os testes focais e a suíte completa;
2. gerar as features cegas nos 87 casos;
3. somente depois juntar os labels de desenvolvimento já autorizados;
4. medir ROC-AUC e validação aninhada sem consultar o holdout consumido;
5. continuar para painéis/mapas v22 apenas se houver sinal superior aos
   componentes v21 e estabilidade por subgrupo;
6. manter todas as máscaras de lesão fora da inferência e do MedGemma.

## Resultado formal da hipótese global v22

O bundle cego foi publicado para os 87 casos de desenvolvimento. O realce
multifásico ficou disponível em 84 casos registrados (39 positivos e 45
negativos); os três fallbacks sem registro foram declarados indisponíveis, sem
exclusão silenciosa. O arquivo de features tem SHA-256
`acfbea6b2b5f4609dbcb268e01ad2157deafca65cc3df065844f0367aa8a2d84`.

Os labels de desenvolvimento foram anexados somente depois da geração das
features. A melhor variável foi `arterial_over_venous_maximum`, com direção
invertida (`lower_is_positive`):

- ROC-AUC direcional: 0,6091;
- sensibilidade no melhor ponto de equilíbrio: 61,54%;
- especificidade no mesmo ponto: 64,44%;
- nenhum limiar aparente atingiu simultaneamente 75%/75%;
- validação aninhada não foi executada porque o gate exploratório já falhou;
- o holdout v21 consumido não foi usado para seleção;
- nenhuma máscara pública de lesão foi lida;
- nenhuma chamada ao MedGemma foi realizada.

Portanto, o realce calculado globalmente sobre o fígado foi encerrado como
hipótese negativa. O resultado sugere diluição do sinal focal por parênquima e
vasos. A continuação permitida é testar as mesmas relações temporais apenas nas
regiões candidatas cegas produzidas pelo localizador. Essa continuação deverá
ser novamente interrompida antes do 4B se não superar o gate exploratório.

## Resultado do recorte por candidatos v22-b

Foi implementado o algoritmo
`model-candidate-dynamic-context-5mm-v1`. A normalização continua usando o
fígado automático inteiro, mas as medidas são restritas a:

- núcleo da máscara candidata derivada do TotalSegmentator;
- contexto físico de 5 mm;
- contraste entre núcleo e anel periférico;
- relações arterial/venosa/tardia e padrão conjunto de APHE/washout.

O bundle foi fechado antes da leitura dos labels, preservou casos sem candidato
e registrou explicitamente candidatos fora do campo de visão multifásico. Foram
processados 84 casos registrados e mantidos três fallbacks indisponíveis. O
SHA-256 das features é
`58452fbbc8cd2b9d1db7ceef77201473943c27ce3dbca0172bcb1aad085b48ef`.

A melhor feature foi `joint_enhancement_core_minus_shell_mean`:

- ROC-AUC: 0,7858;
- sensibilidade no melhor ponto de equilíbrio: 71,79%;
- especificidade no mesmo ponto: 75,56%;
- nenhum limiar aparente atingiu simultaneamente 75%/75%.

Combinações logísticas exploratórias com 4, 5 e 42 features foram avaliadas
fora da amostra em 7 folds. A melhor AUC foi 0,7610, mas o melhor mínimo entre
sensibilidade e especificidade permaneceu em 69,23%. Assim, nenhum calibrador
foi congelado e nenhuma chamada ao 4B foi autorizada por esse gate.

O cruzamento retrospectivo com a auditoria de máscaras venosas de
desenvolvimento mostrou que 10 dos 11 falsos negativos não tinham interseção
entre o candidato automático e a lesão anotada. Apenas um falso negativo tinha
candidato atingindo a anotação. O próximo gargalo é, portanto, o recall do
localizador venoso (56,76% por caso na auditoria v16), não o classificador.
