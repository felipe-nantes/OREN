# Galeria de revisão e preflight do MedGemma 4B

Data do registro: 2026-07-14.

## Galeria local

Foi criada uma galeria para reduzir erros na revisão manual dos 88 painéis:

- `dtwin/benchmark/openswisshcc_gallery.py`;
- `tools/build_openswisshcc_review_gallery.py`;
- `tests/test_openswisshcc_gallery.py`.

Artefato real:

```text
casos/qualification/openswisshcc_v1/prepared/
  development_review_gallery_v1/index.html
```

A galeria:

- revalida o congelamento experimental antes de ser criada;
- mostra os 88 painéis em resolução original;
- identifica 85 multifásicos e 3 fallbacks venosos;
- exige checklist individual de PHI, qualidade/alinhamento e enquadramento;
- salva o progresso somente no armazenamento local do navegador;
- permite copiar um atestado auxiliar depois dos 88 checklists;
- declara `authoritative_approval=false`;
- não abre nem contém ground truth;
- não chama o MedGemma.

O checklist não libera inferência. A aprovação autoritativa continua sendo o
manifesto criado por `tools.review_openswisshcc_panels` depois da declaração
humana real.

## Preflight do backend

O preflight local foi executado sem enviar imagem:

```text
GPU: NVIDIA GeForce RTX 4060 Laptop GPU
VRAM: 8,0 GiB
CUDA: disponível
BF16: disponível
snapshot MedGemma: completo no cache local
```

O gateway foi iniciado em `127.0.0.1:8001`. O health check confirmou:

```text
status: ready
contract: dtwin-medgemma-v1
model_id: google/medgemma-1.5-4b-it
model_version: MedGemma 1.5 4B Instruction-Tuned
quantization: bitsandbytes-nf4
device: cuda
research_only: true
```

As duas configurações congeladas — multifásica e fallback venoso — passaram no
preflight de identidade e conectividade. Nenhum POST `/generate` foi realizado
nesta etapa.

## Correção operacional

`tools/start_medgemma.ps1` ainda apontava para `.venv`, inexistente neste
workspace, enquanto `run_win.ps1` usa `.venv-win`. O inicializador auxiliar
agora possui:

```powershell
[string]$Venv = ".venv-win"
```

O caminho do Python é derivado desse parâmetro. Foram adicionados testes para:

- ambiente Windows configurável;
- preflight `--local-only`;
- processo iniciado com `-WindowStyle Hidden`;
- espera por `model_loaded=true`.

O PID oficial foi atualizado somente após verificar que a linha de comando do
processo corresponde exatamente a `tools/medgemma_server.py --port 8001`.

## Estado metodológico

```text
painéis congelados: 88
painéis aprovados por humano: 0
inferências do benchmark: 0
ground truth aberto pelo executor: não
backend 4B: pronto, aguardando revisão humana
```
