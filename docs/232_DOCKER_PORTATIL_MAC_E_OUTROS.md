# ARGOS/OREN Docker portátil — Mac Apple Silicon e outros computadores

## Resultado da auditoria

O contêiner NVIDIA original não é multi-arquitetura. Sua imagem base
`pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime` publica somente
`linux/amd64`; por isso ela não é uma imagem nativa para Mac M1–M5.

O projeto agora possui dois runtimes independentes:

| Runtime | Arquitetura | Computação | Uso recomendado |
|---|---|---|---|
| `docker/Dockerfile.argos` | AMD64 | CUDA/NVIDIA | Windows ou Linux com GPU NVIDIA |
| `docker/Dockerfile.argos-portable` | AMD64 e ARM64 | CPU no contêiner | Mac Apple Silicon e hosts sem NVIDIA |

No Mac, Docker Desktop não disponibiliza Metal/MPS para contêineres Linux. O
arranjo suportado é, portanto:

```text
Ollama + MedGemma 27B no macOS nativo (Apple Silicon)
                         |
                         | host.docker.internal:8001
                         v
ARGOS portátil ARM64/CPU + Nginx HTTPS + Neo4j no Docker
```

Segmentação e MedSigLIP funcionam no contêiner portátil em CPU, mas são mais
lentos que CUDA/MPS. Isso é uma diferença operacional, não uma equivalência
metodológica automaticamente comprovada. Antes de reutilizar métricas CUDA,
rode a verificação de concordância com o config
`configs/training/medsiglip_frozen_cpu_v1.yaml`.

## Arquivos implementados

- `docker/Dockerfile.argos-portable`: imagem Linux ARM64/AMD64 sem CUDA;
- `compose.portable.yaml`: remove solicitação de GPU e seleciona CPU;
- `tools/initialize_argos_docker.sh`: cria diretórios, senha, certificado e `.env.docker`;
- `tools/bootstrap_argos_mac.sh`: prepara o Python do gateway e verifica o Ollama/27B;
- `tools/start_argos_docker_mac.sh`: inicia Ollama/gateway 27B quando necessário e sobe o Compose;
- `tools/verify_argos_docker_portable.sh`: valida serviços, arquitetura, HTTPS e gateway;
- `tools/export_argos_portable.ps1`: cria pacote sem dados, pesos, segredos ou chave privada;
- `tools/import_argos_portable.sh`: verifica hashes, instala e inicia no destino.

## Transferência recomendada

### 1. No Windows de origem

Pacote de fonte, pequeno e sem dados médicos:

```powershell
powershell -ExecutionPolicy Bypass -File tools\export_argos_portable.ps1 `
  -Output E:\ARGOS_PORTABLE
```

Para incluir também a imagem ARM64 já construída para o Mac:

```powershell
powershell -ExecutionPolicy Bypass -File tools\export_argos_portable.ps1 `
  -Output E:\ARGOS_PORTABLE `
  -IncludeMacArm64Image
```

Para um segundo PC AMD64 sem internet, use adicionalmente:

```powershell
-IncludeAmd64Images
```

O diretório resultante contém:

```text
ARGOS_PORTABLE/
  bundle.json
  checksums.sha256
  argos-source.zip
  source/
  images/                         # somente quando solicitado
```

O pacote não contém DICOM, NIfTI, casos, resultados, pesos Hugging Face,
`.env.docker`, senha Neo4j, certificado antigo ou chave HTTPS privada.

### 2. Pesos no Mac

Os pesos devem permanecer separados do software e ser obtidos/restaurados em:

```text
~/.totalsegmentator
~/.mrsegmentator
~/.cache/huggingface/hub
```

O modelo `medgemma:27b-it-bf16` permanece no armazenamento gerenciado pelo
Ollama. Não publique pesos gated em GitHub, imagem pública ou link aberto.

### 3. No Mac de destino

Instale e abra Docker Desktop. Para desempenho nativo, use a imagem ARM64; não
force `linux/amd64`/Rosetta para o runtime ARGOS.

Instale previamente Python e Ollama. O importador cria a `.venv` e instala o
gateway automaticamente; o modelo gated somente é usado depois que seus termos
forem aceitos e ele estiver presente:

```bash
brew install python@3.11 ollama
ollama pull medgemma:27b-it-bf16
```

Copie `ARGOS_PORTABLE` para o Mac e execute:

```bash
bash ARGOS_PORTABLE/source/tools/import_argos_portable.sh \
  ARGOS_PORTABLE \
  "$HOME/ARGOS/argos-main"
```

O importador:

1. valida todos os SHA-256;
2. copia somente o software;
3. cria dados e estado fora do repositório;
4. gera senha Neo4j exclusiva;
5. gera certificado HTTPS exclusivo para o IP atual;
6. importa a imagem ARM64, se presente, ou a constrói localmente;
7. inicia ARGOS, proxy e Neo4j;
8. conecta o contêiner ao gateway MedGemma 27B do host.

Valide:

```bash
cd "$HOME/ARGOS/argos-main"
bash tools/verify_argos_docker_portable.sh
```

Endereços:

```text
Desktop: http://127.0.0.1:8080
Quest:   https://IP_DO_MAC:8443/quest/
```

## Outro computador

- Windows/Linux NVIDIA: continue usando `tools/start_argos_docker.ps1` e a
  imagem CUDA original.
- Linux/Windows sem NVIDIA: use `compose.yaml + compose.portable.yaml`, sabendo
  que a execução será em CPU.
- Mac Intel: o inicializador seleciona `linux/amd64`, mas ainda sem aceleração
  GPU dentro do Docker.
- Mac Apple Silicon: o inicializador seleciona `linux/arm64` nativo.

## Gates antes de usar exames

- `docker compose ... config` válido;
- `argos`, `proxy` e `neo4j` em execução;
- runtime não root (`uid 10001`, usuário `argos`);
- arquitetura do contêiner igual à declarada no pacote;
- HTTP desktop e HTTPS Quest respondendo;
- dependências CPU importáveis e CUDA ausente no runtime portátil;
- gateway MedGemma do host respondendo como `ready`;
- pesos externos montados como somente leitura;
- smoke test DICOM autorizado concluído;
- comparação de decisões MedSigLIP CPU versus referência congelada executada.

Sem o último gate, o software pode ser usado para desenvolvimento e revisão,
mas métricas obtidas em CUDA não devem ser atribuídas automaticamente ao Mac.
