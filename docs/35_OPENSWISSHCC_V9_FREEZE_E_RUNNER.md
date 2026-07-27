# OpenSwissHCC v9 — freeze e runner cego

Data: 2026-07-14

## Configuração exclusiva

`configs/medgemma_local_4b_multisequence_v9_pairwise.yaml` fixa:

- modelo exato `google/medgemma-1.5-4b-it`;
- modo `choice_classification`;
- timeout interno de 120 segundos;
- zero retry de transporte;
- zero retry de validação;
- RAG desativado na calibração;
- estratégia `volumetric_blocks`.

A configuração volumétrica antiga, com timeout de 600 segundos e retries, não é aceita pelo freeze v9.

## Freeze

O freeze vincula revisão humana, coorte, configuração efetiva, banco de frases pairwise, regra `scores_only_no_decision` e limite máximo de 180 segundos por caso.

Ele não pode ser criado sem um manifesto de revisão humana válido.

## Runner

O runner:

- verifica revisão e freeze antes de carregar o modelo;
- processa os painéis sequencialmente;
- registra a modalidade fora do FOV no prompt;
- valida SHA-256 antes de cada chamada;
- persiste scores de cada painel atomicamente;
- não lê labels;
- não calcula métricas;
- não emite decisão final;
- aborta e remove o staging se o caso exceder 180 segundos.

Uma lista opcional de `--case-id` permite piloto técnico previamente definido. Sem essa opção, processa toda a coorte aprovada.

## Testes

- bloqueio antes do primeiro score quando a revisão é inválida;
- adulteração de revisão, coorte, manifesto ou painel;
- rejeição de timeout acima de 180 segundos;
- rejeição de configuração com retry;
- saída somente de scores;
- remoção de execução parcial após timeout;
- suíte completa: 465 testes aprovados.

## Estado

Nenhuma inferência v9 foi executada. O próximo passo continua condicionado à aprovação humana da galeria e à criação do manifesto assinado.
