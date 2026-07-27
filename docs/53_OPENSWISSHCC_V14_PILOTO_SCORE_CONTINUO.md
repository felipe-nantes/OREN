# OpenSwissHCC v14 — piloto do escore volumétrico contínuo

Data da execução: 2026-07-15

## Conclusão técnica

O piloto v14 foi aprovado para avançar à inferência cega da coorte de
desenvolvimento. Duas passagens planejadas do mesmo caso produziram exatamente
os mesmos escores e ambas terminaram abaixo de 180 segundos.

O piloto não mede acurácia. Nenhum label foi lido e o holdout permaneceu
fechado.

## Implementação validada

- contrato: `dtwin-medgemma-volume-score-v1`;
- endpoint local: `/score-volume`;
- método: `first_token_restricted_softmax_v1`;
- classes fixas: `POSITIVA`, `NEGATIVA`, `INCONCLUSIVA`;
- prefixo protegido: `{"resultado_hipotese":"`;
- uma passagem direta do modelo por requisição;
- nenhuma geração autoregressiva para obter a classe;
- um único runtime/modelo compartilhado com as rotas históricas;
- probabilidades restritas validadas e auditáveis;
- persistência atômica e recusa de sobrescrita;
- revisão humana obrigatória e uso somente em pesquisa.

O arquivo público `tools/medgemma_server.py` foi preservado como bootstrap
compatível com a execução direta usada por `run_win.ps1`. A implementação
histórica está em `tools/medgemma_server_base.py` e a extensão v14 em
`tools/medgemma_server_v14.py`. Essa separação evita carregar uma segunda cópia
do MedGemma na GPU.

## Protocolo congelado

- coorte: 87 casos de desenvolvimento;
- bundle reutilizado: pilhas cegas aprovadas do v13;
- assinatura do protocolo:
  `25702f4016c558bb101791c29f4a608028bc9ca1955e975f993d174f0b61a03b`;
- SHA-256 do arquivo de protocolo:
  `4d6cb82a7d9e8194a71260706ae6da69821992d224ccd26ea2d36fddd1126352`;
- requisições por caso no batch: 1;
- retries automáticos: 0;
- réplicas planejadas somente no piloto: 2;
- tolerância de determinismo: `1e-6`;
- gate temporal: 180 segundos por requisição;
- `ground_truth_read=false`;
- `holdout_opened=false`.

Artefato:

`casos/qualification/openswisshcc_v1/prepared/development_freezes_v14/volume_score_protocol.json`

## Caso e resultado do piloto

Caso selecionado deterministicamente:

`anon-openswiss-04031ea54343b8db`

- 50 cortes axiais;
- mesma pilha e mesmo manifesto nas duas passagens;
- classificação nas duas passagens: `NEGATIVA`;
- diferença absoluta máxima entre probabilidades: `0.0`;
- determinismo: aprovado;
- gates temporais: 2/2 aprovados.

Probabilidades restritas idênticas:

| Classe | Escore |
|---|---:|
| `POSITIVA` | 0,30450436 |
| `NEGATIVA` | 0,39099133 |
| `INCONCLUSIVA` | 0,30450436 |

Esses valores são probabilidades relativas restritas aos primeiros tokens das
três classes. Não são probabilidades clínicas nem probabilidades das sequências
textuais completas.

## Tempo

| Réplica | Gateway | Externo | Gate |
|---|---:|---:|---:|
| 1 | 151,3421 s | 151,4126 s | aprovado |
| 2 | 160,3112 s | 160,3686 s | aprovado |

Margem no pior resultado: 19,6314 segundos.

O tempo total do piloto foi maior que 180 segundos porque ele contém duas
requisições planejadas. O gate é individual por análise, conforme o objetivo do
projeto.

## Tokens auditados

| Classe | Primeiro token ID | Quantidade de tokens |
|---|---:|---:|
| `POSITIVA` | 83600 | 2 |
| `NEGATIVA` | 111574 | 2 |
| `INCONCLUSIVA` | 1204 | 3 |

Os primeiros tokens são distintos, condição necessária para o método v14.

## Integridade

- réplica 1:
  `60ad9d9eeff727a348118616ce205e7e480ab98db9f276bd4c3c133458ac7ac1`;
- réplica 2:
  `7b5991016277a099a438fcb489b7a80cf0e677bf81daed3a07ce55023f232e83`;
- resumo:
  `466c6f9494407e6471785d18f44fead2a0abda0111d3cbb969df21c5198e13d1`.

Diretório autoritativo:

`casos/qualification/openswisshcc_v1/runs/dev_v14_volume_score_pilot/`

## Testes

Após a compatibilidade com execução direta ser restaurada:

- 31 testes focados passaram;
- 587 testes da suíte completa passaram;
- 334 warnings de dependências/depreciações já conhecidos;
- nenhuma regressão detectada nas rotas v1 e v13.

## Próxima etapa permitida

Executar o v14 nos 87 casos sem labels, validar completude, hashes, distribuição
cega e tempo de todos os casos. Somente após a inferência cega completa será
permitida a junção tardia com os labels de desenvolvimento para calibração
aninhada. O holdout deve continuar fechado.

