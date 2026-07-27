# Fundação MedSigLIP zero-shot — sem decisão clínica

## Motivação

O MedGemma 1.5 4B gerativo não separou o par positivo/negativo nos controles de
prompt, resposta, spotlight ou cortes adjacentes. A documentação oficial do
Google recomenda MedSigLIP para classificação visual zero-shot e recuperação
sem geração de texto.

## O que foi adicionado

- `configs/medsiglip_liver_zero_shot.yaml`: prompts positivos e negativos
  balanceados e versionados;
- `dtwin/medsiglip_zero_shot.py`: extração dos 9 tiles axiais e 2 ortogonais,
  carregamento local do modelo, scores sigmoid, normalização pareada e evidência
  exploratória de continuidade axial;
- `tools/score_medsiglip_panel.py`: CLI que persiste apenas hash e scores;
- `tests/test_medsiglip_zero_shot.py`: testes de config, tiles, PHI em metadata,
  normalização, adjacência e shapes inválidos.

## Salvaguardas

- `research_only=true` e `clinical_use_allowed=false` são obrigatórios;
- decisão final permanece `null`;
- `decision_enabled` deve ser `false`;
- o threshold 0,5 é somente exploratório;
- o painel com metadata PNG é rejeitado;
- a saída não contém pixels, DICOM, paths clínicos ou texto de paciente;
- revisão humana permanece obrigatória;
- o modelo não é baixado por padrão (`local_files_only=true`);
- download exige a flag explícita `--allow-download`, após o usuário aceitar os
  termos no Hugging Face.

## Estratégia de memória

MedSigLIP e MedGemma devem rodar sequencialmente na GPU de 8 GB. Os scores são
gerados primeiro, o encoder é descarregado e somente então o 4B gera o relatório.
Esse requisito será medido no piloto; não há alegação de tempo antes da execução.

## Critério para avançar

Os scores só poderão virar decisão depois de:

1. labels positivos revisados para lesão focal hepática visível;
2. conjunto de desenvolvimento balanceado e sem confundimento grosseiro de
   protocolo;
3. threshold e regra de adjacência congelados no desenvolvimento;
4. avaliação única em teste independente;
5. sensibilidade e especificidade ≥75%, com inconclusivos como erro;
6. tempo total por caso ≤180 s.

Referências oficiais:

- https://developers.google.com/health-ai-developer-foundations/medsiglip
- https://developers.google.com/health-ai-developer-foundations/medsiglip/model-card
- https://huggingface.co/google/medsiglip-448
