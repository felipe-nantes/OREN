# LLD-MMRI v23 — protocolo de validação externa independente

## Estado

O protocolo externo foi congelado antes do download das imagens e antes de qualquer
predição. O calibrador v23 do OpenSwissHCC já estava congelado quando as categorias
públicas do LLD-MMRI foram usadas para formar a coorte.

Esta etapa ainda não qualifica o ARGOS. Ela prepara uma validação externa na qual as
predições serão persistidas e assinadas antes da abertura dos labels protegidos para
avaliação.

## Dataset e escopo clínico

- dataset: `wanglab/LLD-MMRI-MedSAM2`;
- revisão fixada: `b7e8da56b267587689d8440e8298205f3fc4914e`;
- licença: CC BY-NC 4.0 e termos não comerciais do dataset;
- modalidade: RM hepática multifásica em NIfTI;
- uso: somente pesquisa, com revisão humana obrigatória;
- redistribuição das imagens: proibida pelo pacote de transferência do ARGOS.

O endpoint foi definido para ser compatível com o alvo de suspeita de HCC:

```text
positivo: HCC (categoria pública 6)                         157 casos
negativo: hemangioma + cisto + FNH (categorias 0, 4 e 5)  178 casos
total                                                              335 casos
```

Foram excluídos antes da inferência: colangiocarcinoma intra-hepático, abscesso e
metástase. Essa exclusão é parte do endpoint congelado e não pode ser alterada depois
de observar as predições.

Esta coorte testa HCC contra mimetizadores benignos. Ela não contém um braço de fígados
clinicamente normais; a especificidade em normalidade continua sendo medida
separadamente no CHAOS. Portanto, nenhum resultado LLD-MMRI deve ser descrito como
especificidade em “pessoas saudáveis”.

## Protocolo congelado

Diretório:

```text
casos/qualification/lld_mmri_v23/prepared/external_protocol_v1
```

- assinatura do protocolo:
  `70422594c09884111e34f3e575e2eba68aa63f3aaadba332e8b2f6577b31fce1`;
- SHA-256 do protocolo:
  `22a6533765a0101167183d392e0be1fb20991abbcd83b6714ea0e8dbf6b0e5ef`;
- calibrador v23:
  `d0a955178783cf7f2914053c87d3d99d186ab4a56960620068bd118e5ccac475`;
- casos: 335;
- predições presentes no congelamento: não;
- imagens baixadas pelo congelamento: não.

Labels e mapeamentos de origem permanecem em subdiretórios protegidos. Eles não devem
ser copiados para o diretório de inferência nem usados para gerar painéis, candidatos,
features ou prompts.

## Download seletivo e fail-closed

O downloader foi implementado para baixar exclusivamente as oito imagens por caso:

```text
T1 pré-contraste
T1 arterial
T1 venosa
T1 tardia
T2
DWI
T1 em fase
T1 fora de fase
```

A seleção foi auditada contra o índice oficial da revisão fixada:

```text
casos do protocolo                 335
imagens selecionadas             2680
imagens únicas                   2680
volume remoto selecionado       11,396 GiB
arquivos fora de images/            0
labels/máscaras selecionados        0
erros de correspondência            0
```

O comando exige aceite explícito e aborta se o protocolo, o mapeamento, a revisão do
dataset, a contagem de fases ou qualquer hash divergir:

```powershell
.\.venv-win\Scripts\python.exe tools\download_lld_mmri_v23_external.py `
  --protocol-root casos\qualification\lld_mmri_v23\prepared\external_protocol_v1 `
  --destination data\raw\LLD_MMRI_v23_hf `
  --accept-license
```

O comando não deve ser executado antes do aceite explícito dos termos pelo responsável
do projeto. O download completo do repositório não deve ser usado, porque também
traria os diretórios públicos de labels.

Depois do download, ou após transportar os arquivos para outra máquina, a integridade
deve ser comprovada novamente sem consultar o índice remoto:

```powershell
.\.venv-win\Scripts\python.exe tools\download_lld_mmri_v23_external.py `
  --protocol-root casos\qualification\lld_mmri_v23\prepared\external_protocol_v1 `
  --destination data\raw\LLD_MMRI_v23_hf `
  --verify-only
```

O verificador confere a assinatura do protocolo e do manifesto, ordem dos casos,
papéis das oito fases, unicidade dos caminhos, tamanho e SHA-256 de cada uma das 2.680
imagens. Qualquer divergência interrompe o fluxo antes da segmentação.

## Validação de software

Após a inclusão do downloader e do verificador fail-closed, a suíte completa foi
executada em 20 de julho de 2026:

```text
929 testes aprovados
0 testes reprovados
476 avisos de depreciação
90,21 segundos
```

Os avisos são provenientes principalmente de dependências científicas e não indicaram
falha funcional nesta execução.

Essa execução já inclui protocolo, download, preparação label-blind, painel e revisão
humana do LLD-MMRI. A suíte completa deverá ser repetida depois da execução real e
antes do congelamento das predições.

## Pipeline externo congelado

Depois do download, a sequência obrigatória é:

1. validar hashes e as oito fases de cada caso;
2. normalizar os papéis das sequências sem consultar labels;
3. segmentar automaticamente o fígado, sem máscara pública de lesão;
4. construir os sinais v11 e os candidatos determinísticos de realce;
5. extrair a geometria v23;
6. aplicar o calibrador v23 congelado, sem reajuste de peso ou limiar;
7. persistir e assinar todas as predições;
8. medir o tempo end-to-end por caso, incluindo preparação;
9. abrir os labels protegidos somente após o congelamento das predições;
10. calcular sensibilidade, especificidade, matriz de confusão, IC 95% e gates
    `75/75/180`.

Qualquer falha técnica, fase ausente, violação de hash ou processamento parcial deve
invalidar o caso; ela não pode ser convertida silenciosamente em negativo.

### Preparação label-blind implementada

O estágio de preparação já está disponível, mas ainda não foi executado nos dados
reais:

```powershell
.\.venv-win\Scripts\python.exe tools\prepare_lld_mmri_v23_external.py `
  --protocol-root casos\qualification\lld_mmri_v23\prepared\external_protocol_v1 `
  --download-root data\raw\LLD_MMRI_v23_hf `
  --failed-audit casos\qualification\lld_mmri_v23\prepared\external_geometry_audit_v1 `
  --harmonization casos\qualification\lld_mmri_v23\prepared\external_dynamic_harmonized_v1 `
  --segmentation-audit casos\qualification\lld_mmri_v23\prepared\external_segmentation_audit335_fullres_v1 `
  --segmentation-audit-signature 401d78e307738165aba10db99ccf18b920493082ae344a06c523ca498a774028 `
  --technical-amendment casos\qualification\lld_mmri_v23\prepared\external_technical_amendment_v2 `
  --technical-amendment-signature 1b31a853e26aa956000dc36831f58651e9ff4ee8651c948733d36bf8e28e9368 `
  --config configs\medgemma_local_4b_lld_v23_uniform9_choice.yaml `
  --profile profiles\figado.yaml `
  --output-root casos\qualification\lld_mmri_v23\prepared\external_inputs_v1 `
  --device gpu
```

Nesta execução, o estágio não repete o TotalSegmentator: ele reutiliza somente as
321 máscaras aprovadas pela auditoria integral assinada. As 14 falhas técnicas não
recebem input nem inferência, mas continuam vinculadas como erros da métrica
primária. O estágio:

- revalida integralmente o download antes de ler NIfTI;
- exige volumes 3D com geometria finita;
- exige as quatro fases T1 dinâmicas na mesma grade física;
- verifica e materializa somente a máscara hepática automática auditada na fase venosa;
- aborta se a máscara estiver vazia, pequena ou em outra geometria;
- publica arquivos com nomes anônimos e papéis padronizados;
- não aceita nem copia labels ou máscaras públicas de lesão;
- persiste checkpoint transacional por caso com `fsync` e backup recuperável;
- publica atomicamente `inputs.jsonl` e `summary.json` assinados.

Se a geometria dinâmica real não coincidir, o estágio falhará intencionalmente. Nesse
caso, deverá ser congelado e auditado um método explícito de registro antes de gerar
features de realce; reamostragem silenciosa não será aceita.

### Painéis e gate humano implementados

Depois de uma preparação real aprovada pelo verificador, os painéis do leitor v11/v4
podem ser gerados com a configuração congelada:

A preparação real foi concluída e reverificada independentemente com 335 casos de
protocolo, 321 inputs elegíveis, 14 falhas técnicas, 2.568 imagens de fase e 321
máscaras hepáticas automáticas. Nenhum label ou máscara de lesão foi lido. A
assinatura ativa da preparação é
`314dff89ee408976881320089d00b97ee0f6f1cb4c5e09ef2991ef5edcc7d737` e o hash de
`inputs.jsonl` é
`7b2544b9fc4be8cb8ff43f23105b4361cb9fb1f5df0ba1537398c99e74e47579`.

```powershell
.\.venv-win\Scripts\python.exe tools\build_lld_mmri_v23_panels.py panels `
  --protocol-root casos\qualification\lld_mmri_v23\prepared\external_protocol_v1 `
  --prepared-root casos\qualification\lld_mmri_v23\prepared\external_inputs_v1 `
  --output-root casos\qualification\lld_mmri_v23\prepared\external_uniform9_panels_v1 `
  --config configs\medgemma_local_4b_lld_v23_uniform9_choice.yaml `
  --profile profiles\figado.yaml

.\.venv-win\Scripts\python.exe tools\build_lld_mmri_v23_panels.py gallery `
  --panel-root casos\qualification\lld_mmri_v23\prepared\external_uniform9_panels_v1 `
  --output-dir casos\qualification\lld_mmri_v23\prepared\external_uniform9_gallery_v1
```

Os painéis reproduzem `multiphase_fusion + uniform_9`, MedGemma 1.5 4B, sem RAG,
sem retry e com as mesmas três fases dinâmicas do v11/v4. Todos permanecem inelegíveis
para inferência até a aprovação técnica explícita e assinada:

A geração usa staging e checkpoint durável por caso. Em desligamento ou
interrupção, a retomada revalida os hashes dos artefatos já concluídos, preserva o
prefixo confirmado e renderiza somente os casos restantes. Um caso parcial sem
checkpoint nunca é reutilizado, e a coleção só é publicada após concluir e
verificar todos os 321 casos elegíveis.

Para máscaras auditadas com menos de nove planos hepáticos, a configuração LLD
ativa `short_liver_policy=blank_tiles`: todos os planos reais aparecem uma única
vez e os espaços restantes da grade são tiles vazios explicitamente identificados.
Não há duplicação nem fabricação de cortes. Essa exceção está vinculada ao adendo
v3 assinado
`3c3b32214cfbacd24e0f3f4bbd3e7ea9a04a27f60963fd5601aaee6517203acd`;
o baseline geral continua rejeitando máscaras curtas.

Os inputs foram rematerializados e verificados sob o adendo v3 com assinatura de
preparação
`be0a407c14cede03dddc5ec0142eadeee3ad2a93ba4559831863e03a53c90da7`.
O hash do manifesto permaneceu idêntico porque imagens e máscaras auditadas não
foram alteradas; apenas o vínculo técnico e a política de composição do painel
mudaram.

```powershell
.\.venv-win\Scripts\python.exe tools\review_lld_mmri_v23.py `
  --panels casos\qualification\lld_mmri_v23\prepared\external_uniform9_panels_v1 `
  --gallery casos\qualification\lld_mmri_v23\prepared\external_uniform9_gallery_v1 `
  --review casos\qualification\lld_mmri_v23\prepared\external_uniform9_review_v1.json `
  --reviewer jm --approve
```

O gate exige aprovação dos 321 casos tecnicamente elegíveis, confere os hashes do painel original e da
cópia da galeria e registra que a revisão é exclusivamente técnica, não diagnóstica.
MedGemma, MedSigLIP e o localizador não devem ser carregados antes desse gate.

Os 321 painéis e a galeria v1 foram concluídos. A assinatura da coorte é
`6879b6a4b6270d971b0606923ee2abe7c877f6a59fe869e751fa0bd41b5a78bc` e a
assinatura da galeria é
`993d99245fe5ba24b56cd3ae99b55510d817a9a7c8dacfb4160ebc8193d4e09c`.
A execução permanece bloqueada no gate humano técnico.

Os manifestos de preparação, painéis, galeria, revisão, sinais, shape, predições e
avaliação preservam o contrato `335 protocolos = 321 elegíveis + 14 falhas`.
Depois da abertura dos labels, cada falha positiva conta como falso-negativo e cada
falha negativa como falso-positivo. ROC-AUC é reportada apenas nos casos com score,
com o número de falhas excluídas explicitamente declarado. Se os casos elegíveis
com score não contiverem as duas classes, ROC-AUC é registrada como indisponível,
com motivo e contagens, em vez de interromper a avaliação ou fabricar scores. O
gate de 180 segundos é declarado explicitamente sobre os 321 casos elegíveis para
inferência; as 14 falhas continuam incidindo nos gates de sensibilidade e
especificidade.

A rodada direta de tempo é retomável por caso, com checkpoint transacional e
validação das predições e das oito etapas obrigatórias. O tempo de um caso já
concluído não inclui o intervalo em que o computador permaneceu desligado, pois
cada registro mede uma chamada contínua independente. Casos acima de 180 segundos
são preservados e fazem o gate falhar, em vez de invalidar ou ocultar a evidência.

## Critério de decisão

O ARGOS 4B somente poderá ser qualificado neste braço se alcançar simultaneamente:

```text
sensibilidade >= 75%
especificidade >= 75%
tempo end-to-end máximo por caso <= 180 s
```

Mesmo em caso de sucesso, o resultado será descrito como desempenho experimental em
HCC versus mimetizadores benignos no LLD-MMRI. A transferência posterior ao 27B no Mac
exigirá execução e calibração próprias; o resultado do 4B não pode ser atribuído ao
27B automaticamente.

## Correção posterior à revisão da galeria v1

A revisão humana técnica rejeitou a galeria v1 por contornos e crops baseados em
máscaras hepáticas incompletas ou fragmentadas. A coorte e a galeria permanecem
preservadas, mas `technical_rejection.json` define
`eligible_for_inference=false`. Antes de uma nova galeria, o protocolo deve passar
por um piloto label-blind com gate anatômico físico e conectividade 3D. Nenhuma
inferência pode reutilizar os painéis v1.
