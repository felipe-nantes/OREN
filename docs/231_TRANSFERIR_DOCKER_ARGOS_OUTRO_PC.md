# Como transferir e executar o ARGOS/OREN Docker em outro PC

Este guia descreve a transferência do ambiente Docker NVIDIA validado em 13 de
agosto de 2026 para outro **PC Windows 10/11 x64 com GPU NVIDIA e WSL2**.

> Para Mac Apple Silicon/M5 e computadores sem NVIDIA, use a imagem ARM64/CPU e
> os automatizadores descritos em `docs/232_DOCKER_PORTATIL_MAC_E_OUTROS.md`.
> O Docker no Mac não recebe MPS/Metal; MedGemma 27B permanece nativo no host.

## 1. O que realmente precisa ser transferido

O ambiente possui quatro partes independentes:

1. **Código e configuração** do repositório ARGOS;
2. **imagens Docker** ou acesso à internet para reconstruí-las;
3. **pesos externos dos modelos**, que não fazem parte das imagens;
4. **dados médicos**, que não devem ser enviados junto com o software.

Não copie o arquivo `.env.docker` do PC atual. Ele contém caminhos absolutos,
uma senha do Neo4j e configurações específicas da máquina. Também não copie a
chave privada HTTPS nem reutilize o certificado antigo do Quest: eles estão
associados ao PC e ao endereço IP atuais.

## 2. Estado atual antes da transferência

No momento em que este documento foi criado, os arquivos Docker ainda estavam
no working tree local e não no commit `main` do GitHub. Portanto, executar apenas:

```powershell
git clone https://github.com/felipe-nantes/argos.git
```

**ainda não reproduz a implementação Docker validada**. Antes de usar o método
Git, as alterações funcionais precisam ser revisadas, commitadas e enviadas ao
repositório. Até isso acontecer, use o método offline descrito na seção 5.

## 3. Requisitos do novo PC

Recomendado:

- Windows 11 x64 atualizado;
- GPU NVIDIA com pelo menos 8 GB de VRAM;
- driver NVIDIA recente com suporte a WSL2;
- 32 GB de RAM ou mais;
- pelo menos 100 GB livres para imagens, caches e casos futuros;
- virtualização habilitada no BIOS/UEFI;
- mesma rede privada do Meta Quest, se o WebXR for utilizado;
- Python entre 3.10 e 3.13 somente para gerar o certificado local e, no modo
  híbrido, hospedar o MedGemma no Windows.

O suporte de GPU do Docker Desktop no Windows exige o backend WSL2 e GPU NVIDIA.
Referências oficiais:

- <https://docs.docker.com/desktop/setup/install/windows-install/>
- <https://docs.docker.com/desktop/features/wsl/>
- <https://docs.docker.com/desktop/features/gpu/>

## 4. Método recomendado — Git + reconstrução no novo PC

Use este método depois que a implementação Docker estiver commitada e enviada ao
GitHub.

### 4.1 No PC atual

Confirme que o commit contém pelo menos:

```text
compose.yaml
docker/
tools/initialize_argos_docker.ps1
tools/setup_docker_windows.ps1
tools/start_argos_docker.ps1
tools/stop_argos_docker.ps1
tools/verify_argos_docker_runtime.ps1
tools/verify_argos_docker_static.py
tools/verify_argos_docker_job.py
tools/verify_medgemma_container.ps1
docs/229_DOCKER_ARGOS_END_TO_END.md
docs/230_RELATORIO_VALIDACAO_DOCKER_PONTA_A_PONTA.md
```

Registre o commit que será instalado:

```powershell
git rev-parse HEAD
```

Guarde esse hash no relatório da nova máquina.

### 4.2 No novo PC

Clone e entre no repositório:

```powershell
git clone https://github.com/felipe-nantes/argos.git C:\ARGOS\argos-main
Set-Location C:\ARGOS\argos-main
git checkout HASH_VALIDADO
```

Substitua `HASH_VALIDADO` pelo commit aprovado no PC de origem.

## 5. Método offline — HD externo, sem depender do GitHub

Este é o método seguro enquanto as alterações Docker ainda não estiverem
versionadas.

### 5.1 Preparar a pasta no PC atual

Conecte um HD externo, por exemplo `E:`, e crie:

```powershell
New-Item -ItemType Directory -Force E:\ARGOS_TRANSFER\source
New-Item -ItemType Directory -Force E:\ARGOS_TRANSFER\images
New-Item -ItemType Directory -Force E:\ARGOS_TRANSFER\weights\huggingface
New-Item -ItemType Directory -Force E:\ARGOS_TRANSFER\weights\totalsegmentator
New-Item -ItemType Directory -Force E:\ARGOS_TRANSFER\weights\mrsegmentator
```

Copie o código sem ambientes virtuais, casos, resultados e dados médicos:

```powershell
Set-Location C:\Users\profurg\Desktop\sander\argos-main

robocopy . E:\ARGOS_TRANSFER\source /E /R:2 /W:2 `
  /XD .git .venv .venv-win .venv-mrseg .local .medgemma `
      .codex .claude .agents .tmp .codex-tmp .pytest_cache `
      casos data artifacts experiments benchmarks flywheel `
  /XF .env.docker *.dcm *.dicom *.nii *.nii.gz *.nrrd *.mha *.mhd `
      *.stl *.vtk *.vtp *.glb *.gltf *.png *.jpg *.jpeg *.webp `
      *.pt *.pth *.safetensors
```

O `robocopy` pode retornar códigos de 1 a 7 mesmo quando a cópia foi concluída;
códigos iguais ou maiores que 8 indicam falha.

### 5.2 Exportar as imagens Docker já construídas

Confirme os nomes:

```powershell
docker image inspect argos-runtime:local
docker image inspect argos-graphify:local
docker image inspect nginx:1.27-alpine
docker image inspect neo4j:5.26-community
```

Exporte tudo em um arquivo:

```powershell
docker image save -o E:\ARGOS_TRANSFER\images\argos-docker-amd64.tar `
  argos-runtime:local `
  argos-graphify:local `
  nginx:1.27-alpine `
  neo4j:5.26-community

Get-FileHash E:\ARGOS_TRANSFER\images\argos-docker-amd64.tar -Algorithm SHA256 |
  Format-List |
  Out-File E:\ARGOS_TRANSFER\images\argos-docker-amd64.sha256.txt
```

O comando `docker image save` é o mecanismo oficial para exportar imagens que
serão restauradas com `docker image load`:
<https://docs.docker.com/reference/cli/docker/image/save/>.

### 5.3 Copiar somente os pesos necessários

Copie os pesos TotalSegmentator e MRSegmentator:

```powershell
robocopy "$env:USERPROFILE\.totalsegmentator" `
  E:\ARGOS_TRANSFER\weights\totalsegmentator /E /R:2 /W:2

robocopy "$env:USERPROFILE\.mrsegmentator" `
  E:\ARGOS_TRANSFER\weights\mrsegmentator /E /R:2 /W:2
```

Copie somente os modelos Hugging Face usados pelo fluxo atual:

```powershell
robocopy "$env:USERPROFILE\.cache\huggingface\hub\models--google--medgemma-1.5-4b-it" `
  E:\ARGOS_TRANSFER\weights\huggingface\models--google--medgemma-1.5-4b-it /E /R:2 /W:2

robocopy "$env:USERPROFILE\.cache\huggingface\hub\models--google--medsiglip-448" `
  E:\ARGOS_TRANSFER\weights\huggingface\models--google--medsiglip-448 /E /R:2 /W:2
```

Não copie `datasets--wanglab--LLD-MMRI-MedSAM2` ou qualquer outro dataset que
esteja no cache Hugging Face. O pacote de transferência deve conter modelos, não
datasets.

### 5.4 Gerar inventário e hashes

```powershell
Get-ChildItem E:\ARGOS_TRANSFER -Recurse -File |
  ForEach-Object {
    $hash = Get-FileHash $_.FullName -Algorithm SHA256
    [PSCustomObject]@{
      path = $_.FullName.Substring('E:\ARGOS_TRANSFER\'.Length)
      bytes = $_.Length
      sha256 = $hash.Hash.ToLowerInvariant()
    }
  } |
  ConvertTo-Json -Depth 3 |
  Set-Content E:\ARGOS_TRANSFER\transfer_manifest.json -Encoding utf8
```

Proteja o HD fisicamente ou use criptografia. Pesos licenciados não devem ser
publicados em GitHub, nuvem pública ou link aberto.

## 6. Instalar o novo PC

### 6.1 Atualizar Windows, WSL2 e o driver NVIDIA

Abra PowerShell como administrador no diretório do ARGOS e execute:

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup_docker_windows.ps1
```

Reinicie o Windows se solicitado. Abra o Docker Desktop e confirme que ele está
usando contêineres Linux com o backend WSL2.

Verifique:

```powershell
wsl --version
wsl --update
docker version
docker info
nvidia-smi
```

Teste a GPU dentro do Docker:

```powershell
docker run --rm --gpus all `
  nvcr.io/nvidia/k8s/cuda-sample:nbody nbody -gpu -benchmark
```

### 6.2 Restaurar as imagens no modo offline

Se você transportou o TAR:

```powershell
Get-FileHash E:\ARGOS_TRANSFER\images\argos-docker-amd64.tar -Algorithm SHA256
Get-Content E:\ARGOS_TRANSFER\images\argos-docker-amd64.sha256.txt

docker image load -i E:\ARGOS_TRANSFER\images\argos-docker-amd64.tar
docker image inspect argos-runtime:local
docker image inspect argos-graphify:local
```

Os hashes devem coincidir antes do `docker image load`.

### 6.3 Copiar o código offline

```powershell
New-Item -ItemType Directory -Force C:\ARGOS\argos-main
robocopy E:\ARGOS_TRANSFER\source C:\ARGOS\argos-main /E /R:2 /W:2
Set-Location C:\ARGOS\argos-main
```

### 6.4 Restaurar os pesos externos

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.totalsegmentator"
New-Item -ItemType Directory -Force "$env:USERPROFILE\.mrsegmentator"
New-Item -ItemType Directory -Force "$env:USERPROFILE\.cache\huggingface\hub"

robocopy E:\ARGOS_TRANSFER\weights\totalsegmentator `
  "$env:USERPROFILE\.totalsegmentator" /E /R:2 /W:2

robocopy E:\ARGOS_TRANSFER\weights\mrsegmentator `
  "$env:USERPROFILE\.mrsegmentator" /E /R:2 /W:2

robocopy E:\ARGOS_TRANSFER\weights\huggingface `
  "$env:USERPROFILE\.cache\huggingface\hub" /E /R:2 /W:2
```

### 6.5 Criar o ambiente Python do host

Para reproduzir exatamente o modo híbrido validado, crie o ambiente do host com
PyTorch CUDA 12.4 e as dependências do MedGemma:

```powershell
Set-Location C:\ARGOS\argos-main
py -3.13 -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install --upgrade pip
.\.venv-win\Scripts\python.exe -m pip install torch==2.6.0 `
  --index-url https://download.pytorch.org/whl/cu124
.\.venv-win\Scripts\python.exe -m pip install -e ".[webapp,quest,medgemma]"
```

Python 3.10, 3.11 ou 3.12 também pode ser usado; ajuste `py -3.13` conforme a
versão instalada.

## 7. Criar a configuração exclusiva do novo PC

### 7.1 Gerar novo certificado do Quest

```powershell
Set-Location C:\ARGOS\argos-main
powershell -ExecutionPolicy Bypass -File setup_quest_https.ps1
```

Isso cria uma chave e um certificado novos em `.local\quest_https`, usando o IP
atual do novo PC.

### 7.2 Criar `.env.docker` novo

```powershell
powershell -ExecutionPolicy Bypass -File tools\initialize_argos_docker.ps1 -Force
```

O script cria:

- caminhos do novo usuário;
- diretórios persistentes do Neo4j;
- senha nova e aleatória do Neo4j;
- mounts para pesos e casos;
- URL interna do MedGemma.

Não envie nem versione o `.env.docker` resultante.

### 7.3 Liberar somente a porta do Quest

Abra PowerShell como administrador:

```powershell
New-NetFirewallRule `
  -DisplayName "OREN Meta Quest HTTPS 8443" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 8443 `
  -Action Allow `
  -Profile Private
```

A porta desktop `8080` permanece restrita a `127.0.0.1`; não a exponha na LAN.

## 8. Primeira inicialização

### Opção A — imagens importadas, modo híbrido validado

Esta opção reproduz a arquitetura que aprovou os 16 gates operacionais: ARGOS,
proxy e Neo4j no Docker; MedGemma na GPU do Windows.

```powershell
Set-Location C:\ARGOS\argos-main
powershell -ExecutionPolicy Bypass -File tools\start_argos_docker.ps1 `
  -MedGemmaMode Host `
  -NoBuild
```

### Opção B — reconstruir as imagens no novo PC

Requer internet:

```powershell
Set-Location C:\ARGOS\argos-main
powershell -ExecutionPolicy Bypass -File tools\start_argos_docker.ps1 `
  -MedGemmaMode Host

docker compose --env-file .env.docker --profile tools build graphify
```

O primeiro build pode demorar bastante. Não interrompa enquanto as dependências
estiverem sendo instaladas.

### Opção C — tudo no Docker, incluindo MedGemma

Esse modo também foi validado, mas é secundário neste notebook. Não deixe duas
instâncias do MedGemma ativas ao mesmo tempo:

```powershell
powershell -ExecutionPolicy Bypass -File tools\start_argos_docker.ps1 `
  -MedGemmaMode Container `
  -NoBuild
```

Como o verificador geral possui dois gates específicos para o gateway do host,
execute-o com `-SkipMedGemma` nesse modo e valide o contêiner separadamente:

```powershell
powershell -ExecutionPolicy Bypass -File tools\verify_argos_docker_runtime.ps1 `
  -SkipMedGemma

docker compose --env-file .env.docker --profile medgemma-container exec -T `
  medgemma python -c `
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8001/health').read().decode())"
```

O health do MedGemma precisa informar `model_loaded=true`, `device=cuda` e
`status=ready`.

## 9. Validar antes de usar qualquer exame

Execute primeiro a validação estática:

```powershell
.\.venv-win\Scripts\python.exe tools\verify_argos_docker_static.py
```

Depois execute os gates operacionais:

```powershell
powershell -ExecutionPolicy Bypass -File tools\verify_argos_docker_runtime.ps1
```

No modo híbrido, o resultado esperado é:

```text
16 gates aprovados
failed_count = 0
```

No modo inteiramente conteinerizado, os dois gates exclusivos do gateway host
são omitidos com `-SkipMedGemma`; use também a validação direta indicada na
seção 8.

Relatório:

```text
artifacts\docker-validation\runtime-verification.json
```

Verifique também:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/health
docker compose --env-file .env.docker ps
```

Todos os serviços obrigatórios devem estar `running` e `healthy`:

```text
argos
proxy
neo4j
```

## 10. Acessar o OREN

No próprio PC:

```text
http://127.0.0.1:8080
```

Descubra o IPv4 da rede privada:

```powershell
Get-NetIPConfiguration |
  Where-Object { $_.NetAdapter.Status -eq 'Up' -and $_.IPv4DefaultGateway } |
  Select-Object -ExpandProperty IPv4Address
```

No Meta Quest:

```text
https://IP_DO_NOVO_PC:8443
```

Instale no Quest o **certificado público** recém-gerado para o novo PC. Nunca
transfira a chave privada `oren-quest-key.pem` para o headset.

## 11. Smoke test real no novo PC

Somente depois dos 16 gates:

1. use um exame DICOM autorizado e desidentificado;
2. execute um exame individual pelo webapp;
3. aguarde `concluido`;
4. anote o ID do job;
5. execute:

```powershell
.\.venv-win\Scripts\python.exe tools\verify_argos_docker_job.py `
  --job-id ID_DO_JOB `
  --http-base http://127.0.0.1:8080 `
  --https-base https://IP_DO_NOVO_PC:8443 `
  --output artifacts\docker-validation\new-pc-job-verification.json
```

O JSON precisa apresentar `passed=true`. Confirme manualmente:

- painel RGB;
- relatório MedGemma;
- volumetria;
- fígado e estruturas no visualizador 3D;
- referência 2D;
- medição tridimensional;
- entrada WebXR no Quest;
- revisão humana obrigatória.

## 12. O que não transferir junto

Não inclua no pacote de software:

```text
casos/
data/
artifacts/
experiments/
benchmarks/
.env.docker
.local/quest_https/oren-quest-key.pem
%LOCALAPPDATA%\ARGOS\docker-state\neo4j
datasets--wanglab--LLD-MMRI-MedSAM2
qualquer DICOM, NIfTI, máscara de lesão ou label protegido
```

Se resultados históricos precisarem ser preservados, transporte-os em pacote
separado, criptografado, com autorização e inventário explícitos. Não os misture
com a distribuição do software.

## 13. Parar e reiniciar

Parar tudo:

```powershell
powershell -ExecutionPolicy Bypass -File tools\stop_argos_docker.ps1 `
  -StopHostMedGemma
```

Reiniciar no modo contêiner:

```powershell
powershell -ExecutionPolicy Bypass -File tools\start_argos_docker.ps1 `
  -MedGemmaMode Container `
  -NoBuild
```

Reiniciar no modo híbrido:

```powershell
powershell -ExecutionPolicy Bypass -File tools\start_argos_docker.ps1 `
  -MedGemmaMode Host `
  -NoBuild
```

## 14. Checklist final de aceite

- [ ] código corresponde ao commit ou pacote aprovado;
- [ ] `.env.docker` foi recriado no novo PC;
- [ ] certificado HTTPS foi recriado para o novo IP;
- [ ] senha e chave privada não foram copiadas do PC antigo;
- [ ] pesos externos estão presentes;
- [ ] nenhum dataset ou dado clínico foi misturado ao pacote;
- [ ] Docker Desktop está em WSL2;
- [ ] GPU NVIDIA aparece dentro do contêiner;
- [ ] ARGOS, proxy e Neo4j estão saudáveis;
- [ ] MedGemma está `ready`, carregado e em CUDA;
- [ ] 16/16 gates do runtime foram aprovados;
- [ ] smoke test DICOM concluiu com `passed=true`;
- [ ] webapp, benchmark, 3D e Quest foram revisados manualmente;
- [ ] o ambiente permanece identificado como pesquisa com revisão humana.
