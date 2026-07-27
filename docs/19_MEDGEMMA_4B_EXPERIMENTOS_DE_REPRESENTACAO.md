# Experimentos de representação — MedGemma 1.5 4B

Data: 2026-07-14  
Estado: desenvolvimento; nenhuma configuração qualificada

## Objetivo

Investigar por que o MedGemma 4B classificou todos os seis casos do piloto como
positivos e testar representações que reduzam falsos positivos sem treinamento.

## Experimento 1 — Spotlight hepático

Foi criado `dtwin/medgemma_spotlight.py`, ainda isolado do fluxo principal. O
módulo:

- recebe somente volume anonimizado e máscara hepática;
- preserva as intensidades dentro do fígado;
- atenua uniformemente o contexto fora da máscara;
- não aceita nem procura máscara de lesão;
- gera a mesma grade 4×3 do baseline;
- remove metadados PNG;
- salva atomicamente;
- mantém aviso de pesquisa e revisão humana.

Foi criado `tools/render_spotlight_panel.py` para gerar o protótipo a partir de
artefatos já preparados.

Testes em `tests/test_medgemma_spotlight.py`:

- preservação exata dos pixels hepáticos;
- atenuação somente fora do fígado;
- rejeição de frações inválidas;
- determinismo de hash;
- grade 1280×960;
- ausência de metadados;
- ausência de contorno amarelo.

Resultado: `6 passed`.

### Resultado visual/modelo

O spotlight deixou o fígado claramente separado de rim, baço e outras estruturas.
No mesmo par positivo/negativo, porém, o MedGemma retornou:

| Grupo | Resultado | Confiança | Tempo |
|---|---|---|---:|
| positivo | POSITIVA | baixa | 2,67 s |
| negativo | POSITIVA | baixa | 2,16 s |

Hipótese não confirmada: atenuar o contexto extra-hepático não criou discriminação.

### Limitação anatômica descoberta

As máscaras de fígado e de grandes vasos produzidas pelo segmentador são
disjuntas. Ao usar somente a máscara hepática como spotlight, regiões vasculares
podem virar áreas internas escuras e mimetizar focos. Por esse motivo o módulo
não foi integrado ao pipeline principal.

## Experimento 2 — Resposta sem JSON/prefill

Com o mesmo par spotlight e resposta direta `LESION`/`NO_LESION`:

| Grupo | Resposta | Tempo |
|---|---|---:|
| positivo | LESION | 1,13 s |
| negativo | LESION | 0,68 s |

Conclusão: o colapso positivo não é causado somente pelo schema JSON.

## Experimento 3 — Raciocínio curto

O modelo recebeu 256 tokens para descrever evidência e terminar com marcador
parseável:

```text
FINAL=LESION | FINAL=NO_LESION | FINAL=INCONCLUSIVE
```

Resultado:

- positivo: `FINAL=LESION`, 3,33 s;
- negativo: `FINAL=LESION`, 2,47 s;
- no negativo, o texto afirmou uma lesão em axial/coronal sem evidência
  confirmada.

Conclusão: permitir raciocínio curto não eliminou o falso positivo.

## Experimento 4 — Blocos axiais adjacentes

Foram gerados painéis com todos os cortes hepáticos adjacentes, reutilizando o
modo volumétrico existente:

| Workspace anonimizado | Cortes axiais | Painéis |
|---|---:|---:|
| case-3a2d474a2823 | 24 | 3 |
| case-6596ee6ee4da | 19 | 3 |
| case-720e5e5f830f | 74 | 9 |
| case-ab1bf4e2c66f | 61 | 7 |
| case-b0626083da5f | 18 | 2 |
| case-f94d72ac3867 | 40 | 5 |

No par testado, todos os cinco painéis positivos e todos os três negativos foram
classificados `LESION`. Tempos por chamada ficaram entre 0,69 s e 1,19 s.

Conclusão:

- a cobertura volumétrica cabe no orçamento temporal;
- cortes adjacentes, isoladamente, não recuperam especificidade;
- a regra de agregação “qualquer positivo” não é a causa primária, porque cada
  painel individual já foi positivo.

## Estado das hipóteses

| Hipótese | Resultado |
|---|---|
| prompt em inglês | não separou o par |
| pergunta booleana | ambos `false`; não separou |
| saída direta sem JSON | ambos `LESION`; não separou |
| raciocínio curto | ambos `LESION`; não separou |
| spotlight hepático | ambos positivos; rejeitado isoladamente |
| cortes adjacentes | todos os painéis positivos; rejeitado isoladamente |

## Próximo caminho técnico

O modelo gerativo 4B, sozinho, não demonstrou sinal discriminativo no piloto. A
documentação oficial do Google recomenda MedSigLIP para classificação zero-shot e
recuperação visual sem geração de texto. MedSigLIP foi pré-treinado com slices de
CT/RM, possui encoder visual e textual e opera em 448×448.

Próximo experimento proposto, ainda sem treinamento:

1. MedSigLIP zero-shot ou recuperação por similaridade gera um sinal independente;
2. MedGemma 4B permanece responsável pela explicação estruturada e relatório;
3. a decisão final usa regra congelada e validada em desenvolvimento;
4. nenhum threshold é escolhido no teste final;
5. OpenSwissHCC ou outra base com positivos e negativos comparáveis permanece
   necessária para prova válida.

Bloqueio externo:

- `google/medsiglip-448` não está no cache local;
- o Hugging Face exige login e aceite explícito dos termos HAI-DEF;
- o assistente não aceita termos legais em nome do usuário.

Referências oficiais:

- https://developers.google.com/health-ai-developer-foundations/medsiglip
- https://developers.google.com/health-ai-developer-foundations/medsiglip/model-card
- https://huggingface.co/google/medsiglip-448
