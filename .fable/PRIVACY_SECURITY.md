# Privacidade e segurança

## Limite

O repositório e o pack são para engenharia/pesquisa. Não armazenar PHI, credenciais, tokens, senhas, chaves, dumps de ambiente, dados clínicos privados ou labels protegidos.

## Possíveis portadores de PHI

`PatientName`, `PatientID`, UIDs, datas/tempos, private tags, overlays, graphics, burned-in annotations, pixel data, nomes de diretório, logs, screenshots, manifests e metadados indiretos. Remover cabeçalho ou converter para NIfTI não prova desidentificação completa.

## Políticas

- Preferir fixtures sintéticas, phantoms, dados públicos desidentificados/licenciados e subconjuntos mínimos.
- `casos/`, `data/`, `dicom*/`, NIfTI/DICOM/STL e artefatos estão ignorados; `.gitignore` é barreira auxiliar, não controle de acesso.
- UIDs persistidos devem ser hash/pseudônimo quando não forem necessários; relações essenciais requerem política aprovada.
- Antes de exportar/compartilhar: inspeção de tags, private elements, overlays/graphics, pixel/burned-in, nomes e logs.
- Endpoints/serviços devem usar allowlist, limites de payload, validação de path e princípio do menor privilégio.
- XR usa token curto/role-scoped; certificados/chaves Quest ficam fora do Git.
- `.env.docker` e estados locais são ignorados; nunca transcrevê-los ao pack.

## Threats prioritários

Path traversal em upload/artifact serving; zip bomb; symlink/reparse point; DICOM malformado/codec; payload excessivo; command injection em subprocesso; cache poisoning; artefato trocado após hash; sessão XR replay; serviço exposto na LAN; dependência comprometida; prompt injection em corpus RAG/documentos.

## Gates

Detecção ou necessidade de PHI aciona HG-11 e STOP. Claims de conformidade LGPD/segurança clínica acionam HG-12 e revisão jurídica/regulatória; testes de engenharia não bastam.

