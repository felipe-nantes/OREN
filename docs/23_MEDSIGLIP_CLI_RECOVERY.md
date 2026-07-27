# Recuperação da CLI MedSigLIP

Data: 2026-07-14

## Problema

`tools/score_medsiglip_panel.py` importava um writer atômico inexistente de
`dtwin.medgemma_client`. O erro só apareceu no smoke test de importação da CLI.

O editor seguro não conseguia reabrir o arquivo devido ao ACL herdado de uma
sandbox anterior. A concessão temporária de permissão foi insuficiente e o ACL
original foi restaurado integralmente.

## Recuperação autorizada

Com autorização explícita do usuário:

1. o arquivo antigo foi movido para um backup único em `%TEMP%`;
2. o caminho original foi recriado pelo editor seguro;
3. foi implementado um writer JSON local com arquivo temporário e `os.replace`;
4. foi adicionado `tests/test_medsiglip_cli.py`;
5. o smoke test e os testes foram executados;
6. somente após aprovação, o backup dentro de `%TEMP%` foi removido.

Nenhum backup permaneceu e nenhuma permissão foi deixada ampliada.

## Validação

- `python -m tools.score_medsiglip_panel --help`: aprovado;
- 13 testes MedSigLIP/spotlight: aprovados;
- writer testado com substituição de um JSON existente;
- arquivo temporário ausente após a escrita;
- `final_decision` permanece `null`.

## Estado externo

A CLI está funcional, mas o modelo real ainda não foi carregado. O download de
`google/medsiglip-448` continua bloqueado por 403 para a conta associada ao token
local (`jotaeme67`). Nenhum peso deve ser considerado instalado até o smoke test
real confirmar o snapshot e a inferência.
