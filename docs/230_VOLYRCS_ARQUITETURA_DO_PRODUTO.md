# Volyrcs — Arquitetura do Produto

**Volumetria hepática e visualização 3-D a partir de DICOM.**

Documento de arquitetura. Define o que o produto é, o que se aproveita do OREN,
o que sai, o que falta construir e em que ordem.

---

## 1. O que o Volyrcs é

Um produto que recebe um exame DICOM de fígado, segmenta automaticamente a
anatomia, **submete a segmentação à aprovação do radiologista** e então mede
volumes e apresenta um modelo 3-D navegável.

```text
DICOM (pasta ou PACS)
   → segmentação automática do fígado
   → segmentos de Couinaud, vasos, vesícula
   → região candidata de lesão (marcação visual)
   → REVISÃO E APROVAÇÃO HUMANA          ← o médico decide
   → volumetria física auditável
   → visualizador 3-D + laudo de medidas
```

### O que o Volyrcs NÃO é

Isto define o produto tanto quanto o que ele é:

- **Não classifica lesão.** Não diz FNH, HCC, hemangioma ou cisto.
- **Não emite diagnóstico** nem sugere conduta.
- **Não declara sensibilidade nem especificidade** para detecção de lesão.
- **Não mede nada que o médico não tenha aprovado.** A medida é da máscara
  aprovada, não da máscara que a máquina propôs.

A região candidata de lesão existe apenas como **marcação visual**, herdada do
`candidate_region.py`, que já carrega no próprio código a frase: *"never a
diagnosis or a ground-truth lesion mask"*.

### Posicionamento regulatório

**Ferramenta de medição sob revisão humana.** O software propõe, o médico
aprova, o software mede o que foi aprovado. Isso mantém o profissional no
circuito de decisão e é o caminho de menor risco regulatório.

Consequência arquitetural obrigatória: **sem aprovação registrada, não há
medida publicada.** Não é um aviso na tela — é um gate no código.

---

## 2. Inventário honesto: o que já está pronto

O Volyrcs não começa do zero. Levantamento do que existe hoje no OREN:

| Componente | Estado | Onde |
|---|---|---|
| Ingestão DICOM + gate de modalidade | pronto | `dtwin/stages.py:stage1_ingest` |
| Normalização e geometria física | pronto | `stage2_normalize` |
| Segmentação hepática (TotalSegmentator) | pronto | `stage3_segment_organ` |
| Segmentação aprimorada (MRSegmentator) | pronto | `dtwin/segmentation_shadow.py` |
| União multifásica | pronto | `webapp/server.py:_build_union_liver_mask` |
| Refino + guarda de fragmentação | pronto | `stage5_refine` |
| Couinaud I–VIII | pronto | docs/208 |
| Vasos + vesícula | pronto | perfil `figado.yaml` |
| Região candidata de lesão | pronto | `dtwin/candidate_region.py` |
| Geração de malha 3-D | pronto | `stage6_mesh` |
| Volumetria física + nota técnica A–D | pronto | `dtwin/volumetry.py` |
| Verificador independente de volumetria | pronto | `tools/verify_volumetry.py` |
| Visualizador 3-D + presets + medição | pronto | `viewer/` |
| Sincronização 2D ↔ 3D | pronto | docs/209, docs/213 |
| WebXR / Meta Quest | pronto | docs/222–227 |
| Empacotamento Docker ponta a ponta | pronto | docs/229 |
| Contrato protegido de máscara | pronto | `dtwin/segmentation_contract.py` |

**A fundação já é órgão-agnóstica.** O `dtwin/core.py` declara explicitamente
que não conhece "fígado": o órgão vem de um perfil YAML versionado. Trocar de
órgão é adicionar um arquivo em `profiles/`, não alterar o motor. A
modularidade que o produto exige **já está na base** — não precisa ser
construída, precisa ser exercitada.

### Qualidade medida da segmentação

Números reais, contra referência humana, com gates pré-especificados:

| Coorte | `total_mr` | MRSegmentator |
|---|---:|---:|
| CHAOS, n=20 (Dice mediano) | 0,9082 | **0,9244** |
| LiverHccSeg contrastado, n=14 | 0,8977 | **0,9138** |

O MRSegmentator melhorou em 18/20 e 14/14 casos respectivamente. O produto
herda esse candidato com o fallback já implementado.

---

## 3. O que sai do OREN

Remoção limpa, não desativação:

| Sai | Motivo |
|---|---|
| `dtwin/medgemma_*.py` (8 módulos) | classificação e triagem |
| `dtwin/medsiglip_zero_shot.py` | classificação |
| `dtwin/learning/` (classificadores, embeddings) | classificação |
| `process_job` / `process_visual_job` | fluxos acoplados a MedGemma |
| Painéis RGB para classificação | entrada do classificador |
| Benchmarks de subtipo e triagem | avaliação de classificação |
| Estágios 4a/4b (importação manual de lesão) | dependem do 3D Slicer |

**O acoplamento é menor do que parece:** apenas 108 das 3.610 linhas de
`webapp/server.py` mencionam MedGemma (3%). O pipeline `stage1..stage7` é
independente da classificação — os estágios de lesão manual são opcionais e o
`candidate_region` roda depois da decisão, nunca antes.

Os painéis RGB permanecem **apenas** como referência visual 2-D no
visualizador, se úteis — nunca como entrada de modelo.

---

## 4. O que falta construir

Ordenado por criticidade. Este é o trabalho real do produto.

### 4.1 Aprovação da segmentação — BLOQUEANTE

Hoje **não existe** revisão da segmentação: `grep` por edição no
`viewer/app.js` retorna zero. Sem isso, o posicionamento de "ferramenta sob
revisão humana" não se sustenta.

Escopo desta fase: **aprovar ou rejeitar**, com o ajuste global preparado mas
não implementado.

- Tela de revisão: cortes axial/coronal/sagital com o contorno sobreposto,
  navegação por corte, mais o 3-D já existente.
- Ações: **Aprovar** ou **Rejeitar** (com motivo estruturado).
- Registro de aprovação assinado: quem aprovou, quando, hash SHA-256 da
  máscara aprovada, versão do modelo, fase usada.
- **Gate:** volumetria e laudo só são publicados com aprovação válida. Máscara
  rejeitada não produz medida.
- **Preparado para o futuro:** a ação de aprovação já grava a máscara aprovada
  como artefato próprio (`mask_organ_approved.nii.gz`) com hash. Quando o
  ajuste global entrar, ele apenas produz uma nova máscara candidata antes da
  aprovação — o contrato e o gate não mudam.

Ajuste global previsto para depois (dilatar/erodir, remover ilha, preencher
cavidade): operações que já existem como funções puras em `stage5_refine`
(`_refine_mask`, `_isolar_orgao_para_visualizacao`), a serem expostas na UI.

### 4.2 Seleção de modalidade pelo profissional

O médico escolhe RM ou TC na entrada do exame.

- **RM: funciona hoje**, com toda a validação medida acima.
- **TC: a escolha aparece na interface, mas ainda não está validada.** Enquanto
  não passar pelos mesmos gates, a opção deve ficar visivelmente marcada como
  indisponível — nunca aceitar um exame de TC e produzir um número não
  validado.

Preparação da modularidade (o trabalho desta fase):

- Extrair a modalidade do perfil para um eixo próprio: `profiles/figado_mr.yaml`
  e `profiles/figado_ct.yaml`, mesmo motor.
- `total_mr` → `total` e `liver_segments_mr` → `liver_segments` já existem no
  TotalSegmentator instalado para TC.
- O gate de modalidade em `stage1_ingest` já aborta corretamente por
  `Modality` DICOM — só precisa ser parametrizado pelo perfil escolhido.

Adicionar TC de verdade depois = rodar os mesmos benchmarks (CHAOS/LiverHccSeg
equivalentes em TC) e passar os mesmos gates. **Não é troca de configuração,
é validação.**

### 4.3 Nó DICOM (recepção do PACS)

Hoje só existe upload de pasta. Falta o produto ser um destino DICOM.

- Serviço C-STORE SCP (AE Title, porta, lista de chamadores autorizados).
- Agrupamento por `StudyInstanceUID` e disparo do processamento ao fechar a
  série.
- Isolamento: o receptor grava numa área de quarentena; o pipeline só lê de lá
  depois da validação de integridade.
- Biblioteca: `pynetdicom` (mesma família do `pydicom` já em uso).

Fora de escopo agora: devolver resultado ao PACS (DICOM SR / captura
secundária). Fica registrado como evolução natural.

### 4.4 Laudo de medidas

Saída que o médico leva para o prontuário.

- PDF/A com: identificação do exame, volumes (fígado, Couinaud I–VIII, vasos,
  vesícula), nota técnica, capturas 3-D, e **declaração explícita de que a
  medida é da máscara aprovada por revisão humana**, com quem aprovou.
- Exportação JSON/CSV já existe em `dtwin/volumetry.py`.

### 4.5 Identidade e separação do produto

- Renomear a superfície: endpoints, título, marca do visualizador.
- **Decisão a tomar:** repositório separado ou o mesmo repositório com um
  pacote `volyrcs/` reaproveitando `dtwin/` como biblioteca. Recomendo o
  segundo — evita duplicar o motor e mantém uma fonte única de verdade para as
  correções de segmentação. Um fork divergiria em semanas.

### 4.6 Substituir as marcações de pesquisa

Existem **1.097 ocorrências** de `research_only` / `clinical_use_allowed=False`
no código. Elas não devem ser simplesmente apagadas: precisam ser **trocadas**
por um contrato coerente com o novo posicionamento —
`measurement_under_human_review`, com a aprovação registrada e a ausência de
alegação diagnóstica explícita.

Apagar sem substituir seria remover a proteção sem colocar nada no lugar.

---

## 5. Arquitetura

### 5.1 Fluxo

```text
┌─ ENTRADA ────────────────────────────────────────────┐
│  upload de pasta  │  nó DICOM C-STORE (a construir)  │
└──────────────────────┬───────────────────────────────┘
                       ▼
        stage1_ingest  (gate de modalidade pelo perfil)
        stage2_normalize
                       ▼
┌─ SEGMENTAÇÃO ────────────────────────────────────────┐
│  stage3_segment_organ  (TotalSegmentator)            │
│  segmentation_shadow   (MRSegmentator, se disponível)│
│  união multifásica     (quando há múltiplas fases)   │
│  stage5_refine         (refino + guarda)             │
│  anatomia: Couinaud I–VIII, vasos, vesícula          │
│  candidate_region      (marcação visual de lesão)    │
└──────────────────────┬───────────────────────────────┘
                       ▼
        stage6_mesh  (malhas 3-D)
                       ▼
┌─ REVISÃO HUMANA ─────────────────── A CONSTRUIR ─────┐
│  cortes 2-D + 3-D  →  Aprovar / Rejeitar             │
│  grava mask_organ_approved.nii.gz + recibo assinado  │
└──────────────────────┬───────────────────────────────┘
                       ▼  (gate: sem aprovação, para aqui)
        volumetry  (mede a máscara APROVADA)
        stage7_export_publish
                       ▼
        visualizador 3-D  +  laudo  +  JSON/CSV
```

### 5.2 A mudança central em relação ao OREN

No OREN, a volumetria mede a máscara automática. No Volyrcs, **a volumetria
mede a máscara aprovada**. É uma linha de dependência nova e é o que sustenta
o posicionamento regulatório inteiro.

```python
# contrato do Volyrcs
if not aprovacao_valida(case):
    raise PipelineError("Volumetria exige segmentação aprovada por revisão humana.")
```

### 5.3 Modularidade por órgão e modalidade

Já suportado pela fundação; o produto passa a exercitá-la em dois eixos:

```text
profiles/
  figado_mr.yaml     ← validado, disponível
  figado_ct.yaml     ← estrutura pronta, aguarda validação
  rim_mr.yaml        ← futuro: só um arquivo novo
```

O motor (`dtwin/core.py`, `stages.py`, `volumetry.py`) não muda ao adicionar
órgão ou modalidade. O que muda é o perfil — e a obrigação de passar pelos
mesmos gates antes de liberar.

### 5.4 Contratos protegidos

Herdados e mantidos:

- Geometria física validada antes de qualquer malha ou medida.
- Hash SHA-256 de toda máscara publicada.
- Falha nunca fabrica dado: aborta com erro explícito (regra de ouro do
  `dtwin/core.py`).
- Idempotência: reexecução limpa artefatos obsoletos.
- Verificador independente da volumetria (`tools/verify_volumetry.py`).

Novo:

- Recibo de aprovação assinado, ligando máscara → revisor → medida.

---

## 6. Plano de fases

| Fase | Entrega | Depende de |
|---|---|---|
| **0** | Separação do produto: pacote `volyrcs/`, remoção da classificação, identidade | — |
| **1** | Aprovação da segmentação + gate na volumetria | 0 |
| **2** | Laudo de medidas (PDF/A) com registro de aprovação | 1 |
| **3** | Perfis por modalidade + seleção RM/TC na interface (TC marcada como indisponível) | 0 |
| **4** | Nó DICOM C-STORE | 0 |
| **5** | Ajuste global da máscara (dilatar/erodir/ilha/cavidade) | 1 |
| **6** | Validação de TC com os mesmos gates → liberar a opção | 3 |

As Fases 0–2 entregam um produto coerente e usável. As Fases 3–6 ampliam
alcance.

---

## 7. Verificação

Cada fase fecha com:

- **Testes automatizados** — a suíte atual tem **1.607 testes passando**; o
  Volyrcs herda os relevantes e adiciona os do gate de aprovação.
- **Gates pré-especificados**, escritos antes de medir. Disciplina já
  estabelecida no projeto, incluindo os resultados negativos documentados
  (docs/190, docs/193) que foram respeitados em vez de arredondados.
- **Smoke real ponta a ponta**: DICOM de verdade entrando, laudo saindo,
  verificado no navegador.
- **Verificador independente** revalidando o manifesto de volumetria.

---

## 8. Riscos declarados

| Risco | Situação |
|---|---|
| Sub-segmentação residual | Medida e conhecida (docs/190). O MRSegmentator melhora, mas não elimina. A revisão humana é a mitigação real. |
| Fragmentação da veia porta | Medida (fração mediana 0,83). Fechamento morfológico foi testado e **reprovado** no gate. Continua aberto. |
| Couinaud incompleto | O gate reprova corretamente quando os 8 segmentos não cobrem o fígado. Publica nada em vez de publicar errado. |
| TC não validada | Por isso a opção nasce marcada como indisponível. |
| Regulatório | O posicionamento de ferramenta sob revisão humana reduz o risco, mas **não é parecer jurídico**. Antes de uso clínico real, uma avaliação regulatória formal (ANVISA RDC 751/2022) é necessária. |

---

## 9. Decisões registradas

| Tema | Decisão |
|---|---|
| Nome | **Volyrcs** |
| Modalidade | RM agora (validada); TC modularizada, liberada só após validação |
| Regulatório | Ferramenta de medição sob revisão humana |
| Lesão | Marcação visual, sem alegação diagnóstica |
| Entrada | Pasta manual + nó DICOM do PACS |
| Saída ao PACS | Fora de escopo nesta versão |
| Revisão | Aprovar/rejeitar agora; ajuste global preparado para depois |
| Escopo anatômico | Fígado, Couinaud I–VIII, vasos, vesícula, região candidata |

---

## 10. Ponto de partida

O trabalho começa pela **Fase 0** (separação) e **Fase 1** (aprovação), porque
a Fase 1 é o que transforma um pipeline de pesquisa em uma ferramenta clínica
defensável. Todo o resto já existe e funciona.
