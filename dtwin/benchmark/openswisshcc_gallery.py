"""Galeria local, não autoritativa, para revisão humana dos painéis OpenSwissHCC."""
from __future__ import annotations

import json
import os
import shutil
import uuid
from html import escape
from pathlib import Path
from typing import Any

from dtwin.benchmark.openswisshcc_alignment import _publish_directory
from dtwin.benchmark.openswisshcc_freeze import verify_experiment_freeze
from dtwin.core import PipelineError

GALLERY_SCHEMA = "argos-openswisshcc-review-gallery-v1"


def _html(entries: list[dict[str, Any]], experiment_signature: str) -> str:
    serialized = json.dumps(entries, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c")
    signature = escape(experiment_signature)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' file:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>ARGOS — revisão OpenSwissHCC</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; background:#0b1220; color:#e5edf8; }}
body {{ margin:0; }}
header {{ position:sticky; top:0; z-index:5; background:#111b2e; border-bottom:1px solid #29405f; padding:16px 22px; }}
h1 {{ margin:0 0 8px; font-size:20px; }}
.notice {{ color:#f8d477; font-weight:700; }}
.toolbar {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:10px; }}
button {{ background:#1d3557; color:#fff; border:1px solid #4977a8; border-radius:7px; padding:8px 12px; cursor:pointer; }}
button:hover {{ background:#284a75; }}
#progress {{ font-variant-numeric:tabular-nums; font-weight:700; }}
main {{ max-width:1500px; margin:auto; padding:20px; display:grid; grid-template-columns:repeat(auto-fit,minmax(520px,1fr)); gap:18px; }}
.card {{ background:#111b2e; border:2px solid #29405f; border-radius:10px; overflow:hidden; }}
.card.complete {{ border-color:#38a169; }}
.meta {{ padding:12px 14px; display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; }}
.kind {{ color:#9fc5e8; }}
.fallback {{ color:#ffcf70; }}
.hash {{ font-family:ui-monospace, monospace; font-size:11px; color:#9cadc4; word-break:break-all; }}
.image-wrap {{ background:#000; text-align:center; }}
img {{ width:100%; height:auto; display:block; image-rendering:auto; }}
fieldset {{ border:0; border-top:1px solid #29405f; margin:0; padding:12px 14px; display:grid; gap:9px; }}
label {{ display:flex; gap:9px; align-items:flex-start; cursor:pointer; }}
input {{ margin-top:3px; transform:scale(1.15); }}
.hidden {{ display:none !important; }}
footer {{ padding:20px; color:#9cadc4; text-align:center; }}
</style>
</head>
<body>
<header>
  <h1>ARGOS — revisão visual de 88 painéis OpenSwissHCC</h1>
  <div class="notice">Checklist auxiliar. Não aprova inferência e não substitui o manifesto assinado.</div>
  <div>Experimento: <code>{signature}</code></div>
  <div class="toolbar">
    <span id="progress">0/0 casos completos</span>
    <button data-filter="all">Todos</button>
    <button data-filter="pending">Pendentes</button>
    <button data-filter="fallback">Fallbacks</button>
    <button id="copy">Copiar atestado auxiliar</button>
    <button id="clear">Limpar checklist local</button>
  </div>
</header>
<main id="grid"></main>
<footer>Uso exclusivo em pesquisa. Nenhum label ou ground truth está presente nesta galeria.</footer>
<script>
const entries = {serialized};
const experimentSignature = {json.dumps(experiment_signature)};
const storageKey = `argos-review-${{experimentSignature}}`;
let state = {{}};
try {{ state = JSON.parse(localStorage.getItem(storageKey) || '{{}}'); }} catch (_) {{ state = {{}}; }}
const criteria = [
  ['no_visible_phi','Sem nome, ID, data ou instituição visível'],
  ['image_quality','Alinhamento RGB aceitável ou qualidade venosa aceitável no fallback'],
  ['liver_framing','Fígado corretamente enquadrado e legível']
];
const grid = document.getElementById('grid');
function completed(id) {{ return criteria.every(([key]) => state[id]?.[key] === true); }}
function save() {{ try {{ localStorage.setItem(storageKey, JSON.stringify(state)); }} catch (_) {{}} update(); }}
function render() {{
  for (const item of entries) {{
    const card = document.createElement('article');
    card.className = 'card'; card.dataset.id = item.case_id; card.dataset.kind = item.candidate_kind;
    const kindClass = item.candidate_kind === 'venous_single_phase_fallback' ? 'fallback' : 'kind';
    const kindText = item.candidate_kind === 'venous_single_phase_fallback' ? 'FALLBACK VENOSO' : 'MULTIFÁSICO RGB';
    card.innerHTML = `<div class="meta"><div><strong>${{item.sequence}}. ${{item.case_id}}</strong><br><span class="${{kindClass}}">${{kindText}}</span></div><div class="hash">SHA-256: ${{item.panel_sha256}}</div></div><a class="image-wrap" href="${{item.image}}" target="_blank" rel="noopener"><img loading="lazy" src="${{item.image}}" alt="Painel pseudonimizado ${{item.case_id}}"></a>`;
    const fieldset = document.createElement('fieldset');
    for (const [key,text] of criteria) {{
      const label = document.createElement('label');
      const box = document.createElement('input'); box.type='checkbox'; box.checked=state[item.case_id]?.[key] === true;
      box.addEventListener('change', () => {{ state[item.case_id] ||= {{}}; state[item.case_id][key]=box.checked; save(); }});
      label.append(box, document.createTextNode(text)); fieldset.append(label);
    }}
    card.append(fieldset); grid.append(card);
  }}
  update();
}}
function update() {{
  let done=0; for (const item of entries) {{ const card=document.querySelector(`[data-id="${{item.case_id}}"]`); const ok=completed(item.case_id); card?.classList.toggle('complete',ok); if(ok) done++; }}
  document.getElementById('progress').textContent=`${{done}}/${{entries.length}} casos completos`;
}}
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {{
  const filter=button.dataset.filter; document.querySelectorAll('.card').forEach(card => {{ const hide=filter==='pending' ? completed(card.dataset.id) : filter==='fallback' ? card.dataset.kind!=='venous_single_phase_fallback' : false; card.classList.toggle('hidden',hide); }});
}}));
document.getElementById('clear').addEventListener('click', () => {{ if(confirm('Limpar todo o checklist local?')) {{ state={{}}; save(); location.reload(); }} }});
document.getElementById('copy').addEventListener('click', async () => {{
  if (!entries.every(item => completed(item.case_id))) {{ alert('Complete os três critérios dos 88 casos antes de gerar o atestado auxiliar.'); return; }}
  const payload={{schema:'argos-openswisshcc-review-checklist-v1',experiment_signature:experimentSignature,case_count:entries.length,cases:entries.map(item=>({{case_id:item.case_id,panel_sha256:item.panel_sha256,confirmations:state[item.case_id]}})),authoritative_approval:false}};
  const text=JSON.stringify(payload,null,2); try {{ await navigator.clipboard.writeText(text); alert('Atestado auxiliar copiado. Ele ainda precisa ser convertido no manifesto assinado pelo CLI.'); }} catch (_) {{ prompt('Copie o atestado auxiliar:',text); }}
}});
render();
</script>
</body>
</html>
"""


def build_review_gallery(
    *, panel_root: Path, freeze_path: Path, output_dir: Path,
    multiphase_config: Path, fallback_config: Path, expected_case_count: int = 88
) -> dict[str, Any]:
    """Crie HTML local a partir do experimento congelado, sem aprovar qualquer caso."""
    panel_root = Path(panel_root).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise PipelineError("Diretório da galeria já existe; não será sobrescrito.")
    freeze = verify_experiment_freeze(
        freeze_path=freeze_path,
        panel_root=panel_root,
        multiphase_config=multiphase_config,
        fallback_config=fallback_config,
        expected_case_count=expected_case_count,
    )
    staging = output_dir.with_name(f".{output_dir.name}.staging.{uuid.uuid4().hex}")
    staging.mkdir(parents=True)
    try:
        entries: list[dict[str, Any]] = []
        for sequence, candidate in enumerate(freeze["candidates"], start=1):
            case_id = str(candidate["case_id"])
            panel = panel_root / case_id / str(candidate["panel_filename"])
            relative = Path(os.path.relpath(panel, staging)).as_posix()
            entries.append(
                {
                    "sequence": sequence,
                    "case_id": case_id,
                    "candidate_kind": candidate["candidate_kind"],
                    "panel_sha256": candidate["panel_sha256"],
                    "image": relative,
                }
            )
        manifest = {
            "schema": GALLERY_SCHEMA,
            "case_count": len(entries),
            "experiment_signature": freeze["experiment_signature"],
            "ground_truth_read": False,
            "inference_executed": False,
            "authoritative_approval": False,
            "research_only": True,
            "entries": entries,
        }
        (staging / "review_gallery_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (staging / "index.html").write_text(
            _html(entries, freeze["experiment_signature"]), encoding="utf-8"
        )
        _publish_directory(staging, output_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
