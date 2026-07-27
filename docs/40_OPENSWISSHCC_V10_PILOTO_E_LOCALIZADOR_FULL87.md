# OpenSwissHCC v10 — piloto A/B e localizador na coorte de desenvolvimento

## Estado desta etapa

Esta etapa é de desenvolvimento experimental e não constitui qualificação clínica.
O holdout permaneceu fechado em todas as operações descritas aqui.

Foram concluídas duas atividades distintas:

1. avaliação exploratória autorizada de 10 casos de desenvolvimento, após a inferência cega;
2. execução cega do localizador de lesões em todos os 87 casos primários de desenvolvimento.

Os labels protegidos dos outros 77 casos não foram abertos. O run completo de 87 casos
continua com `ground_truth_read=false`, `metrics_calculated=false` e `final_decision=null`.

## Avaliação exploratória dos 10 casos

O piloto continha 4 casos positivos e 6 negativos. A melhor feature exploratória foi:

```text
log1p(total_candidate_volume_mm3)
```

Resultado LOOCV observado:

| Medida | Resultado |
|---|---:|
| Sensibilidade | 75,00% (3/4) |
| Especificidade | 83,33% (5/6) |
| Acurácia balanceada | 79,17% |
| Falsos negativos | 1 |
| Falsos positivos | 1 |

Intervalos de confiança de Wilson de 95%:

- sensibilidade: 30,06% a 95,44%;
- especificidade: 43,65% a 96,99%.

Em 50 repetições estratificadas, 44 atingiram simultaneamente 75% de sensibilidade e
75% de especificidade. O resultado não qualifica o sistema porque dez casos são
insuficientes e os intervalos de confiança são muito amplos.

As features derivadas das quatro perguntas do MedGemma 1.5 4B não sustentaram o gate
75/75 no piloto. O melhor desempenho apareceu no volume determinístico do localizador,
e não na resposta do modelo multimodal. Portanto, executar o 4B em toda a coorte antes
de confirmar esse sinal seria consumo desnecessário de tempo e energia.

Artefato:

```text
casos/qualification/openswisshcc_v1/evaluation/
dev_v10_localizer_roi_ab_pilot10/evaluation.json
```

SHA-256: `d72923e065daaced765b6fb631a642f5fb8251b1afe333f65aa34d78b475aa05`.

## Execução cega do localizador em 87 casos

### Fragilidade encontrada e correção

O runner original publicava a coorte inteira somente no final. Uma falha no último caso
apagaria todo o staging. Foi criada uma execução retomável baseada no plano cego assinado
já existente:

- 11 blocos determinísticos;
- 10 blocos com 8 casos e um bloco com 7 casos;
- publicação atômica por bloco;
- retomada por presença de bloco final válido;
- consolidação atômica separada;
- validação de casos planejados, hashes, versão do modelo e flags de segurança;
- rejeição de casos ausentes, extras, duplicados ou adulterados.

Na primeira tentativa do bloco 1, o Windows rejeitou o nome temporário do NIfTI por
comprimento de caminho. O bloco abortou antes de publicar qualquer resultado. A correção
encurtou somente os nomes internos de staging e de arquivo temporário; nomes finais,
conteúdo, hashes e metodologia permaneceram inalterados.

### Resultado técnico

| Medida | Resultado |
|---|---:|
| Casos processados | 87/87 |
| Blocos publicados | 11/11 |
| Falhas técnicas após a correção | 0 |
| Casos com algum candidato | 80 |
| Casos sem candidato | 7 |
| Tempo médio do localizador | 28,35 s |
| Maior tempo por caso | 41,92 s |
| Casos dentro de 90 s | 87/87 |
| Soma do tempo de parede dos blocos | 2.467,53 s |

O número 80/87 não é sensibilidade, positividade clínica nem acurácia. Ele significa apenas
que o modelo de localização produziu pelo menos um voxel candidato dentro da máscara do
fígado em 80 exames.

Modelo executado:

```text
TotalSegmentator 2.15.0 — task liver_lesions_mr — Dataset589 fold0
```

Run consolidado:

```text
casos/qualification/openswisshcc_v1/calibration/
dev_v10_lesion_localizer_full87/summary.json
```

SHA-256: `81826b1d5471170e89a86e1e826ca10cc55028f4f04a489428e110dfa87f6a61`.

Assinaturas verificadas:

- plano de seleção: `956288418fb2cae7252d07ab9f67fd0d5782c331ef9400cd4601abfc0574b046`;
- SHA-256 do plano: `2eadbaf699393b0b0a10a67fba531983c615adfb5ecd88c060f1dff8ea428f3c`;
- manifesto de entradas: `c00ca375d7b78652fbcb1427303c0af969fcd3c222c03faf3e3a4575dad4aa74`.

## Garantias preservadas

- nenhuma máscara de lesão do ground truth entrou no localizador;
- nenhuma decisão clínica foi produzida;
- nenhuma métrica foi calculada durante a execução cega;
- o holdout não foi aberto;
- os dados permanecem em modo pesquisa;
- revisão humana continua obrigatória;
- o run consolidado referencia exatamente os 87 IDs do plano assinado.

## Validação de software

Após a correção de caminho e a execução real:

- testes focados: 10 aprovados;
- suíte completa: **505 aprovados**, sem falhas;
- avisos: 327, todos de depreciação já conhecidos;
- teste novo verifica o nome temporário curto e a publicação atômica do NIfTI;
- testes de merge cobrem ausência de caso, adulteração de máscara e preservação do output.

## Próximo gate

O próximo passo metodologicamente correto é avaliar a feature pré-declarada
`log1p(total_candidate_volume_mm3)` nos 87 casos de desenvolvimento, com validação
cruzada e intervalos de confiança. Essa operação exige autorização explícita para abrir
os labels protegidos dos 77 casos de desenvolvimento ainda não acessados.

Somente depois dessa avaliação será decidido se:

1. o localizador volumétrico merece ser congelado como primeiro leitor;
2. o MedGemma 4B deve ser executado como segundo leitor seletivo;
3. são necessárias features determinísticas adicionais antes de consumir nova inferência.

O holdout deve permanecer fechado até existir uma configuração de desenvolvimento
congelada, reprodutível e com evidência suficientemente robusta.
