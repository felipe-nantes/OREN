# ARGOS/OREN em Docker — arquitetura e validação ponta a ponta

## Decisão técnica

O ARGOS foi organizado em Docker Compose sem incorporar DICOMs, pesos ou
resultados às imagens. O modo padrão é híbrido:

```text
MedGemma 4B no host (GPU, porta 8001)
                 |
Nginx 8080/8443 -> ARGOS/OREN (GPU) -> Neo4j
                 |
        volumes externos de casos e pesos
```

Essa é a configuração recomendada para a RTX 4060 de 8 GB: MedGemma permanece
residente no host, enquanto a segmentação usa a GPU no contêiner quando
necessário. O Compose contém também o perfil opcional `medgemma-container`, mas
MedGemma e segmentação não devem executar inferências simultâneas nesse hardware.

## Serviços

| Serviço | Função | Exposição |
|---|---|---|
| `argos` | webapp, backend, segmentação e visualizador | somente rede interna |
| `proxy` | entrada desktop e Meta Quest | `127.0.0.1:8080`, LAN `:8443` |
| `neo4j` | GraphRAG clínico | somente loopback `7474/7687` |
| `medgemma` | 4B em contêiner, opcional | perfil `medgemma-container` |
| `graphify` | grafo arquitetural | perfil `tools`, rede desativada |

O proxy HTTP e HTTPS aponta para a mesma instância ARGOS. Portanto, jobs criados
no desktop continuam acessíveis pelo Quest e não existem dois estados em memória.

## Dados externos

O arquivo local `.env.docker`, não versionado, declara:

- `ARGOS_CASES_DIR`: jobs, relatórios e benchmarks;
- `ARGOS_DOCKER_STATE_DIR`: persistência Neo4j;
- `TOTALSEG_HOME_DIR`: pesos TotalSegmentator;
- `MRSEGMENTATOR_HOME_DIR`: pesos MRSegmentator;
- `HF_HUB_DIR`: cache local dos pesos MedGemma/MedSigLIP;
- `QUEST_CERT_DIR`: certificado e chave HTTPS do Quest.

Gere-o automaticamente:

```powershell
powershell -ExecutionPolicy Bypass -File tools\initialize_argos_docker.ps1
```

## Instalação Windows

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup_docker_windows.ps1
```

Esse passo habilita WSL2 e instala Docker Desktop. É necessária elevação uma
única vez. Se o Windows solicitar reinício, reinicie antes de continuar. Docker
Desktop deve usar o backend WSL2 para acesso à GPU NVIDIA.

## Inicialização recomendada

```powershell
powershell -ExecutionPolicy Bypass -File tools\start_argos_docker.ps1
```

O script:

1. confirma Docker Engine;
2. cria `.env.docker` se necessário;
3. inicia ou reutiliza o gateway MedGemma 4B no host;
4. valida o Compose;
5. constrói e inicia ARGOS, proxy e Neo4j;
6. espera o endpoint de saúde.

Endereços:

```text
Desktop: http://127.0.0.1:8080
Quest:   https://IP_DO_PC:8443
Neo4j:   http://127.0.0.1:7474
```

## MedGemma inteiramente no Docker

É suportado, mas secundário neste notebook:

```powershell
powershell -ExecutionPolicy Bypass -File tools\start_argos_docker.ps1 `
  -MedGemmaMode Container
```

Não processe segmentação enquanto o 4B estiver residente na mesma GPU de 8 GB.

## Graphify no Docker

```powershell
docker compose --env-file .env.docker --profile tools run --rm graphify --version
```

O serviço não possui rede e recebe apenas código/configuração e `graphify-out`.
Dados médicos não são montados nele.

## Verificação

Validação estática:

```powershell
.\.venv-win\Scripts\python.exe tools\verify_argos_docker_static.py
```

Validação dos serviços em execução:

```powershell
powershell -ExecutionPolicy Bypass -File tools\verify_argos_docker_runtime.ps1
```

O relatório fica em:

```text
artifacts/docker-validation/runtime-verification.json
```

O gate exige Compose válido, contêineres saudáveis, HTTP desktop, HTTPS Quest,
visualizador, MRSegmentator, Neo4j, CUDA, conectividade com MedGemma e Graphify.

Verificação independente de um job concluído:

```powershell
.\.venv-win\Scripts\python.exe tools\verify_argos_docker_job.py `
  --http-base http://127.0.0.1:8080 `
  --https-base https://IP_DO_PC:8443 `
  --job-id ID_DO_JOB
```

O verificador confere o estado final, manifesto do visualizador, hashes de todos
os artefatos autorizados, volumetria, painéis RGB, isolamento do ground truth,
autorizações WebXR e rejeição de path traversal.

Validação controlada do MedGemma no perfil opcional:

```powershell
powershell -ExecutionPolicy Bypass -File tools\verify_medgemma_container.ps1
```

O script restaura automaticamente o modo híbrido ao terminar.

Jobs concluídos são persistidos atomicamente e podem ser recuperados pelo
endpoint de status depois de reiniciar o contêiner ARGOS. A restauração falha de
forma segura se os hashes dos artefatos do visualizador não forem válidos.

O relatório completo da validação real está em
`docs/230_RELATORIO_VALIDACAO_DOCKER_PONTA_A_PONTA.md`.

## Desligamento

```powershell
powershell -ExecutionPolicy Bypass -File tools\stop_argos_docker.ps1
```

Para encerrar também o MedGemma iniciado pelo launcher:

```powershell
powershell -ExecutionPolicy Bypass -File tools\stop_argos_docker.ps1 -StopHostMedGemma
```

## Limites

- uso exclusivo em pesquisa com revisão humana;
- Docker não altera sensibilidade ou especificidade do classificador;
- nenhum dataset ou peso é empacotado na imagem;
- Graphify e GraphRAG clínico continuam separados;
- o smoke test real deve usar DICOM autorizado e preservar o relatório gerado.
