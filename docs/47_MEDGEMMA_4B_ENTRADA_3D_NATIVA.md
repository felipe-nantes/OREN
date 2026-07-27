# Etapa v12 — entrada 3D nativa do MedGemma 1.5 4B

## Motivo

O protocolo v11 combinou três sinais já existentes e alcançou 74,36% de
sensibilidade e 75,00% de especificidade em LOOCV. Como reajustar pesos ou limiar
nos mesmos 87 labels aumentaria o risco de sobreajuste, a etapa seguinte introduz
evidência realmente nova: a representação high-dimensional de múltiplos cortes
suportada pelo MedGemma 1.5 4B.

Referências da implementação:

- [Model card oficial do MedGemma](https://developers.google.com/health-ai-developer-foundations/medgemma/model-card)
- [Repositório oficial](https://github.com/google-health/medgemma)
- [Notebook high-dimensional oficial](https://github.com/Google-Health/medgemma/blob/main/notebooks/high_dimensional_ct_hugging_face.ipynb)
- [Relatório técnico](https://arxiv.org/abs/2604.05081)

## Alterações implementadas

### Gateway

O contrato legado `dtwin-medgemma-v1` e o endpoint `/generate` foram preservados.
Foi adicionado um caminho independente:

```text
contrato: dtwin-medgemma-volume-v1
endpoint: /generate-volume
runtime: Transformers
quantidade: 5 a 85 PNGs
dimensão máxima: 512 × 512 por imagem
```

O conteúdo enviado ao template segue a ordem do notebook oficial:

```text
instrução
imagem 1
SLICE 1
imagem 2
SLICE 2
...
consulta final
```

A geração é determinística (`do_sample=False`). Campos extras são recusados no
payload volumétrico para impedir que nomes de arquivos, UIDs ou outros metadados
sejam enviados ao modelo.

### Preparação da pilha MRI

O módulo `dtwin/benchmark/openswisshcc_highdimensional.py`:

1. lê somente `t1_venous` e `liver_mask_venous`;
2. rejeita qualquer manifesto com entrada de lesão, tumor, label ou ground truth;
3. verifica os hashes do manifesto protegido de inferência;
4. exige geometria idêntica entre volume e máscara hepática;
5. orienta ambos para LPS;
6. usa a máscara hepática apenas para delimitar o intervalo axial;
7. aplica normalização min–max por volume;
8. gera cortes em grayscale replicado para RGB, sem cor, contorno ou máscara visível;
9. limita cada imagem a 512 × 512;
10. usa até 85 cortes equidistantes conforme a fórmula oficial;
11. persiste nomes, ordem, índices, hashes e cobertura em `manifest.json`;
12. recusa o reuso se qualquer PNG for alterado.

### Congelamento e cliente cego

O módulo `dtwin/benchmark/openswisshcc_highdimensional_inference.py`:

- aceita somente endpoint HTTP local;
- assina o protocolo antes da inferência;
- recusa protocolo ou pilha alterados;
- verifica health, modelo, versão e contrato;
- executa uma única chamada por caso;
- exige resposta JSON com classe autorizada;
- mantém `research_only=true`, `clinical_use_allowed=false` e revisão humana;
- não lê ground truth e não calcula métricas.

## Piloto técnico congelado

Seleção do caso:

```text
primeiro case_id em ordem lexicográfica no bundle cego v11
anon-openswiss-04031ea54343b8db
```

Entradas e protocolo:

```text
cortes: 50
cobertura dos voxels hepáticos nos planos selecionados: 100%
tempo de preparação: 1,671 s
hashes de PNG divergentes: 0
manifesto SHA-256:
b0af928aaf44a1a415d44c7847387042d2db2439edd45b5be7b974c29f0e4742

assinatura do protocolo:
9331633b58ab3ddbfb8ac67c38583aa5db4a55fc4e50389335a9ec2f0c23e289

arquivo do protocolo SHA-256:
954b53b3f582f3211249e9a4c92bde90866a030bf6737e806c139c71ec477f54
```

Resultado técnico:

```text
classificação retornada: NEGATIVA
schema de saída: válido
tempo do gateway: 148,4218 s
tempo HTTP: 148,5026 s
tempo total observado: 149,686 s
gate de 180 s: aprovado
pico observado da GPU: 7.943 MiB
resultado SHA-256:
79a7ea917b0a91eca820fc8b5fe737dc36fe14fa8c452f18b8296ada33fe03aa
```

O label desse caso não foi aberto. Portanto, `NEGATIVA` não é acerto nem erro
nesta etapa; é somente evidência de que o fluxo produziu uma saída válida.

## Validação automatizada

Foram executados 25 testes focados, todos aprovados. A cobertura inclui:

- compatibilidade integral do endpoint legado;
- ordem oficial das imagens;
- limites de 5 a 85 cortes;
- PNG, RGB, dimensão e limites agregados;
- recusa de campos extras com potencial PHI;
- recusa de modelo divergente;
- normalização e amostragem determinísticas;
- rejeição de máscara de lesão/ground truth;
- geometria e hashes;
- detecção de PNG adulterado;
- assinatura e imutabilidade do protocolo;
- endpoint exclusivamente local;
- health e saída estruturada.

Após a inclusão do teto configurável de cortes, a suíte completa do ARGOS também
foi executada: **547 testes aprovados, zero falhas**. Os 334 avisos observados são
depreciações já conhecidas de dependências e não representam falhas do pipeline.

## Limitações e decisão

O piloto comprovou viabilidade funcional, mas a margem operacional é pequena:

```text
margem de tempo no request: aproximadamente 31,5 s
margem de VRAM observada em GPU de 8 GB: aproximadamente 249 MiB
```

Não é seguro assumir que 85 cortes cumprirão 180 s nessa GPU. Antes do benchmark
de desenvolvimento, o próximo protocolo deve limitar a pilha a no máximo 50
cortes e executar pilotos cegos adicionais com volumes de diferentes dimensões.
Somente após o protocolo final estar congelado devem ser geradas as predições dos
87 casos. Os labels de desenvolvimento só podem ser abertos após todas as
predições estarem persistidas; o holdout continua fechado.

Não há ainda evidência de aumento de sensibilidade ou especificidade. Esta etapa
prova apenas que a nova representação funciona dentro do tempo para o piloto de
50 cortes.
