# ARGOS — Relatório de conclusão de ciclo: classificador visual supervisionado

**Data:** 25 de julho de 2026
**Escopo:** Fases 0–13 do plano (`docs/120`) + Etapas A/B/C de diagnóstico dirigido
**Público:** equipe do projeto
**Status:** ciclo de investigação encerrado; meta 75%/75% não atingida de forma estável

---

## 1. Onde chegamos

O objetivo era encontrar um classificador visual supervisionado que superasse a
saturação do MedGemma 4B (que responde POSITIVA para quase tudo) e atingisse
**sensibilidade ≥75% e especificidade ≥75% simultaneamente e de forma estável**.

### Melhor resultado obtido

| Candidato | Sensibilidade | Especificidade | AUC | Estável por dataset? |
|---|---:|---:|---:|---|
| MedGemma 4B (linha histórica) | saturado | 0–2% | — | não |
| v23 (melhor resultado histórico, 87 casos) | 82,05% | 79,17% | — | não generalizou (full132: 65,08%/60,87%) |
| Fase 5 — MedSigLIP linear congelado | 72,27% | 73,28% | 0,801 | não |
| Fase 13 — LoRA | 75,00% | 70,45% | 0,819 | não |
| **Etapa C — supervisão multiclasse** | **75,91%** | **76,11%** | **0,853** | **não** |

A Etapa C é o único candidato do projeto a passar o gate agregado (467 casos
multicohort: OpenSwissHCC + LLD-MMRI). Não foi promovido a produção — ver
seção 2.

### O que foi descoberto no caminho (mais importante que o número final)

1. **O erro não estava distribuído.** Praticamente todo o déficit de
   especificidade vinha de um único subtipo — cisto hepático (~42% chamado de
   positivo) — enquanto HCC, FNH e hemangioma já operavam em 74–85%.
2. **Feature engenheirada manualmente falhou.** Duas tentativas de medir
   realce de candidato relativo ao parênquima (hipótese clínica correta: cisto
   não realça) não separaram cisto do resto (AUC 0,49 e 0,55). A causa
   alternativa mais plausível — desalinhamento entre fases dinâmicas — foi
   testada e **refutada** (deslocamento residual ≤1,5 mm, igual ao controle
   já registrado).
3. **Rótulo mais fino ajudou pouco; separar domínio ajudou muito.** Decompondo
   o ganho da Etapa C: **+0,049 AUC veio de não misturar as duas coortes no
   treino; apenas +0,010 veio de ensinar o modelo a distinguir hcc/hemangioma/
   cisto/fnh.** O gargalo real é heterogeneidade entre datasets (domain
   shift), não falta de granularidade clínica.

---

## 2. Por que não está pronto para produção

Regra do próprio protocolo (`docs/120` §7): um candidato só é promovível se
**estável nos três datasets simultaneamente**. A Etapa C não é:

```
lld_mmri                        73,25% / 76,97%   FALHA (sensibilidade)
openswisshcc_development        82,05% / 77,55%   OK
openswisshcc_consumed_holdout   83,33% / 65,00%   FALHA (especificidade)
```

Além disso, os intervalos de confiança de 95% cruzam 75% nos dois eixos
(Wilson: sensibilidade 69,84–81,08%; especificidade 70,42–81,01%) — a
estimativa pontual passa, a confiança estatística não.

**Diagnóstico consolidado:** o teto atual do sinal visual disponível (MedSigLIP
congelado + variantes) fica em torno de 73–76% em cada eixo, instável entre
domínios. Isso não é falha de engenharia — é o limite do que a representação
visual atual consegue generalizar entre OpenSwissHCC e LLD-MMRI.

---

## 3. Linhas testadas e descartadas (para não repetir)

| Linha | Resultado | Por que foi descartada |
|---|---:|---|
| Radiômica sobre fígado inteiro (Fase 7) | 53,64%/57,09% | lesão de 2 cm dilui em ~0,1% dos voxels do órgão |
| Classificador de candidato 2.5D (Fase 8) | 46,15%/45,83% | localizador funcionou (94,6% recall), mas só 87 casos/56 positivos para treinar o classificador |
| Fine-tuning parcial do encoder (Fase 13, 3 estágios) | todos abaixo do congelado | GPU de 8 GB limita a poucos blocos; degrada mais do que ajuda |
| Fusão OOF de sinais (Fase 9 e 9B) | nenhuma supera os sinais isolados | correlação 0,89 entre Fase 5 e LoRA — pouca informação complementar |
| Feature de realce por candidato (Etapa B) | AUC 0,49 / 0,55 | ver seção 1.2 |
| RAG textual / GraphRAG | não resolve especificidade | confirmado anteriormente (LLD: 0,00% especificidade com RAG) |

Não repetir essas linhas sem uma mudança estrutural nova (dado, backbone ou
protocolo) que altere a premissa que as fez falhar.

---

## 4. O que é necessário para evoluir

Em ordem de expectativa de valor, dado o diagnóstico da seção 1.3:

### 4.1 Prioridade alta — testar um leitor visual mais forte (MedGemma 27B)

Já que o gargalo é generalização entre domínios (não falta de rótulo ou
feature), a alavanca mais lógica é uma representação visual mais capaz.
**Protocolo já congelado** em
`configs/training/medgemma_27b_transfer_protocol_v1.yaml`, pronto para rodar
assim que o Mac (backend Ollama 27B) estiver disponível. Nenhum trabalho de
engenharia adicional necessário para iniciar.

### 4.2 Prioridade alta — coorte independente

O `docs/120` §10 já previa isso: nenhum resultado atual pode ser chamado de
validação externa, porque as duas coortes disponíveis já foram abertas e
usadas em desenvolvimento retrospectivo repetidas vezes. Para qualquer
alegação além de "promissor retrospectivamente", é necessário:
- uma terceira base pública ainda não tocada, ou
- casos novos coletados prospectivamente,
com protocolo congelado **antes** de abrir os rótulos.

### 4.3 Prioridade média — dado, não algoritmo

Como o domain shift é o gargalo, mais dados de treino **heterogêneos** (mais
datasets, mais scanners, mais protocolos de aquisição) tem mais chance de
ajudar do que mais engenharia sobre os dois datasets atuais. Isso é uma
decisão de aquisição de dados, não de modelagem.

### 4.4 Não recomendado no momento

- Mais fusão de sinais sobre os candidatos atuais (retorno já demonstrado como
  marginal ou negativo).
- Mais feature engineering radiômica/dinâmica sobre os mesmos dois datasets.
- QLoRA do MedGemma nesta GPU (8 GB) — o próprio plano já descarta.

---

## 5. Estado de engenharia (não bloqueia decisão científica, mas precisa de atenção)

- **Working tree muito à frente do último push remoto.** Todo o código deste
  ciclo está commitado localmente (commits `acb7ac5` até `031f7d5`), mas ainda
  não foi enviado ao `origin`. Ação recomendada: revisar e dar `git push`
  quando a equipe validar este relatório.
- **Fase 11 (gate de tempo/memória) e Fase 12 (integração no webapp) não
  foram executadas** — corretamente, já que são condicionadas à aprovação
  estatística que ainda não ocorreu (`docs/120` determina isso
  explicitamente).
- Suíte de testes: **1237 passando, 0 falhas**, cobrindo toda a linha nova
  (fusão, robustez, diagnóstico por subtipo, classificador multiclasse e sua
  ablação).
- Nenhum artefato previamente congelado (Fase 5, Fase 9, Fase 13) foi
  modificado por este ciclo — todas as novas linhas são módulos adicionais,
  verificados por assinatura/hash.

---

## 6. O que pode e o que não pode ser afirmado hoje

**Pode ser afirmado:**
- O ARGOS produziu, pela primeira vez, um candidato que atinge 75%/75% na
  estimativa pontual agregada de 467 casos multicohort (Etapa C).
- O gargalo do desempenho foi isolado experimentalmente: é heterogeneidade
  entre domínios (datasets), não falta de granularidade de rótulo clínico nem
  falta de feature de realce.
- Duas hipóteses de engenharia foram testadas e refutadas com rigor
  (feature de realce; desalinhamento entre fases), evitando investimento
  futuro nessas linhas sem necessidade.

**Não pode ser afirmado:**
- Que o ARGOS atingiu a meta de forma estável ou pronta para uso.
- Que o resultado da Etapa C generaliza para uma coorte nova.
- Que mais engenharia sobre os dois datasets atuais deve produzir ganho
  adicional relevante (a ablação mostra retorno marginal nessa direção).

---

## 7. Próximo passo recomendado

Com o Mac indisponível no momento, a ação imediata é **consolidar este ciclo
como documentado e aguardar** para rodar a Etapa 27B assim que o hardware
estiver acessível — protocolo já pronto, sem trabalho pendente de engenharia
para iniciar esse teste.

---

## 8. Referências

- Plano original: `docs/120_PLANO_DE_ACAO_CLASSIFICADOR_VISUAL_SUPERVISIONADO.md`
- Diário técnico completo (todas as fases, hashes e assinaturas): `docs/121_IMPLEMENTACAO_CLASSIFICADOR_VISUAL_LOG.md`
- Panorama geral do ARGOS: `docs/119_PANORAMA_GERAL_ATUAL_ARGOS.md`
- Protocolo de transferência 27B (congelado, não executado): `configs/training/medgemma_27b_transfer_protocol_v1.yaml`
