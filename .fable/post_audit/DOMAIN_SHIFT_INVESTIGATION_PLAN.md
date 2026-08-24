# DOMAIN_SHIFT_INVESTIGATION_PLAN — eixo prioritário do ciclo

Base de evidência: SR-007 (probes de origem 100% em embeddings, 98,75% em
medidas físicas — docs/131:21,85, docs/134:53), transferência LLD→OpenSwiss
com perda documentada, LODO existente, classes `*_unspecified` específicas de
OpenSwiss.

## Regra de ouro

**NÃO propor "remover informação de domínio" antes de MEDIR.** O sinal de
origem pode estar correlacionado com anatomia, aquisição, prevalência ou
outros fatores legítimos. Remoção cega pode destruir sinal clínico real ou
apenas esconder o shortcut. A sequência obrigatória:

1. medir ONDE o sinal entra (H-01 é o primeiro degrau);
2. medir SE o classificador o usa além do label (análises condicionais);
3. só então propor intervenção — como MICROEXPERIMENT gated (HG-06/07),
   uma variável por vez, com origin probe antes/depois como endpoint.

Separabilidade ≠ uso: uma probe de 100% prova que a informação EXISTE na
representação, não que a decisão depende dela.

## Fontes candidatas de informação de domínio

| # | Fonte | EVIDENCE | CAN_TEST_WITHOUT_CHANGING_MODEL? | TEST | EXPECTED_RESULT | INTERPRETATION | RISK |
|---|---|---|---|---|---|---|---|
| D1 | Aquisição (protocolo/sequência) | manuscrito: transfer loss; SR-007 | SIM | probe sobre metadados de aquisição vs origem (artefatos congelados) | separabilidade alta esperada | aquisição é proxy quase perfeito de coorte — inevitável; medir magnitude | interpretativo |
| D2 | Resolução/spacing | medidas físicas separam a 98,75% (docs/134) | SIM | probe usando apenas spacing/shape | já quase confirmado | se spacing sozinho separa, harmonização geométrica é canal | baixo |
| D3 | Orientação/direction | specs PH09 (direções variam entre aquisições) | SIM | distribuição de direction por coorte | provável assimetria | canal geométrico secundário | baixo |
| D4 | Disponibilidade de sequência (t2/dwi presentes ou não) | ingest multifase; variantes t2dwi existem | SIM | tabela presença×coorte | assimetria provável | ausência estrutural de sequência é vazamento de coorte via composição de painel | médio (interseção com D8) |
| D5 | Distribuição de intensidade | enhancement vs edgeonly variants congeladas | SIM (H-01) | probe por variante (H-01) | edgeonly < cru, se intensidade domina | localiza canal de intensidade | baixo |
| D6 | Reconstrução/vendor/scanner | metadados DICOM originais retidos (DOM-002) | SIM | inventário de vendor tags por coorte (sem PHI) | separação alta esperada | proxy de coorte; irremovível — quantificar apenas | HG-11 se tocar tags |
| D7 | Composição do painel | painéis gerados por caso; regras por fase | SIM | contagem/layout de painéis por coorte | possível assimetria | painel pode codificar coorte por estrutura, não conteúdo | médio |
| D8 | Preprocessing/crop geometry | fixed_crop vs crop variants congeladas | SIM (H-01) | probe fixed vs adaptativo | se adaptativo>fixed, crop vaza tamanho/forma de aquisição | baixo |
| D9 | Fundo/background | edgeonly variant congelada | SIM (H-01) | probe edgeonly vs cru | se cru≫edgeonly, fundo/textura global vaza | baixo |
| D10 | Segmentação (máscara fonte) | máscaras por backend/coorte | PARCIAL | estatísticas de máscara por coorte (volume, borda) | diferenças prováveis | anatomia real também difere entre coortes — cuidado | interpretativo |
| D11 | Vazamento por metadados no caminho de features | assert_label_blind_record existe (schemas.py) | SIM | auditoria estática dos campos que entram na featurização | esperado limpo (guard existe) | se algo passa, é bug — vira CORRECTNESS gated | baixo |
| D12 | Padrões de falha | 16 falhas; H-02 | SIM | distribuição de falhas por coorte (H-02) | assimetria possível | falha correlacionada com coorte distorce comparação | baixo |
| D13 | Estrutura de labels específica de coorte | SR-007: `*_unspecified` OpenSwiss-only | SIM (fase A de H-05) | contribuição por classe×coorte nos scores congelados | contribuição não trivial esperada | se alta, vocabulário é canal — intervenção só via H-05 fase B gated | médio |

## Sequenciamento

1. **DS-PROBE-01 (= H-01)**: D5/D8/D9 de uma vez, via probes comparativas
   entre variantes congeladas. Primeira task do ciclo (ver FIRST_TASK.md).
2. D2/D3/D4/D12: análises de metadados/presença — baratas, sem GPU, podem
   compor a mesma sessão ou a seguinte.
3. D13 (H-05 fase A) e D7: análises de score/painel.
4. D1/D6/D10: quantificação de proxies inevitáveis (para calibrar
   expectativa: quanto de separabilidade é irredutível).
5. Qualquer INTERVENÇÃO decorrente: MICROEXPERIMENT gated (HG-06/07),
   endpoints obrigatórios incluem origin probe antes/depois, LODO e por-coorte.

## Critério de sucesso do eixo

Não é "zerar a probe de origem" (provavelmente impossível e possivelmente
indesejável). É: (a) mapa quantitativo de canais; (b) distinção
medida entre separabilidade estrutural (aquisição/anatomia) e shortcut
acionável; (c) no máximo 1-2 hipóteses interventivas bem fundamentadas para
OPT_04, cada uma com predição falsificável de LODO/transfer.
