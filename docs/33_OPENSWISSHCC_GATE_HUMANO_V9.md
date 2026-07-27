# OpenSwissHCC v9 — coorte multissequência e gate humano

Data: 2026-07-14

## Artefatos publicados

- Coorte: `casos/qualification/openswisshcc_v1/prepared/development_multisequence_cohort_v9`
- Galeria: `casos/qualification/openswisshcc_v1/prepared/development_review_gallery_v9_multisequence/index.html`
- Casos: 88
- Painéis: 2.149
- Máximo por caso: 37
- Assinatura da coorte: `64782bda03f1d393df51a6d61032ce4b61d18a814393634273027537b4bc6589`
- Assinatura da galeria: `ffad4db41e669e0fa8087f66d401a73217e62024b0f1472f2187cb15b8254b9d`

Nenhuma inferência foi executada. Ground truth e máscaras de lesão permaneceram isolados.

## Limitação de campo de visão

Doze tiles T2 BLADE, distribuídos em sete casos, não possuem ponto hepático correspondente no mesmo plano TRACE. Eles são exibidos explicitamente como `FORA DO FOV NESTE PLANO TRACE` e registrados com `available_in_fov=false`.

Não houve recorte forçado, extrapolação nem substituição por outro plano. Os demais tiles mantêm coordenadas físicas válidas.

## O que revisar

Em cada caso, verificar:

1. se T1 venoso, T2, TRACE e ADC representam anatomia compatível;
2. se o contorno ciano permanece limitado ao fígado no T1;
3. se cortes extremos ainda têm contexto anatômico útil;
4. se o contraste nativo permite distinguir o fígado;
5. se os avisos de T2 fora do FOV correspondem realmente à ausência de cobertura;
6. se não há PHI ou informação de diagnóstico visível.

Registrar caso e painel de qualquer discordância. A galeria não autoriza inferência automaticamente.

## Evidência de software

- testes focalizados do lote/galeria: aprovados;
- validação de caminhos relativos: aprovada;
- hashes de todos os painéis validados durante a construção da galeria;
- suíte completa: 458 testes aprovados, nenhuma falha.

## Próximo passo condicionado

Após aprovação humana da galeria, congelar as assinaturas e executar um piloto balanceado cego com MedGemma 1.5 4B. Medir sensibilidade, especificidade, inconclusivos, falhas e tempo por caso. Não abrir o holdout antes da seleção final.
