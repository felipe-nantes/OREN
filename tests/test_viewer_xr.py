from pathlib import Path

import pyvista as pv

from dtwin import viewer_xr


def _source_metrics(triangles: int) -> dict:
    return {"triangles": triangles, "reconstruction_quality_gate_passed": True}


def test_triangle_budgets_prioritize_liver_and_candidate():
    assert viewer_xr.xr_triangle_budget("organ") == 60_000
    assert viewer_xr.xr_triangle_budget("candidate") == 25_000
    assert viewer_xr.xr_triangle_budget("segment") == 18_000
    assert viewer_xr.xr_triangle_budget("unknown") == 18_000


def test_small_mesh_keeps_authoritative_source(tmp_path: Path):
    source = tmp_path / "organ.stl"
    source.write_bytes(b"solid source\nendsolid source\n")
    mesh = pv.Sphere(theta_resolution=8, phi_resolution=8).triangulate()
    result = viewer_xr.build_xr_render_asset(
        mesh=mesh,
        source_stl=source,
        source_metrics=_source_metrics(mesh.n_cells),
        mask_path=tmp_path / "unused.nii.gz",
        output_path=tmp_path / "organ_xr_lod1.stl",
        material="organ",
        max_volume_error_percent=2.0,
        max_surface_p95_voxels=1.0,
    )
    assert result["lod_level"] == 0
    assert result["stl"] == source.name
    assert result["measurement_authority"] == "binary_mask_in_physical_space"
    assert not (tmp_path / "organ_xr_lod1.stl").exists()


def test_decimated_mesh_is_published_only_after_fidelity_gate(monkeypatch, tmp_path: Path):
    source = tmp_path / "dense.stl"
    mesh = pv.Sphere(theta_resolution=400, phi_resolution=200).triangulate()
    mesh.save(source)
    monkeypatch.setattr(viewer_xr, "xr_triangle_budget", lambda _material: 2_000)
    monkeypatch.setattr(
        viewer_xr,
        "compute_mesh_metrics",
        lambda *_args, **_kwargs: {"reconstruction_quality_gate_passed": True},
    )
    output = tmp_path / "dense_xr_lod1.stl"
    result = viewer_xr.build_xr_render_asset(
        mesh=mesh, source_stl=source, source_metrics=_source_metrics(mesh.n_cells),
        mask_path=tmp_path / "mask.nii.gz", output_path=output, material="organ",
        max_volume_error_percent=2.0, max_surface_p95_voxels=1.0,
    )
    assert result["lod_level"] == 1
    assert result["triangles"] <= 2_100
    assert output.is_file()


def test_failed_lod_gate_falls_back_without_partial_asset(monkeypatch, tmp_path: Path):
    source = tmp_path / "dense.stl"
    mesh = pv.Sphere(theta_resolution=220, phi_resolution=120).triangulate()
    mesh.save(source)
    monkeypatch.setattr(viewer_xr, "xr_triangle_budget", lambda _material: 1_000)
    monkeypatch.setattr(
        viewer_xr,
        "compute_mesh_metrics",
        lambda *_args, **_kwargs: {"reconstruction_quality_gate_passed": False},
    )
    output = tmp_path / "dense_xr_lod1.stl"
    result = viewer_xr.build_xr_render_asset(
        mesh=mesh, source_stl=source, source_metrics=_source_metrics(mesh.n_cells),
        mask_path=tmp_path / "mask.nii.gz", output_path=output, material="organ",
        max_volume_error_percent=2.0, max_surface_p95_voxels=1.0,
    )
    assert result["lod_level"] == 0
    assert result["fallback_reason"] == "decimated_asset_failed_fidelity_gate"
    assert not output.exists()


def test_webxr_client_preserves_desktop_and_exposes_quest_controls():
    app = Path("viewer/app.js").read_text("utf-8")
    xr = Path("viewer/xr.js").read_text("utf-8")
    html = Path("viewer/index.html").read_text("utf-8")
    assert "renderer.setAnimationLoop" in app
    assert "initializeOrenXR" in app
    assert "immersive-vr" in xr and "hand-tracking" in xr
    assert "supportsVr || supportsAr" in xr
    assert "supported || questBrowser" in xr
    assert "Ativar realidade aumentada" in xr
    assert 'window.location.assign("/quest/setup/")' in xr
    assert 'window.location.replace("/quest/")' in xr
    assert "oren:xr-return-url" in xr
    assert "getController" in xr and "squeezestart" in xr
    assert "getHand" in xr and '"pinchstart"' in xr and '"pinchend"' in xr
    assert 'hand.joints?.["index-finger-tip"]' in xr
    assert "updateHandGrabSource" in xr and "twoHandStart" in xr
    assert "PANEL_PAGES" in xr
    for page in ("model", "views", "tools", "structures", "reference", "rgb", "review"):
        assert f"{page}: {{" in xr
    for action in (
        "measure", "dimensions", "cut_axis", "structure_isolate",
        "reference_next", "review_approve",
    ):
        assert action in xr
    assert "setReferenceViewForXR" in app and "setReviewChecklistItem" in app
    assert "getStructureRoles" in app and "getSavedViews" in app
    assert "getStructureCategory" in app and "savedXrPose" in xr
    assert "createExitButton" in xr and "oren-xr-exit-button" in xr
    assert "EXIT_HOLD_MS" in xr and "requestExitToWebapp" in xr
    assert 'window.location.replace("/")' in xr
    assert "HAND_RAY_SMOOTHING" in xr and "PINCH_DEBOUNCE_MS" in xr
    assert "GRAB_FOLLOW" in xr and "refreshHoverVisuals" in xr
    assert "targetRay" in xr and 'ray_source: hand.userData.orenRayState?.source' in xr
    assert "PINCH_CLOSE_MIN_M" in xr and "PINCH_RELEASE_GAP_M" in xr
    assert "updatePrecisionPinch" in xr and "finishPrecisionPinch" in xr
    assert "directPlaneHit" in xr and "HOVER_STABILITY_MS" in xr
    assert "HAND_BONES" in xr and "oren-pinch-confidence" in xr
    assert "createTabletAssembly" in xr and "oren-xr-tablet-root" in xr
    assert "oren-xr-tablet-handle" in xr and "oren-xr-tablet-touch-cursor" in xr
    assert "fingertipPlaneHit" in xr and "updateTabletTouch" in xr
    assert "TABLET_TOUCH_COMMIT_MS" in xr and "TABLET_TOUCH_DEPTH_M" in xr
    assert "startTabletGrab" in xr and "updateTabletGrab" in xr and "stopTabletGrab" in xr
    assert 'else if (action === "tablet_reset") resetTablet()' in xr
    assert "tablet_touch:" in xr and "tablet_grab:" in xr
    assert "drawOrenCore" in xr
    assert "Digital Twin hepático" in xr
    assert "oren-xr-tablet-hud-edges" in xr
    assert "rgba(253,255,254,.97)" in xr and 'color: 0xeaf4ef' in xr
    assert "XR_FRAMEBUFFER_SCALE" in xr and "setFramebufferScaleFactor" in xr
    assert "POINTER_RAYCAST_INTERVAL_MS" in xr and "PERF_STABILITY_THRESHOLD_MS" in xr
    assert "THREE.InstancedMesh" in xr and "oren-hand-joints-instanced" in xr
    assert "applyPerformanceTier" in xr and 'performanceTier === "stability"' in xr
    assert "interactiveMeshes" in xr and "PERF_EVALUATION_INTERVAL_FRAMES" in xr
    assert "setXrPresentationActive" in app and "settleViewerTransitionsForXR" in app
    assert "stabilizeXrScene" in app and "xrExpectedVisible" in app
    assert "XR_SCENE_INTEGRITY_INTERVAL_MS" in xr
    assert "mesh.userData.preXrFrustumCulled" in app
    assert "cameraNear: api.camera.near" in xr and "api.camera.near = 0.01" in xr
    assert 'handle.position.set(0, -0.397, 0.004)' in xr
    assert "createReferencePanelAssembly" in xr and "oren-xr-reference-handle" in xr
    reference_assembly = xr.split("function createReferencePanelAssembly", 1)[1].split("function panelAction", 1)[0]
    assert 'mode = "reference"' in reference_assembly
    assert "referenceHandleHit" in xr and "resetReferenceTablet" in xr
    assert "getRgbPanelCatalog" in app and "refreshRgbPanel" in xr
    assert "rgb_previous" in xr and "rgb_next" in xr
    assert "XR_UI_TEXTURE_SCALE" in xr
    assert "const tabColumns = 4" in xr
    assert "new THREE.PlaneGeometry(0.58, 0.725)" in xr
    assert "if (!xrPresentationActive)" in app
    assert "cleanupXrSession" in xr and 'addEventListener("visibilitychange"' in xr
    assert "refreshEntryReadiness" in xr and "Carregando modelo 3D…" in xr
    assert "getXrReady" in app and "api.getXrReady?.()" in xr
    assert "Recarregar acesso ao Meta Quest" in app
    assert "reportClientEvent" in xr and '"session_failed"' in xr
    assert "const createdSession = await navigator.xr.requestSession" in xr
    assert "failedSession.end()" in xr and "originalModelState = null" in xr
    assert "measurement_authority" not in xr  # browser never promotes a render LOD
    assert 'id="xr-entry"' in html and 'id="xr-profile"' in html
