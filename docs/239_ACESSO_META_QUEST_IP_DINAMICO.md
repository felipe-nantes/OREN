# OREN Meta Quest em redes com IP dinâmico

## Objetivo

O acesso WebXR do OREN agora se adapta automaticamente quando o PC muda de Wi-Fi ou recebe outro IPv4. O operador não precisa editar arquivos, procurar o IP manualmente nem gerar uma nova confiança no Quest a cada rede.

## Como iniciar

1. Conecte o PC e o Meta Quest à mesma rede local.
2. Na raiz do ARGOS, execute `INICIAR_OREN_QUEST.cmd`. Não é necessário abrir o Docker Desktop antes: o launcher o inicia minimizado e aguarda o Engine ficar pronto.
3. Autorize uma única vez a regra do Firewall do Windows, caso o UAC seja exibido. Ela permite somente TCP 8443 a partir da sub-rede local.
4. O script inicia o OREN padronizado em Docker, copia o link e abre no PC uma página com QR.
5. No Quest, leia o QR e escolha um exame recente na página curta `/quest/`.

O arquivo local gerado é `.local/quest_https/ABRIR_NO_META_QUEST.html`. Ele não contém token clínico; aponta apenas para a lista local de casos recentes.

## Certificado instalado uma única vez

Na primeira configuração de uma máquina, execute `SERVIR_CERTIFICADO_QUEST.cmd`, abra no Quest o endereço HTTP exibido e instale a CA pública. A chave privada nunca é servida e permanece em `.local/quest_https`, que está ignorada pelo Git.

A partir daí, a CA fica estável. Quando o IP muda, o OREN emite automaticamente um novo certificado de servidor assinado pela mesma CA. O Quest continua confiando nele sem repetir a instalação.

Instalações antigas são migradas: se o Quest já confiava no certificado anterior e a chave local ainda existe, esse certificado é preservado como a CA estável.

## Limitações da rede

- PC e Quest precisam alcançar um ao outro na LAN.
- Wi-Fi de convidados, hotéis e algumas redes corporativas podem usar isolamento entre clientes. Nessa situação, use um roteador/hotspot privado autorizado; trocar apenas o firewall do PC não remove o isolamento do ponto de acesso.
- O acesso é local e HTTPS. Nenhuma porta é publicada na internet pelo script.

## Componentes

- `tools/quest_network.ps1`: escolhe a interface física ativa com gateway padrão.
- `tools/create_quest_certificate.py`: mantém a CA e renova o certificado do IP.
- `tools/ensure_quest_firewall.ps1`: regra limitada a `LocalSubnet`.
- `tools/start_oren_quest_dynamic.ps1`: orquestra Docker, URL, clipboard e QR.
- `tools/ensure_docker_desktop.ps1`: inicia automaticamente o Docker Desktop e aguarda o Engine por até cinco minutos.
- `tools/create_quest_access_page.py`: cartão offline de acesso.

## Verificação

O comportamento é coberto por testes de troca simulada de IP, estabilidade da CA, migração do certificado legado, assinatura do certificado de servidor, ausência de chaves no servidor público, QR sem token, detecção de interface e restrição do firewall à sub-rede local.
