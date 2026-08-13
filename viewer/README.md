# Visualizador (modo Pesquisa)

Possui extensão progressiva para Meta Quest 3S/WebXR. Consulte
`docs/222_META_QUEST_3S_WEBXR_IMPLEMENTADO.md` para HTTPS, perfis, controles e
LOD auditável. Sem WebXR, o fluxo desktop permanece inalterado.

Visualizador 3D estático (Three.js, sem build) para os STLs gerados pelo pipeline.
**NÃO destinado a decisão clínica.** Coordenadas LPS.

> **Offline:** o Three.js (+ STLLoader + OrbitControls) está vendorizado em
> `viewer/vendor/` e resolvido por um importmap no `index.html`. Não há
> dependência de CDN — funciona sem internet (ex.: na apresentação).

## Uso rápido (drag & drop)

1. Abra `viewer/index.html` no navegador (duplo clique funciona).
2. Arraste para a área indicada o conteúdo da pasta `outputs/` de um caso
   (o `viewer_manifest.json` **e** os arquivos `.stl`).

## Uso servido (carregamento automático via ?case=)

Por restrição do navegador, `fetch` só funciona via http. Sirva a raiz do projeto:

```bash
python -m http.server 8000
```

Depois abra (ajuste o caminho do caso):

```
http://localhost:8000/viewer/index.html?case=../casos/sintetico/outputs
```

Controles: orbitar (arrastar), zoom (scroll), alternar visibilidade e opacidade de
órgão/lesão no painel à direita.

## Revisão integrada ao webapp

Quando aberto pelo botão do webapp, o viewer recebe também `?job=<id>` e mostra
as ações **Aprovar segmentação** e **Solicitar revisão**. A decisão é enviada ao
backend local e persistida no caso como `outputs/approval.json`.

## Recursos do manifesto v2

O visualizador oferece vistas anatômicas nomeadas, controles por estrutura,
corte ortogonal, modo de malha, régua de superfície, captura PNG, tela cheia e
referências axial/coronal/sagital da RM com contorno automático.

Os atalhos **Fígado**, **Segmentos**, **Vasos** e **Candidato** aplicam uma
composição autorizada e enquadram a camada correspondente. Durante a revisão é
possível salvar até oito marcadores visuais; cada marcador restaura câmera,
visibilidade, opacidades, corte, referência 2D e estrutura selecionada e é
persistido no registro de aprovação.

Duas vistas salvas podem ser marcadas como **A** e **B** para comparação lado a
lado. As miniaturas são capturas locais exclusivas do canvas 3D; pixels da RM
2D não são incorporados nem enviados ao backend. Clicar em uma miniatura
restaura a cena correspondente.

Uma estrutura selecionada também pode ser medida em três dimensões LPS:
esquerda–direita (LR), anterior–posterior ou profundidade (AP) e
superior–inferior (SI). As dimensões são calculadas sobre a caixa envolvente da
malha segmentada e permanecem identificadas como medidas automáticas
aproximadas, não como confirmação clínica.

O painel de qualidade mede a fidelidade **da malha à máscara fonte**; ele não
mede acurácia clínica da segmentação. Manifestos v2 exigem um checklist de
revisão e registram o estado do visualizador, medições e hashes dos artefatos.

O contrato completo, os limites e a validação estão documentados em
`docs/166_VISUALIZADOR_3D_AUDITAVEL.md`.
