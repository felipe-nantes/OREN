# Matriz de risco e autoridade

## LOW

Escopo: imports realmente não usados, typing, ortografia, nomes locais, helper puro, mensagem de erro sem semântica, duplicação mecânica e reorganização demonstravelmente behavior-preserving.

Autoridade: `INVESTIGATE`, `TEST`, `MODIFY` após baseline e testes. Requer suíte focal e global; mutation test quando lógica crítica for tocada. Qualquer efeito possível em saída científica promove a HIGH.

## MEDIUM

Escopo: cache, serialização, filesystem I/O, retry, concorrência, memória, performance, APIs internas, limites de módulos, infraestrutura de model loading e armazenamento de artefatos.

Autoridade: `INVESTIGATE`, `TEST`, `PROPOSE_PATCH`; aplicar somente com evidência forte, reversibilidade e escopo explicitamente autorizado. Promova a HIGH se identidade de artefato, ordem, falha, representação ou resultado puder mudar.

## HIGH_SCIENTIFIC_GEOMETRIC

Inclui: seleção DICOM/fase/série, sequência, coorte, inclusão/exclusão, labels e polaridade, orientação/LPS/RAS/origin/spacing/direction/affine, registration/transform direction, resampling/interpolação, máscara/segmentação/postprocessamento, preprocessing/normalização, embedding/model revision, patient grouping/folds/nested CV, tuning/thresholds, denominadores/falhas, métricas/bootstrap/LODO, subtipos e operações quantitativas de malha.

Autoridade: `INVESTIGATE`, `REPRODUCE`, `WRITE_TESTS`, `IDENTIFY_DEFECT`, `PROPOSE_OPTIONS`, `CREATE_HYPOTHETICAL_PATCH`, `BEFORE_AFTER_ANALYSIS`. Não aplicar mudança semântica sem aprovação explícita no gate pertinente.

## OUT_OF_AUTHORITY

Inclui: diagnóstico, prognóstico, tratamento, prescrição, threshold clínico, segurança/validação clínica, recomendação médica/cirúrgica, definição de “anatomia verdadeira”, advice ao paciente e mudança da pergunta científica.

Autoridade: nenhuma decisão. Pare, documente e solicite autoridade humana qualificada.

## Regra de composição

Risco final é o máximo entre impacto direto, dependência transitiva e possibilidade de falha silenciosa. Uma tarefa multimódulo não faz média de riscos. `HIGH + LOW = HIGH`.

## Matriz operacional

| Impacto | Falha silenciosa | Downstream | Nível mínimo |
|---|---|---|---|
| apenas texto/typing | baixo | local | LOW |
| I/O/cache/performance | médio | controlado | MEDIUM |
| representação/resultado possível | qualquer | qualquer | HIGH |
| clínica/pergunta científica | qualquer | qualquer | OUT_OF_AUTHORITY |

