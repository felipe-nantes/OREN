# CHAOS v1.03 — gate de aquisição do braço negativo

O CHAOS será usado somente como braço secundário de estresse de especificidade
sob mudança de domínio. Ele não será combinado com LiverHccSeg como matriz de
confusão primária.

## Fonte congelada

```text
dataset: CHAOS v1.03
registro Zenodo: 3431873
arquivo permitido: CHAOS_Train_Sets.zip
bytes: 890771694
MD5 oficial: df21053002a1cc86df918a87da3b2c19
licença: CC BY-NC-SA 4.0
```

O conjunto de teste não será baixado e seu ground truth não será solicitado.
A aquisição usa apenas o treino público, que contém T1-DUAL, T2-SPIR e máscaras
dos órgãos.

## Segurança implementada

O comando abaixo permanece bloqueado sem `--accept-license`:

```powershell
.\.venv-win\Scripts\python.exe tools\download_chaos_v103.py `
  --out data\downloads\CHAOS_v1.03 `
  --accepted-by jm `
  --accept-license
```

O downloader:

1. exige aceite explícito e identificador do responsável;
2. baixa somente a URL oficial do ZIP de treino;
3. escreve em staging sem publicar conteúdo parcial;
4. valida nome, bytes, MD5 e SHA-256;
5. rejeita path traversal no ZIP;
6. confirma a presença de MRI, T1DUAL e T2SPIR;
7. publica o arquivo e o manifesto atomicamente;
8. registra que o conjunto de teste e seu ground truth não foram solicitados.

Nenhum download real foi executado durante a implementação deste gate.

## Aquisição autorizada e concluída

O aceite foi registrado pelo responsável `jm` e o arquivo oficial foi baixado
em 2026-07-18:

```text
bytes: 890771694
MD5: df21053002a1cc86df918a87da3b2c19
SHA-256: 535f7d3417a0e0f0d9133fb3d962423d2a9cf3f103e4f09a3d8a1daf87d5d2fc
arquivos no ZIP: 8937
conjunto de teste baixado: não
extraído: não
```

O próximo comando extrai somente `Train_Sets/MR/`, sem CT e sem conjunto de
teste, depois de revalidar o ZIP e o manifesto de licença:

```powershell
.\.venv-win\Scripts\python.exe tools\extract_chaos_mri_v103.py `
  --download-root data\downloads\CHAOS_v1.03 `
  --out data\raw\CHAOS_MRI_v1.03
```
