# Relatório de validação Docker ponta a ponta do ARGOS/OREN

Data da validação: 13 de agosto de 2026.

## Conclusão executiva

O ARGOS/OREN permaneceu funcional após a conteinerização. A validação cobriu o
runtime Docker, a suíte automatizada completa, dois processamentos reais de um
exame DICOM multifásico, o visualizador desktop, os recursos WebXR servidos por
HTTPS, a integração com MedGemma 1.5 4B, Neo4j e Graphify, a persistência de jobs
concluídos e a recuperação depois de reiniciar os contêineres.

O resultado é uma aprovação **funcional e de engenharia**, não uma aprovação
clínica. Docker não comprova sensibilidade, especificidade ou validade médica.

## Ambiente validado

- Windows com Docker Desktop e backend WSL2;
- GPU NVIDIA GeForce RTX 4060 Laptop GPU, aproximadamente 8 GB;
- ARGOS/OREN no contêiner `argos`, executado como usuário não root;
- Nginx como entrada única em HTTP desktop e HTTPS para Meta Quest;
- Neo4j 5.26 Community;
- MedGemma 1.5 4B NF4 no host como modo operacional padrão;
- MedGemma 1.5 4B em contêiner como modo opcional validado;
- caches de modelos, pesos, certificados, casos e estado persistidos fora das
  imagens Docker.

## Regressão automatizada

Comando:

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q
```

Resultado final:

```text
1581 passed, 3 skipped, 0 failed
Tempo: 99,64 segundos
```

Os testes ignorados são opcionais e não representam falhas. A suíte inclui
ingestão, harmonização, segmentação, painéis, MedGemma, benchmark, RAG,
volumetria, artefatos do visualizador, WebXR, webapp, segurança e integração
Docker.

## Verificação visual no navegador

Além dos testes de API, foi executada uma inspeção real no navegador do Codex:

- a página de exame individual carregou com título, navegação, seletor DICOM,
  opção de 3D aprimorado e avisos de pesquisa;
- a página de benchmark carregou com formulário, composição da coorte e botão
  inicialmente bloqueado sem arquivos, como esperado;
- o visualizador do job `e4455b849b88` renderizou o fígado, estruturas internas,
  referência 2D, controles de opacidade, presets, volumetria e qualidade das
  malhas;
- o botão `Medir` ativou a régua tridimensional;
- o preset `Anatomia interna` mudou para o estado ativo;
- não foram observados erros ou avisos no console nessas três páginas.

## Gates do runtime Docker

O verificador operacional aprovou 16 de 16 gates:

1. configuração Compose válida;
2. contêineres obrigatórios saudáveis;
3. webapp em `http://127.0.0.1:8080`;
4. HTTPS local do Quest;
5. HTTPS pela interface LAN;
6. shell do visualizador servido;
7. capacidade de segmentação disponível;
8. ARGOS executado como usuário não root;
9. política offline de modelos ativa;
10. volumes de casos com escrita e pesos somente leitura;
11. ausência de DICOM, NIfTI e resultados médicos na imagem Docker;
12. Neo4j respondendo a consulta Cypher;
13. GPU disponível dentro do contêiner;
14. MedGemma do host saudável;
15. MedGemma do host acessível pelo ARGOS conteinerizado;
16. Graphify disponível no perfil de ferramentas.

Evidência: `artifacts/docker-validation/runtime-verification.json`.

## Smoke test real 1 — fluxo padrão

Fonte autorizada:

```text
C:\Users\profurg\Desktop\sander\MOSTRUARIO_DICOM_ALTA_QUALIDADE\casos\03_TCGA-DD-A4NJ
```

Foram enviados 352 arquivos DICOM, distribuídos igualmente em pré-contraste,
arterial, venosa e tardia. O job `281772ff1f00` concluiu ingestão, segmentação,
geração de painéis, classificação, localização candidata, máscara de união e
modelo 3D.

Resultados:

- estado final `concluido`;
- visualizador pronto;
- 14 malhas;
- 3 painéis RGB;
- 113 artefatos autorizados baixados e conferidos por SHA-256;
- gate de reconstrução do órgão aprovado;
- isolamento do ground truth aprovado;
- separação de papéis WebXR paciente/clínico aprovada;
- tentativa de path traversal rejeitada;
- tempo interno total: 247,2825 s;
- tempo observado pelo cliente: 253,852 s;
- volume hepático calculado: 1970,7831 mL.

Evidências:

- `artifacts/docker-validation/e2e-smoke.json`;
- `artifacts/docker-validation/job-281772ff1f00-verification.json`.

## Smoke test real 2 — 3D aprimorado

O mesmo exame foi processado com a segmentação 3D aprimorada. O job
`e4455b849b88` concluiu todas as etapas, inclusive
`segmentacao_3d_aprimorada`.

Resultados:

- estado final `concluido`;
- visualizador pronto;
- 14 malhas;
- 3 painéis RGB;
- 102 artefatos autorizados conferidos por SHA-256;
- gate de reconstrução do órgão aprovado;
- persistência do estado final aprovada;
- recuperação do job após reinício do ARGOS aprovada;
- nova verificação independente após o reinício aprovada;
- tempo interno total: 252,4353 s;
- tempo observado pelo cliente: 256,340 s;
- volume hepático calculado: 1569,9257 mL.

Tempos internos por etapa:

| Etapa | Segundos |
|---|---:|
| Ingestão e segmentação inicial | 59,8117 |
| Painéis | 4,4843 |
| Classificação | 10,7400 |
| Localização candidata | 25,2926 |
| Segmentação 3D aprimorada | 89,9660 |
| Modelo 3D | 62,1254 |

Evidências:

- `artifacts/docker-validation/e2e-smoke-enhanced-3d.json`;
- `artifacts/docker-validation/job-e4455b849b88-final-verification.json`.

## MedGemma opcional em contêiner

O perfil `medgemma-container` foi testado isoladamente e aprovado:

- modelo carregado: `google/medgemma-1.5-4b-it`;
- quantização NF4;
- CUDA ativa;
- GPU RTX 4060 reconhecida;
- contrato `dtwin-medgemma-v1` saudável;
- backend ARGOS reconheceu o serviço como pronto;
- nenhuma porta do MedGemma foi publicada no host;
- o script de teste restaurou o modo híbrido com MedGemma no host ao terminar.

Evidência: `artifacts/docker-validation/medgemma-container-verification.json`.

## Resiliência e segurança verificadas

- jobs concluídos são persistidos atomicamente em `webapp_job_state.json`;
- o endpoint de status restaura jobs concluídos após reinício;
- artefato adulterado impede a restauração, em vez de fabricar sucesso;
- o Nginx é recriado quando necessário para não reter o IP interno antigo do
  contêiner ARGOS;
- alternância host/contêiner do MedGemma evita duas instâncias concorrentes;
- o serviço opcional do MedGemma aceita `0.0.0.0` somente com o marcador privado
  `ARGOS_CONTAINER=1`;
- o modo padrão no host continua restrito ao loopback;
- dados médicos e pesos não são incorporados às camadas da imagem;
- caminhos arbitrários e path traversal são rejeitados pelo verificador.

## Limitações encontradas

1. **Meta de 180 segundos não atingida neste notebook.** Os dois fluxos reais
   levaram aproximadamente 247 e 252 segundos internamente. A conteinerização é
   funcional, mas o gate histórico de até 3 minutos permanece aberto.
2. **Partição de Couinaud não aprovou o gate de cobertura.** As malhas são
   disponibilizadas como evidência complementar, mas não devem ser tratadas como
   uma partição volumétrica completa do fígado.
3. **Diferença de volumetria entre os modos.** O fluxo padrão calculou 1970,8 mL
   e o aprimorado 1569,9 mL no mesmo exame. Isso decorre de máscaras diferentes
   e precisa de validação contra referência antes que um modo seja declarado
   volumetricamente autoritativo.
4. **A validação real usou um exame multifásico.** Ela prova integração ponta a
   ponta, não robustez em uma coorte diversa.
5. **Meta Quest não foi usado fisicamente nesta rodada.** Foram testados HTTPS,
   entrega dos recursos XR, manifesto, papéis e autorizações. Interação manual,
   conforto, tracking e desempenho dentro do headset ainda exigem smoke humano.
6. **A classificação foi preservada como saída de pesquisa.** Nenhum resultado
   foi convertido em aprovação clínica e nenhum ground truth foi usado na
   inferência.
7. Os avisos de depreciação da suíte não quebram o runtime atual, mas devem ser
   tratados antes de atualizações maiores de NumPy, scikit-image, Starlette e
   scikit-learn.

## Critério de aceite obtido

O ciclo Docker pode ser considerado concluído para operação experimental porque:

- o fluxo DICOM real chega a relatório, painéis, volumetria e visualizador 3D;
- o modo padrão e o 3D aprimorado concluem em contêiner;
- os artefatos são verificáveis por hash;
- jobs sobrevivem ao reinício do backend;
- desktop e Quest compartilham a mesma instância e o mesmo estado;
- MedGemma host e MedGemma opcional conteinerizado foram validados;
- 1.581 testes automatizados passaram sem falhas;
- os limites clínicos e de desempenho permanecem explicitamente abertos.

## Reexecução

```powershell
# Iniciar o modo recomendado
powershell -ExecutionPolicy Bypass -File tools\start_argos_docker.ps1

# Verificar os 16 gates operacionais
powershell -ExecutionPolicy Bypass -File tools\verify_argos_docker_runtime.ps1

# Verificar um job concluído
.\.venv-win\Scripts\python.exe tools\verify_argos_docker_job.py `
  --http-base http://127.0.0.1:8080 `
  --https-base https://192.168.15.10:8443 `
  --job-id e4455b849b88

# Validar temporariamente o MedGemma em contêiner e restaurar o host
powershell -ExecutionPolicy Bypass -File tools\verify_medgemma_container.ps1

# Regressão completa
.\.venv-win\Scripts\python.exe -m pytest -q
```
