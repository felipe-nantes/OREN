# Plano — Realismo anatômico seguro no visualizador OREN e WebXR

Data: 2026-08-14  
Estado: implementação concluída em código; validação física no Quest 3S pendente

## 1. Baseline protegido antes do desenvolvimento

A versão atual foi congelada antes de qualquer nova alteração:

- testes relevantes: **139 aprovados**;
- tag Git de segurança: `safety/oren-spatial-v2-2-20260814`;
- commit do snapshot: `a591925ceda96b49789426a88a69a8f74267df83`;
- tag Docker de segurança: `argos-runtime:oren-spatial-v2-2-safe`;
- imagem Docker: `sha256:7f1d6ad924e12fe11c620ae34060ccc59f23f723252bcebfb5a6107cee5333e8`;
- `argos`, `proxy` e `neo4j` estavam saudáveis no congelamento.

O snapshot não muda a branch ou os arquivos de trabalho. Ele existe para restaurar o visualizador estável mesmo que uma experiência futura falhe.

## 2. Problema visual identificado

O material atual é funcional e semanticamente seguro, mas a aparência de “massinha” decorre da combinação de:

- variação tonal procedural de baixa frequência aplicada por vértice;
- ausência de albedo orgânico de alta frequência;
- ausência de mapa de normal ou microrelevo;
- rugosidade quase uniforme;
- pouca oclusão visual em sulcos e no hilo hepático;
- superfície suavizada iluminada por um conjunto simples de luzes.

A imagem de referência combina microtextura, reflexo úmido controlado, variação cromática fina, sombras de contato e contraste entre parênquima, vesícula e vasos.

## 3. Limite científico obrigatório

O novo acabamento será denominado **Representação anatômica realista**, e não “fígado real do paciente”.

- Geometria, volume e medições continuam vindo das máscaras do exame.
- Texturas são ilustrativas e não representam histologia ou textura real do paciente.
- Microrelevo será somente de iluminação; não deslocará vértices nem alterará dimensões.
- Nenhuma estrutura anatômica poderá ser criada a partir de um atlas para preencher uma ausência.
- Uma estrutura somente aparecerá quando existir uma máscara válida do próprio caso.
- A ausência de máscara deve ser exibida como “estrutura não disponível”, nunca preenchida visualmente.

O pipeline atual pode fornecer, quando a segmentação tiver sucesso:

- fígado;
- vesícula biliar;
- veia porta e veia esplênica;
- veia cava inferior;
- segmentos de Couinaud I–VIII;
- lesão manual ou candidato automático, quando existentes.

O modelo `total_mr` instalado não fornece uma árvore arterial hepática. Portanto, vasos arteriais vermelhos semelhantes aos da referência não serão inventados. Eles somente poderão entrar futuramente por uma máscara manual ou por um segmentador de RM validado.

## 4. Resultado funcional desejado

O visualizador terá um controle único:

```text
Representação anatômica realista  [ativada/desativada]
```

- Ativada: materiais realistas, microtextura e iluminação anatômica.
- Desativada: restaura exatamente o acabamento atual protegido.
- A troca não recarrega o caso, não troca a malha e não altera opacidade, corte, medição, seleção ou posição.
- O mesmo controle existirá no desktop e no tablet do Meta Quest.
- Durante o desenvolvimento, o acabamento atual permanece padrão.
- Após os gates automatizados, visuais e físicos, o realista poderá se tornar padrão, mantendo o botão de retorno.

## 5. Arquitetura proposta

### 5.1 Perfis de material

Criar dois perfis explícitos e versionados:

```text
scientific_current_v1
anatomic_realistic_v1
```

O perfil atual não será reescrito. O novo perfil será aplicado sobre as mesmas malhas e poderá ser removido sem perda de estado.

O manifesto deve registrar:

- perfil selecionado;
- versão do pacote de texturas;
- SHA-256 dos assets;
- `texture_source: illustrative_not_patient_derived`;
- qualidade efetiva escolhida pelo dispositivo;
- motivo de fallback, se ocorrer.

### 5.2 Pacote de texturas original e local

Produzir assets próprios, inspirados apenas nas características visuais da referência, sem copiar a imagem anexada:

- fígado: albedo orgânico, normal de microtextura e mapa combinado de rugosidade/oclusão;
- vesícula: material verde-oliva escuro, superfície mais lisa e reflexo moderado;
- veias: azul vascular dessaturado, reflexo úmido discreto;
- lesão/candidato: materiais visualmente distintos e sem aparência de diagnóstico confirmado;
- Couinaud: manter cores de navegação quando o preset de segmentos estiver ativo.

Os mapas serão comprimidos em KTX2/Basis, locais e reutilizados entre casos. Não haverá download externo durante a revisão.

### 5.3 Microtextura sem alterar anatomia

O fígado receberá:

- normal map de amplitude baixa;
- variação fina de rugosidade;
- variação cromática multiescala sem repetição evidente;
- oclusão/curvatura pré-calculada quando disponível;
- brilho úmido localizado, sem transparência gelatinosa;
- falsa dispersão subsuperficial leve baseada em luz, sem `transmission` real.

São proibidos displacement, tesselação dinâmica e qualquer deformação da malha de medição.

### 5.4 Iluminação

Adotar iluminação clínica de estúdio:

- luz principal suave;
- preenchimento neutro;
- recorte posterior discreto;
- ambiente PMREM pequeno e local;
- sombras de contato pré-calculadas ou aproximadas.

No Quest não serão usadas sombras dinâmicas, SSAO ou pós-processamento pesado. O objetivo é melhorar leitura de volume sem aumentar instabilidade.

## 6. Estratégia de desempenho para Meta Quest 3S

O usuário verá apenas um botão de realismo, mas internamente haverá qualidade adaptativa:

- desktop: mapas de até 2K quando houver memória;
- Quest em qualidade: fígado em 1K e estruturas secundárias em 512 px;
- Quest em estabilidade: mapas reduzidos e normal secundária desativada;
- texturas compartilhadas por categoria, sem material novo por caso;
- materiais compilados antes de aparecerem para evitar travada na primeira troca;
- nenhuma alocação ou geração de textura dentro do loop de frames;
- descarte explícito de texturas e materiais ao sair do caso.

Gates de fluidez:

- meta: 72 Hz;
- p95 do frame time ≤ 13,9 ms no cenário de referência;
- nenhum desaparecimento ou flicker de malha;
- troca de perfil sem congelamento perceptível;
- ausência de crescimento contínuo de memória após alternar dez vezes;
- se o p95 ultrapassar o limite por janelas consecutivas, reduzir detalhes;
- se a degradação persistir, retornar automaticamente ao modo atual e informar o usuário.

## 7. Execução faseada

### Fase 1 — Contrato e fallback

- Implementar os dois perfis sem modificar o baseline.
- Adicionar o botão no desktop e a ação correspondente no tablet XR.
- Preservar estado de câmera, modelo, cortes, opacidade e medições durante a troca.
- Adicionar fallback transacional: qualquer erro de asset/material restaura o modo atual.

Aceite: alternar repetidamente produz o mesmo estado anterior e nunca oculta o fígado.

### Fase 2 — Protótipo do fígado

- Aplicar o novo material somente ao fígado de um caso de mostruário.
- Comparar albedo, normal, rugosidade e iluminação separadamente.
- Congelar parâmetros somente após captura desktop e inspeção física no Quest.

Aceite: melhora visual clara sem alterar geometria, volume, medidas ou hashes clínicos.

### Fase 3 — Vesícula e vasos existentes

- Aplicar materiais específicos à vesícula, veia porta/esplênica e veia cava.
- Preservar oclusão: estruturas internas só aparecem através do fígado quando a opacidade for reduzida ou houver corte.
- Não publicar estruturas ausentes ou inválidas.

Aceite: cores realistas, nenhuma estrutura inventada e todas as regras de profundidade preservadas.

### Fase 4 — Couinaud, lesão e candidatos

- Manter Couinaud como camada educacional/navegacional, não como textura superficial real.
- Usar material realista distinto para lesão manual.
- Manter candidato e região classificada como overlays de revisão, sem aparência de confirmação clínica.

Aceite: sem confusão entre anatomia, ground truth manual e hipótese automática.

### Fase 5 — Otimização WebXR

- Comprimir texturas.
- Pré-aquecer shaders e materiais.
- Integrar a degradação ao `performanceTier` existente.
- Medir draw calls, triângulos, textura, memória e p95.

Aceite: orçamento de 72 Hz cumprido e fallback automático comprovado.

### Fase 6 — Validação e promoção

- Testar desktop, WebXR VR e mixed reality.
- Fazer comparação visual A/B com o modo atual.
- Revisar cinco casos diversificados do mostruário.
- Realizar sessão física de dez minutos no Quest 3S.
- Somente após aprovação, tornar o realista padrão; o botão de desativação permanece.

## 8. Testes obrigatórios

- modo atual permanece pixel e funcionalmente restaurável;
- perfil desconhecido é rejeitado;
- falha de textura retorna ao modo atual;
- assets possuem allow-list e SHA-256;
- nenhuma textura remota é carregada;
- ausência de vesícula/vaso não quebra o caso;
- medidas e volumes são idênticos entre os dois perfis;
- plano de corte e inversão não fazem o órgão desaparecer;
- seleção, opacidade, estruturas e sincronização 2D/3D continuam funcionando;
- desktop sem WebXR permanece funcional;
- dez alternâncias não aumentam materiais, texturas ou listeners;
- saída e reentrada no XR restauram o perfil corretamente;
- qualidade adaptativa reduz custo sem mudar a malha de medição;
- suíte atual continua verde e novos testes de material são adicionados.

## 9. Critério final de sucesso

A tentativa será válida somente se:

1. a aparência deixar de ser plástica/massinha em avaliação visual;
2. fígado, vesícula e vasos disponíveis forem reconhecíveis e coerentes;
3. nenhum detalhe ilustrativo for apresentado como anatomia medida;
4. volume e medições permanecerem invariantes;
5. o modo atual puder ser restaurado instantaneamente pelo botão;
6. não houver flicker, desaparecimento ou regressão de interação;
7. o Quest 3S mantiver o orçamento de fluidez definido;
8. os testes automatizados e o gate físico forem aprovados.

## 10. Rollback

Em qualquer falha, restaurar o código pelo snapshot:

```bash
git restore --source safety/oren-spatial-v2-2-20260814 -- viewer webapp dtwin tests
```

Ou restaurar diretamente o runtime Docker protegido:

```bash
docker tag argos-runtime:oren-spatial-v2-2-safe argos-runtime:local
```

Nenhum rollback deve apagar casos, DICOMs, máscaras ou relatórios.
