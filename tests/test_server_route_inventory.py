"""Guarda do inventário público de webapp.server (REF-03/W-001).

Escrita ANTES da decomposição por seams: pina as rotas da API e os símbolos
que testes/tools monkeypatcham ou importam. Se um seam remover uma rota ou
quebrar um patch-point do namespace `server`, este teste falha antes de
qualquer runtime — é o contrato da façade.

Se falhar após mudança intencional de API: atualize a lista JUNTO com a
mudança e o registro correspondente — nunca remova o teste.
"""
from __future__ import annotations

from webapp import server

ROTAS_ESPERADAS = {
    ("GET", "/api/health"),
    ("GET", "/api/medgemma-backends"),
    ("GET", "/api/segmentation-visualization"),
    ("POST", "/api/analyze"),
    ("GET", "/api/status/{job_id}"),
    ("POST", "/api/benchmarks"),
    ("GET", "/api/benchmarks/{benchmark_id}"),
    ("GET", "/api/benchmarks/{benchmark_id}/report.json"),
    ("GET", "/api/benchmarks/{benchmark_id}/report.csv"),
    ("POST", "/api/jobs/{job_id}/xr-session"),
    ("GET", "/api/quest/recent-jobs"),
    ("GET", "/api/jobs/{job_id}/xr-session/{token}"),
    ("POST", "/api/jobs/{job_id}/xr-client-event"),
    ("POST", "/api/jobs/{job_id}/xr-session/{token}/approval"),
    ("GET", "/api/jobs/{job_id}/model/viewer_manifest.json"),
    ("GET", "/api/jobs/{job_id}/rgb-panels"),
    ("GET", "/api/jobs/{job_id}/rgb-panels/{filename}"),
    ("GET", "/api/jobs/{job_id}/model/{filename}"),
    ("POST", "/api/jobs/{job_id}/approval"),
}

# Símbolos monkeypatched por tests/ ou importados por tools/ — o contrato da
# façade: precisam existir como atributos de webapp.server para sempre.
PATCH_POINTS = (
    "WORKSPACE", "REPO", "MEDGEMMA_BACKENDS", "MRSEGMENTATOR_EXE",
    "ENHANCED_3D_OPT_IN_ENABLED", "MONOPHASE_DELAYED_VISUAL_BUNDLE",
    "MONOPHASE_DELAYED_ADVISORY_ENABLED", "MONOPHASE_DELAYED_VISUAL_AUTO_PROMOTED",
    "process_job", "process_visual_job", "process_benchmark",
    "process_monophase_medsiglip_job",
    "_segment", "_mask_quality", "find_best_series", "_run", "_load_report",
    "_probe_backend", "write_run_outputs",
    "_run_benchmark_case", "_run_visual_benchmark_case", "_visual_model_info",
    "_is_visual_scenario", "_graceful", "_friendly",
    "_build_union_liver_mask", "_run_delayed_medsiglip_advisory",
    "_subtype_fields", "_aviso_volume_figado", "_MOTIVOS_MASCARA",
    # varredura completa de setattr(server, ...) em tests/ e tools/ (seam 2
    # revelou alvos fora dos 5 arquivos originais — ex.: o guard da GOV-01
    # patcha _visual_bundle_root):
    "_build_model", "_case_dir_for_job", "_persist_series_selection",
    "_visual_bundle_root", "load_screening_config",
)


def _rotas_do_app() -> set[tuple[str, str]]:
    rotas = set()
    for rota in server.app.routes:
        caminho = getattr(rota, "path", None)
        metodos = getattr(rota, "methods", None)
        if caminho is None or not caminho.startswith("/api/") or not metodos:
            continue
        for metodo in metodos - {"HEAD", "OPTIONS"}:
            rotas.add((metodo, caminho))
    return rotas


def test_inventario_de_rotas_api_intacto():
    atuais = _rotas_do_app()
    removidas = sorted(ROTAS_ESPERADAS - atuais)
    novas = sorted(atuais - ROTAS_ESPERADAS)
    assert removidas == [], f"rotas removidas/alteradas: {removidas}"
    assert novas == [], (
        f"rotas novas fora do inventário (adicione aqui junto com a mudança): {novas}"
    )


def test_patch_points_da_facade_existem():
    ausentes = [nome for nome in PATCH_POINTS if not hasattr(server, nome)]
    assert ausentes == [], (
        "símbolos monkeypatched/importados sumiram do namespace server "
        f"(a façade do REF-03 exige mantê-los): {ausentes}"
    )
