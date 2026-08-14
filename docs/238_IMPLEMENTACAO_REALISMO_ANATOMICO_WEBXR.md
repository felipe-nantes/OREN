# Implementação — Realismo anatômico seguro no OREN/WebXR

Data: 2026-08-14  
Build: `20260814-anatomic-v1-2`  
Estado: código e runtime automatizados concluídos; inspeção física final no Quest 3S pendente

Imagem Docker validada: `sha256:3f654600f8f47530e9a9da2f06b78d578d9362742d96a0e39093724d086b04b2`.

## 1. Segurança e rollback

Antes da implementação, o visualizador estável foi congelado em:

- tag Git `safety/oren-spatial-v2-2-20260814`;
- commit `a591925ceda96b49789426a88a69a8f74267df83`;
- imagem Docker `argos-runtime:oren-spatial-v2-2-safe`;
- ID `sha256:7f1d6ad924e12fe11c620ae34060ccc59f23f723252bcebfb5a6107cee5333e8`.

O novo acabamento não substitui nem reescreve o material protegido. O botão
restaura `scientific_current_v1` sem recarregar o caso.

## 2. O que foi implementado

### Perfis reversíveis

- `scientific_current_v1`: acabamento anterior protegido;
- `anatomic_realistic_v1`: acabamento ilustrativo realista;
- botão no desktop e ação `render_realism` no tablet do WebXR;
- câmera, visibilidade, opacidade, seleção, cortes e medidas são preservados na troca;
- erro de asset restaura o perfil científico e registra `asset_load_error`.

### Pacote original de materiais

O pacote `oren-liver-realistic-v1` é local, versionado e gerado por
`tools/build_anatomic_material_textures.py`. A fonte é uma imagem original
ilustrativa, não derivada do paciente. Ela produz:

- albedo orgânico;
- normal map de baixa amplitude;
- mapa de rugosidade;
- bordas seladas para amostragem repetida sem emendas;
- manifesto com tamanho, bytes e SHA-256 de cada asset.

Não existe `displacementMap`: a textura não move nenhum vértice. A geometria,
volumetria e as medições continuam sendo determinadas exclusivamente pelas
máscaras do exame.

### Anatomia secundária

- vesícula biliar: verde-oliva, superfície lisa e brilho moderado;
- veia porta/esplênica: azul venoso dessaturado;
- veia cava inferior: azul venoso profundo;
- Couinaud continua como camada de navegação colorida;
- lesão/candidato e região classificada continuam overlays de revisão;
- uma estrutura só aparece se a respectiva malha existir no manifesto do caso.

Não foi criada artéria hepática: o segmentador MR atual não fornece essa máscara.

### Qualidade adaptativa no Quest

- desktop usa mapas de 1024 × 1024;
- URL Quest/User-Agent Quest usa mapas de 512 × 512;
- tier `stability` reduz anisotropia, normal map e clearcoat;
- tier `quality` restaura o detalhe completo;
- shaders são pré-aquecidos no desktop;
- três janelas consecutivas acima do orçamento restauram o perfil científico e
  registram `performance_budget_exceeded`;
- ao sair do XR, o tier volta para `quality`.

PNG otimizado foi mantido nesta versão porque o runtime não possui `toktx` nem
transcodificador KTX2 vendorizado. Isso evita adicionar uma dependência externa
ou um caminho de rede ao visualizador. O conjunto Quest soma aproximadamente
1,25 MB em disco, contra aproximadamente 5,39 MB no desktop.

## 3. Auditabilidade

O estado de revisão agora persiste:

- `rendering_profile`;
- `rendering_quality_tier`;
- `material_pack_id`;
- `material_pack_variant`;
- `rendering_fallback_reason`.

Os únicos valores aceitos são validados pelo backend. Caminhos ou IDs arbitrários
enviados pelo navegador são rejeitados.

## 4. Evidências visuais

As capturas ficam em `experiments/realistic_material_v1/`:

- `baseline_scientific_current_v1.png`;
- `phase2_liver_texture_closeup.png`;
- `phase3_realistic_anatomy_structures.png`;
- `phase4_adaptive_realistic_quality.png`;
- `phase4_scientific_fallback_restored.png`.

## 5. Validação automatizada

Os testes cobrem:

- determinismo do gerador de textura;
- bordas repetíveis;
- hashes e bytes dos dois pacotes;
- ausência de displacement e de URLs remotas;
- allow-list local de assets;
- validação dos perfis, tiers, variantes e motivos de fallback;
- ação desktop e WebXR;
- degradação adaptativa e fallback após três janelas críticas;
- viewer, artefatos 3D, webapp, launcher/certificado Quest e volumetria.

Resultado local final: **136 testes aprovados**, sem falhas.

## 6. Gate físico restante

O software pode ser aberto no Quest, mas a aprovação final exige uma sessão física:

1. abrir um caso pelo link HTTPS Quest;
2. alternar o realismo dez vezes;
3. testar default, anatomia interna, segmentos, corte e opacidade;
4. confirmar ausência de flicker/sumiço do fígado;
5. confirmar legibilidade do tablet e interação por mãos;
6. observar `window.__argosXR.getPerformance()` e registrar p95;
7. manter a sessão por dez minutos;
8. aprovar ou rejeitar visual e fluidez.

Até essa inspeção, `scientific_current_v1` permanece como padrão. O modo realista
é opt-in e sempre pode ser desligado pelo botão.

## 7. Correção de opacidade anatômica — build v1-3

Após revisão visual, foi identificado que vasos e vesícula permaneciam no pipeline
transparente mesmo quando o slider indicava 100%. A causa era a função de oclusão,
que considerava somente fígado e segmentos como superfícies sólidas.

A correção passou a tratar `vessel` e `gallbladder` como superfícies sólidas em
opacidade `1.0`:

- `transparent=false`;
- `depthWrite=true`;
- `depthTest=true` permanece obrigatório;
- ao reduzir a opacidade abaixo de 100%, `transparent=true` e `depthWrite=false`;
- presets default, anatomia interna, triagem e segmentos agora iniciam vasos e
  vesícula em 100% de opacidade.

Evidências:

- `experiments/realistic_material_v1/phase5_opaque_vessels_gallbladder.png`;
- `experiments/realistic_material_v1/phase5_internal_anatomy_opaque_structures.png`.
