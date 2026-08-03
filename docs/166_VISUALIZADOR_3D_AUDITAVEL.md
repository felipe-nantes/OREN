# Visualizador 3D auditável de fígado por RM

**Data:** 2 de agosto de 2026  
**Estado:** implementado e validado em modo de pesquisa  
**Escopo:** reconstrução anatômica para revisão humana; não destinado a decisão clínica

## 1. Objetivo

O visualizador deixou de ser apenas uma renderização de arquivos STL. Ele passou a
ser uma superfície de revisão que mantém, no mesmo contexto:

- o modelo tridimensional segmentado;
- as imagens bidimensionais de RM que deram origem ao modelo;
- métricas de fidelidade da reconstrução à máscara fonte;
- proveniência geométrica e hashes dos artefatos;
- controles de inspeção e um checklist humano auditável.

A distinção central é obrigatória: as métricas implementadas avaliam **malha versus
máscara**, não máscara versus anatomia verdadeira. Um erro de segmentação pode ter
uma malha geometricamente perfeita e ainda assim continuar sendo um erro.

## 2. Funcionalidades implementadas

### 2.1 Exploração tridimensional

- rotação, zoom e enquadramento automático;
- vistas anatômicas reproduzíveis: padrão, anterior, superior e direita;
- visibilidade, isolamento e opacidade por estrutura;
- modo de malha (*wireframe*);
- corte ortogonal axial, coronal ou sagital, com inversão e posição ajustável;
- régua de superfície em milímetros;
- captura PNG do palco 3D;
- modo de tela cheia;
- atalhos `0`, `1`, `2`, `3`, `M`, `C` e `Esc`.

As estruturas exibidas dependem das máscaras realmente produzidas no caso. O
fluxo atual pode incluir fígado, segmentos de Couinaud, veia porta/esplênica,
veia cava inferior, vesícula e lesão manual. Uma estrutura ausente não é
inventada nem substituída por atlas.

### 2.2 Referência bidimensional

O `finalize` gera imagens sem metadados com:

- todos os planos axiais que contêm voxels da máscara hepática;
- um plano coronal no centroide;
- um plano sagital no centroide;
- janela de intensidade única e determinística por caso;
- contorno amarelo da máscara hepática automática;
- orientação canônica LPS e posição física em milímetros;
- SHA-256 individual.

O painel 2D serve para detectar problemas que uma superfície suavizada pode
ocultar: fígado incompleto, ilhas espúrias, vazios, contorno deslocado ou baixa
qualidade da imagem. Ele não substitui um visualizador DICOM diagnóstico.

### 2.3 Qualidade e proveniência

Para cada malha são registrados:

- volume da máscara e volume encerrado pela malha;
- erro absoluto percentual de volume;
- área de superfície;
- dimensões e contagem de vértices/triângulos;
- topologia fechada e manifold;
- distância média, p95 e máxima dos vértices à superfície da máscara;
- spacing da aquisição, SHA-256 e avisos do gate de reconstrução.

O manifesto `argos-viewer-manifest-v2` também informa geometria de aquisição,
interpolação e suavização usadas na malha. A aprovação nunca depende de um
percentual arredondado: o backend verifica os hashes declarados antes de servir e
antes de considerar o caso pronto.

### 2.4 Relações espaciais

Quando existe lesão **manual**, o manifesto pode registrar distâncias aproximadas
entre suas superfícies e o fígado/vasos e a sobreposição com segmentos de
Couinaud. Esses dados são descritivos e não constituem plano cirúrgico. Na
ausência de lesão manual, nenhuma lesão é inferida para preencher a interface.

### 2.5 Revisão humana auditável

A aprovação integrada ao webapp exige confirmar:

1. que o contorno 2D acompanha o fígado nas referências revisadas;
2. que o modelo 3D não apresenta ausência grosseira ou estrutura espúria;
3. que orientação e relações anatômicas são coerentes.

O registro inclui decisão, revisor, observação, checklist, vista, clipping,
visibilidade/opacidade, medições, hash do manifesto e hashes dos artefatos. Uma
solicitação de revisão não exige marcar o checklist como aprovado.

## 3. Segurança e compatibilidade

- O contrato anterior continua aceito para manifestos legados.
- O primeiro painel e os nomes históricos de STL permanecem compatíveis.
- O backend serve somente arquivos declarados no manifesto; caminhos arbitrários
  não são aceitos.
- Imagem ou STL com hash divergente retorna erro e invalida o estado de pronto.
- PNGs de referência não carregam EXIF nem cabeçalhos DICOM.
- Nenhum UID DICOM ou dado identificável é gravado no manifesto.
- A gravação do manifesto é atômica para evitar um caso parcialmente publicado.

## 4. Limites deliberados

Não foram adicionados nesta etapa:

- ressecção virtual, margem oncológica ou cálculo de remanescente;
- territórios vasculares ou planejamento de hepatectomia;
- árvore biliar interna quando não existe máscara MR validada;
- máscara vascular treinada apenas em CT aplicada silenciosamente à RM;
- afirmação de acurácia clínica baseada apenas na qualidade da malha.

Essas funções exigem segmentações próprias, validação por estrutura e protocolo
clínico. Adicioná-las apenas como efeito visual produziria uma precisão aparente
que os dados não sustentam.

## 5. Validação realizada

- testes unitários de geração de referências 2D, métricas, relações espaciais e
  sobreposição por segmento;
- testes de integração do `finalize` e do contrato HTTP;
- verificação de conteúdo, MIME, hash e checklist de aprovação;
- smoke test real com 45 cortes hepáticos, três malhas e 47 PNGs;
- inspeção visual axial, coronal e sagital;
- teste em navegador local, incluindo vista anatômica, clipping e troca de plano;
- correção do canvas para telas high-DPI, eliminando recorte e desalinhamento do
  ray casting.

No caso real do smoke test, a malha do fígado preservou o volume da máscara com
erro de 0,23%. As estruturas vasculares mostraram avisos próprios, demonstrando
que o gate não mascara problemas menores sob uma aprovação global.

## 6. Referências de arquitetura

As decisões foram inspiradas por funcionalidades e limites descritos em:

- Fujifilm Synapse 3D Liver Analysis para separação de estruturas, registro
  multifásico, volumetria e planejamento;
- documentação oficial do 3D Slicer Segmentations para representações 2D/3D,
  visibilidade, opacidade e mensuração;
- Ivashchenko et al. para implementação clínica de modelos hepáticos derivados
  de RM e interação em dispositivo;
- Oh et al. para a variação de Dice entre fígado, tumor, vasos e via biliar,
  justificando gates e avisos independentes por estrutura.

O relatório de origem usado nesta implementação está em
`C:/Users/profurg/Desktop/sander/oren_web/documentos/relatorio_reconstrucoes_3d_digitais_figado_rm.docx`.

## 7. Próximas evoluções tecnicamente justificadas

1. validar separadamente Couinaud e vasos em conjunto MR revisado por especialista;
2. sincronizar um cursor 3D com o plano 2D, se for necessário apontar a mesma
   coordenada nas duas representações;
3. substituir PNGs por um visualizador DICOM dedicado somente após preservar
   desidentificação, registro de fases e contrato de auditoria;
4. implementar planejamento de ressecção apenas quando houver segmentação
   vascular/biliar validada e critérios cirúrgicos formalizados.

