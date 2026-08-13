# Graphify no ARGOS — grafo arquitetural do código

## Finalidade

O Graphify foi incorporado como ferramenta de engenharia para mapear arquivos,
símbolos, chamadas e dependências do código do ARGOS. Ele auxilia manutenção,
análise de impacto e navegação da arquitetura.

Ele **não** participa da inferência médica, não altera painéis, prompts,
segmentação, relatórios ou métricas e não substitui o GraphRAG clínico existente
em `dtwin/graphrag`. Os dois grafos permanecem fisicamente e semanticamente
separados.

## Versão instalada

- repositório: `Graphify-Labs/graphify`;
- pacote: `graphifyy` com suporte opcional a Neo4j;
- versão: `0.9.42`;
- commit fixado: `7fe58b0b0f3873be9a21c30106b8b8527c353aa6`;
- ambiente isolado local: `.local/graphify-venv`;
- clone de instalação: `.codex-tmp/graphify-source`.

O ambiente e o clone são locais e ignorados pelo Git. O script de instalação
permite reconstruí-los com a mesma revisão.

## Instalação reproduzível

No PowerShell, a partir da raiz do ARGOS:

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup_graphify_argos.ps1
```

Esse comando baixa o commit fixado, cria um ambiente Python isolado, instala o
extra Neo4j e registra a integração de projeto do Codex.

## Construção segura do grafo

```powershell
powershell -ExecutionPolicy Bypass -File tools\graphify_argos.ps1 -Action Build
```

A construção usa obrigatoriamente `--code-only`. Portanto:

- a extração estrutural é local e determinística;
- nenhuma chave de API ou LLM externo é utilizada;
- DICOMs, NIfTIs, máscaras, casos, datasets e resultados experimentais são
  bloqueados também por `.graphifyignore`;
- nenhuma informação clínica é enviada ao Neo4j automaticamente.

Saídas autoritativas:

```text
graphify-out/graph.json
graphify-out/graph.html
graphify-out/GRAPH_REPORT.md
graphify-out/GRAPH_TREE.html
```

`graph.html` é a exploração completa por relações; `GRAPH_TREE.html` é uma
alternativa mais leve, organizada pela hierarquia de arquivos do projeto.

## Operação

Atualizar após mudanças de código:

```powershell
powershell -ExecutionPolicy Bypass -File tools\graphify_argos.ps1 -Action Update
```

Consultar a arquitetura:

```powershell
powershell -ExecutionPolicy Bypass -File tools\graphify_argos.ps1 `
  -Action Query `
  -Question "Como o webapp aciona a segmentacao hepatica?"
```

Explicar um símbolo:

```powershell
powershell -ExecutionPolicy Bypass -File tools\graphify_argos.ps1 `
  -Action Explain `
  -Question "SegmentationWorker"
```

Localizar um caminho no grafo:

```powershell
powershell -ExecutionPolicy Bypass -File tools\graphify_argos.ps1 `
  -Action Path -From "webapp" -To "MedGemma"
```

## Neo4j

O driver Neo4j foi instalado para permitir exportação futura, mas nenhum push é
feito por padrão. Se essa opção for adotada, o grafo arquitetural deverá usar
outro database ou namespace, credenciais próprias e política de retenção
independente do GraphRAG clínico. O banco clínico atual nunca deve receber os nós
do Graphify implicitamente.

## Limites metodológicos

O Graphify melhora compreensão e manutenção do software. Ele não constitui uma
intervenção diagnóstica e não sustenta alegação de ganho de sensibilidade ou
especificidade. Qualquer ganho clínico continua exigindo benchmark separado e
protocolo congelado.
