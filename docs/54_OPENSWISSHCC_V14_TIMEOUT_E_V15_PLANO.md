# OpenSwissHCC — reprovação temporal v14 e transição para v15

Data: 2026-07-16

## Conclusão do v14

O protocolo v14 de escore volumétrico contínuo não cumpriu o requisito
operacional de 180 segundos em 100% dos casos e está reprovado como candidato à
qualificação.

Não foram calculadas métricas de acurácia e o holdout permaneceu fechado.

## Evidência observada

- 52 resultados cegos completos e válidos;
- tempos dos casos persistidos entre 105,1801 s e 159,5842 s;
- zero resultados persistidos acima de 180 s;
- caso 53 sem resultado persistido após timeout HTTP de 180 s;
- o runner abortou imediatamente;
- nenhum retry automático foi realizado;
- a passagem órfã continuou usando a GPU depois do cliente abandonar a conexão;
- o gateway precisou ser encerrado para liberar a GPU.

Caso que falhou:

```text
índice: 53/87
case_id: anon-openswiss-7e1337c532007417
quantidade de cortes: 44
manifest SHA-256: 3151f64f6b2185fa4bda0573ed9b83e1982ff740aaa2778b486142e0708bd709
cobertura hepática declarada: 100%
```

O caso não tinha a maior pilha possível. Portanto, não é defensável interpretar
o evento apenas como consequência de 50 cortes. A execução contínua, estado do
runtime, memória/driver e custo específico da pilha podem contribuir. Para o
gate do projeto, a causa operacional exata não altera o resultado: uma análise
excedeu três minutos.

## Integridade metodológica

O caso que sofreu timeout não será repetido e contado como sucesso dentro do
v14. Fazer isso violaria:

- o protocolo congelado com zero retries automáticos;
- o requisito de uma análise em até 180 segundos;
- a exigência de 100% dos casos dentro do teto;
- a auditabilidade do benchmark.

Os 52 resultados válidos permanecem preservados apenas como artefatos de
desenvolvimento e diagnóstico técnico. O v14 não pode abrir o holdout.

## Proposta v15

O v15 preservará:

- `google/medgemma-1.5-4b-it`;
- runtime CUDA com NF4;
- T1 venosa axial;
- mesmo prompt pathology-target;
- mesmo método `first_token_restricted_softmax_v1`;
- mesmas três classes e prefixo protegido;
- uma requisição por caso;
- zero retries automáticos;
- mesmo gate de 180 segundos;
- nenhuma leitura de labels na preparação/inferência;
- holdout fechado e revisão humana obrigatória.

A única mudança de representação será:

```text
máximo de cortes por caso: 32
amostragem: equidistante no intervalo axial hepático
```

Esse teto é definido por restrição operacional, antes de observar qualquer
relação entre os escores v15 e os labels. Ele reduz o custo de atenção
multimodal e cria margem para variação de runtime.

## Ordem obrigatória

1. preparar um novo bundle cego com 32 cortes;
2. validar hashes, ordem, cobertura declarada e salvaguardas;
3. congelar um novo protocolo e assinatura v15;
4. iniciar o gateway em estado limpo;
5. executar duas réplicas planejadas do caso que falhou no v14;
6. exigir determinismo dentro de `1e-6`;
7. exigir ambas as réplicas abaixo de 150 segundos, criando margem mínima de
   30 segundos para o gate de 180 segundos;
8. somente então iniciar os 87 casos cegos;
9. abortar na primeira falha de contrato, hash ou tempo;
10. somente após 87/87 permitir avaliação com labels de desenvolvimento,
    mediante autorização explícita.

O piloto v15 usa um gate interno mais conservador de 150 segundos para decidir
se vale executar a coorte. O requisito final do projeto continua sendo 180
segundos por análise.

## Critérios de parada

O v15 deve ser abandonado antes da coorte completa se:

- uma das duas réplicas do caso crítico exceder 150 segundos;
- os escores divergirem acima de `1e-6`;
- houver passagem órfã, timeout ou erro de contrato;
- a redução de cortes alterar qualquer salvaguarda de segurança;
- qualquer label ou máscara de lesão entrar na inferência.

