# Qualificação MedGemma 4B — MedSigLIP e OpenSwissHCC

Data do registro: 2026-07-14.

## 1. Objetivo desta etapa

Avaliar alternativas sem treino próprio para aumentar a discriminação entre
exames positivos e negativos, preservando:

- uso exclusivo em pesquisa;
- revisão humana obrigatória;
- ausência de decisão clínica automática;
- isolamento do ground truth durante a inferência;
- limite operacional alvo de 180 segundos por exame;
- nenhuma máscara de lesão na entrada do MedGemma ou do MedSigLIP.

Nenhum resultado desta etapa autoriza alegação de desempenho clínico ou
publicável. Os lotes locais continuam com revisão especializada pendente e têm
forte confusão de protocolo e origem.

## 2. MedSigLIP oficial

### 2.1 Snapshot local

O acesso autorizado ao modelo `google/medsiglip-448` foi confirmado. O cache
padrão do Hugging Face falhou no Windows ao criar arquivos de lock por hash. O
snapshot foi baixado pelo modo `local_dir` para uma área ignorada pelo Git:

```text
casos/qualification/models/medsiglip-448
```

Foram verificados os nove arquivos do repositório. O arquivo
`model.safetensors` tem 3.513.309.984 bytes. Pesos, tokens e dados não foram
adicionados ao Git.

### 2.2 Dependência de runtime

O primeiro carregamento real demonstrou que o tokenizer SigLIP exige
`protobuf`. Foi acrescentado ao extra `medgemma`:

```toml
"protobuf>=5.29,<7"
```

O ambiente Windows recebeu `protobuf 6.33.6`. Um teste verifica que `protobuf`
e `sentencepiece` permanecem declarados.

### 2.3 Correção do cálculo de score

A primeira implementação aplicava `sigmoid` a cada logit e depois fazia uma
normalização própria entre médias de prompts. O model card oficial usa
`softmax(logits_per_image, dim=1)` sobre os textos candidatos.

O scorer foi corrigido para:

1. validar logits finitos;
2. aplicar softmax numericamente estável sobre todos os prompts;
3. somar a massa de probabilidade dos prompts positivos;
4. manter o score como evidência exploratória, sem decisão final;
5. emitir `argos-medsiglip-scores-v2` com
   `scoring_method=softmax_logits_prompt_ensemble`.

Os artefatos v1 não podem ser misturados ou reutilizados como v2.

### 2.4 Testes

A suíte focalizada passou com 16 testes cobrindo:

- configuração research-only e decisão desabilitada;
- extração determinística dos 11 tiles;
- rejeição de PNG com metadados;
- softmax e invariância a deslocamento dos logits;
- rejeição de logits não finitos;
- adjacência axial;
- escrita atômica do CLI;
- dependências do tokenizer.

O smoke real na GPU gerou JSON v2 válido, com `final_decision: null`.

## 3. Experimentos MedSigLIP

### 3.1 Baseline uniforme ampliado

Foram avaliados como desenvolvimento exploratório:

- 12 casos TCGA-LIHC marcados como positivos no nível do paciente;
- 10 casos provenientes do lote informado como negativo;
- painel `uniform_9`, recortado ao redor do fígado e sem contorno;
- labels anexados somente depois de todos os scores existirem.

Limitações obrigatórias:

- todos os casos permanecem `pending_review`;
- HCC no nível do paciente não prova lesão visível na série selecionada;
- negativos não têm revisão especializada caso a caso;
- protocolos e origens dos grupos são diferentes.

Com o primeiro ensemble e persistência axial, nenhum limiar de 1 a 9 atingiu
simultaneamente 75% de sensibilidade e 75% de especificidade. O melhor
compromisso observado foi:

```text
persistência >= 5 tiles
sensibilidade: 83,3% (10/12)
especificidade: 70,0% (7/10)
```

### 3.2 Calibração de prompts e holdout interno

Seis ensembles clínicos foram declarados antes da avaliação. Todos os 132
conjuntos de scores (6 variantes x 22 painéis) foram produzidos sem rótulos. A
divisão foi estratificada e determinística por SHA-256:

- calibração: 6 positivos e 5 negativos;
- holdout: 6 positivos e 5 negativos.

Foi selecionado `v5_mimic_aware` com persistência mínima de 8 tiles. Na
calibração:

```text
sensibilidade: 83,3% (5/6)
especificidade: 100% (5/5)
```

O holdout foi aberto uma única vez e falhou a meta:

```text
TP=4, FN=2, TN=5, FP=0
sensibilidade: 66,7% (IC95% Wilson 30,0%–90,3%)
especificidade: 100% (IC95% Wilson 56,6%–100%)
acurácia balanceada: 83,3%
```

Não é permitido reduzir o limiar depois desse resultado e continuar chamando o
mesmo conjunto de holdout.

### 3.3 Cobertura volumétrica MedSigLIP

Foram gerados 124 painéis para os mesmos 22 exames, todos com:

- crop hepático;
- ausência de contorno;
- hashes verificados;
- cobertura axial exata de 100% dos voxels hepáticos;
- tiles reais reconstruídos pelos manifestos, ignorando espaços vazios.

Tempo observado no lote:

```text
geração dos painéis: 25,8 s para 22 exames
MedSigLIP: 90,5 s para 124 painéis / 22 exames
média combinada: 5,286 s por exame
```

A regra previamente congelada (`v5_mimic_aware`, probabilidade 0,5,
persistência >= 8) produziu:

```text
TP=12, FN=0, TN=0, FP=10
sensibilidade: 100%
especificidade: 0%
```

Conclusão: MedSigLIP zero-shot não pode ser usado como gate final com a
configuração atual.

## 4. TotalSegmentator `liver_lesions_mr`

Foi investigado como segundo leitor/localizador sem treino próprio:

- TotalSegmentator 2.15.0;
- task específica para MR;
- `Dataset589_ct_mri_liver_lesions_750subj`;
- licença adicional não exigida pelo registry local;
- `fast=True` não suportado;
- máscara hepática existente reutilizada via `crop_path`;
- máscara de lesão não enviada ao MedGemma.

O smoke GPU atingiu o timeout externo após 1.204 segundos (20 minutos), sem
saída final. O task está formalmente reprovado para o caminho online de 180
segundos nesta GPU. Ele pode ser reconsiderado somente para curadoria offline.

## 5. OpenSwissHCC como benchmark público

Os metadados oficiais foram baixados do Zenodo e seus MD5 foram verificados:

- `participants.tsv`;
- `README.md`;
- `data_description.txt`;
- registro JSON do Zenodo.

O dataset contém 132 sujeitos únicos:

- 63 HCC positivos;
- 69 HCC negativos;
- DCE-MRI multiparamétrica com fases nativa, arterial, venosa e tardia;
- T2, DWI e ADC quando disponíveis;
- máscaras hepáticas e de lesão mantidas como derivados separados.

O pacote `derivatives.zip` tem 113.529.097 bytes e foi validado com:

```text
md5:e7df6554b20aeb941d697710e4201c18
```

### 5.1 Extração permitida

O ZIP contém 2.799 arquivos:

```text
698  máscaras hepáticas automáticas
664  máscaras manuais de lesão
109  máscaras hepáticas manuais
64   máscaras manuais adicionais
1264 transformações de registro
```

Foi extraído exclusivamente o prefixo:

```text
derivatives/automated_liver_annotations/
```

Resultado do gate:

```text
arquivos extraídos: 698
sujeitos: 132
máscaras manuais de lesão extraídas: 0
```

A extração validou caminhos absolutos, componentes `..`, confinamento no
diretório de destino, escrita atômica e SHA-256 de cada arquivo. O manifesto
local permanece em `casos/`, fora do Git.

### 5.2 Split confirmado pelos membros dos ZIPs

Os limites reais foram confirmados pela inspeção dos membros, não inferidos
apenas pelos nomes dos arquivos:

```text
sub-001-sub-044.zip: sujeitos 001–044
sub-044-sub-088.zip: sujeitos 045–088
sub-088-sub-132.zip: sujeitos 089–132
```

Split congelado:

- desenvolvimento: sujeitos 001–044 e 089–132, 88 casos
  (39 positivos, 49 negativos);
- teste final lacrado: sujeitos 045–088, 44 casos
  (24 positivos, 20 negativos).

O ZIP intermediário não foi baixado. O preparador rejeita qualquer sujeito do
intervalo 045–088 nos arquivos de desenvolvimento.

### 5.3 Preparação real e auditoria independente

Os dois arquivos de desenvolvimento foram baixados e verificados:

```text
sub-001-sub-044.zip  md5:4daf23886b23639514a689082aa5578c
sub-088-sub-132.zip  md5:df0280231b3b7cf3a4628fa53d06a611
```

O preparador seguro gerou 88 casos pseudonimizados, separando fisicamente
`inputs/` de `protected_ground_truth/`. O schema e o identificador do dataset
nos inputs são neutros, e nenhum ID público ou label é exposto ao pipeline.

Auditoria após a preparação:

```text
casos: 88
positivos protegidos: 39
negativos protegidos: 49
arquivos: 1609
volumes de imagem: 1133
máscaras hepáticas automáticas: 476
tamanho preparado: 5,853 GB
erros de tamanho/SHA-256: 0
termos ou arquivos proibidos na entrada: 0
```

Cada fase T1 selecionada exige uma máscara hepática automática correspondente.
A escrita é atômica, não sobrescreve um destino existente e utiliza nomes
temporários curtos para compatibilidade com o limite de caminhos do Windows.

### 5.4 Registro multifásico e gate anatômico

Os transforms oficiais T1 foram extraídos por whitelist: Euler+B-spline
arterial→venosa, Euler+B-spline tardia→venosa e groupwise. São 440 arquivos
(cinco por caso), todos com SHA-256 validado, sem holdout e sem derivados
manuais ou de lesão.

O ambiente usa `itk-elastix==0.25.3`, declarado no extra opcional
`openswiss`. A auditoria pairwise das 88 máscaras automáticas produziu:

```text
arterial: mediana Dice 0,9588; 87/88 >= 0,90
tardia:   mediana Dice 0,9756; 84/88 >= 0,90
tempo total de 176 transforms: 408 s
```

O refinamento groupwise foi rejeitado: o `BSplineStackTransform` 4D não foi
reproduzido corretamente pelo wrapper utilizado e nenhum pareamento temporal
ultrapassou Dice 0,377 no outlier testado. Ele não integra o candidato.

A estratégia congelada para desenvolvimento compara, por fase, regradeamento
físico por identidade e transform pairwise. A alternativa com maior Dice
hepático é escolhida, com empate a favor da identidade. O painel só pode ser
gerado se arterial e tardia atingirem Dice >= 0,80 contra a máscara venosa.
Essa escolha usa somente máscaras automáticas de fígado, nunca lesão ou label.

Smokes reais:

```text
caso bom:        Dice arterial 0,9652; tardia 0,9843; 25,45 s
caso recuperado: tardia pairwise 0,2241 -> identidade 0,8706; 13,96 s
caso reprovado:  melhor tardia 0,3622; abortou sem cache parcial
```

O cache é imutável e assinado pelos hashes dos inputs, transforms, versão do
algoritmo e limiar. Reuso só ocorre após revalidar os hashes das saídas.


### 5.5 Construção do candidato em 88 casos

Foi criado um orquestrador sem acesso ao ground truth. Cada caso roda em
subprocesso isolado, com timeout de 150 s para alinhamento e 30 s para
renderização. O painel candidato usa uma única fusão RGB `uniform_9`, prompt
pathology-target, timeout MedGemma de 120 s, zero retry e saída compacta.

O primeiro lote levou 1.490 s. Dez casos processaram corretamente, mas a
publicação atômica do diretório falhou com `WinError 5` transitório no Windows
(seis alinhamentos e quatro painéis). A publicação passou a usar até 12
tentativas com coleta de handles e backoff limitado. O teste simula duas falhas
consecutivas antes do sucesso. A repetição seletiva recuperou 10/10 casos.

Estado auditado após a correção:

```text
casos de desenvolvimento: 88
alinhamentos válidos: 85
painéis prontos para revisão: 85
falhas do gate Dice: 3
falhas técnicas remanescentes: 0
tamanho total dos painéis: 98,87 MB
metadados PNG: 0
staging remanescente: 0
```

Os três casos reprovados obtiveram melhor Dice 0,7665, 0,7497 e 0,3622. Eles
permanecem na coorte e deverão contar como falha técnica/erro na avaliação ou
seguir um fallback predefinido antes do congelamento; não serão excluídos.

Todos os 85 painéis têm `visible_phi_confirmed=false` e
`eligible_for_inference=false`. A inspeção visual pelas ferramentas do Codex
foi bloqueada pela ACL local, portanto nenhuma inferência foi executada. A
revisão visual humana continua sendo gate obrigatório.

## 6. Segurança e metodologia preservadas

- Nenhum token foi salvo no projeto.
- Pesos e dados permanecem em `casos/`, fora do Git.
- Nenhuma máscara manual de lesão foi extraída ou enviada a modelo.
- Scores MedSigLIP mantêm `final_decision: null`.
- Ground truth foi anexado somente após inferência.
- Revisão humana continua obrigatória.
- Resultados exploratórios reprovados foram preservados, não ocultados.
- Nenhuma alegação de 75% foi feita.

## 7. Próximos passos

1. escolher uma representação multifásica usando somente desenvolvimento;
2. medir MedGemma 4B e abordagens auxiliares no desenvolvimento;
3. congelar prompts, hashes, regras e timeouts;
4. baixar ou abrir o bloco final somente depois do congelamento;
5. executar uma única avaliação final com IC95%, matriz de confusão e revisão
   humana.

Até que o benchmark público independente cumpra os dois gates, o objetivo de
75%/75% permanece não demonstrado.






