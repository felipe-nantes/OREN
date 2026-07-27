# LLD-MMRI v23 — execução label-blind

## Objetivo

Validar externamente o ARGOS 4B em HCC versus mimetizadores benignos:

- 157 casos HCC positivos;
- 178 casos negativos (hemangioma, cisto e FNH);
- 335 casos e 2.680 imagens NIfTI;
- sensibilidade e especificidade mínimas de 75%;
- tempo direto ponta a ponta máximo de 180 segundos por caso;
- uso somente em pesquisa e revisão humana obrigatória.

As imagens são CC BY-NC 4.0 e não entram no Git nem no pacote público de
transferência. Labels e máscaras públicas de lesão permanecem fora da inferência.

## Estado em 20 de julho de 2026

- protocolo externo v23 congelado: `70422594c09884111e34f3e575e2eba68aa63f3aaadba332e8b2f6577b31fce1`;
- calibrador v23 congelado: `d0a955178783cf7f2914053c87d3d99d186ab4a56960620068bd118e5ccac475`;
- 2.680 imagens baixadas e verificadas, sem labels ou máscaras de lesão;
- manifesto do download: `6c16c463bac90b740953e94fdd3751e10f91dbc3716bf2b6b939b507d6e94157`;
- auditoria geométrica original: 230 casos compatíveis e 105 com divergência de
  grade em ao menos uma fase T1 dinâmica;
- harmonização física label-blind concluída em 1.340 fases dinâmicas, sendo 136
  reamostradas e 1.204 preservadas;
- assinatura da harmonização: `3e1bb21777cba6f71f786887f724f3e3c18b7928c29a7a95304e04e4c7920e0d`;
- piloto inicial full-resolution: 5/5 segmentações, 23,31–31,30 s e cobertura
  hepática dinâmica de 100%;
- piloto dos 10 piores campos de visão: 10/10 segmentações, máximo de 43,07 s;
- no piloto de risco, 8/10 casos cobriram pelo menos 99% do fígado em todas as
  fases; os mínimos observados foram 96,96% e 84,80%, ambos na fase tardia;
- a fase venosa cobriu 100% do fígado em todos os 10 casos de risco;
- auditoria integral das 335 máscaras está em execução antes de qualquer adendo
  técnico ou predição;
- qualificação 75/75/180 ainda não foi realizada.

## Invariantes

- nenhuma máscara de lesão ou label entra em segmentação, painel, localizador,
  MedSigLIP, MedGemma ou fusão;
- a máscara automática usada nesta etapa é somente a máscara hepática gerada na
  fase venosa;
- reamostragem usa transformação identidade em coordenadas físicas e não é
  chamada de registro anatômico ou correção de movimento;
- pixels fora do campo de visão não podem ser interpretados como ausência de
  realce nem preenchidos com anatomia inventada;
- qualquer política para cobertura parcial deve ser congelada usando apenas a
  auditoria label-blind dos 335 casos, antes das predições;
- o holdout OpenSwissHCC não participa desta etapa.

## Sequência executada

### 1. Verificar o download

```powershell
.\.venv-win\Scripts\python.exe tools\download_lld_mmri_v23_external.py `
  --protocol-root casos\qualification\lld_mmri_v23\prepared\external_protocol_v1 `
  --destination data\raw\LLD_MMRI_v23_hf `
  --verify-only
```

### 2. Auditar geometria original

```powershell
.\.venv-win\Scripts\python.exe tools\audit_lld_mmri_v23_geometry.py `
  --protocol-root casos\qualification\lld_mmri_v23\prepared\external_protocol_v1 `
  --download-root data\raw\LLD_MMRI_v23_hf `
  --output casos\qualification\lld_mmri_v23\prepared\external_geometry_audit_v1
```

O resultado `failed_do_not_segment` foi esperado: 105 casos não possuíam as quatro
fases T1 na mesma grade física. Nenhuma reamostragem silenciosa foi permitida.

### 3. Harmonizar as fases dinâmicas

```powershell
.\.venv-win\Scripts\python.exe tools\harmonize_lld_mmri_v23_dynamic_t1.py `
  --protocol-root casos\qualification\lld_mmri_v23\prepared\external_protocol_v1 `
  --download-root data\raw\LLD_MMRI_v23_hf `
  --failed-audit casos\qualification\lld_mmri_v23\prepared\external_geometry_audit_v1 `
  --output casos\qualification\lld_mmri_v23\prepared\external_dynamic_harmonized_v1
```

Algoritmo congelado: `identity-physical-grid-to-venous-linear-v1`. A grade venosa
é a referência. A interpolação é linear, o valor externo é zero e as imagens já
compatíveis são preservadas por hardlink ou cópia.

### 4. Pilotos de segmentação

Piloto inicial em cinco casos:

```powershell
.\.venv-win\Scripts\python.exe tools\pilot_lld_mmri_v23_segmentation.py `
  --protocol-root casos\qualification\lld_mmri_v23\prepared\external_protocol_v1 `
  --download-root data\raw\LLD_MMRI_v23_hf `
  --failed-audit casos\qualification\lld_mmri_v23\prepared\external_geometry_audit_v1 `
  --harmonization casos\qualification\lld_mmri_v23\prepared\external_dynamic_harmonized_v1 `
  --output casos\qualification\lld_mmri_v23\prepared\external_segmentation_pilot5_fullres_v1 `
  --cases 5 --selection first_n --device gpu
```

Piloto dirigido aos dez piores campos de visão:

```powershell
.\.venv-win\Scripts\python.exe tools\pilot_lld_mmri_v23_segmentation.py `
  --protocol-root casos\qualification\lld_mmri_v23\prepared\external_protocol_v1 `
  --download-root data\raw\LLD_MMRI_v23_hf `
  --failed-audit casos\qualification\lld_mmri_v23\prepared\external_geometry_audit_v1 `
  --harmonization casos\qualification\lld_mmri_v23\prepared\external_dynamic_harmonized_v1 `
  --output casos\qualification\lld_mmri_v23\prepared\external_segmentation_pilot10_lowcoverage_v1 `
  --cases 10 --selection lowest_whole_grid_support --device gpu
```

Assinatura do piloto de risco:
`de2c0c2a66cdd22bbd5a2b1e9c81f70514f212da1c0aa0740ffd1a6e879e6204`.

### 5. Auditar as 335 máscaras antes da preparação

```powershell
.\.venv-win\Scripts\python.exe tools\pilot_lld_mmri_v23_segmentation.py `
  --protocol-root casos\qualification\lld_mmri_v23\prepared\external_protocol_v1 `
  --download-root data\raw\LLD_MMRI_v23_hf `
  --failed-audit casos\qualification\lld_mmri_v23\prepared\external_geometry_audit_v1 `
  --harmonization casos\qualification\lld_mmri_v23\prepared\external_dynamic_harmonized_v1 `
  --output casos\qualification\lld_mmri_v23\prepared\external_segmentation_audit335_fullres_v1 `
  --cases 335 --selection first_n --device gpu
```

Esse artefato continua marcado como `technical_timing_only=true` e
`eligible_for_inference=false`. Após finalizar, o verificador independente deve
reabrir todas as máscaras e recomputar hashes, geometria, voxels, cobertura e
agregações.

Verificação independente após a publicação do diretório:

```powershell
.\.venv-win\Scripts\python.exe tools\verify_lld_mmri_v23_segmentation_audit.py `
  --protocol-root casos\qualification\lld_mmri_v23\prepared\external_protocol_v1 `
  --download-root data\raw\LLD_MMRI_v23_hf `
  --failed-audit casos\qualification\lld_mmri_v23\prepared\external_geometry_audit_v1 `
  --harmonization casos\qualification\lld_mmri_v23\prepared\external_dynamic_harmonized_v1 `
  --segmentation-audit casos\qualification\lld_mmri_v23\prepared\external_segmentation_audit335_fullres_v1
```

### Recuperação determinística de falha da máscara hepática

A auditoria completa encontrou no caso `anon-lld-7b387848a6fa9d72` uma falha
pontual do modelo full-resolution: a geometria de saída estava correta, porém a
máscara continha somente 22 voxels e foi rejeitada antes de qualquer inferência.
O mesmo volume venoso, executado com o modelo `fast=True` de 3 mm, produziu uma
máscara válida com 150.249 voxels e cobertura dinâmica mínima de 100%.

A política label-blind passou a ser:

1. executar `total_mr/liver` em full-resolution;
2. validar existência, NIfTI, geometria e mínimo de 300 voxels;
3. somente se esse gate falhar, apagar a saída inválida e repetir com
   `fast=True`;
4. abortar o caso se as duas tentativas falharem;
5. registrar ambas as tentativas, o motivo técnico, a tentativa selecionada e o
   tempo total acumulado.

No caso real acima, a recuperação levou 89,37 segundos no total e selecionou
explicitamente `fallback_fast_3mm`. O fallback não lê labels, máscaras de lesão
ou diagnóstico e não permite que uma máscara reprovada siga para os painéis.
Ele pode ser desativado para diagnóstico com `--disable-fast-fallback`.

### Adendo obrigatório para campo de visão parcial

A preparação continua exigindo 99% de cobertura hepática em todas as fases por
padrão. Uma fase parcial somente pode entrar no fluxo quando existir um adendo
técnico label-blind congelado após a auditoria integral das 335 máscaras. O
verificador do adendo recompõe a distribuição por fase e confere auditoria,
configuração, profile, hashes do código, política e assinatura.

O contrato autorizado exige referência venosa com 100% de cobertura, usa venoso
em escala de cinza nos pixels sem fase correspondente, analisa shape apenas na
interseção de voxels disponíveis e não exclui casos parciais da métrica primária.
O `amendment.json` verificado é copiado para a preparação e ligado à assinatura
do artefato. Sem esse arquivo, o gate antigo de 99% permanece inalterado.

Após a auditoria completa, congelar com:

```powershell
.\.venv-win\Scripts\python.exe tools\freeze_lld_mmri_v23_technical_amendment.py `
  --protocol-root casos\qualification\lld_mmri_v23\prepared\external_protocol_v1 `
  --download-root data\raw\LLD_MMRI_v23_hf `
  --failed-audit casos\qualification\lld_mmri_v23\prepared\external_geometry_audit_v1 `
  --harmonization casos\qualification\lld_mmri_v23\prepared\external_dynamic_harmonized_v1 `
  --segmentation-audit casos\qualification\lld_mmri_v23\prepared\external_segmentation_audit335_fullres_v1 `
  --config configs\medgemma_local_4b_lld_v23_uniform9_choice.yaml `
  --profile profiles\figado.yaml `
  --output casos\qualification\lld_mmri_v23\prepared\external_technical_amendment_v1
```

## Correção de estabilidade do TotalSegmentator

O arquivo global `C:\Users\profurg\.totalsegmentator\config.json` foi encontrado
com bytes NUL após uma interrupção durante a atualização não atômica do contador do
próprio TotalSegmentator. A falha ocorria em `setup_totalseg()` antes da leitura da
RM e não era causada pelo exame ou pela GPU.

O adaptador LLD-MMRI passou a:

- criar um `TOTALSEG_HOME_DIR` efêmero por chamada;
- reutilizar somente o diretório local de pesos verificados;
- criar `config.json` atomicamente;
- desativar estatísticas de uso no runtime isolado;
- restaurar todas as variáveis de ambiente mesmo após exceção.

Os testes cobrem execução válida, falha forçada e restauração do ambiente. O JSON
global corrompido não é mais lido por esse pipeline.

## Timeout isolado por tentativa

Durante a auditoria integral, o processo permaneceu ativo sem CPU/GPU, log ou
checkpoint por mais de 47 minutos no caso 175. Reiniciar o mesmo processo não
eliminou o risco de novo bloqueio. Para impedir que um único caso paralise a
coorte, cada chamada `total_mr/liver` pode agora ser executada em subprocesso
isolado com `--isolate-attempts` e timeout rígido configurável por
`--attempt-timeout-seconds`.

Na execução externa v23, o limite foi fixado operacionalmente em 75 segundos por
tentativa: full-resolution e, se necessário, fast 3 mm. Ao expirar, toda a
árvore do worker é encerrada, saídas parciais são removidas e a tentativa fica
registrada como falha técnica. Se ambas expirarem ou falharem no gate, o caso é
persistido como `technical_failure_no_valid_liver_mask` e conta como erro; não é
criada máscara heurística. O checkpoint continua reproduzível e retomável.

Após a correção, o caso que havia bloqueado o processo concluiu normalmente em
51,77 segundos e o checkpoint avançou de 174 para 176. Os testes focados de
preparação, timeout, checkpoint e auditoria passaram 22/22.

Em uma interrupção posterior, o arquivo principal do checkpoint foi substituído
por 268.973 bytes NUL. As máscaras existentes foram preservadas para auditoria,
mas os receipts por tentativa deixaram de ser recuperáveis com fidelidade. Para
não reconstruir evidência parcial nem misturar registros aproximados ao estudo,
a execução interrompida foi arquivada em
`interrupted_segmentation_audit335_checkpoint_nul_20260721_133041` e a auditoria
integral foi reiniciada desde o caso 1.

O gravador passou a usar `flush` + `fsync`, validação JSONL e de tamanho antes da
publicação, além de manter `checkpoint_rows.backup.jsonl` com a última geração
válida. Um checkpoint corrompido nunca substitui o backup válido. A suíte focada
após essa proteção passou 23/23.

Como o host pode desligar inesperadamente, a tarefa local
`Argos-LLD-MMRI-v23-Audit335` foi configurada com dois gatilhos: retomada no logon
e nova tentativa a cada cinco minutos. `MultipleInstances=IgnoreNew` impede duas
auditorias simultâneas; `StartWhenAvailable` recupera gatilhos perdidos; falhas
recebem até 99 reinícios com intervalo de um minuto. Cada retomada valida o
checkpoint e continua somente depois da última linha confirmada. A tarefa deve
ser removida após a publicação e verificação dos 335 casos.

## Próximas etapas condicionais

### Estado congelado da auditoria integral (2026-07-22)

A execução `retry6` terminou e publicou os 335 casos. O verificador independente
reabriu as máscaras, recomputou geometria, voxels, cobertura e hashes e aprovou o
artefato com a assinatura:

`401d78e307738165aba10db99ccf18b920493082ae344a06c523ca498a774028`

Resultado técnico congelado:

- 321 casos possuem máscara hepática válida;
- 67 casos utilizaram o fallback `fast=True`;
- 14 casos são `technical_failure_no_valid_liver_mask`;
- nenhuma máscara foi fabricada para recuperar falhas;
- as 14 falhas ficam fora da inferência, mas contam como erros na métrica
  primária;
- nenhum tempo de segmentação isolada excedeu 180 segundos;
- ground truth não foi lido e nenhuma máscara de lesão foi aberta.

O adendo técnico foi ampliado antes das predições para separar a distribuição
de cobertura das 321 máscaras válidas das 14 falhas explícitas. Ele vincula os
IDs das falhas, proíbe inferência e fabricação de máscara nesses casos e preserva
a contabilização como erro. O adendo foi congelado e reverificado com a
assinatura:

`caefd4a973c3868d3b7778ee2aa75011b16052f85cf77d639b55f348c4f18166`

Esse adendo v1 foi preservado como registro histórico. Antes da preparação real,
os módulos de preparação, painéis e shape receberam proteção adicional de
checkpoint e propagação do contrato 335/321/14. Como o adendo vincula os hashes
do código, o preflight recusou corretamente o v1. Um adendo v2 foi então
recongelado e verificado independentemente, ainda label-blind, com 335 casos de
protocolo, 321 elegíveis, 14 falhas técnicas, `ground_truth_read=false` e
`lesion_masks_read=0`. A assinatura ativa passou a ser:

`1b31a853e26aa956000dc36831f58651e9ff4ee8651c948733d36bf8e28e9368`

A tarefa agendada temporária foi removida após a verificação. A preparação dos
inputs deve materializar somente os 321 casos tecnicamente elegíveis e carregar
as 14 falhas no resumo assinado, para que nenhuma etapa posterior as descarte da
avaliação.

A preparação foi tornada retomável antes da execução real. Cada caso concluído é
persistido em um único registro transacional contendo manifesto e recibo, com
`flush`, `fsync`, substituição atômica e backup da geração anterior. Se o arquivo
principal estiver corrompido após desligamento, o loader recupera exclusivamente o
último backup JSONL válido. Ao retomar, todos os hashes dos arquivos já preparados
são revalidados antes que o prefixo seja aceito.

### Preparação externa concluída e verificada

A preparação real foi publicada após o preflight label-blind do adendo v2. O
verificador independente recomputou manifestos, recibos, geometrias e hashes antes
de liberar a geração de painéis. Resultado:

- protocolo: 335 casos;
- elegíveis materializados: 321 casos;
- falhas técnicas preservadas: 14 casos;
- imagens de fase materializadas: 2.568;
- máscaras hepáticas automáticas: 321;
- labels lidos: falso;
- máscaras de lesão lidas: 0;
- máscaras de lesão copiadas: falso;
- status verificado: `ready_for_label_blind_panel_generation`.

Assinatura da preparação:

`314dff89ee408976881320089d00b97ee0f6f1cb4c5e09ef2991ef5edcc7d737`

SHA-256 do manifesto `inputs.jsonl`:

`7b2544b9fc4be8cb8ff43f23105b4361cb9fb1f5df0ba1537398c99e74e47579`

### Adendo v3 — máscaras com menos de nove planos hepáticos

A primeira geração de painéis foi interrompida com segurança após nove casos. O
caso `anon-lld-78beb07bef5ca29b` contém fígado em somente seis planos axiais na
máscara automática auditada, enquanto o renderizador `uniform_9` rejeitava menos
de nove planos. O checkpoint, os nove painéis e o recibo da falha foram preservados
em `interrupted_external_uniform9_panels_v1_pre_short_liver_policy_20260722_1038`.

Foi adicionada uma política opt-in exclusiva da configuração LLD-MMRI:
`short_liver_policy=blank_tiles`. Ela mantém a grade axial 3×3, renderiza cada
corte real exatamente uma vez e preenche somente os espaços restantes com tiles
textuais vazios. Nenhum corte é duplicado, interpolado ou fabricado. O manifesto
registra índices reais, quantidade de cortes reais, quantidade de tiles vazios e
a política aplicada. Configurações baseline sem essa opção continuam rejeitando
máscaras curtas.

Os testes focados do renderizador, do adendo e dos painéis passaram 18/18. Como o
renderizador e a configuração são fontes assinadas, o adendo v2 não foi reutilizado.
O adendo v3 foi congelado e verificado independentemente, ainda sem labels ou
máscaras de lesão, com assinatura:

`3c3b32214cfbacd24e0f3f4bbd3e7ea9a04a27f60963fd5601aaee6517203acd`

Uma coleção de inputs v2 é rematerializada sob esse vínculo antes de reiniciar os
321 painéis do zero, impedindo mistura de artefatos produzidos por configurações
diferentes.

A coleção `external_inputs_v2` foi concluída e verificada independentemente com
335 casos de protocolo, 321 elegíveis, 14 falhas, zero labels e zero máscaras de
lesão. Como as imagens permaneceram idênticas, `inputs.jsonl` conservou o hash
`7b2544b9fc4be8cb8ff43f23105b4361cb9fb1f5df0ba1537398c99e74e47579`.
A nova assinatura, que vincula o adendo v3 e a configuração de painel, é:

`be0a407c14cede03dddc5ec0142eadeee3ad2a93ba4559831863e03a53c90da7`

A geração integral dos 321 painéis foi então reiniciada do zero com essa coleção.

### Painéis v3 concluídos e galeria publicada

Os 321 painéis foram concluídos e auditados independentemente antes da cópia para
a galeria. A auditoria confirmou a ordem congelada, todos os hashes dos painéis e
manifestos, assinaturas individuais, dimensões, PNGs sem metadados, ausência de
lesão pré-marcada e inferência ainda bloqueada. A coorte possui assinatura:

`6879b6a4b6270d971b0606923ee2abe7c877f6a59fe869e751fa0bd41b5a78bc`

Três casos usaram a política curta, sempre sem duplicação:

- `anon-lld-78beb07bef5ca29b`: 6 cortes reais + 3 tiles vazios;
- `anon-lld-9334c03a7047dc33`: 8 cortes reais + 1 tile vazio;
- `anon-lld-85403ca8c93410c3`: 7 cortes reais + 2 tiles vazios.

A galeria realizou uma segunda validação de todos os hashes e foi publicada com
321 casos, ainda pendente de revisão humana técnica. Sua assinatura é:

`993d99245fe5ba24b56cd3ae99b55510d817a9a7c8dacfb4160ebc8193d4e09c`

Nenhuma inferência é permitida antes da aprovação explícita da galeria.

O contrato 335/321/14 também foi propagado aos painéis, galeria, revisão humana,
sinais, shape, predições, medição direta e avaliação. Falhas não recebem predição
fabricada; após abrir os labels, elas entram como erro da classe verdadeira.

O gate temporal mede execução end-to-end exclusivamente nos 321 casos elegíveis
para inferência e expõe o campo
`all_inference_eligible_cases_within_180_seconds`. As 14 falhas técnicas não
recebem execução ou tempo fabricado, mas permanecem erros da métrica de acurácia.
ROC-AUC usa somente casos elegíveis com score. Se a exclusão técnica remover uma
das classes, o avaliador registra AUC indisponível, motivo e contagens por classe,
sem abortar a avaliação e sem criar score artificial.

A medição end-to-end direta também usa checkpoint durável por caso. Cada medição
concluída preserva o relógio contínuo daquele caso, a reprodução exata da predição
congelada, as oito etapas obrigatórias e a assinatura individual. Após desligamento,
o runner valida o contexto, a assinatura e o prefixo persistido e executa somente
os casos restantes. Uma execução válida acima de 180 segundos permanece evidência
válida e faz o gate temporal falhar; ela não é descartada como arquivo inválido.

A geração dos painéis também foi tornada retomável por caso antes da execução
integral. O staging determinístico mantém `checkpoint_cases.jsonl`; cada registro
somente é aceito após revalidar os hashes do painel, do manifesto e dos candidatos.
Após uma interrupção ou desligamento, casos confirmados não são renderizados de
novo e qualquer diretório parcial sem checkpoint é removido antes da retomada. A
publicação final continua atômica. O teste de interrupção e retomada passou, e a
suíte LLD-MMRI v23 completa passou com 67 testes.

1. concluir e verificar a auditoria das 335 máscaras;
2. congelar um adendo técnico label-blind para campos de visão parciais, se
   necessário, sem excluir casos com base no diagnóstico;
3. preparar os 335 inputs e gerar painéis uniform-9;
4. realizar revisão humana apenas de qualidade técnica e ausência de PHI;
5. executar localizador, shape, MedSigLIP e MedGemma 4B;
6. congelar as 335 predições e a medição direta de tempo;
7. abrir os labels públicos somente após o congelamento;
8. calcular sensibilidade, especificidade, IC 95%, matriz de confusão e gate
   75/75/180;
9. transportar o protocolo qualificado para o Mac/MedGemma 27B.

## Desvio metodológico conhecido

Três linhas do arquivo protegido foram exibidas acidentalmente durante a
implementação do avaliador, antes das predições. Nenhuma regra decisória foi
alterada depois disso. O evento e os hashes estão em
`external_protocol_v1/PROTOCOL_DEVIATION_20260720.md`. A publicação deve declarar
essa limitação e não pode chamar o processo de cegamento humano absoluto.

## Rejeição técnica da galeria v1 e gate anatômico v2

A revisão humana da galeria `external_uniform9_gallery_v1` rejeitou os painéis
antes da inferência. O contorno e o crop estavam frequentemente apoiados em
máscaras hepáticas parciais ou fragmentadas. O caso
`anon-lld-684ad096062a0306` exemplifica a falha: a máscara full-resolution tinha
8.533 voxels, mas apenas aproximadamente 15,07 mL, sete componentes e fração do
maior componente de 0,7593. O gate antigo de 300 voxels validava existência e
geometria, não plausibilidade anatômica.

Os artefatos v1 e suas assinaturas foram preservados como evidência rejeitada.
`technical_rejection.json` bloqueia explicitamente seu uso em inferência. Nenhuma
predição foi executada com esses painéis.

Foi iniciado um protocolo corretivo label-blind. Ele mede volume físico,
extensão axial, extensão no plano e conectividade 3D; uma máscara aprovada conserva
somente o maior componente conectado. Os limites iniciais do piloto são 300 mL,
60 mm axiais, 70 mm em cada eixo no plano e fração do maior componente de pelo
menos 0,90. O modo fast 3 mm é testado como candidato primário porque, no caso
representativo, produziu aproximadamente 609 mL e fração conexa 0,9996. Um piloto
de 20 casos precede qualquer nova preparação integral ou inferência.

Durante uma busca textual de diagnóstico, uma linha do diretório protegido do
caso representativo foi exibida acidentalmente. Essa informação não foi usada na
seleção, nos limites, na segmentação ou na avaliação visual. O incidente fica
registrado; o piloto continua orientado por imagens e máscaras automáticas, e
nenhum outro label ou máscara de lesão deve ser aberto.

A revisão do painel corretivo mostrou que o caso representativo ainda não tinha
cobertura completa do fígado, apesar de volume e conectividade plausíveis. O piloto
foi interrompido em 9/20 e marcado como não retomável. Segmentações fast nas fases
nativa, arterial, venosa e tardia produziram aproximadamente 303, 735, 609 e
492 mL, com Dice entre fases de 0,53 a 0,80. Essa discordância impede selecionar a
maior máscara ou uni-las sem fabricar cobertura.

O próximo piloto deve ser independente de máscara: campo abdominal completo, sem
contorno e sem crop comandado pela segmentação. Em paralelo, outro segmentador
específico de RM hepática pode ser comparado. O TotalSegmentator isolado não está
qualificado como fonte de cobertura completa para esta coorte.

### Piloto full-FOV sem máscara

Foi implementado um renderizador opt-in cuja API não aceita máscara de fígado,
máscara de lesão ou ground truth. Ele preserva o campo adquirido completo, não
desenha contorno, não escurece o fundo e amostra nove planos axiais distintos ao
longo de toda a extensão corporal, além de vistas coronal e sagital no centro
corporal. O baseline segmentado permanece inalterado.

Uma galeria piloto label-blind com os nove primeiros casos do protocolo e o caso
representativo da falha foi gerada e verificada independentemente. Nenhuma
máscara de órgão, lesão ou ground truth foi lida. Todos os PNGs possuem dimensões
1536x1152, nenhum metadado embutido e hashes consistentes. A coleção possui
assinatura:

`8f5b50d82b3de76be46772057fb8efaa6482da15f010ef72227858f37846e591`

A galeria possui assinatura:

`cfa24ba56ae3a518a5c3a4d9aa15e093be211c6b42419af095b6203ada4b625c`

O piloto permanece inelegível para inferência até revisão humana confirmar que o
fígado está visível por completo, sem crop, contorno enganoso ou PHI aparente.

### Piloto full-FOV 3x9 para maior cobertura axial

Foi acrescentada uma variante opt-in que preserva todas as salvaguardas do
full-FOV sem máscara e aumenta a amostragem de nove para 27 planos axiais
distintos. Os planos são selecionados sistematicamente ao longo de toda a
extensão corporal adquirida e divididos, em ordem, em três painéis de nove
cortes. O baseline de um painel permanece reproduzível e inalterado.

Esta representação não afirma cobertura de todos os cortes nem de 100% dos
voxels hepáticos. Ela reduz o espaçamento entre amostras sem depender de uma
segmentação hepática que falhou no gate visual. Cada painel conserva o campo de
visão completo, não desenha contorno, não aplica crop hepático e registra os
índices axiais e hashes no manifesto autoritativo.

Três painéis foram escolhidos para o piloto porque as medições anteriores
projetaram aproximadamente 112 segundos para três leituras. Cinco leituras
chegaram a aproximadamente 154 segundos e deixariam margem insuficiente para o
limite end-to-end de 180 segundos. Essa projeção não substitui uma medição real
no LLD-MMRI; nenhuma inferência está autorizada antes da aprovação visual.

A coorte piloto possui dez casos e trinta painéis, com assinatura:

`87227e06ad726d41315ff4e91dbb951ce60508dd9ee9414c02dbae94e68698a8`

A galeria possui assinatura:

`89bfca22c17821edda2cf9f6dce219888e631d7aa8abee38aee48c7055e32d9b`

Uma verificação separada confirmou 10/10 manifestos, 30/30 hashes, 27 índices
axiais distintos por caso, PNGs 1536x1152 sem metadados e zero leitura de
máscaras de órgão, máscaras de lesão ou ground truth. A coleção continua com
`eligible_for_inference=false` até revisão humana.

Antes da revisão, o gate foi fortalecido para vincular também o conteúdo exato
de `index.html` ao manifesto. A galeria v2 substitui a v1 como objeto de revisão,
sem apagar a evidência anterior. Sua assinatura é:

`0cbf16abe2edc993763746f1f5c0897dbcb3f97ea2954c6a6581d3334feb0063`

O hash do HTML revisável é:

`b0433e22a3887d1615cd8d99b90827a1204d2cbe6e2bf71e7f7a2b21e980163e`

Também foram implementados, sem executar inferência, o registro de aprovação
humana assinado, o congelamento do protocolo temporal e o runner sequencial de
três chamadas. O preflight exige a cadeia íntegra coorte → galeria/HTML → revisão
→ configuração/prompt → protocolo. A medição resultante cobre as três chamadas,
validação, agregação e persistência; ela não será apresentada como tempo completo
desde DICOM enquanto esse gate end-to-end não for medido separadamente.

O runner temporal foi tornado resistente a desligamentos antes da primeira
execução real. Cada caso só é publicado após as três respostas, agregação e
relatório terem sido persistidos; um staging interrompido não é tratado como
resultado. Na retomada, todos os hashes, assinaturas, três respostas e vínculo ao
protocolo são revalidados antes de reutilizar o caso. Casos completos não chamam
novamente o modelo, e qualquer resultado adulterado faz o processo abortar.

### Revisão v2 e correção liver-enriched v3

A revisão humana aprovou o campo de visão completo da v2, mas identificou que o
terceiro painel frequentemente avançava além do fígado. A v2 foi, portanto,
considerada adequada para demonstrar ausência de crop, porém inadequada para
inferência. Um painel sem fígado obrigaria o MedGemma a escolher uma classe,
criando risco de falso positivo, inconclusivo e gasto temporal sem evidência.
Nenhuma inferência v2 foi executada.

A auditoria label-blind dos 321 localizadores automáticos encontrou 307 casos com
maior componente em pelo menos nove planos e fração de componente de pelo menos
0,75. Quatorze casos não passaram esse gate; quatro deles tinham menos de nove
planos no maior componente. Esses critérios são exclusivamente técnicos e foram
definidos sem labels ou máscaras de lesão.

O protocolo v3 usa o maior componente somente para localizar um intervalo axial
amplo, com margem de 20 mm, preservando integralmente o campo de visão no plano.
Ele nunca desenha a máscara, não recorta o fígado e não escurece o restante da
anatomia. Vinte e sete cortes distintos são distribuídos de forma intercalada em
três painéis, fazendo cada painel atravessar o território hepático inteiro. Se o
localizador falhar no gate, a máscara é ignorada para seleção e o caso recebe dois
painéis intercalados no primeiro 75% da extensão corporal cranial-caudal.

O piloto v3 contém os dez casos comparáveis anteriores e todos os quatorze casos
de fallback, totalizando 24 casos e 58 painéis. A coorte possui assinatura:

`dd8f2ab5584be4d66b83b2aba4654a30989db3406a385e1d384f7b0c18d9cb99`

A galeria possui assinatura:

`4cde18f7a1b605d73d48373fdcacec4d6bbc4da05659190b69b74844ce0d0126`

O HTML revisável possui hash:

`f01cc9da99c7da11a61c4f9c82112b75ee23540c9ecb1abdb4f6cf17b1ef9b2a`

Uma verificação separada confirmou 24/24 manifestos, 58/58 painéis, hashes,
dimensões 1536x1152, ausência de metadados PNG, zero máscaras de lesão e zero
ground truth. A coleção permanece com `eligible_for_inference=false` até nova
revisão humana.

### Aprovação e piloto temporal liver-enriched v3

A galeria v3 foi aprovada para inferência cega pelo revisor `jm`, exclusivamente
quanto à representação técnica. A revisão confirmou fígado reconhecível em todos
os painéis, ausência de painéis puramente não hepáticos, ausência de contorno ou
crop destrutivo e ausência visual de PHI ou anotação de lesão. A revisão não foi
uma avaliação diagnóstica. Sua assinatura é:

`121661fe4749fccb4e969d5643f6ec4d997fb6340014a399f4fac0b049c36646`

Antes da primeira chamada ao modelo, foi congelado o protocolo de 24 casos e 58
painéis: dez casos estáveis com três painéis e quatorze fallbacks com dois. O
protocolo vincula hashes da configuração, prompt, coorte, galeria, HTML, revisão,
manifestos e todos os PNGs. Sua assinatura é:

`714b84ea85b65fb15c7e2dc718aef4f93a968ec8a578937dee601e1b37e256bc`

O piloto cego foi executado no MedGemma 1.5 4B em CUDA, com quantização NF4 e
chamadas sequenciais. Todos os 24 casos foram concluídos, sem falha técnica. O
resultado cego agregado foi 23 `POSITIVA` e 1 `NEGATIVA`. Não houve leitura de
labels, ground truth ou máscaras de lesão durante preparação, inferência ou
verificação. A assinatura do run é:

`b9d06d88f692eceee9c8f6b5cf600c1c12a01d82bf7c7321e07019ae914eefaa`

No escopo medido — chamadas dos dois ou três painéis, validação, agregação e
persistência — o tempo médio foi 17,04 segundos por caso e o máximo 21,80
segundos. Todos passaram o teto de 180 segundos. Este resultado não é apresentado
como tempo end-to-end desde o DICOM, pois segmentação e geração dos painéis foram
pré-computadas e devem ser medidas em gate separado.

Um verificador sem acesso ao modelo revalidou os 24 manifestos de caso, os 24
`medgemma_report.json`, os 58 painéis referenciados, os hashes, assinaturas,
contagens, regras temporais e ausência de staging ou falha residual. Os testes
focados da representação, revisão, protocolo, runner, retomada e adulteração
passaram 15/15.

Os labels continuam fechados. Antes de avaliá-los, deve ser congelado um protocolo
de avaliação que defina a métrica deste braço positivo e a contabilização das 14
falhas técnicas da coorte completa de 335 casos. O piloto de 24 casos não pode ser
usado isoladamente para afirmar sensibilidade, especificidade ou a meta 75/75.

### Escala para os 321 casos elegíveis

Como o piloto foi deliberadamente enriquecido com os quatorze fallbacks e apenas
dez casos estáveis, ele não é uma amostra apropriada para estimar a métrica final.
Foi implementada uma geração completa, na ordem congelada do protocolo, mantendo
o contrato `335 = 321 elegíveis + 14 falhas técnicas`.

A geração completa usa checkpoint JSONL transacional com `fsync` e backup
rotativo. Antes de retomar, revalida contexto, ordem, manifesto e hashes de todos
os painéis concluídos. Um diretório parcial do caso corrente é descartado e
recriado; casos confirmados não são renderizados novamente. O resumo final só é
publicado atomicamente depois dos 321 casos.

A execução foi iniciada em tarefa local retomável
`Argos-LLD-MMRI-v23-LiverEnriched321`, com saída esperada em
`external_liver_enriched_full321_v3`. Ela permanece label-blind: as máscaras
automáticas de fígado servem apenas para localização axial grosseira, não são
renderizadas e não comandam crop no plano. Labels e máscaras de lesão continuam
fechados.
# Incidente de checkpoint liver-enriched full321 — 22/07/2026

- A geração `external_liver_enriched_full321_v3` foi interrompida após 192 casos
  confirmados por um `PermissionError` transitório do Windows ao substituir
  atomicamente `checkpoint_cases.jsonl`.
- O checkpoint principal e o backup permaneceram válidos e idênticos em 192
  casos; o caso seguinte havia sido renderizado, mas não foi aceito como
  concluído e deve ser refeito na retomada.
- A escrita atômica passou a repetir a operação de substituição diante de locks
  transitórios de leitores ou antivírus, preservando `fsync`, validação JSONL e
  backup rotativo.
- A correção foi validada por teste que simula duas recusas consecutivas do
  Windows e pela suíte focada: 31 testes aprovados.
- Labels e máscaras de lesão permaneceram fechados (`ground_truth_read=false`,
  `lesion_masks_read=0`).

## Coorte liver-enriched full321 v3 concluída e verificada

A geração completa foi publicada em
`external_liver_enriched_full321_v3` com 321 casos elegíveis, 307 casos com
localizador estável, 14 fallbacks independentes da máscara e 949 painéis. As 14
falhas técnicas da preparação continuam fora da inferência e permanecem
contabilizadas como erros no protocolo de 335 casos.

O verificador independente recalculou a assinatura da coorte, a assinatura da
preparação, todos os 321 hashes de manifesto e os 949 hashes de PNG. Também
revalidou os índices axiais intercalados, o contrato de 3 painéis estáveis ou 2
painéis fallback, dimensões RGB 1536×1152 e ausência de metadados PNG. Resultado:

- coorte: `44194d22bec69b735e8cdafc01300dcf9380fb62410c3af2024450089f36afc9`;
- verificação: `88047db31b27c0fd314a27e209cae14ece29bd3ce82452a38cd567428c3aaf60`;
- galeria: `a77902c729bd1fb24a04d8113a687b6e6436653719924c5336e5ea900cc8c1c5`;
- HTML: `b8f244f8d0c6da95c6fd300d7e3876ccc8def497fd1d1cbc3050bc38a33d2620`.

A galeria completa foi publicada em `external_liver_enriched_gallery321_v3` e
permanece pendente de revisão humana exclusivamente técnica. Durante toda a
geração e verificação, `ground_truth_read=false` e `lesion_masks_read=0`.

Foram adicionados testes negativos do verificador para adulteração de bytes do
PNG, metadados embutidos e alteração do intercalamento axial. A suíte focada
consolidada passou 35/35.

## Aprovação full321 e inferência cega 4B

O revisor `jm` aprovou tecnicamente a galeria completa. A revisão foi registrada
com schema específico de coorte completa e assinatura
`b56463f2709d658e64b544bcb11f985c97aba9acc287b348d03ac5a27d73cf0d`.

Antes da inferência, o contrato foi reforçado para transportar explicitamente:

- 335 casos no protocolo público;
- 321 casos elegíveis para inferência;
- 14 falhas técnicas excluídas da inferência;
- as mesmas 14 falhas contabilizadas obrigatoriamente como erros na métrica
  primária.

O protocolo temporal foi congelado e revalidado com assinatura
`bd6e49495890ce752ab71e1e81c6f0b3ac397ec45f2135cb1531929ec4225e42`.
Ele exige MedGemma 1.5 4B, configuração assinada, agregação determinística e
teto de 180 segundos para as chamadas sequenciais de 2 ou 3 painéis, validação,
agregação e persistência. Esse gate ainda não representa o tempo DICOM
end-to-end, que será medido separadamente.

A execução foi iniciada como tarefa retomável
`Argos-LLD-MMRI-v23-LiverEnrichedTiming321-v3`, com persistência atômica por
caso e retomada após reinicialização. O preflight confirmou modelo
`google/medgemma-1.5-4b-it`, NF4, CUDA e contrato HTTP correto. Labels e máscaras
de lesão permanecem fechados.

## Inferência cega full321 v3 concluída — 22/07/2026

A inferência MedGemma 1.5 4B foi concluída para os 321 casos elegíveis, sem
falha de chamada, sem diretório de staging remanescente e com persistência de
321 `medgemma_report.json` e 321 `timing_manifest.json`. O verificador
independente revalidou a coleção completa após o congelamento da execução.

Resultado verificado:

- status: `verified_complete_label_blind`;
- casos do protocolo: 335;
- casos inferidos: 321;
- falhas técnicas pré-inferência: 14, obrigatoriamente contadas como erros na
  métrica primária;
- imagens/chamadas de painel: 949;
- falhas durante a inferência: 0;
- tempo médio por caso: 20,6088 s;
- maior tempo por caso: 22,0216 s;
- casos acima de 180 s: 0;
- `ground_truth_read=false`;
- `lesion_masks_read=0`;
- assinatura do protocolo:
  `bd6e49495890ce752ab71e1e81c6f0b3ac397ec45f2135cb1531929ec4225e42`;
- assinatura da revisão:
  `b56463f2709d658e64b544bcb11f985c97aba9acc287b348d03ac5a27d73cf0d`;
- assinatura final da execução:
  `8372e5a05b7f0a4714cd78e181985ee1ed6dfe822469366e46a844601425c232`.

As 321 predições foram congeladas antes de qualquer abertura de labels. A
distribuição cega foi 314 `POSITIVA` e 7 `NEGATIVA`; essa distribuição não é
tratada como métrica de desempenho antes da avaliação pública congelada. A
tarefa recorrente foi desativada após a verificação para impedir nova passagem
sobre a coleção concluída.

O gate temporal aprovado mede inferência sequencial dos painéis, validação,
agregação e persistência. Ele não substitui o gate futuro de 180 segundos
end-to-end desde a entrada DICOM, que permanece pendente.

## Avaliação externa congelada liver-enriched v3 — 22/07/2026

Antes da abertura dos labels públicos, foram congelados e verificados:

- protocolo de avaliação:
  `0f21fc49e5b6919a2042fa64eb07e455d3489bf436cbf3cd031c03771f8591c7`;
- lote de 321 predições:
  `31ce5cc1bb691db2b72a38f9d52296a0cfd58e34fa700a0cfc0b2d8f7d7e2342`;
- SHA-256 do JSONL de predições:
  `a7b4cf2963c131c9d3731259ce6df288a0766c2056d91eb6ff8d5762b6250f69`.

O protocolo fixou antes dos labels: decisão discreta original do MedGemma,
`INCONCLUSIVA` como erro, 14 falhas técnicas como erros, limiares de 75% para
sensibilidade e especificidade e escore contínuo restrito à ROC-AUC. O escore
é o máximo da probabilidade de `POSITIVA` entre os painéis e não altera a
classificação discreta congelada.

Após a verificação integral do congelamento, os labels públicos foram abertos
exclusivamente pelo avaliador. Nenhuma máscara de lesão foi lida. Resultado
primário sobre os 335 casos:

- matriz de confusão: TP=148, TN=3, FP=175, FN=9;
- sensibilidade: 94,27% (IC 95% de Wilson: 89,47%–96,96%);
- especificidade: 1,69% (IC 95% de Wilson: 0,57%–4,84%);
- acurácia: 45,07%;
- acurácia balanceada: 47,98%;
- ROC-AUC exploratória nos 321 elegíveis: 0,5145;
- falhas técnicas: 5 casos positivos e 9 negativos;
- assinatura da avaliação:
  `ac266a5a65a57f27955db8f3be386cd18dd854f500bc9de164a03223fa4165b7`.

A conferência independente reproduziu exatamente TP, TN, FP e FN. O braço
liver-enriched v3 atingiu o requisito de sensibilidade e o tempo de inferência
por painéis, mas falhou de forma ampla na especificidade. O comportamento é de
viés para `POSITIVA`: 314 das 321 predições elegíveis foram positivas. Por
subtipo negativo, foram corretos 0/46 FNH, 1/79 hemangiomas e 2/53 cistos
hepáticos. Portanto, esta configuração não está qualificada e não deve ser
levada ao holdout nem apresentada como tendo atingido 75/75.

O próximo desenvolvimento deve ser realizado sem reutilizar este conjunto
como novo teste final. A prioridade é criar, em dados de desenvolvimento, uma
regra ou segundo estágio específico para diferenciar HCC de lesões benignas,
preservando a sensibilidade. O gate DICOM end-to-end de 180 segundos continua
pendente e somente será executado em uma configuração que demonstre potencial
real para o gate de acurácia.

## Exploração pós-label: RAG + pathology-target + liver-enriched — 23/07/2026

Esta rodada não é uma nova validação externa independente: os rótulos públicos
LLD-MMRI já haviam sido abertos após a avaliação liver-enriched v3. Ela é,
portanto, desenvolvimento exploratório pós-label para medir se o contexto RAG
e o foco explícito em HCC versus mimetizadores benignos reduzem falsos positivos.

Antes da leitura dos rótulos nesta rodada, foram congelados 321 relatórios e
949 chamadas de painel. A verificação independente confirmou 321/321 casos
elegíveis, zero falhas de execução, 14 falhas técnicas prévias preservadas como
erros e nenhuma leitura de máscara de lesão. A inferência sequencial por caso
ficou entre 39,69 s em média e 42,80 s no máximo, abaixo do teto operacional
de 180 s para o conjunto de painéis.

Assinaturas congeladas:

- protocolo de inferência: `c92e0423aa5997a5656f8b71be7157b4b58136853c76653102f6a3c626840981`;
- lote de predições: `0f8627aff097aba94408cc9e8371d19ff642f665f36e232063650edf4c0a758b`;
- SHA-256 das predições: `082d75c2cabcde7d65497c40e6cad6bb5ec0a7cae2d9b002740b22784aa09b59`;
- avaliação pós-label: `1506a6e41f7e6afcd1235bcaccd613e5464161fa715bfe7afc15a98fbf3503a1`.

O resultado foi inequivocamente negativo para a hipótese de que esta forma de
RAG/prompt resolveria a especificidade: as 321 predições elegíveis foram
`POSITIVA` (0 negativas, 0 inconclusivas). Sobre os 335 casos, com as falhas
técnicas contabilizadas como erro, a matriz foi TP=152, TN=0, FP=178 e FN=5:

- sensibilidade: 96,82% (IC 95% Wilson: 92,76%–98,63%);
- especificidade: 0,00% (IC 95% Wilson: 0,00%–2,11%);
- acurácia: 45,37%; acurácia balanceada: 48,41%; ROC-AUC exploratória: 0,4822.

Nenhum FNH (0/46), hemangioma (0/79) ou cisto hepático (0/53) foi classificado
corretamente como negativo. Assim, o RAG textual e o prompt pathology-target,
na interface `choice_classification` atual, não reduziram o viés para positivo;
esta configuração está reprovada para 75/75 e não deve ser levada ao holdout.
O próximo passo de desenvolvimento é investigar a interface de decisão e a
calibração/segundo estágio em dados de desenvolvimento, sem ajustar um limiar
retrospectivamente para maquiar a especificidade.
