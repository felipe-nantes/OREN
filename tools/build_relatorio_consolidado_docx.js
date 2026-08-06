const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageBreak, TableOfContents, LevelFormat, PageNumber, Footer, Header,
  convertInchesToTwip,
} = require("docx");
const fs = require("fs");

const W = 9026;                       // largura util A4 com margens de 1 polegada
const ACCENT = "1F3864";
const GREY = "F2F2F2";

// ---------- helpers ----------
const P = (text, opts = {}) => new Paragraph({
  spacing: { after: opts.after ?? 120, line: opts.line ?? 276 },
  alignment: opts.align ?? AlignmentType.JUSTIFIED,
  indent: opts.indent,
  children: [new TextRun({ text, size: opts.size ?? 21, italics: opts.i, bold: opts.b, color: opts.color })],
});

// paragrafo com trechos em negrito: rich([["texto ",0],["negrito",1]])
const rich = (parts, opts = {}) => new Paragraph({
  spacing: { after: opts.after ?? 120, line: 276 },
  alignment: opts.align ?? AlignmentType.JUSTIFIED,
  children: parts.map(([t, b]) => new TextRun({ text: t, bold: !!b, size: opts.size ?? 21, italics: opts.i })),
});

const H1 = (t) => new Paragraph({
  heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 180 },
  children: [new TextRun({ text: t, bold: true, size: 30, color: ACCENT })],
});
const H2 = (t) => new Paragraph({
  heading: HeadingLevel.HEADING_2, spacing: { before: 280, after: 140 },
  children: [new TextRun({ text: t, bold: true, size: 25, color: ACCENT })],
});
const H3 = (t) => new Paragraph({
  heading: HeadingLevel.HEADING_3, spacing: { before: 220, after: 110 },
  children: [new TextRun({ text: t, bold: true, size: 22, color: "2E5395" })],
});

const bullets = (items) => items.map((t) => new Paragraph({
  numbering: { reference: "viñeta", level: 0 },
  spacing: { after: 60, line: 264 },
  children: [new TextRun({ text: t, size: 21 })],
}));

const numbered = (items) => items.map((t) => new Paragraph({
  numbering: { reference: "numerada", level: 0 },
  spacing: { after: 60, line: 264 },
  children: [new TextRun({ text: t, size: 21 })],
}));

const mono = (text) => new Paragraph({
  spacing: { before: 80, after: 140 },
  shading: { type: ShadingType.CLEAR, fill: GREY },
  children: text.split("\n").map((l, i) => new TextRun({
    text: l, font: "Consolas", size: 17, break: i === 0 ? 0 : 1,
  })),
});

const quote = (text) => new Paragraph({
  spacing: { before: 140, after: 160 },
  indent: { left: 480, right: 240 },
  border: { left: { style: BorderStyle.SINGLE, size: 18, color: ACCENT, space: 12 } },
  children: [new TextRun({ text, size: 21, italics: true })],
});

// cols: array de larguras somando W. rows: array de arrays de string.
function table(cols, header, rows, aligns) {
  const cell = (t, w, opts = {}) => new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: opts.head ? { type: ShadingType.CLEAR, fill: ACCENT } : (opts.zebra ? { type: ShadingType.CLEAR, fill: GREY } : undefined),
    margins: { top: 60, bottom: 60, left: 90, right: 90 },
    children: [new Paragraph({
      alignment: opts.align ?? AlignmentType.LEFT,
      spacing: { after: 0, line: 240 },
      children: [new TextRun({ text: t, bold: opts.head || opts.b, size: 18, color: opts.head ? "FFFFFF" : undefined })],
    })],
  });
  const al = (i) => (aligns && aligns[i] === "r") ? AlignmentType.RIGHT : (aligns && aligns[i] === "c") ? AlignmentType.CENTER : AlignmentType.LEFT;
  return new Table({
    columnWidths: cols,
    width: { size: W, type: WidthType.DXA },
    rows: [
      new TableRow({
        tableHeader: true,
        children: header.map((h, i) => cell(h, cols[i], { head: true, align: al(i) })),
      }),
      ...rows.map((r, ri) => new TableRow({
        children: r.map((c, i) => cell(String(c), cols[i], {
          zebra: ri % 2 === 1,
          align: al(i),
          b: /^\*\*/.test(String(c)),
        })),
      })),
    ],
  });
}
// remove marcadores ** usados para negrito em celulas
const T = (cols, header, rows, aligns) =>
  table(cols, header, rows.map((r) => r.map((c) => String(c).replace(/\*\*/g, ""))), aligns);

const SPACER = () => new Paragraph({ spacing: { after: 160 }, children: [] });
const BREAK = () => new Paragraph({ children: [new PageBreak()] });

// ---------- conteudo ----------
const doc = new Document({
  creator: "Projeto ARGOS/OREN",
  title: "ARGOS/OREN — Relatório técnico-científico consolidado",
  description: "Histórico completo de desenvolvimento, experimentos, resultados e decisões",
  numbering: {
    config: [
      { reference: "viñeta", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 240 } } } }] },
      { reference: "numerada", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 240 } } } }] },
    ],
  },
  styles: {
    default: { document: { run: { font: "Calibri", size: 21 } } },
  },
  sections: [{
    properties: { page: { margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "ARGOS/OREN — documento de pesquisa · uso clínico não autorizado · página ", size: 16, color: "808080" }),
            new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "808080" }),
          ],
        })],
      }),
    },
    children: [

// ============ CAPA ============
new Paragraph({ spacing: { before: 1600, after: 120 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "ARGOS / OREN", bold: true, size: 56, color: ACCENT })] }),
new Paragraph({ spacing: { after: 400 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Relatório técnico-científico consolidado", size: 28, color: "555555" })] }),
new Paragraph({ spacing: { after: 100 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Triagem assistida de lesões focais hepáticas em ressonância magnética", bold: true, size: 24 })] }),
new Paragraph({ spacing: { after: 600 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Histórico integral de experimentos, resultados, decisões e justificativas", size: 22, italics: true, color: "555555" })] }),

new Paragraph({ spacing: { after: 60 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Universidade Estadual de Maringá · GETS · Hospital Universitário", size: 20 })] }),
new Paragraph({ spacing: { after: 60 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "5 de agosto de 2026", size: 20 })] }),
new Paragraph({ spacing: { after: 800 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Base documental: 185 documentos técnicos versionados · 1.450 testes automatizados", size: 19, color: "666666" })] }),

new Paragraph({
  spacing: { before: 200, after: 100 },
  shading: { type: ShadingType.CLEAR, fill: "FFF2CC" },
  border: { top: { style: BorderStyle.SINGLE, size: 8, color: "BF8F00" }, bottom: { style: BorderStyle.SINGLE, size: 8, color: "BF8F00" },
            left: { style: BorderStyle.SINGLE, size: 8, color: "BF8F00" }, right: { style: BorderStyle.SINGLE, size: 8, color: "BF8F00" } },
  children: [new TextRun({ text: "  AVISO — Este documento descreve pesquisa. Nenhum resultado aqui constitui diagnóstico, laudo médico ou desempenho clínico comprovado. Todos os artefatos do sistema carregam clinical_use_allowed = false e exigem revisão humana obrigatória.  ", bold: true, size: 19, color: "7F6000" })],
}),

BREAK(),

// ============ SUMARIO ============
H1("Sumário"),
new TableOfContents("Sumário", { hyperlinks: true, headingStyleRange: "1-3" }),
BREAK(),

// ============ RESUMO ============
H1("Resumo"),

rich([
  ["O ARGOS (atualmente também designado OREN) é um sistema de triagem assistida por computador para detecção de lesões focais hepáticas em exames de ressonância magnética multifásica, desenvolvido inteiramente sobre datasets públicos de pesquisa e executado em hardware de consumo (NVIDIA RTX 4060 Laptop, 8 GB de VRAM). O sistema recebe uma exportação DICOM bruta, resolve automaticamente as fases dinâmicas, segmenta o fígado, gera painéis enriquecidos, classifica o exame como positivo ou negativo para a patologia-alvo (carcinoma hepatocelular), identifica a variação mais provável e produz um modelo tridimensional auditável — em aproximadamente 115 a 130 segundos por exame."],
], { after: 160 }),

rich([
  ["A meta técnica pré-especificada foi mantida imutável durante todo o desenvolvimento: "],
  ["sensibilidade ≥ 75%, especificidade ≥ 75%, tempo end-to-end ≤ 180 segundos, com falhas técnicas e resultados inconclusivos contabilizados como erro", 1],
  [". Ao longo de 185 documentos técnicos e aproximadamente vinte e cinco configurações distintas testadas, "],
  ["apenas uma configuração atingiu a meta binária no agregado", 1],
  [": o classificador visual supervisionado sobre embeddings congelados do MedSigLIP-448, que obteve "],
  ["75,91% de sensibilidade e 76,11% de especificidade", 1],
  [" (AUC 0,853) em validação cruzada aninhada sobre 467 exames de três coortes."],
], { after: 160 }),

rich([
  ["O segundo objetivo — identificar qual das quatro variações (carcinoma hepatocelular, hiperplasia nodular focal, hemangioma e cisto hepático) está presente com 75% de acurácia — "],
  ["não foi atingido, e demonstrou-se aritmeticamente inalcançável com os dados atuais", 1],
  [". A melhor medição honesta é de 64,81% de acurácia balanceada."],
], { after: 160 }),

rich([
  ["O achado científico mais consequente do projeto não é uma métrica, mas um diagnóstico de causa: "],
  ["o gargalo dominante não é discriminação biológica entre lesões, e sim heterogeneidade de domínio entre instituições", 1],
  [". Uma ablação controlada demonstrou que aproximadamente 85% do ganho da melhor configuração vem de separação de domínio e apenas 15% de granularidade de rótulo clínico. Sete tentativas independentes de contornar esse limite — por geometria, supervisão aprendida, aprendizado de múltiplas instâncias, novas modalidades, cobertura axial integral, localização espacial e fusão tolerante a sinal ausente — falharam de forma consistente contra o mesmo obstáculo."],
], { after: 160 }),

rich([
  ["Conclui-se que o avanço material do projeto depende de uma coorte real adicional, de instituição distinta e com rótulo fino de subtipo, e não de nova engenharia de atributos, arquitetura ou limiar sobre os dados atualmente disponíveis."],
]),

BREAK(),

// ============ 1. INTRODUCAO ============
H1("1. Introdução e objetivos"),

H2("1.1 Contexto clínico"),
P("O carcinoma hepatocelular é a neoplasia primária mais frequente do fígado e seu prognóstico depende fortemente da detecção precoce. A ressonância magnética multifásica com contraste é uma das modalidades de referência para caracterização de lesões focais hepáticas, mas a interpretação exige distinguir a patologia-alvo de um conjunto de achados benignos que a mimetizam — hiperplasia nodular focal, hemangioma, cisto hepático, além de variantes vasculares, pseudolesões e artefatos."),
P("Essa distinção é precisamente o problema difícil. Um sistema que apenas detecta \"alguma alteração\" produz sensibilidade alta e especificidade inaceitável, porque o fígado normal contém estruturas vasculares e variações de realce que se assemelham a lesões em fases isoladas. O projeto ARGOS foi organizado desde o início em torno dessa dificuldade."),

H2("1.2 Metas pré-especificadas"),
P("A meta técnica foi fixada no início do desenvolvimento e nunca foi alterada em função de resultados observados — princípio metodológico central deste projeto:"),
mono("sensibilidade      >= 75%\nespecificidade     >= 75%\ntempo end-to-end   <= 180 segundos por exame\nfalhas técnicas e INCONCLUSIVA contam como ERRO\nzero vazamento de ground truth"),
P("Posteriormente foi acrescentada uma segunda meta, proposta como missão de orientação: identificar corretamente qual das quatro variações está presente, em pelo menos 75% dos casos."),

H2("1.3 Princípios metodológicos adotados"),
P("Todo o histórico do projeto está subordinado a um conjunto de regras que valem mais que qualquer resultado individual. Elas são a razão pela qual este relatório contém muito mais rejeições do que aprovações:"),
...bullets([
  "Divisão sempre por paciente, nunca por painel, corte ou candidato — impedindo que imagens do mesmo paciente apareçam simultaneamente em treino e teste.",
  "Seleção de hiperparâmetros, agregação e limiar exclusivamente dentro dos folds internos (nested cross-validation). O limiar jamais é escolhido sobre o conjunto no qual a métrica é reportada.",
  "Gates numéricos pré-especificados por escrito, antes de qualquer execução. Um gate perdido por pouco continua perdido — não se afrouxa critério após ver o número.",
  "Falhas técnicas e resultados inconclusivos contam como erro. Não é permitido remover casos difíceis da métrica sob o argumento de encaminhamento à revisão humana.",
  "Execução label-blind: o gerador de imagens, o encoder e a inferência nunca acessam rótulos ou máscaras de lesão. Máscaras públicas de lesão podem supervisionar treino, jamais entrar como entrada na inferência.",
  "Congelamento por assinatura criptográfica: protocolos, splits, predições e avaliações são assinados em SHA-256, tornando impossível alterar silenciosamente um resultado já registrado.",
  "Holdout aberto uma única vez. Depois de consumido, um conjunto deixa permanentemente de ser validação externa e passa a ser desenvolvimento retrospectivo.",
]),

quote("Registrar como atingido o teto observado das abordagens atuais sem treino. — docs/46, ao encerrar a linha de fusão v11 que ficou a um único verdadeiro positivo da meta."),

BREAK(),

// ============ 2. MATERIAIS E METODOS ============
H1("2. Materiais e métodos"),

H2("2.1 Coortes e procedência dos dados"),
P("Nenhum paciente foi recrutado e nenhuma imagem foi obtida diretamente de serviço clínico. Todo o dado utilizado provém de datasets públicos de pesquisa já publicados e liberados por seus autores originais, aos quais cabe a responsabilidade pela aprovação ética e pelo consentimento dos sujeitos."),
SPACER(),
T([2100, 2000, 2200, 2726],
  ["Coorte", "Fonte", "Composição", "Papel no projeto"],
  [
    ["OpenSwissHCC", "Zenodo (MD5 verificado)", "132 sujeitos: 63 HCC+, 69 HCC−; DCE-MRI multifásica, T2, DWI, ADC", "Coorte principal de desenvolvimento até a Etapa C; holdout de 44 casos consumido em docs/91"],
    ["LLD-MMRI", "Hugging Face (wanglab/LLD-MMRI-MedSAM2)", "335 exames com rótulo fino: 157 HCC, 79 hemangiomas, 53 cistos, 46 FNH", "Única coorte com subtipo clínico documentado; base de toda a linha de identificação de variação"],
    ["LiverHccSeg", "Zenodo 8179129, v1.1, CC BY 4.0", "Braço positivo externo", "Validação externa de sensibilidade (docs/84)"],
    ["CHAOS MRI", "Zenodo 3431873", "20 casos com máscara hepática anotada por humano", "Validação externa de especificidade (docs/87) e referência humana de segmentação (docs/176)"],
    ["TCGA-LIHC", "TCIA / GDC (NIH)", "11–12 casos positivos", "Estresse inicial (docs/21) e primeiro sinal externo real do classificador congelado (docs/168)"],
  ],
  ["l", "l", "l", "l"]),
SPACER(),
P("A composição por múltiplas fontes foi uma decisão registrada em docs/80, que também nomeia a alternativa considerada e descartada (Duke Liver Dataset, por não resolver a lacuna de ressonância multifásica). Essa mesma composição é, como se demonstrará, a causa raiz do confundimento de domínio que domina o teto de desempenho do sistema."),

H2("2.2 Restrições de hardware"),
P("Todo o desenvolvimento ocorreu em uma única estação: NVIDIA RTX 4060 Laptop com 8 GB de VRAM, aproximadamente 32 GB de RAM, Windows 11. Essa restrição não é um detalhe operacional — ela determinou decisões arquiteturais fundamentais:"),
...bullets([
  "Treinamento completo do MedGemma foi descartado desde o planejamento.",
  "QLoRA do MedGemma foi explicitamente adiada para hardware de pelo menos 16 GB.",
  "MedSigLIP e MedGemma nunca podem ocupar a GPU simultaneamente — o encoder é descarregado antes do gerador ser carregado.",
  "A primeira geração de modelos usa obrigatoriamente embeddings congelados e classificadores leves.",
  "Todo processamento longo exige checkpoint atômico e retomada após interrupção.",
]),

H2("2.3 Desenho estatístico"),
P("A avaliação primária de todos os candidatos supervisionados é validação cruzada aninhada agrupada por paciente, com 5 folds externos e 4 internos. Os folds foram congelados e assinados antes de qualquer extração supervisionada. Cada caso recebe exatamente uma predição out-of-fold, produzida por um modelo que nunca viu aquele paciente."),
P("As métricas são reportadas com intervalo de confiança de 95% de Wilson e bootstrap por paciente com 2.000 reamostragens. Complementarmente foram executadas repetições de validação cruzada estratificada com sementes congeladas (tipicamente 50 repetições) e leave-one-dataset-out, este último sendo o teste que revelou a instabilidade decisiva do projeto."),

BREAK(),

// ============ 3. MEDSIGLIP ============
H1("3. Como o MedSigLIP foi utilizado e treinado"),

P("Esta seção responde em detalhe à questão de como o componente central do sistema foi construído, porque ela é frequentemente mal compreendida: o MedSigLIP, na configuração que está em produção, não foi treinado — ele foi utilizado como extrator de características congelado, e o que foi treinado é uma cabeça de classificação linear sobre suas saídas."),

H2("3.1 Por que MedSigLIP, e não outro encoder"),
P("A escolha está registrada em docs/20, no início do projeto. O MedGemma 1.5 4B generativo, testado exaustivamente, não separou o par positivo/negativo em nenhum dos controles aplicados — variação de prompt, formato de resposta, realce por spotlight, cortes adjacentes. A documentação oficial do Google recomenda o MedSigLIP para classificação visual e recuperação sem geração de texto."),
rich([
  ["É necessário registrar honestamente o limite dessa justificativa: "],
  ["nunca foi realizada uma comparação sistemática contra outros encoders candidatos", 1],
  [" (BiomedCLIP, DINOv2, ResNet médico ou equivalentes). A razão documentada é o abandono da abordagem generativa, não a vitória do MedSigLIP em uma disputa controlada."],
]),

H2("3.2 Contrato do extrator congelado"),
P("O extrator de embeddings foi implementado na Fase 4 do plano (docs/120, docs/121) com um contrato imutável, verificado por hash a cada execução:"),
mono("modelo:               google/medsiglip-448\nrevision:             9cea28a1a1195f665105faa6e8544c112fd960a4\nentrada:              448 x 448 RGB\npooling:              vision_pooler_output\ndimensão do vetor:    1152\nnormalização:         L2\nsaída:                float32\ninferência interna:   float16 / CUDA\nbatch inicial:        4\ndownloads:            desabilitados"),
P("O extrator recebe exclusivamente registros label-blind; valida o hash de cada imagem e a ausência de metadados PNG; grava um arquivo .npy por painel de forma atômica; sincroniza o checkpoint a cada lote; retoma execuções interrompidas; rejeita NaN, infinitos, dimensão ou norma divergentes; registra revisão e hashes do snapshot do modelo; descarrega o modelo e libera o cache CUDA ao terminar; e nunca abre rótulos ou máscaras. O pico de VRAM foi mantido abaixo de 7,5 GB."),

H2("3.3 A representação de entrada"),
P("O que o encoder recebe não é um corte isolado nem o volume inteiro, mas um painel enriquecido pelo fígado (liver-enriched), construído deterministicamente a partir da segmentação automática:"),
...numbered([
  "A segmentação hepática automática (TotalSegmentator, tarefa total_mr) define a região de interesse.",
  "As três fases dinâmicas — arterial, portal/venosa e tardia — são harmonizadas na grade da fase venosa por registro, com gate anatômico exigindo Dice ≥ 0,80 entre as fases registradas.",
  "As três fases são compostas nos canais R, G e B de uma imagem RGB. Isso é fisicamente significativo: um voxel que realça na arterial e sofre washout na tardia produz uma assinatura de cor distinta de um vaso, que permanece brilhante em todas as fases.",
  "São gerados 2 ou 3 painéis por exame, com janelamento calculado sobre o fígado inteiro.",
  "Nenhum contorno de lesão, texto clínico, marcação ou PHI é desenhado na imagem enviada ao modelo.",
]),

H2("3.4 O que efetivamente foi treinado — a cabeça de classificação"),
P("Sobre os embeddings congelados de 1.152 dimensões foi treinada uma regressão logística com regularização L2 e balanceamento de classes. Os detalhes do procedimento:"),
...bullets([
  "Padronização (StandardScaler) ajustada exclusivamente sobre os painéis dos folds de treino.",
  "Grade de regularização C ∈ {0,01; 0,1; 1,0}.",
  "Agregação por exame testada entre mean, max e top2_mean — porque um exame produz múltiplos painéis e é preciso uma regra para consolidá-los em uma decisão.",
  "Modelo, agregação e limiar selecionados exclusivamente por validação cruzada interna.",
  "Predição do paciente externo produzida sem qualquer uso do seu rótulo.",
  "Um único score out-of-fold por caso; o arquivo de predições não contém ground truth.",
  "Falhas técnicas contabilizadas como falso negativo ou falso positivo conforme o rótulo, e apenas no avaliador.",
]),
P("O tempo total de treinamento e seleção dessa cabeça é de aproximadamente 60 segundos — consequência direta de o encoder estar congelado. Esse é o ponto que torna a arquitetura viável em 8 GB de VRAM."),

H2("3.5 Tentativas de treinar o encoder — todas rejeitadas"),
P("A Fase 13 do plano previa fine-tuning parcial caso os embeddings congelados demonstrassem sinal real mas insuficiente. Essa condição foi atingida, e três estágios foram executados sobre os mesmos 467 casos e os mesmos folds externos."),
SPACER(),
T([2500, 1500, 1500, 1200, 2326],
  ["Estágio", "Sensib.", "Especif.", "AUC", "Decisão e motivo"],
  [
    ["Cabeça MLP não linear, encoder congelado", "70,45%", "69,64%", "0,802", "REJEITADO — não superou a cabeça linear da Fase 5"],
    ["Último bloco visual liberado integralmente", "57,27%", "55,47%", "0,590", "REJEITADO — degradou fortemente o sinal pré-treinado"],
    ["LoRA rank 4 nas projeções Q/V do último bloco", "75,00%", "70,45%", "0,819", "NÃO PROMOVIDO — recuperou sensibilidade e AUC, mas perdeu especificidade"],
    ["Referência: cabeça linear congelada (Fase 5)", "72,27%", "73,28%", "0,801", "Mantida como candidata de referência"],
  ],
  ["l", "r", "r", "r", "l"]),
SPACER(),
rich([
  ["A conclusão metodológica dessa fase é relevante e contraintuitiva: "],
  ["ajustar o encoder degradou o resultado", 1],
  [". O estágio 2, que liberou o último bloco visual completo, produziu AUC de 0,590 — praticamente ruído — a partir de um modelo que congelado entregava 0,801. O LoRA, muito mais conservador, recuperou o patamar mas não superou o congelado nos dois eixos simultaneamente. Isso indica que o conhecimento médico pré-treinado do MedSigLIP é frágil ao ajuste com o volume de dados disponível, e que o caminho de ganho não passa por adaptar o encoder."],
]),

H2("3.6 A supervisão multiclasse — o modelo em produção"),
P("A configuração finalmente promovida a bundle de produção, denominada Etapa C, difere da Fase 5 em um único aspecto: a granularidade do rótulo usado no ajuste. Em vez de treinar um classificador binário, treina-se um classificador multiclasse de seis classes, e a decisão binária é derivada da massa de probabilidade atribuída às classes positivas."),
mono("classes:      fnh | hcc | hemangioma | hepatic_cyst | negative_unspecified | positive_unspecified\npositivo =    {hcc, positive_unspecified}\nagregação:    top2_mean\nC:            0.01\nlimiar:       0.4748805111520148\ncasos treino: 467\nsplits:       41c15cc14b89ee80... (assinatura congelada)"),
P("As classes unspecified existem porque os positivos do OpenSwissHCC não estão documentados como especificamente HCC na fonte protegida. Atribuir-lhes um subtipo seria fabricar informação; recebem, portanto, uma classe explicitamente não especificada."),
P("O bundle de produção é assinado: o carregador verifica a assinatura do manifesto e o hash do modelo antes de qualquer inferência, e falha fechado em caso de divergência."),

quote("Distinção metodológica crítica: a métrica de seleção por validação cruzada do bundle não é a estimativa de generalização. A generalização honesta do bundle continua sendo o nested-OOF da Etapa C. — docs/123"),

BREAK(),

// ============ 4. RESULTADOS ============
H1("4. Resultados — histórico integral por era"),

P("Esta seção percorre cronologicamente todas as configurações testadas. Para cada uma registra-se o que foi tentado, o resultado quantitativo obtido e o motivo documentado da aprovação ou rejeição. A densidade de rejeições é intencional e metodologicamente saudável."),

// --- ERA 1 ---
H2("4.1 Era 1 — MedGemma generativo isolado (docs 17 a 23)"),
P("A hipótese inicial era que um modelo de linguagem-visão médico generativo poderia classificar diretamente o exame a partir de um painel de imagem e um prompt clínico. Foram testadas oito variações."),
SPACER(),
T([3000, 3200, 2826],
  ["Configuração testada", "Resultado", "Decisão e motivo"],
  [
    ["JSON compacto livre", "Não fechava JSON válido ou copiava placeholders", "REJEITADO — falha de contrato, não de clínica"],
    ["Pontuação fechada A/B/C com quadrado latino", "Probabilidades quase uniformes (0,344 / 0,330 / 0,325); especificidade 0/2", "REJEITADO — escolher limiar aqui esconderia o viés"],
    ["Rótulo JSON predefinido com prefixo causal", "Tempo resolvido; dois negativos preparados classificados POSITIVA", "REJEITADO — especificidade não atingida"],
    ["Recorte hepático sem contorno amarelo", "Ainda POSITIVA em negativo", "REJEITADO — o contorno não era a causa do falso positivo"],
    ["Piloto balanceado, 6 casos", "Sensibilidade 100%, especificidade 0%, acurácia 50%", "REJEITADO — todos os 6 classificados POSITIVA; sem discriminação útil"],
    ["Spotlight hepático (atenuação fora do fígado)", "Positivo e negativo ambos POSITIVA", "REJEITADO — hipótese não confirmada"],
    ["Resposta sem JSON (LESION / NO_LESION)", "Ambos LESION", "REJEITADO — o colapso não era efeito do schema"],
    ["Raciocínio curto, 256 tokens", "Ambos FINAL=LESION", "REJEITADO"],
    ["Blocos axiais adjacentes (todos os cortes)", "Todos os 8 painéis LESION", "REJEITADO — cobertura não recupera especificidade"],
    ["Estresse TCGA-LIHC, 12 positivos", "12/12 POSITIVA, tempo médio 35,3 s", "Sensibilidade 100% descartada como evidência — reforça o colapso"],
  ],
  ["l", "l", "l"]),
SPACER(),
rich([
  ["O padrão é inequívoco: o modelo generativo colapsava em POSITIVA independentemente do conteúdo. Registre-se a honestidade metodológica de docs/21, que "],
  ["recusou reportar 100% de sensibilidade como resultado", 1],
  [", identificando corretamente que se tratava de saturação e não de detecção."],
]),
P("Um achado adicional dessa era é diagnóstico e permanece válido: a auditoria de dataset em docs/17 revelou confundimento de protocolo severo — positivos majoritariamente em T1 pós-contraste e negativos em T1 in/out-phase e T2. Um classificador poderia aprender protocolo em vez de patologia. Esse achado antecipa, em forma embrionária, o problema de domínio que dominaria todo o projeto."),

// --- ERA 2 ---
H2("4.2 Era 2 — OpenSwissHCC, cobertura e representação (docs 24 a 50)"),
P("Estabelecida a coorte OpenSwissHCC com split congelado por inspeção real dos arquivos (desenvolvimento: sujeitos 001–044 e 089–132, 88 casos; holdout lacrado: sujeitos 045–088, 44 casos), iniciou-se uma sequência de tentativas de aumentar cobertura e resolução da representação visual."),
SPACER(),
T([1400, 3400, 1900, 2326],
  ["Versão", "O que foi tentado", "Resultado (LOOCV)", "Decisão"],
  [
    ["v3", "prefilled_label sobre 88 painéis uniform_9", "100% / 0%", "REJEITADO — sem discriminação"],
    ["v4", "Escolha balanceada A/B/C, quadrado latino", "23,1% / 83,7%", "REJEITADO"],
    ["v5", "MedSigLIP zero-shot como segundo leitor", "61,5% / 61,2%", "REJEITADO isoladamente"],
    ["v4+v5", "Fusão determinística exploratória", "74,4% / 75,5%; apenas 7/50 repetições estáveis", "REJEITADO — instabilidade estatística"],
    ["v6", "MedSigLIP + fusão sobre volumétrico", "59,0% / 59,2%; 0/50 estáveis", "REJEITADO"],
    ["v7", "Frases clínicas pairwise por painel", "56,4% / 57,1%; 0/50", "REJEITADO"],
    ["v8", "Um corte axial por imagem", "40% / 100% (piloto 10)", "REJEITADO — perdeu 3 de 5 positivos"],
    ["v9", "Multissequência 2×2: T1 venoso, T2, DWI TRACE, ADC", "53,85% / 60,42%; AUC 0,565", "REJEITADO"],
    ["v10", "Localizador 3D como feature única", "53,85% / 54,17%", "REJEITADO — piloto de 10 casos não reproduziu"],
    ["v11", "Fusão MedGemma 0,40 + MedSigLIP 0,40 + localizador 0,20", "74,36% / 75,00%; 12/50 estáveis", "REJEITADO — melhor candidato da era"],
    ["v12/v13", "Entrada 3D nativa, até 50 cortes por caso", "51,28% / 31,25%", "REJEITADO — pior que v11"],
  ],
  ["l", "l", "l", "l"]),
SPACER(),

H3("Achados diagnósticos desta era"),
rich([["Diluição por escala de tile.", 1], [" A auditoria de docs/31 mediu que um painel de 1536×1152 é reduzido pelo processador para 896×896 com 256 tokens visuais, formando uma grade aproximada de 16×16. Com 12 células por painel, cada corte recebe cerca de 4×5 tokens. A conclusão registrada — "], ["cobertura volumétrica não equivale a resolução suficiente para lesões pequenas", 1], [" — encerrou a linha de aumentar cobertura."]]),
rich([["O teto da v11.", 1], [" A fusão v11 obteve 74,36% de sensibilidade em LOOCV, o que corresponde a 29 de 39 positivos. A meta exigia 30. O projeto ficou literalmente a "], ["um único verdadeiro positivo", 1], [" da meta, e a decisão registrada foi não reajustar pesos nem limiar sobre os mesmos rótulos — encerrando a linha em vez de forçar o número."]]),
rich([["Dimensionalidade não é o gargalo.", 1], [" A v13, com entrada 3D nativa de até 50 cortes, teve desempenho substancialmente pior que a v11, e passou com folga no gate temporal. Isso isolou a conclusão de que o obstáculo é discriminação, não capacidade de processamento."]]),

// --- ERA 3 ---
H2("4.3 Era 3 — Leitores focais e atlas (docs 51 a 79)"),
P("Nova família de tentativas, agora com foco em direcionar a atenção do modelo para regiões específicas em vez de apresentar o fígado inteiro."),
SPACER(),
T([1400, 3600, 1700, 2326],
  ["Versão", "Abordagem", "Resultado", "Decisão"],
  [
    ["v14/v15", "Score contínuo, pilotos de 32 cortes", "56,41% / 60,42%", "REJEITADO"],
    ["v16", "Leitor focal com stacks e gate humano", "48,72% / 43,75%; 0/50 estáveis", "REJEITADO"],
    ["v17", "Atlas axial com scorer 4B", "41,03% / 45,83%; AUC 0,443", "REJEITADO — AUC abaixo de 0,5"],
    ["v18", "Atlas em blocos", "41,03% / 41,67%; AUC 0,427", "REJEITADO"],
    ["v19/v20", "Atlas com RAG textual", "43,59% / 45,83%; AUC 0,414 — e 69,23% / 77,08% em variante", "REJEITADO no braço primário"],
  ],
  ["l", "l", "l", "l"]),
SPACER(),
rich([["Três versões consecutivas produziram AUC abaixo de 0,5. Isso é mais informativo do que um resultado ruim comum: significa que o score "], ["ordenava os casos pior que o acaso", 1], [". A conclusão documentada é que ajustar limiar não recuperaria a meta, e inverter o sinal pós-hoc seria uma nova hipótese ilegítima sobre os mesmos dados."]]),

// --- ERA 4 ---
H2("4.4 Era 4 — Validação externa pública e abertura do holdout (docs 80 a 91)"),
P("Esta era marca a primeira tentativa de validação fora da coorte de desenvolvimento, e contém o evento metodologicamente mais importante da história do projeto: o consumo do holdout."),
SPACER(),
T([2400, 2200, 2100, 2326],
  ["Braço", "Coorte", "Resultado", "Interpretação registrada"],
  [
    ["Positivo externo", "LiverHccSeg", "Sensibilidade 78,57%", "PASSA o gate nominal, mas limite inferior do IC não sustenta 75% populacional"],
    ["Negativo externo", "CHAOS MRI", "Especificidade 100,00%", "PASSA; galeria aprovada com ressalva de qualidade inferior"],
    ["Consolidação", "LiverHccSeg + CHAOS", "78,57% / 100,00%", "Qualificação simultânea NÃO DEMONSTRADA — braços de classe única, domínios distintos"],
    ["Holdout v21", "OpenSwissHCC, 44 casos", "83,33% / 35,00%; AUC 0,498", "REPROVADO — especificidade colapsa; holdout consumido permanentemente"],
  ],
  ["l", "l", "l", "l"]),
SPACER(),
rich([["A abertura do holdout produziu o resultado mais duro do projeto: sensibilidade de 83,33% acompanhada de especificidade de 35,00% e "], ["AUC de 0,4979 — indistinguível do acaso", 1], [". O sistema não estava ordenando os casos; estava chamando quase tudo de positivo. A consequência permanente é que os 44 casos deixaram de ser validação externa e passaram a desenvolvimento retrospectivo, restringindo severamente todas as avaliações posteriores."]]),

// --- ERA 5 ---
H2("4.5 Era 5 — Geometria vascular e features determinísticas (docs 92 a 118)"),
P("Diante do fracasso das abordagens puramente visuais, o projeto voltou-se para características geométricas e físicas mensuráveis, calculadas deterministicamente a partir das máscaras e das fases."),
SPACER(),
T([1500, 3300, 1900, 2326],
  ["Versão", "Feature adicionada", "Resultado", "Decisão"],
  [
    ["v22", "Realce multifásico exato top-5", "50,00% / 0,00% (piloto 10)", "REJEITADO"],
    ["v23", "Geometria vascular / shape fusion", "82,05% / 79,17%; 49/50 repetições", "MELHOR BASELINE da era — mas 1 repetição abaixo de 75%; congelado como referência"],
    ["v24", "Planaridade e contraste", "Perdeu 1 TN; especificidade −2,09 pp", "REJEITADO — pior que v23"],
    ["v25", "Esfericidade inversa", "Decisão idêntica à v23 nos 87 casos", "REJEITADO — não corrigiu nenhum erro"],
    ["v26", "Preenchimento de bounding box", "Mais próxima da v23, mas não superou", "REJEITADO — falhou o gate de 50/50"],
    ["v24 liver-enriched", "Painéis enriquecidos pelo fígado", "61,90% / 59,42%", "REJEITADO"],
    ["v25 pathology-target", "Prompt de alvo patológico", "60,32% / 57,97%", "REJEITADO"],
    ["v26 + RAG", "Alvo patológico com RAG textual", "65,08% / 60,87%", "REJEITADO"],
    ["v27", "Recalibração aninhada", "61,90% / 55,07%", "REJEITADO"],
  ],
  ["l", "l", "l", "l"]),
SPACER(),
rich([["A v23 é o resultado que mais se aproximou da meta nas eras pré-supervisionadas, e sua história é instrutiva. Ela atinge 82,05% / 79,17% no desenvolvimento restrito de 87 casos — acima da meta —, mas "], ["esse desempenho não se sustentou na coorte ampliada de 132 casos", 1], [". Esse par dev87 → full132 é a primeira manifestação limpa e reprodutível do problema de domain shift, e reaparecerá de forma idêntica em todas as eras seguintes."]]),
P("As três extensões geométricas seguintes (v24, v25, v26) foram pré-especificadas com gates explícitos e todas falharam. A auditoria dos 17 erros persistentes da v23 (docs/103) mostrou que nenhuma das features geométricas corrigia os casos difíceis — eles eram sistematicamente os mesmos."),

// --- ERA 6 ---
H2("4.6 Era 6 — Classificador visual supervisionado (docs 119 a 127)"),
rich([["Esta é a era que produz o sistema em produção. O diagnóstico que a motivou, registrado em docs/120, é preciso: "], ["faltava um classificador visual supervisionado especificamente para separar patologia-alvo de mimetizadores benignos", 1], [". Todas as abordagens anteriores ou eram zero-shot, ou treinavam sobre features derivadas, nunca sobre a representação visual com supervisão direta."]]),
SPACER(),
T([2600, 1400, 1400, 1100, 2526],
  ["Fase", "Sensib.", "Especif.", "AUC", "Decisão e motivo"],
  [
    ["Fase 5 — MedSigLIP linear congelado", "72,27%", "73,28%", "0,801", "Gate de continuação APROVADO (pior eixo > 60%); não promovido"],
    ["Fase 7 — Classificador radiômico", "53,64%", "57,09%", "0,618", "REJEITADO — não supera 60% nos dois eixos"],
    ["Fase 8 — Classificador 2.5D de patches", "46,15%", "45,83%", "0,521", "REJEITADO — localizador achou as lesões, classificador não separou"],
    ["Fase 9 — Fusão tardia com v23 (80/20)", "73,02%", "71,01%", "0,764", "REJEITADO — melhorou o v23 mas não atingiu a meta"],
    ["Fase 13-3 — LoRA Q/V", "75,00%", "70,45%", "0,819", "NÃO PROMOVIDO — perdeu especificidade"],
    ["Fase 9B — Fusão Fase 5 + LoRA", "72,73%", "72,87%", "0,799", "REJEITADO — não supera os sinais individuais"],
    ["Etapa C — supervisão multiclasse", "75,91%", "76,11%", "0,853", "APROVADO no agregado — primeiro e único"],
  ],
  ["l", "r", "r", "r", "l"]),
SPACER(),

H3("O resultado da Etapa C em detalhe"),
mono("467 casos multicohort\nTP 167 | TN 188 | FP 59 | FN 53 | falhas técnicas 16\n\nsensibilidade   = 75,91%   IC95% Wilson 69,84 – 81,08%\nespecificidade  = 76,11%   IC95% Wilson 70,42 – 81,01%\nbootstrap por paciente: sens 70,25 – 81,82% | esp 70,99 – 81,47%\nROC-AUC         = 0,8534\n\ngate 75/75 (estimativa pontual): APROVADO"),

H3("Desempenho por coorte — a razão pela qual não foi promovido como qualificado"),
T([3200, 1400, 1600, 2826],
  ["Coorte", "n", "Sensibilidade", "Especificidade"],
  [
    ["lld_mmri", "335", "73,25%", "76,97%"],
    ["openswisshcc_development", "88", "82,05%", "77,55%"],
    ["openswisshcc_consumed_holdout", "44", "83,33%", "65,00%"],
  ],
  ["l", "r", "r", "r"]),
SPACER(),
rich([["O gate agregado passa, mas "], ["nenhuma das três coortes passa individualmente nos dois eixos", 1], [". O holdout consumido possui apenas 20 negativos — cada caso vale 5 pontos percentuais de especificidade, de modo que mesmo um resultado favorável ali não estaria estabelecido. Por regra da matriz de decisão de docs/120, o candidato foi declarado retrospectivo instável e não promovido como qualificado."]]),

H3("Distribuição dos erros por tipo de lesão"),
T([3200, 1400, 4426],
  ["Lesão", "n", "Comportamento correto"],
  [
    ["HCC (patologia-alvo)", "157", "73,25% detectado"],
    ["FNH", "46", "89,13% corretamente negativo"],
    ["Hemangioma", "79", "78,48% corretamente negativo"],
    ["Cisto hepático", "53", "64,15% corretamente negativo"],
  ],
  ["l", "r", "l"]),
SPACER(),
P("O cisto hepático é o maior modo de erro isolado: 36% são chamados de positivo. A investigação de docs/159 estabeleceu que os cistos classificados incorretamente são indistinguíveis dos corretos, tanto na lesão quanto no parênquima adjacente, e que o erro é confiante em vez de marginal. Não existe regra física que corrija esse comportamento."),

H3("Validação em lote cego de 120 casos"),
P("O bundle congelado foi avaliado em um lote cego preparado independentemente. O resultado agregado foi 86,00% de acurácia, com 84,00% de sensibilidade e 88,00% de especificidade. Esse número, entretanto, não pode ser apresentado como validação: a auditoria de proveniência mostrou que 86 dos 100 casos elegíveis estavam no conjunto de treino do bundle. O documento registra explicitamente a proibição de chamá-lo de generalização ou desempenho externo."),

// --- ABLACAO ---
H2("4.7 A ablação decisiva — biologia ou calibração de domínio?"),
rich([["Este é o experimento mais importante do projeto. A Etapa C passou o gate usando classes específicas de coorte (positive_unspecified e negative_unspecified), o que permite ao modelo condicionar sua calibração ao domínio de origem. Antes de qualquer afirmação, era necessário determinar se o ganho vinha da "], ["biologia", 1], [" — o rótulo fino ajudando a separar mimetizadores — ou da "], ["calibração de domínio", 1], [" — as classes de coorte funcionando como indicador de dataset."]]),
P("O desenho que isola a questão: restringir ao LLD-MMRI, única coorte com rótulos finos reais, onde não existe classe de coorte por construção, e comparar dois braços que diferem exclusivamente na granularidade do rótulo. Mesmo módulo, mesmos embeddings, mesmos splits congelados, mesma agregação, mesma seleção de limiar."),
SPACER(),
T([4500, 1500, 1500, 1526],
  ["Configuração (dentro do LLD-MMRI, 335 casos)", "Sensib.", "Especif.", "AUC"],
  [
    ["Braço binário", "76,43%", "75,84%", "0,8567"],
    ["Braço multiclasse", "75,16%", "76,97%", "0,8664"],
  ],
  ["l", "r", "r", "r"]),
SPACER(),
P("Na decisão binária, o rótulo fino é praticamente um empate — troca 1,3 ponto de sensibilidade por 1,1 ponto de especificidade. No AUC, adiciona apenas 0,010. A decomposição completa do ganho:"),
mono("Fase 5 binário, treino nos 467 (subset LLD):   AUC 0,8081   (baseline)\nbinário, treino SÓ no LLD (335):               AUC 0,8567   (+0,049)\nmulticlasse, treino SÓ no LLD (335):           AUC 0,8664   (+0,058)\nmulticlasse, treino nos 467 c/ classes coorte: AUC 0,8630"),
rich([["Portanto o salto de aproximadamente +0,055 AUC da Etapa C decompõe-se em "], ["+0,049 de separação de domínio", 1], [" — parar de misturar OpenSwissHCC no treino — e apenas "], ["+0,010 de granularidade de rótulo clínico", 1], [". O ganho é aproximadamente 85% domínio e 15% biologia."]]),
quote("O gargalo não é \"o modelo não sabe distinguir cisto de HCC\". É heterogeneidade de domínio: misturar OpenSwissHCC e LLD-MMRI no treino piora o desempenho em cada coorte, e um classificador binário simples treinado por coorte já passa o gate na sua própria coorte. — docs/121"),
P("Três consequências foram registradas. Primeira: a supervisão multiclasse funcionou majoritariamente porque as classes de coorte agiram como indicador de domínio. Segunda: treino por coorte não é candidato promovível, porque uma instituição nova não possui rótulos in-domain para calibrar — é diagnóstico, não solução. Terceira: perseguir rótulos de subtipo melhores tem retorno marginal; o valor está em generalização entre domínios."),

// --- ERA 7: SUBTIPO ---
H2("4.8 Era 7 — Identificação da variação (docs 128 a 161)"),
P("A segunda missão — nomear qual das quatro lesões está presente — recebeu tratamento tão rigoroso quanto o endpoint binário, com gates pré-especificados por escrito antes de cada execução."),
SPACER(),
T([3400, 2200, 1200, 2226],
  ["Abordagem testada", "Acurácia balanceada", "Gate", "Decisão"],
  [
    ["Bundle da Etapa C expondo subtipo", "52,18%", "≥ 60%", "REPROVADO — e recall de cisto de apenas 33,33%"],
    ["MedGemma 4B nomeando subtipo", "0,00%", "≥ 40%", "REPROVADO integralmente"],
    ["Realce relativo substituindo as fases", "Piorou o baseline", "≥ 62%", "REPROVADO"],
    ["Descritores físicos de realce sozinhos", "64,97%", "≥ 62%", "PASSA o gate parcial"],
    ["ROI de ground truth + descritores físicos", "74,47%", "—", "TETO de referência com ROI perfeita"],
    ["T2WI e DWI adicionados", "+0,23 ponto", "≥ 80%", "REPROVADO — ganho é ruído"],
    ["Recorte MedSigLIP na ROI correta", "79,49%", "≥ 80%", "REPROVADO por 0,51 ponto"],
    ["Heurísticas geométricas de seleção", "+0,0", "—", "REPROVADO"],
    ["Seleção de componente aprendida", "+0,9", "—", "REPROVADO"],
    ["Multiple-instance learning (sem seleção)", "−0,35", "—", "REPROVADO"],
  ],
  ["l", "r", "c", "l"]),
SPACER(),

H3("A aritmética que fecha a questão"),
P("O subtipo efetivo é o produto de dois fatores independentes: o acerto de localização do componente que contém a lesão, e a discriminação dada a localização correta. Os dois foram medidos separadamente:"),
mono("subtipo efetivo  =  recall do localizador  ×  acerto dado localizado\n\ndiscriminação máxima com ROI de ground truth  =  79,49%\noráculo de seleção de componente               =  82,40%\nrecall do localizador (união arterial+venosa)  =  80,00%"),
rich([["Para atingir 75% de subtipo seria necessário 94% de acerto de centro, contra um oráculo de 82,4% — ou seja, "], ["em 17,6% dos casos o componente correto sequer existe entre os candidatos preditos", 1], [". A meta é aritmeticamente inalcançável com esta representação, e três mecanismos independentes (geometria, supervisão aprendida e ausência de seleção) falharam contra o mesmo oráculo."]]),
P("O ganho mais significativo desta linha foi a união dos localizadores venoso e arterial, que elevou o recall de 69,0% para 80,0% — com o ganho concentrado exatamente nas duas classes que eram o gargalo, confirmando a hipótese pré-registrada. Vale notar que docs/93 havia descartado essa mesma união no OpenSwissHCC; ela funcionou no LLD-MMRI, o que é mais uma manifestação de dependência de domínio."),

H3("O subtipo é condicionado à coorte, não à lesão"),
P("A investigação de docs/161 mediu a massa de probabilidade atribuída às quatro classes nomeadas, usando os mesmos modelos por fold, em dados reais:"),
SPACER(),
T([4500, 4526],
  ["Coorte", "Massa nas 4 classes de subtipo"],
  [
    ["lld_mmri", "99,32%"],
    ["openswisshcc_development", "1,43%"],
    ["openswisshcc_consumed_holdout", "1,47%"],
  ],
  ["l", "r"]),
SPACER(),
rich([["O modelo roteia com aproximadamente 99% de pureza pela coorte de origem. A consequência prática é severa e precisa ser dita com clareza: "], ["em uma instituição nova, a identificação da variação não degradaria — ela simplesmente não dispararia", 1], [". A causa provável é o espaço de rótulos, já que o OpenSwissHCC possui apenas classes unspecified, o que é corrigível — mas torna o rótulo fino de subtipo obrigatório em qualquer coorte futura."]]),
P("O sistema protege-se disso por construção: a guarda de subtipo exige pelo menos 50% de massa nas classes nomeadas antes de nomear qualquer lesão. Verificação empírica: determina em 321 de 321 casos do LLD, em 0 de 130 do OpenSwiss, e em 1 de 330 da coorte sintética."),

H3("Os três números de subtipo e sua desambiguação"),
P("Circulam três valores de acurácia de subtipo separados por 44 pontos percentuais. Confundi-los seria o erro mais fácil de cometer ao apresentar este trabalho:"),
SPACER(),
T([1400, 3600, 4026],
  ["Valor", "O que é", "Validade"],
  [
    ["96,43%", "25 casos LLD pelo frontend (docs/171)", "IN-SAMPLE — 25/25 verificados no manifesto de treino do bundle; medido sem o gate anatômico que está em produção, que recusaria 2 dos 5 positivos. Prova que o fluxo funciona; não é generalização"],
    ["52,19%", "Caminho de produção, nested-OOF (docs/177)", "O que o sistema efetivamente entrega fora da amostra"],
    ["64,81%", "Cascata de representações (docs/156)", "Melhor medição honesta obtida"],
  ],
  ["c", "l", "l"]),
SPACER(),

// --- ERA 8: PRODUTO ---
H2("4.9 Era 8 — Produto, visualizador e auditoria (docs 162 a 178)"),
P("Com o classificador consolidado, o esforço deslocou-se para tornar o sistema operável de ponta a ponta e auditável."),
...bullets([
  "Ingestão de DICOM bruto do PACS com resolução automática de fases (docs/167): exclui reconstruções MPR/MIP/subtração, ordena por posição física em vez de nome de arquivo.",
  "Fallback monofásico explícito quando não há três fases (docs/173), sem jamais fabricar fases sintéticas.",
  "Visualizador 3D auditável (docs/166): cortes ortogonais, régua, vistas anatômicas, painel 2D de ressonância com contorno da máscara, métricas de fidelidade malha-versus-máscara e checklist de revisão.",
  "Região candidata localizada apenas após a decisão estar congelada (docs/169), eliminando vazamento circular entre localização e classificação.",
  "Gate anatômico de plausibilidade da máscara hepática, unificado entre o exame individual e o benchmark.",
]),

H3("O gate anatômico e uma inconsistência corrigida"),
P("A verificação pelo frontend revelou que o gate de plausibilidade da máscara existia apenas no caminho de exame individual. O mesmo exame — os mesmos arquivos — era recusado em uma página e contabilizado como acerto na outra. Aplicando o gate às 25 máscaras do benchmark de docs/171, 2 casos reprovam, e ambos são HCC: 2 dos 5 positivos daquela coorte. A correção unificou o ponto de decisão e adicionou um teste de regressão estrutural que falha se qualquer fluxo voltar a contornar o gate."),

H3("Validação da segmentação contra referência humana"),
P("Mediu-se que 76% dos 321 casos LLD produzem volume hepático segmentado abaixo de 900 mL, com mediana de 637 mL — muito abaixo do esperado para um fígado adulto. Duas explicações eram plausíveis: o segmentador falha, ou aqueles fígados são pequenos. A questão foi resolvida contra a anotação humana do CHAOS:"),
SPACER(),
T([4500, 4526],
  ["Métrica (20 casos CHAOS, referência humana)", "Resultado"],
  [
    ["Dice mediano", "0,908"],
    ["Razão volume predito / referência", "0,85 (mín. 0,76; máx. 0,96)"],
    ["Casos abaixo de 70% do volume de referência", "0 de 20"],
    ["Volume de referência humano", "mediana 1.446 mL"],
  ],
  ["l", "r"]),
SPACER(),
rich([["O segmentador não está defeituoso — Dice de 0,908 contra anotação humana é sólido. A causa da subestimação foi isolada: a "], ["fase de contraste", 1], [". Medição dentro do mesmo exame (docs/165): arterial 122 mL, venosa 486 mL, tardia 607 mL, união das três 650 mL — cinco vezes de variação apenas mudando a fase. O modelo, validado em T1 sem contraste, degrada na fase venosa com contraste, que é justamente a que o pipeline utiliza."]]),

H3("Primeiro sinal externo real"),
P("A coorte TCGA-LIHC, externa e nunca vista, foi processada com desenho pareado: os painéis gerados pela ingestão automática são byte-idênticos aos do mapeamento aprovado manualmente, em 11 de 11 casos. Isso isola a ingestão da generalização."),
mono("casos           = 11\nsensibilidade   = 45,45%\nIC 95%          = 21,3 – 72,0%"),
P("Como os painéis são idênticos, a queda não vem da ingestão automática de fases — é generalização do classificador congelado. É o primeiro sinal externo real do projeto, e ele é desfavorável. O resultado é inteiramente coerente com o diagnóstico de docs/161."),

// --- ERA 9: MONOFASICO ---
H2("4.10 Era 9 — Suporte monofásico (docs 179 a 185)"),
P("A frente mais recente atacou o caso em que o exame não traz as três fases dinâmicas. Sete configurações foram testadas."),
SPACER(),
T([3000, 2000, 2000, 2026],
  ["Configuração", "Interno (LLD)", "Externo (OpenSwiss)", "Decisão"],
  [
    ["Binário só na fase tardia", "77,71% / 75,84%", "25,40% / 81,16%", "Rejeitado como decisor; virou segundo leitor consultivo"],
    ["Binário na fase arterial", "73,25% / 75,28%", "—", "REJEITADO — não passa nem internamente"],
    ["Binário na fase portal/venosa", "74,52% / 73,60%", "—", "REJEITADO"],
    ["Subtipo multiclasse na fase tardia", "48,88% balanceada", "—", "REJEITADO — top-2 de 77,91% não substitui top-1"],
    ["Subtipo pareado one-vs-one", "+0,65 ponto", "—", "REJEITADO — gate exigia +5 pontos"],
    ["Representação por corte axial", "+2,17 pontos", "—", "REJEITADO — gate exigia +5"],
    ["Fusão tardio + axial + ADC", "71,79% / 73,47%", "54,17% / 50,00%", "REJEITADO"],
    ["Supervisão localizada de candidatos", "46–64% / 42–56%", "—", "REJEITADO"],
  ],
  ["l", "l", "l", "l"]),
SPACER(),
rich([["O padrão repete-se com precisão desconfortável: o que funciona no LLD desaba no OpenSwiss. Um resultado desta era merece destaque porque elimina uma hipótese: a supervisão localizada "], ["resolveu o problema de localização", 1], [" — recall de 100% dos positivos em alguma caixa candidata, 86,49% na configuração operacional de top-8 — "], ["e ainda assim a classificação permaneceu próxima do acaso", 1], [". Localizar bem não basta."]]),
P("Uma varredura retrospectiva de todos os limiares possíveis nos 44 casos externos confirmou que nenhum dos quatro sinais possui qualquer limiar que alcance simultaneamente 75% nos dois eixos. O problema é de ordenação e separabilidade, evidenciado por AUCs próximas de 0,5 — não de calibração."),

H3("O que foi efetivamente promovido"),
P("Apenas uma configuração desta era chegou ao produto, com trava dupla: um segundo leitor consultivo para exames identificados com segurança como fase tardia isolada. Ele roda ao lado do MedGemma 4B com RAG, exibe concordância ou discordância ao revisor, eleva a prioridade de revisão quando discorda, e nunca altera a decisão principal. O artefato persistido registra explicitamente affects_primary_decision = false. A promoção automática permanece desabilitada por padrão."),

BREAK(),

// ============ 5. SISTEMA ATUAL ============
H1("5. O sistema em produção"),

H2("5.1 Arquitetura do fluxo"),
mono("DICOM bruto do PACS\n   ↓  resolução automática de fases (exclui MPR/MIP/subtração)\n   ↓  des-identificação automática\n   ↓  segmentação hepática (TotalSegmentator total_mr)\n   ↓  GATE ANATÔMICO — máscara implausível vira falha técnica\n   ↓  harmonização das 3 fases na grade venosa\n   ↓  painéis liver-enriched (RGB = arterial/venosa/tardia)\n   ↓  embeddings MedSigLIP-448 congelados (1152-d)\n   ↓  bundle de produção assinado → decisão binária\n   ↓  guarda de subtipo (≥50% de massa nomeada) → variação\n   ↓  localizador de região candidata (APÓS a decisão congelada)\n   ↓  reconstrução 3D por campo contínuo\n   ↓  revisão humana OBRIGATÓRIA"),

H2("5.2 Desempenho medido do sistema atual"),
T([4000, 2500, 2526],
  ["Endpoint", "Resultado", "Fonte"],
  [
    ["Sensibilidade (agregado, 467 casos)", "75,91% (IC 69,8–81,1)", "docs/121"],
    ["Especificidade (agregado, 467 casos)", "76,11% (IC 70,4–81,0)", "docs/121"],
    ["ROC-AUC", "0,853", "docs/121"],
    ["Subtipo do caminho em produção", "52,19% balanceada", "docs/177"],
    ["Subtipo da melhor configuração medida", "64,81% balanceada", "docs/156"],
    ["Sinal externo (TCGA-LIHC, n=11)", "45,45% sensibilidade", "docs/168"],
    ["Tempo por exame", "114 a 130 s", "docs/175"],
  ],
  ["l", "r", "c"]),
SPACER(),

H2("5.3 Verificação funcional pelo frontend"),
P("O pipeline foi exercitado pelo caminho real da interface, injetando os arquivos DICOM na mesma função que o seletor de pasta aciona:"),
SPACER(),
T([2400, 1800, 2600, 2226],
  ["Caso", "Referência", "Resultado", "Variação"],
  [
    ["ARGOS-BLIND-0046", "HCC", "POSITIVA — score 0,633 (limiar 0,475), 114 s", "HCC — correto"],
    ["ARGOS-BLIND-0048", "Hemangioma", "NEGATIVA — score 0,104, 127 s", "Hemangioma — correto"],
    ["ARGOS-BLIND-0026", "HCC", "Recusado pelo gate anatômico (283 mL)", "—"],
  ],
  ["l", "l", "l", "l"]),
SPACER(),
P("Nos dois casos que concluíram o pipeline, a decisão binária, a variação e o indicador de alvo da triagem estavam todos corretos. No caso 0046 o aviso de volume hepático disparou automaticamente, sinalizando que a segmentação recuperou 485 mL — abaixo da faixa adulta típica. O sistema avisou contra o próprio resultado, que é o comportamento desejado."),

BREAK(),

// ============ 6. DISCUSSAO ============
H1("6. Discussão"),

H2("6.1 Quatro confirmações independentes do mesmo obstáculo"),
P("O resultado científico central deste projeto não é uma métrica, mas a identificação convergente de uma causa. Quatro linhas de investigação metodologicamente independentes, conduzidas em momentos diferentes e com desenhos diferentes, chegaram ao mesmo obstáculo:"),
SPACER(),
T([1800, 3600, 3626],
  ["Fonte", "Desenho", "Achado"],
  [
    ["docs/121", "Ablação binário vs. multiclasse restrita ao LLD", "85% do ganho vem de separação de domínio, 15% de rótulo clínico"],
    ["docs/131", "Predição da coorte a partir das features físicas", "A coorte é previsível com 98,75% de acurácia balanceada"],
    ["docs/161", "Massa de probabilidade por classe, mesmos modelos", "99,32% de massa no LLD contra 1,43% no OpenSwiss"],
    ["docs/182 e 184", "Sete configurações monofásicas, incluindo localização resolvida", "Toda representação que funciona no LLD desaba no OpenSwiss"],
  ],
  ["c", "l", "l"]),
SPACER(),
rich([["A conclusão que essas quatro linhas sustentam conjuntamente é que "], ["o gargalo do sistema não é discriminação biológica entre lesões, nem escolha de limiar, nem arquitetura de classificador, nem cobertura ou resolução da representação", 1], [". É heterogeneidade de domínio entre instituições. Um classificador binário simples treinado dentro de uma única coorte já passa o gate naquela coorte (LLD: 76,43% / 75,84%). O que não sobrevive é a transferência."]]),

H2("6.2 O padrão que se repete em toda a história"),
P("Vista em retrospecto, a história inteira do ARGOS é a mesma observação repetida em escalas crescentes de sofisticação:"),
...bullets([
  "v23: 82,05% / 79,17% em 87 casos de desenvolvimento; não sustentado nos 132 ampliados.",
  "v11: 74,36% / 75,00% em LOOCV; apenas 12 de 50 repetições estáveis.",
  "Holdout v21: 83,33% de sensibilidade com 35,00% de especificidade e AUC de 0,498.",
  "Etapa C: passa no agregado de 467; nenhuma das três coortes passa individualmente.",
  "Monofásico tardio: 77,71% / 75,84% no LLD; 25,40% / 81,16% no OpenSwiss.",
  "TCGA-LIHC: 45,45% de sensibilidade com painéis byte-idênticos aos aprovados.",
]),
P("Cada uma dessas linhas foi, à época, uma tentativa legítima de resolver o problema por meios diferentes. Nenhuma delas contornou o obstáculo, porque nenhuma delas endereçava a causa."),

H2("6.3 O que este projeto demonstra sobre método"),
rich([["Uma contribuição não numérica merece registro. O projeto acumulou aproximadamente vinte e cinco rejeições documentadas contra uma única aprovação parcial. Essa proporção "], ["é o resultado do rigor, não apesar dele", 1], [". Em diversos momentos existiu um número aparentemente favorável que teria sido publicável se as regras tivessem sido afrouxadas:"]]),
...bullets([
  "docs/21: 12 de 12 positivos detectados — recusado como evidência, corretamente identificado como saturação.",
  "docs/40: piloto de 10 casos com 75,00% / 83,33% e 44 de 50 repetições aprovadas — recusado por amostra insuficiente, e de fato não se reproduziu.",
  "docs/46: v11 a um único verdadeiro positivo da meta — encerrado em vez de reajustar pesos.",
  "docs/126: 86,00% de acurácia em lote cego — recusado após auditoria mostrar que 86 de 100 casos estavam no treino.",
  "docs/156: cascata reprovada por 0,19 ponto, menos de meio caso — registrada como reprovada.",
  "docs/143: recorte MedSigLIP reprovado por 0,51 ponto — gate fixado antes, mantido depois.",
]),
P("Em cada um desses casos, a decisão registrada foi contra o interesse imediato do projeto. Um sistema que aceitasse esses números teria hoje uma alegação de desempenho muito superior e completamente insustentável sob escrutínio."),

BREAK(),

// ============ 7. LIMITACOES ============
H1("7. Limitações"),
P("As limitações abaixo devem ser apresentadas antes de serem perguntadas."),
...numbered([
  "Não é desempenho clínico. Todos os números são validação cruzada em dados de desenvolvimento, com prevalência artificial. Em triagem real a especificidade pesa consideravelmente mais.",
  "A coorte de origem é previsível com 98,75% de acurácia a partir das features físicas. Existe confundimento entre coortes que permanece não resolvido.",
  "O único sinal externo verdadeiramente independente disponível é de 45,45% de sensibilidade, com n = 11 e intervalo de confiança de 21,3 a 72,0%.",
  "A segmentação hepática subestima o volume na fase com contraste: mediana de 637 mL, com 76% dos casos abaixo do piso adulto de 900 mL. A causa foi medida (Dice de 0,908 contra referência humana em T1 sem contraste), mas o efeito limita o modelo tridimensional.",
  "A identificação de variação praticamente não dispara fora do LLD-MMRI — 0 de 130 casos do OpenSwiss recebem subtipo nomeado.",
  "Nunca foi realizada comparação sistemática contra outros encoders candidatos. A escolha do MedSigLIP é documentada pelo abandono da via generativa, não por disputa controlada.",
  "Não há comparação documentada com a literatura publicada de triagem de HCC por ressonância — nem contra desempenho de radiologistas, nem contra outros sistemas.",
  "As quatro subclasses (HCC, FNH, hemangioma, cisto) são as classes rotuladas no LLD-MMRI, não uma curadoria clínica prévia de relevância diagnóstica.",
  "O holdout OpenSwissHCC foi consumido e não pode ser reutilizado como validação externa.",
  "clinical_use_allowed permanece false em todo artefato produzido pelo sistema.",
]),

BREAK(),

// ============ 8. PROXIMOS PASSOS ============
H1("8. Conclusão e próximos passos"),

H2("8.1 Estado consolidado"),
T([4500, 4526],
  ["Missão", "Situação"],
  [
    ["Triagem com 75% / 75%", "ATINGIDA no agregado: 75,91% / 76,11%, AUC 0,853 — não estável por coorte"],
    ["Identificar a variação em 75%", "NÃO ATINGIDA. Melhor medição honesta: 64,81%. O limite é aritmético e está demonstrado"],
  ],
  ["l", "l"]),
SPACER(),

H2("8.2 O que destrava o projeto"),
rich([["A recomendação técnica deste relatório é inequívoca e decorre das quatro confirmações independentes da Seção 6.1: "], ["o avanço material depende de uma coorte real adicional, de instituição distinta, com rótulo fino de subtipo", 1], [". Especificação registrada em docs/157:"]]),
...bullets([
  "Aproximadamente 100 negativos — o holdout atual possui 20, e o intervalo de confiança de especificidade tem 38 pontos de largura.",
  "Aproximadamente 50 casos de FNH — hoje são 46, que é o teto da fonte pública disponível, e é a pior classe do sistema.",
  "Instituição diferente — sem isso o confundimento de domínio não pode ser resolvido nem sequer medido corretamente.",
  "Rótulo fino de subtipo obrigatório — sem ele o problema documentado em docs/161 se reproduz.",
]),
P("Verificou-se que não existe dataset público de ressonância com os quatro subtipos proveniente de outra instituição. O caminho é aquisição institucional, com prazo realista de 6 a 12 meses, sendo a rotulagem por dois leitores independentes o gargalo real do cronograma."),

H2("8.3 Ganho disponível e ainda não implementado"),
P("A cascata de representações — fusão onde há recorte disponível, recorte quando não há fígado inteiro, e fígado inteiro como último recurso — supera o caminho atualmente em produção em todas as classes:"),
SPACER(),
T([2800, 1800, 1800, 2626],
  ["Classe", "Em produção", "Cascata", "Diferença"],
  [
    ["FNH", "52,2%", "67,4%", "+15,2"],
    ["HCC", "74,5%", "74,5%", "0"],
    ["Hemangioma", "48,1%", "57,0%", "+8,9"],
    ["Cisto hepático", "34,0%", "60,4%", "+26,4"],
    ["Balanceada", "52,19%", "64,81%", "+12,6"],
  ],
  ["l", "r", "r", "r"]),
SPACER(),
P("Ambos os valores foram medidos em validação cruzada aninhada com denominador honesto, sendo portanto diretamente comparáveis. Não foi implementado por dois motivos verificados: não existe modelo de fusão treinado — a medição de docs/156 foi produzida com modelos por fold, sem artefato de produção assinado — e não há como validar um modelo novo hoje, porque todo caso disponível para teste está no conjunto de treino do bundle."),

H2("8.4 Próximo experimento cientificamente válido"),
P("Enquanto a coorte não chega, o experimento prescrito pelos próprios documentos 184 e 185 é construir um candidato espacial único que combine, na mesma caixa, as fases dinâmicas e as sequências ortogonais T2, DWI e ADC — em vez de agregar scores globais independentes por modalidade. Isso requer registrar T2, DWI e ADC na mesma grade venosa, o que ainda não existe no pipeline: hoje apenas as fases arterial e tardia passam por esse registro."),
P("A justificativa clínica é direta: um radiologista não soma impressões globais por sequência; ele examina um ponto específico e verifica se há hipersinal em T2, restrição em difusão e realce arterial com washout tardio simultaneamente naquele ponto. É a coincidência espacial entre sequências que carrega o sinal, e é exatamente isso que a fusão de scores globais descarta."),
rich([["Registre-se, contudo, o teto realista dessa linha: mesmo que ela produza ganho dentro do LLD, "], ["não existe hoje onde validá-la de forma limpa", 1], [", pois os 132 casos do OpenSwissHCC já foram integralmente consumidos como desenvolvimento. O resultado seria, na melhor das hipóteses, um candidato mais forte para quando a segunda coorte estiver disponível."]]),

BREAK(),

// ============ 9. REFERENCIAS ============
H1("9. Referências internas"),
P("Este relatório é integralmente rastreável aos documentos técnicos versionados do projeto. Os principais são listados abaixo; todos possuem assinaturas SHA-256 dos artefatos correspondentes."),
SPACER(),
T([1400, 7626],
  ["Documento", "Conteúdo"],
  [
    ["docs/17–23", "Qualificação do MedGemma 4B generativo e transição para MedSigLIP"],
    ["docs/24", "Fundação OpenSwissHCC; split congelado; correção do método de scoring do MedSigLIP"],
    ["docs/29–50", "Iterações v3 a v13: cobertura volumétrica, multissequência, localizador 3D, fusão v11, entrada 3D nativa"],
    ["docs/46", "Teto documentado das abordagens sem treino supervisionado"],
    ["docs/51–79", "Iterações v14 a v20: score contínuo, leitor focal, atlas axial e em blocos, RAG"],
    ["docs/80–91", "Validação externa pública (LiverHccSeg, CHAOS) e consumo do holdout OpenSwissHCC"],
    ["docs/92–118", "Geometria vascular v22 a v27; baseline v23 congelado"],
    ["docs/120", "Plano de ação do classificador visual supervisionado — 15 fases, gates e matriz de decisão"],
    ["docs/121", "Log de implementação da Etapa C; ablação domínio versus biologia"],
    ["docs/123", "Bundle de produção e benchmark visual"],
    ["docs/126–127", "Lote cego de 120 casos e correção da guarda de proveniência"],
    ["docs/128–146", "Linha de identificação de variação: pré-especificações, tetos e reprovações"],
    ["docs/150", "Demonstração aritmética da inalcançabilidade da meta de subtipo"],
    ["docs/156", "Cascata de representações — melhor medição honesta de subtipo"],
    ["docs/159", "Análise do erro em cisto hepático"],
    ["docs/161", "Demonstração de que o subtipo é condicionado à coorte"],
    ["docs/165–169", "Visualizador 3D auditável, ingestão de DICOM bruto, região candidata"],
    ["docs/174", "Consolidado de estado para apresentação"],
    ["docs/175", "Teste pelo frontend e correção do volume hepático"],
    ["docs/176", "Validação do segmentador contra referência humana CHAOS"],
    ["docs/177", "Acurácia de subtipo do caminho em produção"],
    ["docs/178", "Procedência dos dados e origem da escolha de encoder"],
    ["docs/179–185", "Frente monofásica: sete configurações, segundo leitor consultivo"],
  ],
  ["c", "l"]),
SPACER(),

new Paragraph({
  spacing: { before: 400, after: 100 },
  shading: { type: ShadingType.CLEAR, fill: "FFF2CC" },
  border: { top: { style: BorderStyle.SINGLE, size: 8, color: "BF8F00" }, bottom: { style: BorderStyle.SINGLE, size: 8, color: "BF8F00" },
            left: { style: BorderStyle.SINGLE, size: 8, color: "BF8F00" }, right: { style: BorderStyle.SINGLE, size: 8, color: "BF8F00" } },
  children: [new TextRun({ text: "  Declaração final — Todos os resultados apresentados são retrospectivos e de pesquisa. Nenhum constitui validação clínica, diagnóstico ou laudo médico. A revisão humana permanece obrigatória em todo o fluxo, e clinical_use_allowed permanece false em todos os artefatos gerados pelo sistema.  ", bold: true, size: 19, color: "7F6000" })],
}),

    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(process.argv[2] || "ARGOS_OREN_relatorio.docx", buf);
  console.log("OK:", process.argv[2]);
});
