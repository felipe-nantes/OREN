# OpenSwissHCC v22 — localizador venoso + arterial registrada

## Hipótese

O localizador `liver_lesions_mr` aplicado apenas à fase venosa atingiu recall
retrospectivo por caso de 56,76%. No v22-b, 10 dos 11 falsos negativos do melhor
sinal dinâmico não tinham candidato atingindo a lesão anotada. A próxima
hipótese é recuperar candidatos visíveis na fase arterial sem introduzir
ground truth na inferência.

## Contrato

O algoritmo `venous-registered-arterial-union-v22`:

1. preserva a máscara candidata venosa congelada;
2. executa uma passada adicional do mesmo TotalSegmentator na arterial já
   registrada para a geometria venosa;
3. usa somente a máscara automática do fígado como crop;
4. valida geometria e hashes;
5. calcula a união binária exata dos candidatos venosos e arteriais;
6. registra voxels novos, tempos por fase e tempo combinado;
7. não lê labels ou máscaras públicas de lesão e não toma decisão clínica.

No Windows, a execução usa runtime TotalSegmentator isolado e bloqueia o módulo
opcional `pyarrow` somente nos workers `spawn`. Isso evita a falha transacional
`WinError 6714` já documentada, sem alterar o ambiente Python global.

Casos sem registro permanecem com o candidato venoso e são declarados como
fallback. O orçamento combinado do localizador é 150 s, deixando margem para
renderização, extração de features e MedGemma dentro do teto final de 180 s.

## Gate piloto

Antes de executar os 87 casos, uma seleção de desenvolvimento deve verificar:

- ganho de recall nas lesões que o venoso não atingiu;
- aumento de falsos candidatos e volume candidato;
- tempo combinado máximo;
- integridade do manifesto e ausência de ground truth na execução.

As máscaras venosas públicas de desenvolvimento podem ser usadas somente após
a geração cega para auditoria retrospectiva. As máscaras do holdout v21
permanecem fechadas.

## Resultado do piloto arterial

O piloto cego executou 10 casos: seis positivos sem localização venosa, dois
positivos localizados e dois negativos com falso candidato. O tempo combinado
venoso + arterial teve média de 53,89 s e máximo de 73,73 s.

Na auditoria retrospectiva dos oito casos com máscaras venosas públicas:

- o venoso atingia 2/8 casos;
- a união venoso + arterial atingiu 3/8;
- apenas 1/6 perdas venosas foi recuperada;
- um negativo recebeu 11.258 voxels candidatos arteriais novos;
- nenhum dado de ground truth entrou na execução e o holdout não foi aberto.

O ganho de recall foi insuficiente diante do ruído adicional. Por isso, a
passada arterial não será expandida ao full87 nem adicionada ao protocolo de
produção. O próximo experimento usará propostas determinísticas de realce sobre
todo o fígado, evitando depender de uma localização venosa prévia.
