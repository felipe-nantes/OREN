# ROB-09 — Proposta de política de storage/retention/de-ID (SR-010, W-020)

Data: 2026-08-25 · **PROPOSTA para o gate HG-11** — nada aqui entra em vigor
sem ratificação humana. Nenhum PHI foi lido, movido ou inserido no pack para
escrever este documento (só estrutura de diretórios e o código já auditado).

## O problema (SR-010, verificado no código)

1. `raw_dicom_phase_resolver._materialize` hardlinka/copia os **bytes DICOM
   originais** para `resolved_raw_phases/`, enquanto o manifesto declara
   `phi_persisted: false` — a declaração e a realidade divergem.
2. Cada job do webapp retém em `casos/webapp/<job>/`: `_upload/` (DICOM
   bruto como chegou) e `case/` (derivados). Não há TTL: uploads persistem
   indefinidamente.
3. A conversão a NIfTI descarta headers, mas ninguém detecta **burned-in
   PHI** (texto queimado no pixel); o demo autoassume a confirmação humana
   que o stage1 documenta como exigida.

## Política proposta (para decisão, item a item)

**P1 — Correção da declaração (código, pequena).** O manifesto do resolver
passa a declarar `phi_persisted: true` enquanto os DICOM materializados
existirem, OU o resolver ganha uma etapa de limpeza pós-conversão que
apaga `resolved_raw_phases/` após o NIfTI ser validado — aí a declaração
volta a ser verdadeira. Recomendação: a segunda (limpeza), pois os bytes
originais seguem em `_upload/`.

**P2 — TTL de uploads.** `_upload/` de jobs CONCLUÍDOS é elegível a remoção
após N dias (proposta: 30), mantendo `case/outputs/` (derivados sem header).
Jobs não concluídos: manter até revisão. Execução SEMPRE por comando
explícito do operador (nunca automática nesta fase), com lista prévia.

**P3 — Escopo de retenção do DICOM original.** Para casos que alimentaram
resultados publicados/congelados: reter o original ENQUANTO a política de
pesquisa exigir re-verificação (posição conservadora: reter, com registro).
Para demos/smoke: elegíveis a P2.

**P4 — Burned-in PHI.** Sem detector automático confiável no repositório
hoje. Proposta honesta: (a) o disclaimer do viewer continua exigindo revisão
humana; (b) NENHUMA imagem derivada sai de `casos/` para docs/pack/Git sem
inspeção visual humana registrada (regra já implícita na Figura 6 do
manuscrito — "inserir imagens reais anonimizadas e autorizadas").

**P5 — Backup/migração.** Cópias para o SSD (D:) herdam a mesma política;
`casos/webapp` NÃO migrou (decisão de 2026-08-24) e qualquer migração futura
segue verificação por comparação direta antes de qualquer remoção de origem.

## O que esta proposta NÃO faz

- Não apaga nada agora; não altera código sem o gate; não introduz detector
  de PHI "mágico" (seria falsa segurança); não muda contratos científicos.

## Decisões pedidas ao operador (HG-11)

1. Ratificar P1 (qual variante: declarar `true` OU limpar pós-conversão)?
2. Ratificar P2 com N=30 dias (ou outro N)?
3. Ratificar P3 (retenção conservadora p/ casos de resultados congelados)?
4. Ratificar P4/P5 como regras operacionais permanentes?
