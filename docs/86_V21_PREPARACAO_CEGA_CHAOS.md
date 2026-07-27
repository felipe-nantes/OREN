# ARGOS v21 — preparação cega do braço secundário CHAOS

## Escopo

Esta etapa prepara o CHAOS v1.03 exclusivamente como braço secundário de
especificidade e estresse de mudança de domínio. Ela não constitui a matriz de
confusão primária combinada, pois classe, dataset e protocolo de aquisição estão
confundidos: os positivos independentes vieram do LiverHccSeg e os controles
negativos vêm do CHAOS.

O holdout OpenSwissHCC permaneceu fechado durante toda a etapa.

## Autorização e aquisição

- licença autorizada pelo usuário: CC BY-NC-SA 4.0;
- arquivo oficial: `CHAOS_Train_Sets.zip`;
- tamanho validado: 890.771.694 bytes;
- MD5 oficial validado: `df21053002a1cc86df918a87da3b2c19`;
- SHA-256 local: `535f7d3417a0e0f0d9133fb3d962423d2a9cf3f103e4f09a3d8a1daf87d5d2fc`;
- somente `Train_Sets/MR/` foi extraído;
- o conjunto de teste e CT não foram extraídos.

A extração contém 20 sujeitos e 3.187 arquivos, com assinatura de árvore:

```text
6529f2982dc1fa56314f601641038a6f48394e3000fa3f2db6ffbffba4bf82db
```

## Correção do registry

O CHAOS reutiliza `SeriesInstanceUID` entre diretórios InPhase e OutPhase. O
discoverer foi corrigido para agrupar por UID e diretório físico quando um UID
aparece em mais de um diretório. Isso preserva as duas séries sem mudar o hash
legado para datasets onde o UID é único.

O registry reconstruído possui 60 registros:

- 20 T1 in-phase;
- 20 T1 out-phase;
- 20 T2-SPIR;
- 60 identificadores de série únicos;
- modalidade MR em todos os registros;
- nenhum UID bruto persistido no manifesto operacional.

## Coorte pública e preparação cega

O protocolo público independente usado para selecionar os 20 controles tem
assinatura:

```text
75d63e46e89cb043dd5b7bc09e997bd6b9302de116692b5634c83f8f55644237
```

A preparação:

1. revalida a extração completa por hash;
2. revalida o manifesto cego e o mapa operacional;
3. exige exatamente T1 in-phase, T1 out-phase e T2-SPIR por sujeito;
4. converte os DICOMs para NIfTI;
5. reduz a máscara multiórgão pública ao rótulo hepático `63`;
6. descarta os demais rótulos de órgãos;
7. reamostra T1 out-phase e T2-SPIR para a grade T1 in-phase quando necessário;
8. exige suporte hepático mínimo de 95%;
9. não copia nem lê máscara de lesão, tumor ou classe patológica.

Foram preparados 20/20 casos. A assinatura da preparação é:

```text
c047393c43e5bf5ade43366d3e72a624acb093440cc33d51ab5a1deca9bb6975
```

O preflight independente confirmou todos os hashes, geometrias e suporte
hepático, sem rótulos patológicos e sem abrir o holdout.

## Representação visual v21

Foi criada uma configuração específica para evitar interpretação semântica
incorreta das sequências CHAOS:

```text
R = T1 in-phase
G = T1 out-phase
B = T2-SPIR
```

Essas sequências não são fases dinâmicas arterial, portal ou tardia. O leitor
permanece o mesmo MedGemma 1.5 4B do protocolo v21:

- `choice_classification`;
- `uniform_9`;
- uma imagem por caso;
- timeout do modelo de até 120 segundos;
- zero retry;
- RAG desligado;
- nenhuma recalibração usando o CHAOS.

Foram renderizados 20/20 painéis, todos ainda inelegíveis para inferência. A
assinatura da coorte visual é:

```text
c07132616654ac50444d95ca134cf180817b8ce35a8d969a7e2c83a0071cc79d
```

A galeria técnica cega possui assinatura:

```text
9b0abbbac64e253cbe1512de320ccadc2fa01908309182526f46ca67a440dc94
```

Após a implementação, a suíte completa do ARGOS passou com:

```text
821 passed, 0 failed
```

Os 396 avisos são depreciações já conhecidas de dependências e não falhas dos
gates CHAOS.

## Gate humano pendente

Antes da inferência, o revisor deve confirmar em todos os 20 painéis:

- fígado visível e com crop não destrutivo;
- orientação plausível;
- contorno hepático sem ocultar o parênquima;
- fusão RGB interpretável nas três sequências declaradas;
- ausência de PHI;
- ausência de qualquer marcação de lesão;
- ausência de painel tecnicamente impossível de interpretar.

Esta revisão é somente técnica. Não se deve avaliar diagnóstico nem tentar
confirmar que cada caso é negativo visualmente.

## Próxima etapa após aprovação

Após aprovação explícita e assinada da galeria:

1. congelar hashes dos painéis, configuração e regra de decisão;
2. executar os sinais cegos do protocolo v21 no 4B;
3. persistir predições antes de abrir qualquer rótulo protegido;
4. congelar e assinar o protocolo de avaliação do braço negativo;
5. solicitar autorização específica para abrir apenas o ground truth público
   CHAOS necessário à avaliação;
6. calcular especificidade, taxa de falsos positivos, inconclusivos e tempo;
7. reportar o resultado como estresse secundário de domínio, separadamente da
   sensibilidade LiverHccSeg e sem alegar validação 75/75 combinada.

## Infraestrutura pronta, ainda bloqueada

O código necessário às etapas posteriores já foi implementado sem executar os
modelos:

- gate de revisão humana assinado e vinculado aos hashes de todos os painéis;
- executor em estágios separados para TotalSegmentator, MedSigLIP e MedGemma;
- localizador configurado explicitamente com `t2_spir` e `liver_mask`, sem
  registrar incorretamente o CHAOS como T1 venoso;
- schemas CHAOS separados dos artefatos LiverHccSeg;
- montagem dos três sinais v11 sem decisão ou ground truth;
- aplicação futura do calibrador v11 congelado, sem ajuste no CHAOS;
- freeze das predições e do protocolo de avaliação;
- avaliador negativo de classe única com especificidade, FP, IC95% Wilson e
  tempo, exigindo autorização explícita e assinatura exata;
- bloqueio permanente de matriz primária combinada por confusão dataset/classe.

O problema `WinError 6714` observado anteriormente no `spawn` do
TotalSegmentator também foi tratado sem modificar o ambiente virtual. Durante
somente o estágio localizador no Windows, o ARGOS adiciona um `sitecustomize`
temporário ao `PYTHONPATH` dos novos subprocessos para bloquear o pacote
opcional `pyarrow`. O processo principal continua inalterado, nenhuma pasta do
pacote é renomeada e todas as variáveis/diretórios temporários são restaurados
em `finally`, inclusive quando há exceção. O manifesto do localizador registra
o identificador `pyarrow_blocked_for_windows_spawn_v1` quando a proteção é
aplicada.

Um preflight real foi executado sem arquivo de revisão e abortou corretamente:

```text
[ABORTADO] Revisao humana CHAOS v21 ausente
```

Portanto, nenhum modelo foi carregado e nenhuma inferência foi iniciada antes do
gate humano.
