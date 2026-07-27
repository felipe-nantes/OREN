# OpenSwissHCC v22 — protocolo congelado do piloto exact-top5

## Estado

O protocolo de avaliação foi congelado antes da revisão humana e antes da
criação do diretório de predições. Nenhum label, máscara, holdout ou chamada ao
MedGemma foi usado nesta etapa.

Protocolo:

`casos/qualification/openswisshcc_v1/prepared/development_protocols_v22/enhancement_t3_exact_top5_pilot10_evaluation_v1.json`

- assinatura: `6de4e026336c6d5f092b3b67dd17068a10459a2c2300bf4843187796c9e799d8`;
- SHA-256 do arquivo: `1e135930817e25628df1e9b0bd09c87214d2e77ea2cb9f6c0931e0398b07d3ff`;
- casos: 10;
- stacks esperados: 48;
- run de scores reservado: `dev_v22_enhancement_t3_exact_top5_pilot10_4b_v1`;
- predições presentes no congelamento: não.

## Regra de decisão predeclarada

Para cada caso:

1. pelo menos um candidato `POSITIVA` → caso `POSITIVA`;
2. sem positivo, mas com pelo menos um `INCONCLUSIVA` → caso `INCONCLUSIVA`;
3. somente quando todos os candidatos forem `NEGATIVA` → caso `NEGATIVA`.

Não haverá calibração de limiar após a abertura dos labels.

Na métrica principal:

- inconclusivo em caso positivo conta como falso negativo;
- inconclusivo em caso negativo conta como falso positivo;
- meta do piloto: sensibilidade ≥75%, especificidade ≥75% e todos os casos ≤180 s;
- intervalos de confiança: Wilson 95%.

## Limites metodológicos

O piloto contém apenas dez casos de desenvolvimento e não pode qualificar o
sistema final, mesmo se alcançar os três gates. Ele serve para decidir se vale
executar uma coorte de desenvolvimento maior. O tempo medido será do scoring
dos stacks preparados; o tempo desde DICOM cru continuará não comprovado até
uma medição operacional separada.

O avaliador pós-predição exige:

- os dez IDs e a assinatura da galeria congelada;
- exatamente 48 chamadas candidatas;
- run de scores completo e sem ground truth durante a inferência;
- hash de cada predição;
- gate temporal individual;
- labels públicos lidos somente depois da conclusão das predições;
- holdout e máscaras de lesão fechados.
