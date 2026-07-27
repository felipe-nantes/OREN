# OpenSwissHCC — remediação técnica v2

## Estado de entrada

A galeria v1 continha 88 candidatos congelados sob a assinatura:

```text
074b5673c4aa0ccbef0d8cf2bc4ed17fa190c16b2843a1de20cc21983fb7a93c
```

A revisão humana declarou 21 casos problemáticos:

- 19 com código `M` (alinhamento/fusão visual não aceitável);
- 5 com código `C` (enquadramento/corte não aceitável), sobrepostos aos anteriores
  em quatro casos;
- 1 com código `I` (imagem inexistente na galeria).

Os 21 IDs e códigos estão em
`development_review_triage_v1/technical_triage.json`. A declaração contém
somente qualidade técnica, sem diagnóstico, label ou ground truth.

Existe uma discrepância ainda não resolvida: o revisor informou 66 aprovados,
mas forneceu 21 pendentes; 88 menos 21 resulta em 67. A galeria v2 deve ser
usada para identificar o caso restante antes da assinatura autoritativa.

## Incidente do painel ausente

O diretório de `anon-openswiss-5e519974f0a2c3e8` estava ausente, embora o freeze
e a galeria ainda apontassem para ele. O candidato foi reconstruído usando as
entradas neutras, o alinhamento congelado e a mesma configuração. O PNG
reconstruído produziu exatamente o SHA-256 esperado:

```text
efe6f726cd4288b206e87dc949e2fe7b89ea653d53df129bf1203aeacf4991a4
```

Uma cópia antiga e idêntica com sufixo `_a` estava dentro da raiz candidata e
criava um 89º diretório inválido. Ela foi preservada em `prepared/quarantine/`,
fora da coorte. Depois disso, a verificação integral do freeze v1 voltou a
passar com 88 casos, `ground_truth_read=false` e `inference_executed=false`.

## Política de remediação

A coorte v1 nunca é sobrescrita. A CLI
`tools.remediate_openswisshcc_candidates` cria uma raiz v2 atômica:

- `M` ou `C`: novo painel venoso monocromático, sem RAG, `uniform_9`, sem
  overlay e com margem de recorte hepático ampliada de 15% para 30%;
- somente `I`: candidato fonte restaurado e mantido;
- sem código: arquivos copiados byte a byte, com hash idêntico ao freeze v1.

O motivo auditável do fallback de revisão é:

```text
human_review_alignment_or_framing_failure
```

A remediação não remove casos. O resultado esperado continua sendo 88 casos:
20 fallbacks de revisão, 1 candidato restaurado mantido e 67 candidatos
inalterados.

## Comando de construção

```powershell
.\.venv-win\Scripts\python.exe -B -m tools.remediate_openswisshcc_candidates `
  --source-panels casos/qualification/openswisshcc_v1/prepared/development_candidate_v1 `
  --source-freeze casos/qualification/openswisshcc_v1/prepared/development_experiment_v1/experiment_freeze.json `
  --inputs casos/qualification/openswisshcc_v1/prepared/development_v1 `
  --triage casos/qualification/openswisshcc_v1/prepared/development_review_triage_v1/technical_triage.json `
  --out casos/qualification/openswisshcc_v1/prepared/development_candidate_v2
```

## Próximo gate

Depois da construção:

1. congelar a coorte v2 com a configuração de fallback de revisão;
2. gerar a galeria v2;
3. revisar todos os painéis alterados e esclarecer a discrepância 66/21;
4. gerar o manifesto humano autoritativo dos 88 casos;
5. somente então executar o MedGemma 1.5 4B.

Nenhum ganho de acurácia é alegado nesta etapa. A finalidade é impedir que
painéis tecnicamente inválidos contaminem o benchmark.

## Resultado executado

A construção v2 foi concluída em 14 de julho de 2026 com:

- 88 candidatos publicados atomicamente;
- 67 candidatos inalterados, com SHA-256 idêntico à v1;
- 1 candidato ausente reconstruído e mantido com o hash congelado original;
- 20 fallbacks venosos de revisão;
- 68 candidatos multifásicos RGB e 20 candidatos monocromáticos;
- 0 painel ausente, 0 divergência de hash e 0 relatório MedGemma produzido;
- `ground_truth_read=false` e `inference_executed=false`.

O primeiro ensaio de construção foi abortado antes da publicação porque dois
nomes temporários aninhados ultrapassaram o limite de caminho usado pelo PIL no
Windows. O staging externo passou a usar o prefixo curto `._rem_<8-hex>`. A
repetição concluiu os 88 casos e não deixou diretórios parciais.

O freeze v2 usa a versão explícita:

```text
openswisshcc-development-medgemma-4b-v2-review-remediated
```

Assinatura verificada:

```text
0c933740c159579d19d4fe33b10784ca376dc795e5f2dd64b38c3c7b05eac80c
```

Artefatos:

```text
prepared/development_candidate_v2/
prepared/development_experiment_v2/experiment_freeze.json
prepared/development_review_gallery_v2/index.html
```

A galeria v2 contém 88 links válidos e continua
`authoritative_approval=false`. A inferência permanece bloqueada até a revisão
humana integral e a criação do manifesto assinado.

## Segunda revisão humana — caso 72

A revisão humana da galeria v2 aprovou tecnicamente 87 casos e reprovou o item
72, `anon-openswiss-cb2c5c63fc28b8ee`, por não permitir distinguir o fígado
com segurança. O caso foi classificado como falha técnica de qualidade `Q` e
permanece bloqueado para inferência.

A análise de intensidade, usando apenas a fase venosa e a máscara hepática,
mostrou janela global original aproximada de `0–331`. Foi gerada uma variante
isolada com percentis `20–95`, janela aproximada de `1–253`, sem overlay,
RAG, máscara de lesão ou ground truth:

```text
config: medgemma_local_4b_venous_review_fallback_high_contrast_pathology.yaml
painel: development_candidate_v2_case72_contrast_trial/
SHA-256: 712844659d4dfba1403e452c565b69dd3da3b7b540bae14c74bd45e1a9c9b826
```

Essa variante é apenas um trial técnico: não pertence ao freeze v2 e não pode
ser inferida até receber aprovação humana e ser formalizada em novo freeze.

## Coorte final v3 e aprovação humana

O revisor humano aprovou a variante de alto contraste do caso 72. A coorte
final `development_candidate_v3_final` preserva 87 painéis byte a byte e
substitui somente `anon-openswiss-cb2c5c63fc28b8ee` pelo painel aprovado.

Composição final:

- 68 candidatos multifásicos RGB;
- 19 fallbacks venosos de revisão;
- 1 fallback venoso de alto contraste;
- 88 casos aprovados para inferência de pesquisa.

Assinaturas finais:

```text
freeze v3: 5639f77d0b78f8be0711a8022423b6e260bd25814c868909c65f9216fa9b516a
revisão humana: 0d8b816989ab9873c0ac3a2faf7b2e987036fcba623912d37b5333e1424f0005
```

O executor passou a aceitar variantes adicionais somente por chave fechada e
SHA-256 exato do YAML congelado. Caminhos arbitrários não são aceitos pelo
candidato. O preflight final validou as três configurações nos 88 casos, e a
suíte completa terminou com 416 testes aprovados. Nesse ponto,
`ground_truth_read=false` e nenhuma saída da rodada v3 existia.


