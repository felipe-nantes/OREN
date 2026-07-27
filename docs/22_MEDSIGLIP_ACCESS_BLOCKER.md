# Bloqueio de acesso ao MedSigLIP

Data: 2026-07-14

## Tentativa autorizada

Após autorização explícita do usuário e confirmação de aceite dos termos, foi
tentado o download de `google/medsiglip-448` para o cache local do Hugging Face.

## Resultado

O servidor respondeu `403 Forbidden / GatedRepoError` antes de transferir os
pesos. A mensagem informou que a conta autenticada não pertence à lista
autorizada do repositório.

Conta associada ao token local, consultada sem exibir a credencial:

```text
jotaeme67 (Joao Marcelo)
```

Estado do cache após a falha:

- diretório de cache criado;
- 3 arquivos de metadados;
- 22.863 bytes;
- nenhum peso do modelo baixado;
- nenhum teste MedSigLIP real executado.

## Ação necessária

Uma das opções abaixo deve ser concluída pelo titular da conta:

1. aceitar os termos de `google/medsiglip-448` enquanto estiver logado como
   `jotaeme67`; ou
2. atualizar localmente o token para a conta que já aceitou os termos.

O token não deve ser enviado por chat nem versionado no repositório.

## CLI experimental

O arquivo `tools/score_medsiglip_panel.py` possui uma importação incorreta
detectada pelo smoke test. A tentativa de correção pelo editor seguro falhou por
um problema de ACL da sandbox, mesmo após concessão temporária autorizada. O ACL
original foi restaurado integralmente; nenhuma permissão ampliada permaneceu.

A CLI não deve ser usada até ser recriada/corrigida e testada. Os módulos puros
continuam com seus testes aprovados, mas isso não substitui o smoke test real com
os pesos.
