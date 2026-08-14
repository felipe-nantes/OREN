# Runbook — Rodar o projeto no MAC

Guia operacional para executar o Digital Twin Cirúrgico no MAC (única máquina de
execução: Ollama + MedGemma 27B + segmentação).
Caminho assumido: `/Users/sander_gurgel/Documents/projetos_sander/argos-main`.

> Existe também um modo Docker portátil ARM64, mantendo Ollama/MedGemma no host.
> Para transferência automatizada e uso em Docker, consulte
> `docs/232_DOCKER_PORTATIL_MAC_E_OUTROS.md`.

## Serviços e ordem de subida

| # | Serviço | Porta | Terminal |
|---|---|---|---|
| 1 | Ollama (daemon + modelo `medgemma:27b-it-bf16`) | 11434 | aba 1 |
| 2 | Gateway MedGemma | 8001 | aba 2 |
| 3 | Webapp (upload + relatório + 3D) | 8080 | aba 3 |

Ordem **obrigatória**: Ollama → Gateway → Webapp. Cada serviço roda em primeiro
plano — use uma aba de terminal para cada. Rode **sempre a partir da raiz do repo**.

## Modo rápido (um comando)

O script `run_mac.sh` sobe tudo na ordem certa, com verificações de saúde entre
cada etapa, e encerra o que ele iniciou no Ctrl+C:

```bash
cd /Users/sander_gurgel/Documents/projetos_sander/argos-main
./run_mac.sh                 # 27B e 4B; escolha do modelo na própria página
./run_mac.sh --model 27b     # só o 27B (mais leve para subir)
./run_mac.sh --model 4b      # só o 4B
./run_mac.sh --skip-verify   # pula a verificação de dispositivo
```

Abra `http://127.0.0.1:8080` quando ele indicar. Os passos manuais abaixo
continuam válidos para diagnóstico ou se preferir controlar cada serviço.

### Escolha do modelo MedGemma

Com `--model both` (padrão), sobem dois gateways — 27B em `:8001` e 4B em
`:8002` — e a página mostra um seletor. O seletor **só aparece quando os dois
respondem**: oferecer um modelo desligado produziria falha no meio da análise,
depois da segmentação já ter rodado.

**O que essa escolha afeta, e o que não afeta.** O exame trifásico roda o
classificador visual congelado (MedSigLIP) e **não passa pelo MedGemma** — a
escolha não muda o resultado dele. Ela vale para o **fallback monofásico** (o
caminho de quando o exame não traz as três fases dinâmicas) e para o
**benchmark**.

### Apple Silicon — leia antes de confiar nos números

O classificador visual é fixado em CUDA no config padrão e **falha num Mac**. O
`run_mac.sh` aponta para `configs/training/medsiglip_frozen_mps_v1.yaml`, que só
difere em `device` (mps) e `dtype` (float32) — a representação, o modelo e a
revisão são os mesmos.

Isso não é equivalência provada. O bundle de produção foi treinado sobre
embeddings de float16/CUDA, e um vetor levemente diferente pode atravessar o
limiar de decisão (0,4749). Na primeira execução o script roda automaticamente:

```bash
.venv/bin/python tools/verify_medsiglip_device_agreement.py
```

Ela reextrai painéis conhecidos no dispositivo atual, classifica com o **mesmo
bundle congelado** e compara decisão a decisão. O critério de aprovação é
concordância de decisão, não similaridade de vetor. Se reprovar, os números
medidos em CUDA **não valem** para este caminho sem remedição própria.

### Segmentação no Mac

O TotalSegmentator é chamado com `gpu` e cai para `cpu` quando não há CUDA — ou
seja, no Mac ele roda em CPU. Funciona, mas é sensivelmente mais lento que no
Windows com GPU. Isso afeta o tempo por exame, não o resultado.

---

## 0. Atualizar o código (aplicar o bundle vindo do PC Windows)

Só quando houver mudança nova vinda do Windows. Transfira o `argos-main.bundle`
para o MAC e:

```bash
cd /Users/sander_gurgel/Documents/projetos_sander/argos-main

BKP=~/argos_bkp_$(date +%Y%m%d_%H%M%S); mkdir -p "$BKP"
cp -R webapp viewer dtwin configs profiles tools tests docs contexto *.py *.md *.toml *.txt "$BKP" 2>/dev/null
echo "backup em: $BKP"

git init -b main 2>/dev/null || git init 2>/dev/null
git fetch ~/Downloads/argos-main.bundle main
git reset --hard FETCH_HEAD        # .venv/ e casos/ ficam intactos (gitignored)
git log --oneline -3
```

## 1. Verificar o ambiente

```bash
cd /Users/sander_gurgel/Documents/projetos_sander/argos-main
.venv/bin/python digital_twin.py doctor
```
Esperado: "Núcleo completo" e uma linha `torch device: ...`. Só reinstale se o
doctor acusar falta de dependência (o pacote não mudou nesta atualização):
```bash
.venv/bin/python -m pip install -e ".[webapp,medgemma,seg]"
```

## 2. Aba 1 — Ollama

```bash
ollama serve                      # se ainda não estiver rodando como serviço
```
Confirme o modelo (em outra aba):
```bash
ollama list | grep medgemma       # deve listar medgemma:27b-it-bf16
```

## 3. Aba 2 — Gateway MedGemma (:8001)

```bash
cd /Users/sander_gurgel/Documents/projetos_sander/argos-main
.venv/bin/python tools/medgemma_server.py --config configs/medgemma_ollama_27b.yaml --port 8001
```
Confirme:
```bash
curl -s http://127.0.0.1:8001/health
# esperado: "status":"ready" ... "model_id":"medgemma:27b-it-bf16"
```
`"status":"failed"` → leia o campo `load_error` (Ollama fora do ar ou modelo sem visão).

## 4. Aba 3 — Webapp (:8080)

```bash
cd /Users/sander_gurgel/Documents/projetos_sander/argos-main
WEBAPP_MEDGEMMA_CONFIG=configs/medgemma_ollama_27b.yaml \
  .venv/bin/python -m uvicorn webapp.server:app --port 8080
```
Confirme:
```bash
curl -s http://127.0.0.1:8080/api/health
# esperado: {"backend":"pronto"}
```
`"desligado"` → o gateway/Ollama não estão prontos; volte aos passos 2 e 3.

## 5. Usar o fluxo

1. Abra `http://127.0.0.1:8080` no navegador.
2. Arraste a **pasta DICOM da RM** (ou um DICOM multi-frame).
3. Aguarde: des-identificação → segmentação do fígado → painel 2D → MedGemma. A
   **primeira** análise demora mais (Ollama carrega o 27B na memória).
4. Sai o **relatório** (sempre `pending_review`). Se algo falhar, aparece um
   cartão honesto "análise não concluída" — nunca um achado fabricado.
5. Clique em **"Visualizar fígado em 3D e revisar"**.
6. No visualizador, inspecione o contorno e registre **Aprovar segmentação** ou
   **Solicitar revisão** → salvo em `casos/webapp/<id>/case/outputs/approval.json`.

## 6. Encerrar

`Ctrl+C` nas abas do webapp e do gateway. O Ollama pode continuar no ar.

## Solução de problemas

- **Webapp `backend: desligado`** → gateway (:8001) ou Ollama fora do ar (`curl .../8001/health`).
- **Gateway `status: failed`** → `load_error`: rode `ollama serve`; confira a tag com `ollama list`.
- **`ModuleNotFoundError: torch` no gateway** → `pip install -e ".[seg]"` (o /health usa torch).
- **Segmentação cai da GPU para CPU** → normal no MAC (sem CUDA); mais lento (timeout até ~40 min).
- **Rode sempre da raiz do repo** — o webapp grava em `casos/webapp/` relativo ao diretório atual.
- **Nunca commite `casos/`** — é dado de paciente e já está no `.gitignore`.
