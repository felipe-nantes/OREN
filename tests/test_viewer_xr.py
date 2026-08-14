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
    assert "roundedPanelGeometry" in xr and "THREE.ExtrudeGeometry" in xr
    assert 'panelTop: "rgba(46,49,47,.94)"' in xr and 'color: 0x282d2a' in xr
    assert 'color: 0x87ad9a' in xr and 'text: "#f4f7f5"' in xr
    assert "rgba(253,255,254,.97)" not in xr and "color: 0xeaf4ef" not in xr
    assert "XR_FONT_FAMILY" in xr and '"Roboto", "Noto Sans"' in xr
    assert "XR_ENTRY_CALIBRATION_FRAMES" in xr and "applyHeadRelativeLayout" in xr
    assert "beginEntryCalibration" in xr and "updateEntryCalibration" in xr
    assert "XR_ENTRY_CALIBRATION_TIMEOUT_MS" in xr and "XR_ENTRY_WARMUP_MS" in xr
    assert 'performanceTier = "stability"' in xr and "setFoveation?.(0.9)" in xr
    assert "const XR_UI_TEXTURE_SCALE = 1.25" in xr
    assert "lastPosePersistedAt" not in xr
    assert "XR_FRAMEBUFFER_SCALE" in xr and "setFramebufferScaleFactor" in xr
    assert "POINTER_RAYCAST_INTERVAL_MS" in xr and "PERF_STABILITY_THRESHOLD_MS" in xr
    assert "THREE.InstancedMesh" in xr and "oren-hand-joints-instanced" in xr
    assert "applyPerformanceTier" in xr and 'performanceTier === "stability"' in xr
    assert 'api.setRenderingQualityTier?.(nextTier)' in xr
    assert 'api.setRenderingQualityTier?.("stability")' in xr
    assert 'api.setRenderingQualityTier?.("quality")' in xr
    assert "performanceStressWindows >= 3" in xr
    assert "enforceRealismPerformanceFallback" in xr
    assert 'fallbackReason: "performance_budget_exceeded"' in xr
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
    assert "XR_WIREFRAME_TRIANGLE_LIMIT" in app
    assert "wireframeRoleForCurrentContext" in app
    assert "mesh.material.wireframe = requested" in app
    assert "getWireframeStatus" in app and "status?.reason" in xr
    assert "group.add(measurementGroup)" in app
    assert "xrRoot.add(api.group); xrRoot.add(api.measurementGroup)" not in xr
    assert "worldPointToModelPoint" in app and "isWorldPointVisibleByClipping" in app
    assert "allowHidden: true" in xr and "isStructureVisible" in app
    assert 'id="xr-entry"' in html and 'id="xr-profile"' in html


def test_uxvr_spatial_v2_preserves_every_existing_action_contract():
    source = Path("viewer/xr.js").read_text("utf-8")
    required_actions = {
        "default", "anatomy", "triage", "segments", "opacity", "volume", "render_realism", "reset", "tablet_reset",
        "view_default", "view_anterior", "view_superior", "view_right", "anatomical_liver",
        "anatomical_segments", "anatomical_vascular", "anatomical_candidate", "save_view", "restore_view",
        "measure", "clear_measure", "dimensions", "wireframe", "cut", "cut_position", "cut_axis", "cut_invert",
        "structure_next", "structure_focus", "structure_isolate", "structure_restore", "structure_visibility",
        "structure_opacity", "reference_axial", "reference_coronal", "reference_sagittal", "reference_previous",
        "reference_next", "reference_sync", "reference_reset", "rgb_previous", "rgb_next", "rgb_first", "rgb_reset",
        "review_3d", "review_2d", "review_candidate", "review_research", "candidate_decision", "review_approve",
        "review_revision",
    }
    pages = source.split("const PANEL_PAGES", 1)[1].split("function roundRect", 1)[0]
    for action in required_actions:
        assert f'["{action}",' in pages
    assert "function performAction(action)" in source
    assert "const panel = createSpatialPanelV2();" in source
    assert "buttons.push({ action" in source
    assert 'getRenderingProfile?.() === "anatomic_realistic_v1"' in source
    assert 'api.setRenderingProfile?.(' in source


def test_uxvr_spatial_v2_is_legible_contextual_and_offline():
    source = Path("viewer/xr.js").read_text("utf-8")
    assert "const XR_SPATIAL_THEME" in source
    assert "const XR_PAGE_CONTEXT" in source
    assert "const XR_ACTION_HINTS" in source
    assert "OREN SPATIAL" in source
    assert "SELECIONADA" in source
    assert "Quest 3S" in source and "qualidade adaptativa" in source
    assert 'accent: "#78b99b"' in source
    assert "INTERFACE ESPACIAL" in source
    assert "fitCanvasText" in source
    assert "getStructureCategory" in source and "isStructureVisible" in source
    assert "http://" not in source and "https://" not in source


def test_uxvr_spatial_v2_avoids_redundant_texture_uploads_and_heavy_glass():
    source = Path("viewer/xr.js").read_text("utf-8")
    assert source.count('if (signature === lastDrawSignature) return false;') >= 3
    assert source.count("texture.generateMipmaps = false") >= 3
    assert source.count("THREE.LinearFilter") >= 6
    assert "textureUploadCount" in source and "getPerformanceStats" in source
    assert "panel_texture_uploads" in source and "reference_texture_uploads" in source
    assert "tablet.frameEdges.visible = showDecorativeEdges" in source
    assert "referenceTablet.edges.visible = showDecorativeEdges" in source
    assert "tablet.frameEdges.visible = true; referenceTablet.edges.visible = true;" in source
    assert "const FRAME_BUDGET_MS = 13.9" in source
    assert "transparent: false, opacity: 1" in source
    assert "MeshPhysicalMaterial" not in source
    assert "transmission:" not in source


def test_uxvr_spatial_v2_uses_neutral_clinical_glass_palette():
    source = Path("viewer/xr.js").read_text("utf-8")
    v2 = source.split("function createSpatialPanelV2()", 1)[1].split("function createExitButton()", 1)[0]
    assert 'panelMiddle: "rgba(31,35,33,.95)"' in source
    assert 'surface: "rgba(43,48,45,.94)"' in source
    assert 'border: "rgba(226,237,231,.24)"' in source
    assert 'rgba(47,52,49,.95)' in v2
    assert 'rgba(139,200,172,.46)' in v2
    assert 'rgba(28,158,111,.99)' not in v2
    assert '"#8bffd1"' not in v2
