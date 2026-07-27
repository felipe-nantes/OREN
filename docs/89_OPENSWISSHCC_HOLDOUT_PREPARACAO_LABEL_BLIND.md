# OpenSwissHCC holdout — preparação label-blind e gate visual

Data: 2026-07-18.

## Autorização e escopo

Foi autorizada exclusivamente a aquisição e preparação das imagens dos sujeitos
045–088 do holdout OpenSwissHCC. Labels, `participants.tsv` e máscaras públicas
de lesão permaneceram fechados durante toda esta etapa.

Nenhuma inferência, predição, métrica ou decisão clínica foi executada.

## Aquisição oficial

Arquivo oficial:

```text
sub-044-sub-088.zip
bytes: 4.281.349.276
MD5 oficial: 201ea2266c1874cc95105f5f0a9fcf7c
SHA-256 local: 523629b9d8ad9d36c3ddf5870e7556e942ccf2da8691d5d21f832d58c083dddf
```

O servidor limitou conexões individuais. Foi criado um downloader HTTP por
faixas, retomável, que validou `Content-Range`, o tamanho exato de cada parte e
o MD5 integral antes da publicação atômica. O download verificado terminou em
875,604 segundos.

## Preparador isolado

O novo preparador:

- não possui argumento para `participants.tsv`;
- aceita exclusivamente `sub-044-sub-088.zip` com o MD5 oficial;
- exige exatamente sujeitos 045–088;
- seleciona somente volumes NIfTI de imagem;
- usa somente máscaras hepáticas automáticas já isoladas;
- não cria diretório de ground truth;
- mantém IDs públicos apenas na proveniência protegida, fora dos inputs;
- publica atomicamente e recusa sobrescrita.

Resultado:

```text
casos: 44
volumes de imagem: 516
máscaras hepáticas automáticas: 222
arquivos de input: 738
bytes de input: 2.886.065.122
labels lidos: não
participants.tsv lido: não
ground truth criado: não
máscaras de lesão lidas: 0
máscaras de lesão copiadas: 0
IDs públicos nos inputs: não
```

Integridade:

```text
protocol.json SHA-256:
233509056ee571799e9d7242fae0c40af6bd049660ec45ea49e09dac25c3a1fa

holdout_inputs.jsonl SHA-256:
bb20ce0a6b8ea53ddc75767ef88c444dbae80ffadec041fd80d58775c3638439

input tree SHA-256:
dc8ec516c2ec28a456a368781466b4709dade153e8dd08535571704c5faed01b

auditoria SHA-256:
bf06a3bad5fedbd7e3d53c4d255bb1922de67d5e1e90fc3d62076e7f84db0ced
```

## Registro multifásico label-blind

Foram extraídos por whitelist somente os cinco parâmetros técnicos de registro
T1 por caso a partir do `derivatives.zip` oficial. Nenhuma anotação manual ou
máscara de lesão foi materializada.

```text
casos com transforms: 44
arquivos técnicos: 220
manifesto de registro SHA-256:
5bb8ef17acf540e93c187d99ade1fb34ba0da788db17bd348c9abecc6586b52f
```

O alinhamento escolheu identidade física ou transform publicado usando apenas o
Dice das máscaras hepáticas automáticas, com mínimo congelado em 0,80.

```text
casos multifásicos aprovados pelo gate: 43
fallback venoso técnico: 1
casos excluídos: 0
resumo de alinhamento SHA-256:
a8f200b787f115c3005b19f84cc82150485a7e23397256f79b98ac60d6923911
```

O caso anônimo abaixo obteve melhor Dice 0,096 e não foi forçado a passar:

```text
anon-openswiss-70e5cfd52cd33c59
índice na galeria: 28
fallback: venous_single_phase
```

A decisão de fallback foi exclusivamente geométrica, anterior à inferência e
sem acesso ao ground truth.

## Painéis congelados para revisão

Representação:

```text
43 painéis RGB: R=arterial registrada, G=venosa, B=tardia registrada
1 painel em tons de cinza: fase venosa do fallback técnico
9 axiais + 1 coronal + 1 sagital por caso
estratégia: uniform_9
RAG: desabilitado
resposta futura: choice_classification
modelo futuro: MedGemma 1.5 4B
```

Todos os 44 candidatos permanecem:

```text
eligible_for_inference=false
status=rendered_pending_human_review
holdout_ground_truth_opened=false
```

Assinaturas:

```text
coorte de painéis SHA-256:
3b47addfbcea5ba4066c85fbc5ba41128b8f835c36c878d7dd8354b15a9fde81

cohort signature:
ec220ad9ccd2ad7ae2188b6ae7fa332379c0ca75cb25f24ae81a345618a43ad3

galeria manifest SHA-256:
0a972a5a71fe1e47e769aa03c67b8b6cb0008e914852e3b86f30d4b3060bfee5

gallery signature:
6a1f264c9323224a5105da37e8bbdc27bd7cebb0614d4eed7fc879b3a4b929cb

index.html SHA-256:
364982f4c81a55c5263b006f1ed08dd83457d3bd6f521a167e3afaeec0add1c7
```

## Gate humano solicitado

A revisão deve ser exclusivamente técnica. Para cada item, avaliar:

1. o fígado aparece de forma reconhecível nos cortes centrais;
2. o crop não remove porção importante do fígado;
3. axial, coronal e sagital são plausíveis;
4. nos painéis RGB, não há desalinhamento destrutivo ou fantasmas intensos;
5. o contorno hepático acompanha o órgão sem esconder o parênquima;
6. não há PHI, texto diagnóstico ou marcação de tumor/lesão;
7. o item 28 deve estar em tons de cinza por ser fallback venoso declarado.

Não procurar confirmar HCC e não usar aparência diagnóstica como critério de
aprovação. Achado suspeito visível não reprova um painel tecnicamente válido.

Somente depois da aprovação assinada desta galeria será permitido congelar os
hashes como elegíveis e iniciar os três sinais cegos. Labels e máscaras de
lesão continuarão fechados até todas as predições e o protocolo final estarem
congelados.
# Continuação

O gate humano assinado, o executor cego em estágios e o freeze das predições estão documentados em `docs/90_OPENSWISSHCC_HOLDOUT_GATE_E_EXECUTOR_CEGO_V21.md`.
