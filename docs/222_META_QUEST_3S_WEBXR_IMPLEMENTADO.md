# OREN no Meta Quest 3S — WebXR implementado

## Estado e contrato

O visualizador desktop continua sendo a base do OREN e agora possui uma extensão
progressiva WebXR. Em computador sem WebXR nada muda. No Meta Quest 3S, em HTTPS,
o botão imersivo é habilitado. Esta implementação é somente para pesquisa e
educação; não constitui dispositivo médico, diagnóstico ou validação clínica.

```text
DICOM bruto -> pipeline OREN existente -> máscara/volumetria autoritativa
-> STL desktop -> LOD WebXR com hash e gate -> link HTTPS temporário
-> Quest 3S -> interação -> revisão humana
```

## Funções no headset

- VR e mixed reality quando o navegador oferece `immersive-ar`.
- Segurar, mover e girar com grip do controle ou pinça da mão.
- Duas mãos/controles para escala e rotação combinadas.
- Raios, seleção de estruturas e feedback háptico.
- Composições Fígado, Anatomia, Triagem e Segmentos.
- Opacidade, plano de corte, medição em milímetros e volumetria.
- painel espacial, recentralização, saída e restauração da posição.
- perfil Paciente, sem aprovação e sem ferramentas técnicas sensíveis.
- perfil Médico/pesquisador, com ferramentas exploratórias completas.

## LOD, fidelidade e desempenho

`dtwin/viewer_xr.py` cria um STL LOD opcional por estrutura. O STL original nunca
é substituído. Cada LOD registra hash fonte/derivado, triângulos, nível, gate de
fidelidade e autoridade de medição. Se o gate falhar, volta ao original e remove
o parcial. A autoridade continua sendo a máscara binária no espaço físico, nunca
a malha simplificada.

Orçamentos: fígado 60 mil triângulos; candidatos, lesões e vasos 25 mil; região
classificada 30 mil; Couinaud 18 mil; vesícula 15 mil. O cliente monitora p95 do
frame time em relação ao orçamento de 72 Hz.

## Sessões seguras

`POST /api/jobs/{job_id}/xr-session` cria link com papel `patient` ou `clinician`
e TTL de 5–120 minutos (30 padrão). Somente SHA-256 do segredo fica persistido.
O segredo fica no fragmento da URL, é validado após carregar o viewer e o perfil
fica bloqueado. Paciente recebe HTTP 403 ao tentar aprovação. A sessão e revisão
continuam válidas após reinício do servidor HTTPS.

## HTTPS no Windows

Instalação única:

```powershell
.\.venv-win\Scripts\python.exe -m pip install -e ".[webapp,quest]"
.\setup_quest_https.ps1
```

Instale `.local/quest_https/oren-quest-cert.pem` como certificado confiável no
Quest/rede de pesquisa. A chave privada nunca deve sair do PC. Inicie por
`INICIAR_OREN_QUEST.cmd` ou:

```powershell
.\run_quest_win.ps1
```

Abra no Quest a `viewer_url` retornada pela criação da sessão. Ambos devem estar
na mesma LAN.

### Alternativa sem instalar certificado no Horizon OS

Em Quest Browser/Horizon OS 79 ou superior, execute
`INICIAR_OREN_QUEST_SEM_CERTIFICADO.cmd`, adicione a origem exibida ao flag
`chrome://flags/#unsafely-treat-insecure-origin-as-secure` e reinicie o navegador
por `Relaunch`. Essa opção é exclusivamente para desenvolvimento na LAN privada.

## Controles

- gatilho/pinça: botão, seleção e ponto de medição;
- grip: segurar e mover;
- duas mãos/grips: escala e rotação;
- Recentrar: posição confortável em escala anatômica;
- Sair do XR: encerra imersão e restaura desktop.

## Gates automatizados

- inicialização XR opcional e desktop preservado;
- controllers, hand-tracking, grip e painel espacial presentes;
- LOD somente após gate e com fallback limpo;
- allow-list fechada e SHA-256 dos assets;
- TTL e papel fixo; paciente não aprova;
- certificado/chave sob `.local/`, fora do Git.

## Gate físico pendente

Antes do aceite no dispositivo: abrir VR e mixed reality; testar dois controles e
duas mãos; avaliar conforto/legibilidade por 10 minutos; confirmar escala, oclusão,
cortes e medidas; verificar p95; confirmar restrições do paciente; encerrar XR e
confirmar restauração do desktop. Isso valida interação/renderização, não acurácia
clínica.
