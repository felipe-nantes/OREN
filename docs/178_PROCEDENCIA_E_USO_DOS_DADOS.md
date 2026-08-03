# Procedência dos dados — de onde vêm e sob que termos

**Data:** 3 de agosto de 2026
**Motivação:** auditoria dos documentos encontrou zero menções a consentimento,
LGPD ou aprovação ética formal. A informação existe, mas estava dispersa em
documentos de engenharia de dataset, nunca reunida numa resposta direta.

---

## 1. Não há coleta de dados de pacientes novos

Todo dado usado no ARGOS/OREN vem de **datasets públicos de pesquisa**, já
publicados e liberados por seus autores originais. Nenhum paciente foi
recrutado, nenhuma imagem foi obtida diretamente de serviço clínico. A
responsabilidade pela aprovação ética e pelo consentimento dos sujeitos
originais é dos autores de cada dataset, no momento da publicação.

| Dataset | Fonte | Registro | Licença |
|---|---|---|---|
| LiverHccSeg | Zenodo | [8179129](https://zenodo.org/records/8179129), v1.1 | **CC BY 4.0** ([docs/81](81_V21_PREPARACAO_REAL_LIVERHCCSEG.md)) |
| CHAOS MRI | Zenodo | [3431873](https://zenodo.org/records/3431873) | ver termos do registro ([docs/85](85_CHAOS_V103_GATE_DE_AQUISICAO.md)) |
| OpenSwissHCC | Zenodo | metadados baixados e verificados por MD5 ([docs/24](24_MEDSIGLIP_E_OPEN_SWISS_QUALIFICATION.md)) | ver termos do registro |
| LLD-MMRI | Hugging Face | [`wanglab/LLD-MMRI-MedSAM2`](https://huggingface.co/datasets/wanglab/LLD-MMRI-MedSAM2) | ver termos do repositório |
| TCGA-LIHC | TCIA / GDC (The Cancer Genome Atlas) | coorte pública padrão de oncologia | programa NIH, termos próprios |
| gd_eob_dtpa *(não usado no caminho de produção)* | Zenodo | [18622298](https://zenodo.org/records/18622298), rev. 3 | ver termos do registro |

**Ressalva honesta:** este documento lista o que está registrado nos artefatos
de engenharia do projeto (registro Zenodo/HuggingFace, hash verificado, versão).
Ele **não** substitui a leitura do termo de uso de cada dataset — se o
orientador pedir o texto exato de consentimento/aprovação de algum deles, a
fonte é a publicação original, não este projeto.

---

## 2. O que o pipeline faz com os dados, independente da origem

Documentado e testado, não apenas declarado:

- **des-identificação automática** de toda pasta DICOM recebida, antes de
  qualquer processamento (`webapp/server.py`, docstring de módulo);
- nenhuma imagem, caminho de arquivo ou identificador de paciente sai do
  ambiente de execução — o envio é processado localmente;
- `research_only=true` e `clinical_use_allowed=false` são obrigatórios em
  **todo** artefato gerado, sem exceção;
- revisão humana é sempre exigida antes de qualquer uso do resultado.

---

## 3. Por que datasets diferentes, e o que isso custou

[docs/80](80_COORTE_PUBLICA_INDEPENDENTE_V21.md) registra a decisão de compor
várias fontes públicas em vez de uma só, e nomeia a alternativa considerada e
descartada (Duke Liver Dataset) por não resolver a lacuna de RM multifásica.
Essa composição é também a causa raiz do confundimento de domínio medido em
[docs/161](161_SUBTIPO_E_CONDICIONADO_A_COORTE.md): datasets diferentes têm
características de aquisição diferentes, e o modelo aprende a diferenciá-los.

---

## 4. Por que MedSigLIP, e não outro encoder

Registrado em [docs/20](20_MEDSIGLIP_ZERO_SHOT_FOUNDATION.md), no início do
projeto, mas nunca puxado para os documentos de síntese:

> O MedGemma 1.5 4B generativo não separou o par positivo/negativo nos
> controles de prompt, resposta, spotlight ou cortes adjacentes. A
> documentação oficial do Google recomenda MedSigLIP para classificação visual
> zero-shot e recuperação sem geração de texto.

**Isso não é uma comparação sistemática entre encoders candidatos** (MedSigLIP
vs. BiomedCLIP, DINOv2, ResNet, etc.) — nenhuma foi feita. É a razão registrada
para abandonar a abordagem generativa e adotar embeddings congelados. Se
perguntado "por que não testaram outro encoder", a resposta honesta é que essa
comparação não foi feita, não que MedSigLIP venceu uma disputa.

---

## 5. O que continua sem resposta escrita

Para não prometer cobertura que não existe:

- **Comparação com literatura publicada** de triagem de HCC por RM (sensibilidade/
  especificidade de radiologistas ou de outros sistemas de IA). Exigiria revisão
  bibliográfica real; não foi feita.
- **Justificativa formal das quatro subclasses** (FNH, HCC, hemangioma, cisto).
  A razão de fato é que são as classes rotuladas no LLD-MMRI — não houve uma
  decisão clínica prévia de que essas quatro são as mais relevantes a
  distinguir.
- **Por que ressonância e não tomografia.** Decorre de os datasets disponíveis
  serem de RM; não há uma comparação de modalidades documentada.
