# OpenSwissHCC v16 — auditoria retrospectiva do localizador

## 1. Escopo autorizado

Em 17/07/2026 foi autorizada a abertura exclusiva das máscaras públicas de lesão dos 87 casos de desenvolvimento para auditar retrospectivamente o localizador v16.

Restrições mantidas:

- as máscaras não participaram da geração de candidatos, dos stacks, da inferência ou da calibração v16;
- nenhuma máscara foi enviada ao MedGemma;
- somente máscaras manuais da fase T1 venosa dos casos de desenvolvimento foram extraídas;
- o holdout permaneceu fechado;
- a análise é diagnóstica e não qualifica uma nova configuração.

O pacote público `derivatives.zip` foi validado pelo MD5 publicado `e7df6554b20aeb941d697710e4201c18` e pelo SHA-256 local `535201b09a271c85a3de15f4a0f1f61749db3e62c4116c9753d1a3c9d4ba8f3f`.

Antes de ler os voxels, foi congelado o protocolo:

```text
schema: argos-openswisshcc-v16-localizer-audit-protocol-v1
assinatura: 1708469f0ae979481d9473d70dee333fce64e801bfd21d41423e49d53a511e5f
casos: 87
positivos: 39
negativos: 48
positivos com máscara venosa: 37
máscaras venosas: 74
holdout_opened: false
```

Dois positivos não possuíam máscara manual venosa pública. Eles foram excluídos apenas dos denominadores da auditoria espacial, sem serem transformados em sucesso ou falha.

## 2. Definições congeladas

Foram medidos dois eventos diferentes:

1. **Hit do componente:** pelo menos um voxel da máscara manual intersecta um dos componentes selecionados pelo v16.
2. **Visibilidade no stack:** pelo menos um voxel da máscara manual pertence à união exata dos cortes T1 venosos e dos crops de 80 mm realmente renderizados para o MedGemma.

O segundo evento é o mais próximo da pergunta operacional “a lesão apareceu na evidência vista pelo modelo?”. Ele não pressupõe que o modelo tenha reconhecido essa lesão.

As máscaras e imagens têm tamanho e spacing idênticos. Diferenças de precisão do cabeçalho NIfTI atingiram no máximo 0,000229 mm na origem e `6,3×10⁻⁹` na direção. A auditoria aceitou somente tamanho idêntico, spacing com tolerância `1×10⁻⁷`, origem até 0,001 mm e direção até `1×10⁻⁶`. Não houve registro nem reamostragem.

## 3. Resultado principal

| Métrica | Resultado | IC 95% de Wilson |
|---|---:|---:|
| Recall por caso — componente selecionado | 21/37 = **56,76%** | 40,91%–71,33% |
| Recall por caso — lesão visível no stack | 23/37 = **62,16%** | 46,10%–75,94% |
| Recall por lesão — componente selecionado | 24/74 = **32,43%** | 22,86%–43,73% |
| Recall por lesão — lesão visível no stack | 29/74 = **39,19%** | 28,86%–50,58% |

O gate de 75% não foi atingido. Mesmo com um leitor hipoteticamente perfeito, os stacks v16 atuais só apresentaram alguma lesão venosa anotada em 62,16% dos positivos auditáveis.

## 4. Localizador completo versus seleção de componentes

Foi comparada também a máscara candidata completa, antes da seleção dos 3–5 maiores componentes:

| Representação | Recall por caso | Recall por lesão |
|---|---:|---:|
| Máscara candidata completa | 21/37 = 56,76% | 26/74 = 35,14% |
| Componentes selecionados | 21/37 = 56,76% | 24/74 = 32,43% |

Componentes descartados recuperariam duas lesões adicionais, mas nenhum caso adicional. Portanto, aumentar apenas `MAX_CANDIDATES` não resolve o gargalo por caso. A maior perda ocorre antes do ranking: o `liver_lesions_mr` aplicado somente ao T1 venoso não produz candidato sobre 16 dos 37 casos auditáveis.

## 5. Efeito do tamanho da lesão

O diâmetro equivalente foi calculado a partir do volume físico da máscara venosa:

| Diâmetro equivalente | Lesões | Hit do componente | Visível no stack |
|---|---:|---:|---:|
| menor que 10 mm | 11 | **0/11 = 0%** | **0/11 = 0%** |
| 10–20 mm | 43 | 14/43 = 32,56% | 18/43 = 41,86% |
| 20 mm ou maior | 20 | 10/20 = 50,00% | 11/20 = 55,00% |

O v16 atual é especialmente inadequado para lesões pequenas. Esse achado não deve ser convertido em limiar otimizado no mesmo conjunto; ele serve para definir o requisito de cobertura da próxima representação.

## 6. Localização versus leitura do MedGemma 4B

A decisão LOOCV original foi reconstruída usando, na mesma ordem congelada, o score e o threshold de cada fold:

| Subgrupo positivo auditável | Acertos LOOCV |
|---|---:|
| Todos com máscara venosa | 18/37 = 48,65% |
| Alguma lesão visível no stack | 13/23 = **56,52%** |
| Nenhuma lesão visível no stack | 5/14 = 35,71% |
| Componente selecionado toca lesão | 12/21 = 57,14% |
| Componente selecionado não toca lesão | 6/16 = 37,50% |

Isso prova dois gargalos independentes:

- **Cobertura:** 14/37 casos não exibiram nenhuma lesão venosa anotada; o teto de visibilidade atual é 62,16%, abaixo da meta.
- **Leitura:** mesmo quando há lesão no stack, a decisão LOOCV acerta apenas 56,52%, também abaixo da meta.

O resultado categórico bruto do 4B foi ainda menor: 7/23 positivos quando a lesão estava visível. Ele é diagnóstico secundário e não substitui a métrica LOOCV.

## 7. Consequência para o plano

O v16 não deve seguir diretamente para holdout e não deve ser “corrigido” apenas alterando threshold, número máximo de candidatos, RAG ou GraphRAG.

O próximo experimento deve ser um v17 de desenvolvimento, novamente cego durante a inferência, com duas frentes:

1. **Cobertura de resgate:** preservar os candidatos, mas acrescentar cobertura determinística do fígado inteiro quando a representação candidata não cobre todas as regiões. A primeira meta técnica é mostrar alguma lesão venosa em pelo menos 28/37 casos auditáveis; o alvo recomendado é maior que 90% para não impor um teto próximo de 75%.
2. **Leitor compacto:** comparar o v11, que já obteve 74,36%/75,00%, com uma evidência focal compacta de menos frames. Os 29 frames por candidato do v16 podem diluir a evidência no 4B. A alternativa deve manter fases originais, posição anatômica e comparação no mesmo plano, sem contorno na entrada do modelo.

Opções de cobertura a testar no desenvolvimento:

- união de localizadores executados em venoso e arterial/delayed, condicionada ao orçamento de 180 segundos;
- grid hepático físico determinístico com centros espaçados e cobertura verificável;
- painel global v11 seguido de no máximo um ou dois stacks focais;
- resgate específico para ausência de candidato, sem usar máscara de lesão;
- análise separada para lesões menores que 10 mm.

RAG e GraphRAG permanecem úteis depois que a lesão está visível: podem ajudar a separar vasos, pseudolesões e variantes anatômicas. Eles não recuperam a evidência ausente do crop e, por isso, não são a primeira correção desta falha.

## 8. Artefatos e validação

Artefatos locais, fora do Git:

- `casos/qualification/openswisshcc_v1/authorized_ground_truth_v16/audit_protocol_v1.json`
- `casos/qualification/openswisshcc_v1/authorized_ground_truth_v16/venous_masks_v1/extraction_manifest.json`
- `casos/qualification/openswisshcc_v1/audits/dev_v16_candidate_localization_venous_v1/audit.json`
- `casos/qualification/openswisshcc_v1/audits/dev_v16_candidate_localization_venous_v1/case_localization.csv`
- `casos/qualification/openswisshcc_v1/audits/dev_v16_candidate_localization_venous_v1/lesion_localization.csv`

Assinatura do resultado: `e7a98b41e033e7ac1e16ae9a3a39d898aeabf4b09e8ca6498da580fe51c157fc`.

Validação executada:

```text
38 testes focados: 38 passed
toda a suíte OpenSwissHCC: 294 passed
```

Nenhuma inferência foi executada nesta auditoria e o holdout permanece fechado.
