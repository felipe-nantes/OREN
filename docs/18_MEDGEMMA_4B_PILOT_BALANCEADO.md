# Piloto balanceado MedGemma 1.5 4B — resultados e decisões

Data: 2026-07-13/14  
Modo: pesquisa, revisão humana obrigatória  
Configuração: `configs/medgemma_local_4b_fast_pathology.yaml`

## Escopo

Foi executado um piloto de desenvolvimento com três casos fornecidos como
positivos e três casos fornecidos como negativos. Os labels permanecem
`pending_review`; este piloto não é validação clínica nem teste independente.

Run local, fora do Git:

```text
casos/qualification/fast_dev_runs/
20260714T001803Z_6ee41c58_fast_pathology_balanced_dev_v1
```

O dry-run anterior confirmou seis paths válidos, hashes, isolamento de ground
truth e ausência de chamada ao modelo.

## Resultado

| Métrica | Resultado |
|---|---:|
| casos completos | 6/6 |
| falhas técnicas | 0 |
| timeouts | 0 |
| sensibilidade provisória | 100% (3/3) |
| especificidade provisória | 0% (0/3) |
| acurácia provisória | 50% |
| gate simultâneo de 75% | FAIL |

Todos os casos foram classificados como `POSITIVA`. A configuração, portanto,
não possui discriminação útil neste piloto.

## Tempo por caso

| Caso anonimizado | Grupo | Importação/segmentação | MedGemma | Total |
|---|---|---:|---:|---:|
| anon-dev-positive-001 | positivo | 27,36 s | 3,11 s | 31,57 s |
| anon-dev-positive-002 | positivo | 32,47 s | 2,56 s | 36,30 s |
| anon-dev-positive-003 | positivo | 29,67 s | 2,68 s | 33,60 s |
| anon-dev-negative-001 | negativo | 25,70 s | 2,38 s | 29,12 s |
| anon-dev-negative-002 | negativo | 23,86 s | 2,54 s | 27,42 s |
| anon-dev-negative-003 | negativo | 23,48 s | 2,42 s | 26,98 s |

Todos os casos ficaram abaixo do limite de 180 segundos. O objetivo de latência
está tecnicamente atendido neste hardware, mas o objetivo de sensibilidade e
especificidade não está.

## Controles do formato de resposta

Foram feitos controles fora do benchmark, sem entrada nas métricas:

1. Instrução para ignorar a imagem e completar `NEGATIVA`: o modelo obedeceu em
   2,95 s. Isso demonstra que o gateway/prefixo não força tecnicamente
   `POSITIVA`.
2. Prompt clínico conservador em português sobre um negativo: `POSITIVA`, com
   confiança numérica não compatível com o schema final.
3. Prompt clínico conservador em inglês, pareado:
   - positivo: `POSITIVA`, confiança baixa, 3,18 s;
   - negativo: `POSITIVA`, confiança baixa, 3,12 s.
4. Pergunta booleana direta `ha_lesao_focal_suspeita`:
   - positivo: `false`, confiança baixa, 4,24 s;
   - negativo: `false`, confiança baixa, 3,20 s.

Conclusão: trocar rótulo, idioma ou formato muda a classe dominante, mas não
produziu separação entre o par. Não é metodologicamente aceitável escolher o
formato que melhora apenas uma metade da métrica.

## Integridade visual do painel

A inspeção inicial por miniatura pareceu mostrar linhas vazias, mas o transporte
da miniatura estava truncando o JPEG. Uma segunda inspeção, com miniatura completa
abaixo do limite de bytes, confirmou que o PNG contém:

- nove cortes axiais;
- vista coronal;
- vista sagital;
- aviso de pesquisa.

O painel 4×3 está íntegro. Nenhuma correção de layout foi feita.

## Problema metodológico identificado nos positivos

O lote `D:\lote_positivo_1_real` contém 17 pastas:

- 12 identificadas como casos TCGA;
- 5 identificadas apenas pelo nome de série VIBE/T1.

A inspeção dos três primeiros painéis mostrou que pelo menos uma alteração
visualmente dominante parece extra-hepática. Um exame não saudável não é
automaticamente positivo para o alvo definido pelo projeto:

```text
suspeita de lesão focal hepática
```

Além disso, um diagnóstico de HCC no nível do paciente não garante que uma lesão
focal esteja visível na única série selecionada. Portanto, a sensibilidade de
100% deste piloto não deve ser apresentada como desempenho real.

## Decisões

- manter o run como evidência de engenharia e latência;
- rejeitar a configuração atual como classificador qualificado;
- não ajustar limiar usando os três negativos;
- separar TCGA-LIHC dos casos não confirmados;
- exigir revisão da condição-alvo e visibilidade na série para o conjunto de
  desenvolvimento positivo;
- testar uma representação que indique claramente o interior da máscara hepática
  sem marcar lesões;
- manter `INCONCLUSIVA` como erro na métrica principal;
- preservar isolamento de labels, PHI e revisão humana.

## Próxima hipótese

O recorte sem contorno inclui rim, baço e outros tecidos próximos. O modelo pode
estar atribuindo achados extra-hepáticos ao fígado. A próxima representação a
testar deve preservar o sinal do parênquima e escurecer determinística e
uniformemente os pixels fora da máscara hepática, sem usar máscara de lesão.

Essa hipótese só poderá ser aceita se melhorar simultaneamente positivos e
negativos revisados; ganho unilateral não será considerado qualificação.
