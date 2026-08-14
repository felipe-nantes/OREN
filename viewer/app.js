// Visualizador offline do OREN. Three.js e loaders ficam vendorizados; nenhuma
// imagem, malha ou decisão de revisão deixa o computador por este módulo.
import * as THREE from "three";
import { STLLoader } from "./vendor/STLLoader.js";
import { OrbitControls } from "./vendor/OrbitControls.js";
import { initializeOrenXR } from "./xr.js?v=oren-20260814-anatomic-v1-3";

const $ = (id) => document.getElementById(id);
const holder = $("canvas-holder");
const controlsDiv = $("controls");
const metaDiv = $("meta");
const drop = $("drop");
const approvalDiv = $("approval");
const approvalStatus = $("approval-status");
const approveButton = $("approve");
const revisionButton = $("request-revision");
const measurementStatus = $("measurement-status");
const referenceDock = $("reference-dock");
const referenceBody = $("reference-body");
const referenceImage = $("reference-image");
const referenceSlider = $("reference-slider");
const referenceMeta = $("reference-meta");
const referenceSync = $("reference-sync");
const referenceSyncStatus = $("reference-sync-status");
const clipSection = $("clip-section");
const clipEnabled = $("clip-enabled");
const clipAxis = $("clip-axis");
const clipInvert = $("clip-invert");
const clipPosition = $("clip-position");
const clipValue = $("clip-value");
const selectionSection = $("selection-section");
const selectionName = $("selection-name");
const selectionCategory = $("selection-category");
const selectionMetrics = $("selection-metrics");
const selectionWarning = $("selection-warning");
const selectionActionStatus = $("selection-action-status");
const selectionDimensionsResult = $("selection-dimensions-result");
const selectionDimensionsMetrics = $("selection-dimensions-metrics");
const anatomicalViewsSection = $("anatomical-views-section");
const anatomicalViewStatus = $("anatomical-view-status");
const savedViewsDiv = $("saved-views");
const savedViewStatus = $("saved-view-status");
const savedViewComparison = $("saved-view-comparison");
const savedViewComparisonGrid = $("saved-view-comparison-grid");
const savedViewComparisonStatus = $("saved-view-comparison-status");

function makeStudioEnvironment(renderer) {
  const canvas = document.createElement("canvas");
  canvas.width = 16;
  canvas.height = 256;
  const context = canvas.getContext("2d");
  const gradient = context.createLinearGradient(0, 0, 0, canvas.height);
  gradient.addColorStop(0, "#ffffff");
  gradient.addColorStop(0.5, "#c9d2d6");
  gradient.addColorStop(1, "#3a3f45");
  context.fillStyle = gradient;
  context.fillRect(0, 0, canvas.width, canvas.height);
  const texture = new THREE.CanvasTexture(canvas);
  texture.mapping = THREE.EquirectangularReflectionMapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  const pmrem = new THREE.PMREMGenerator(renderer);
  const environment = pmrem.fromEquirectangular(texture).texture;
  texture.dispose();
  pmrem.dispose();
  return environment;
}

const scene = new THREE.Scene();
scene.background = null;
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
camera.position.set(120, 120, 120);
const renderer = new THREE.WebGLRenderer({
  antialias: true,
  alpha: true,
  preserveDrawingBuffer: true,
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.35;
renderer.localClippingEnabled = true;
holder.prepend(renderer.domElement);
scene.environment = makeStudioEnvironment(renderer);
scene.add(new THREE.HemisphereLight(0xffffff, 0x40454b, 0.5));
const keyLight = new THREE.DirectionalLight(0xfff4e6, 1.1);
const rimLight = new THREE.DirectionalLight(0xdfe9ff, 0.5);
scene.add(keyLight, rimLight);

const orbit = new OrbitControls(camera, renderer.domElement);
orbit.enableDamping = true;
orbit.dampingFactor = 0.08;
const group = new THREE.Group();
scene.add(group);
const measurementGroup = new THREE.Group();
measurementGroup.name = "oren-measurements";
// Measurements use the same canonical LPS millimetre coordinate system as
// the segmentation meshes and therefore must follow every XR transform.
group.add(measurementGroup);
const loader = new STLLoader();
const textureLoader = new THREE.TextureLoader();
const sharedMaterialTextures = new Set();
const realisticMaterialPack = {
  state: "idle",
  promise: null,
  textures: null,
  error: null,
};
const REALISTIC_MATERIAL_ASSETS = Object.freeze({
  desktop: Object.freeze({
    albedo: "./assets/materials/liver_realistic_v1_albedo.png?v=8f06fa09e6b9",
    normal: "./assets/materials/liver_realistic_v1_normal.png?v=8f06fa09e6b9",
    roughness: "./assets/materials/liver_realistic_v1_roughness.png?v=8f06fa09e6b9",
  }),
  quest: Object.freeze({
    albedo: "./assets/materials/liver_realistic_v1_quest512_albedo.png?v=68ceac258cf5",
    normal: "./assets/materials/liver_realistic_v1_quest512_normal.png?v=68ceac258cf5",
    roughness: "./assets/materials/liver_realistic_v1_quest512_roughness.png?v=68ceac258cf5",
  }),
});
const REALISTIC_MATERIAL_PACK_ID = "oren-liver-realistic-v1";
const RENDERING_QUALITY_TIERS = Object.freeze(["quality", "stability"]);
const meshes = {};
const meshItems = {};
const clippingPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
const localClippingPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
const clippingNormalMatrix = new THREE.Matrix3();
let sceneBounds = new THREE.Box3();
let sourceBounds = new THREE.Box3();
let sceneRadius = 1;
let currentManifest = null;
let currentView = "padrao";
let currentPreset = "custom";
let wireframeEnabled = false;
let wireframeStatus = { enabled: false, role: null, reason: null };
let measurementEnabled = false;
let measurePendingPoint = null;
let measurementValues = [];
let measurementObjects = [];
let structureMeasurements3d = [];
let structureDimensionObjects = [];
let selectedRole = null;
let selectedMaterialState = null;
let selectionContextPreset = null;
let selectionIsolated = false;
let currentAnatomicalView = "none";
let currentMaterialProfile = "default";
const SCIENTIFIC_CURRENT_PROFILE = "scientific_current_v1";
const ANATOMIC_REALISTIC_PROFILE = "anatomic_realistic_v1";
let currentRenderingProfile = SCIENTIFIC_CURRENT_PROFILE;
let currentRenderingQualityTier = "quality";
let currentRenderingFallbackReason = null;
let savedViews = [];
let savedViewSequence = 0;
let comparedSavedViewIds = [];
let referenceView = "axial";
let referenceSyncPreviousClippingState = null;
let referenceFiles = {};
let referenceBaseUrl = "";
let referenceObjectUrls = [];
let viewerReadyForReview = false;
let xrPresentationActive = false;
const loadingState = {
  phase: "idle", completed: 0, total: 0, ready: false,
  startedAt: 0, firstOrganMs: null, readyMs: null,
};
let cameraTween = null;
let sceneIntroTween = null;
const meshVisibilityTweens = new Map();
const objectScaleTweens = new Map();
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

const VIEWER_PRESETS = Object.freeze({
  default: {
    label: "Restaurar padrão",
    description: "Fígado sólido com acabamento orgânico; estruturas internas respeitam a oclusão anatômica.",
  },
  anatomy: {
    label: "Anatomia interna",
    description: "Fígado translúcido com vasos e vesícula destacados.",
  },
  triage: {
    label: "Triagem",
    description: "Candidato e região classificada sobre o fígado translúcido.",
  },
  segments: {
    label: "Segmentos",
    description: "Couinaud I–VIII com referências vasculares, quando disponíveis.",
    requiresSegments: true,
  },
});
const RENDERING_PROFILES = Object.freeze({
  [SCIENTIFIC_CURRENT_PROFILE]: {
    label: "Representação atual",
    description: "Acabamento científico protegido e reproduzível.",
  },
  [ANATOMIC_REALISTIC_PROFILE]: {
    label: "Representação anatômica realista",
    description: "Textura ilustrativa; geometria, volume e medidas não são alterados.",
  },
});
const DEFAULT_VISUAL_PRESET = "default";
const REQUIRED_COUINAUD_ROLES = Object.freeze([
  "couinaud_i", "couinaud_ii", "couinaud_iii", "couinaud_iv",
  "couinaud_v", "couinaud_vi", "couinaud_vii", "couinaud_viii",
]);
const MAX_SAVED_VIEWS = 8;
const ANATOMICAL_VIEWS = Object.freeze({
  liver: {
    label: "Fígado",
    preset: "default",
    targetCategories: ["organ"],
    description: "Superfície hepática sólida no enquadramento completo do órgão.",
  },
  segments: {
    label: "Segmentos",
    preset: "segments",
    targetCategories: ["segment"],
    description: "Atlas de Couinaud sólido com referências vasculares disponíveis.",
  },
  vascular: {
    label: "Vasos",
    preset: "anatomy",
    targetCategories: ["vessel"],
    description: "Estruturas vasculares enquadradas com o fígado translúcido como contexto.",
  },
  candidate: {
    label: "Candidato",
    preset: "triage",
    targetCategories: ["candidate", "lesion"],
    description: "Região automática não confirmada enquadrada no contexto de triagem.",
  },
});

const orenEase = (value) => 1 - ((1 - value) ** 4);
const tweenProgress = (startedAt, duration, now) => Math.min(Math.max((now - startedAt) / duration, 0), 1);

function updateOrenAnimations(now) {
  if (cameraTween) {
    const progress = tweenProgress(cameraTween.startedAt, cameraTween.duration, now);
    const eased = orenEase(progress);
    camera.position.lerpVectors(cameraTween.fromPosition, cameraTween.toPosition, eased);
    orbit.target.lerpVectors(cameraTween.fromTarget, cameraTween.toTarget, eased);
    if (progress >= 1) {
      camera.position.copy(cameraTween.toPosition);
      orbit.target.copy(cameraTween.toTarget);
      cameraTween = null;
      orbit.enabled = !measurementEnabled;
    }
  }

  if (sceneIntroTween) {
    const progress = tweenProgress(sceneIntroTween.startedAt, sceneIntroTween.duration, now);
    const eased = orenEase(progress);
    group.scale.setScalar(THREE.MathUtils.lerp(0.94, 1, eased));
    sceneIntroTween.meshes.forEach(({ mesh, opacity }) => {
      mesh.material.opacity = THREE.MathUtils.lerp(0, opacity, eased);
    });
    if (progress >= 1) {
      group.scale.setScalar(1);
      sceneIntroTween.meshes.forEach(({ mesh, opacity }) => { mesh.material.opacity = opacity; });
      sceneIntroTween = null;
    }
  }

  meshVisibilityTweens.forEach((tween, mesh) => {
    const progress = tweenProgress(tween.startedAt, tween.duration, now);
    mesh.material.opacity = THREE.MathUtils.lerp(tween.fromOpacity, tween.toOpacity, orenEase(progress));
    if (progress >= 1) {
      mesh.material.opacity = tween.toOpacity;
      if (tween.hideAfter) mesh.visible = false;
      meshVisibilityTweens.delete(mesh);
    }
  });

  objectScaleTweens.forEach((tween, object) => {
    const progress = tweenProgress(tween.startedAt, tween.duration, now);
    object.scale.setScalar(THREE.MathUtils.lerp(0.05, 1, orenEase(progress)));
    if (progress >= 1) objectScaleTweens.delete(object);
  });
}

function settleViewerTransitionsForXR() {
  cameraTween = null;
  orbit.enabled = false;
  if (sceneIntroTween) {
    group.scale.setScalar(1);
    sceneIntroTween.meshes.forEach(({ mesh, opacity }) => {
      mesh.material.opacity = opacity;
      mesh.userData.targetOpacity = opacity;
    });
    sceneIntroTween = null;
  }
  meshVisibilityTweens.forEach((tween, mesh) => {
    mesh.material.opacity = tween.toOpacity;
    mesh.visible = !tween.hideAfter;
  });
  meshVisibilityTweens.clear();
  objectScaleTweens.forEach((_tween, object) => { object.scale.setScalar(1); });
  objectScaleTweens.clear();
}

function setXrPresentationActive(active) {
  xrPresentationActive = Boolean(active);
  if (xrPresentationActive) settleViewerTransitionsForXR();
  const selectedMesh = selectedRole ? meshes[selectedRole] : null;
  if (selectedMesh && selectedMaterialState) {
    if (xrPresentationActive) {
      selectedMesh.material.emissive.setHex(selectedMaterialState.emissive);
      selectedMesh.material.emissiveIntensity = selectedMaterialState.emissiveIntensity;
      selectedMesh.material.clearcoat = selectedMaterialState.clearcoat;
    } else {
      selectedMesh.material.emissive.setHex(0x2daf79);
      selectedMesh.material.emissiveIntensity = Math.max(selectedMaterialState.emissiveIntensity + 0.24, 0.30);
      selectedMesh.material.clearcoat = Math.max(selectedMaterialState.clearcoat, 0.30);
    }
    selectedMesh.material.needsUpdate = true;
  }
  Object.values(meshes).forEach((mesh) => {
    if (xrPresentationActive) {
      mesh.userData.preXrFrustumCulled = mesh.frustumCulled;
      mesh.frustumCulled = false;
      mesh.userData.xrExpectedVisible = Boolean(mesh.visible);
      mesh.userData.xrExpectedMaterialVisible = mesh.material.visible !== false;
      if (mesh.visible) {
        const opacity = Number(mesh.userData.targetOpacity);
        if (Number.isFinite(opacity) && opacity > 0) mesh.material.opacity = opacity;
      }
    } else if (typeof mesh.userData.preXrFrustumCulled === "boolean") {
      mesh.frustumCulled = mesh.userData.preXrFrustumCulled;
      delete mesh.userData.preXrFrustumCulled;
      delete mesh.userData.xrExpectedVisible;
      delete mesh.userData.xrExpectedMaterialVisible;
    }
  });
  applyWireframeState();
  group.updateMatrixWorld(true);
  return xrPresentationActive;
}

function stabilizeXrScene() {
  if (!xrPresentationActive) return false;
  group.visible = true;
  Object.values(meshes).forEach((mesh) => {
    mesh.frustumCulled = false;
    const expectedVisible = mesh.userData.xrExpectedVisible;
    if (typeof expectedVisible === "boolean" && mesh.visible !== expectedVisible) {
      mesh.visible = expectedVisible;
    }
    const expectedMaterialVisible = mesh.userData.xrExpectedMaterialVisible;
    if (typeof expectedMaterialVisible === "boolean" && mesh.material.visible !== expectedMaterialVisible) {
      mesh.material.visible = expectedMaterialVisible;
    }
    if (mesh.visible) {
      const targetOpacity = Number(mesh.userData.targetOpacity ?? 1);
      if (!Number.isFinite(mesh.material.opacity) || mesh.material.opacity <= 0) {
        mesh.material.opacity = Number.isFinite(targetOpacity) && targetOpacity > 0 ? targetOpacity : 1;
      }
    }
  });
  refreshClippingPlaneWorld();
  group.updateMatrixWorld(true);
  return true;
}

const AXIS_UP = new THREE.Vector3(0, 0, 1);
function repositionLights() {
  const direction = camera.position.clone().normalize();
  const side = new THREE.Vector3().crossVectors(AXIS_UP, direction).normalize();
  if (!Number.isFinite(side.x)) side.set(1, 0, 0);
  keyLight.position.copy(direction).addScaledVector(side, 0.5).addScaledVector(AXIS_UP, 0.55);
  rimLight.position.copy(direction).multiplyScalar(-1)
    .addScaledVector(side, -0.4).addScaledVector(AXIS_UP, 0.3);
}

function resize() {
  const width = holder.clientWidth;
  const height = holder.clientHeight;
  // Keep the drawing buffer scaled by devicePixelRatio while the CSS canvas
  // remains exactly the size of its holder.  Passing false here made the
  // intrinsic high-DPI dimensions become CSS dimensions, cropping the scene
  // and offsetting ray-cast measurements on displays above 1x DPI.
  renderer.setSize(width, height, true);
  camera.aspect = width / Math.max(height, 1);
  camera.updateProjectionMatrix();
}
window.addEventListener("resize", resize);
document.addEventListener("fullscreenchange", resize);
resize();
renderer.setAnimationLoop((time, xrFrame) => {
  updateOrenAnimations(performance.now());
  if (!renderer.xr.isPresenting) orbit.update();
  if (window.__orenXrFrame) window.__orenXrFrame(time, xrFrame);
  repositionLights();
  renderer.render(scene, camera);
});

function disposeObject(object) {
  if (object.geometry) object.geometry.dispose();
  if (object.material) {
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of materials) {
      if (material.map && !sharedMaterialTextures.has(material.map)) material.map.dispose();
      if (material.normalMap && !sharedMaterialTextures.has(material.normalMap)) material.normalMap.dispose();
      if (material.roughnessMap && !sharedMaterialTextures.has(material.roughnessMap)) material.roughnessMap.dispose();
      material.dispose();
    }
  }
}

function clearMeasurements() {
  for (const object of measurementObjects) {
    objectScaleTweens.delete(object);
    object.removeFromParent();
    disposeObject(object);
  }
  measurementObjects = [];
  structureDimensionObjects = [];
  measurementValues = [];
  structureMeasurements3d = [];
  measurePendingPoint = null;
  if (selectionDimensionsResult) selectionDimensionsResult.hidden = true;
  updateMeasurementStatus();
}

function clearScene() {
  clearStructureSelection();
  cameraTween = null;
  sceneIntroTween = null;
  meshVisibilityTweens.clear();
  objectScaleTweens.clear();
  holder.classList.remove("is-model-loaded");
  clearMeasurements();
  for (const role of Object.keys(meshes)) {
    group.remove(meshes[role]);
    disposeObject(meshes[role]);
    delete meshes[role];
    delete meshItems[role];
  }
  group.position.set(0, 0, 0);
  controlsDiv.innerHTML = "";
  for (const url of referenceObjectUrls) URL.revokeObjectURL(url);
  referenceObjectUrls = [];
  referenceFiles = {};
  referenceBaseUrl = "";
  viewerReadyForReview = false;
  currentPreset = "custom";
  currentAnatomicalView = "none";
  currentMaterialProfile = DEFAULT_VISUAL_PRESET;
  currentRenderingProfile = SCIENTIFIC_CURRENT_PROFILE;
  savedViews = [];
  savedViewSequence = 0;
  comparedSavedViewIds = [];
  if (anatomicalViewsSection) anatomicalViewsSection.hidden = true;
  if (savedViewsDiv) savedViewsDiv.innerHTML = "";
  if (savedViewComparison) savedViewComparison.hidden = true;
  if (savedViewStatus) savedViewStatus.textContent = "Nenhuma vista salva.";
  renderer.toneMappingExposure = 1.35;
}

function mergeVerticesByPosition(geometry, precisionDecimals = 4) {
  const position = geometry.getAttribute("position");
  const scale = 10 ** precisionDecimals;
  const hashToIndex = new Map();
  const positions = [];
  const indices = new Array(position.count);
  for (let index = 0; index < position.count; index += 1) {
    const key = [
      Math.round(position.getX(index) * scale),
      Math.round(position.getY(index) * scale),
      Math.round(position.getZ(index) * scale),
    ].join("_");
    let mergedIndex = hashToIndex.get(key);
    if (mergedIndex === undefined) {
      mergedIndex = positions.length / 3;
      hashToIndex.set(key, mergedIndex);
      positions.push(position.getX(index), position.getY(index), position.getZ(index));
    }
    indices[index] = mergedIndex;
  }
  const merged = new THREE.BufferGeometry();
  merged.setIndex(indices);
  merged.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return merged;
}

function tissueMaterial(item) {
  const color = new THREE.Color(item.color);
  const materialType = item.material || (item.role === "lesao" ? "lesion" : "organ");
  const opacity = Number.isFinite(Number(item.opacity)) ? Number(item.opacity) : 0.88;
  let material;
  if (materialType === "lesion") {
    material = new THREE.MeshPhysicalMaterial({
      color, transparent: true, opacity, roughness: 0.5, metalness: 0,
      clearcoat: 0.3, clearcoatRoughness: 0.4,
      emissive: color, emissiveIntensity: 0.08,
    });
  } else if (materialType === "candidate") {
    material = new THREE.MeshPhysicalMaterial({
      color, transparent: true, opacity, roughness: 0.32, metalness: 0,
      clearcoat: 0.55, clearcoatRoughness: 0.22,
      emissive: color, emissiveIntensity: 0.22,
      polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1,
      depthTest: false, depthWrite: false,
    });
  } else if (materialType === "classified_region") {
    // Vive DENTRO da malha do órgão (a união ⊇ a região classificada, por
    // construção -- docs/189 §5.2), então precisa do mesmo truque de
    // profundidade do candidato para não ser ocultada pelo próprio órgão.
    // Wireframe + baixa opacidade lê como camada de auditoria, não como
    // tecido -- é fronteira a marcar, não massa a mostrar.
    material = new THREE.MeshPhysicalMaterial({
      color, transparent: true, opacity, roughness: 0.15, metalness: 0,
      wireframe: true,
      emissive: color, emissiveIntensity: 0.5,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
      depthTest: false, depthWrite: false,
    });
  } else if (materialType === "segment") {
    material = new THREE.MeshPhysicalMaterial({
      color, transparent: true, opacity, roughness: 0.5, metalness: 0,
      clearcoat: 0.25, clearcoatRoughness: 0.5, envMapIntensity: 0.55,
    });
  } else if (materialType === "vessel") {
    material = new THREE.MeshPhysicalMaterial({
      color, transparent: true, opacity, roughness: 0.28, metalness: 0,
      clearcoat: 0.65, clearcoatRoughness: 0.2, envMapIntensity: 0.8,
    });
  } else if (materialType === "gallbladder") {
    material = new THREE.MeshPhysicalMaterial({
      color, transparent: true, opacity, roughness: 0.36, metalness: 0,
      clearcoat: 0.55, clearcoatRoughness: 0.3, envMapIntensity: 0.7,
    });
  } else {
    const tissueColor = color.clone().lerp(new THREE.Color(0x9c5541), 0.35);
    material = new THREE.MeshPhysicalMaterial({
      color: tissueColor, transparent: true, opacity,
      roughness: 0.38, metalness: 0,
      clearcoat: 0.45, clearcoatRoughness: 0.32,
      sheen: 0.25, sheenRoughness: 0.5, sheenColor: new THREE.Color(0xf2c9b8),
      envMapIntensity: 1.15,
    });
  }
  material.side = THREE.DoubleSide;
  return material;
}

function addMesh(item, geometry) {
  const merged = mergeVerticesByPosition(geometry);
  merged.computeVertexNormals();
  const mesh = new THREE.Mesh(merged, tissueMaterial(item));
  mesh.visible = item.default_visible !== false;
  mesh.userData.role = item.role;
  mesh.userData.label = item.label || item.role;
  mesh.userData.targetOpacity = mesh.material.opacity;
  mesh.userData.materialBaseline = {
    color: mesh.material.color.getHex(),
    roughness: mesh.material.roughness,
    metalness: mesh.material.metalness,
    clearcoat: mesh.material.clearcoat,
    clearcoatRoughness: mesh.material.clearcoatRoughness,
    sheen: mesh.material.sheen,
    sheenRoughness: mesh.material.sheenRoughness,
    sheenColor: mesh.material.sheenColor.getHex(),
    emissive: mesh.material.emissive.getHex(),
    emissiveIntensity: mesh.material.emissiveIntensity,
    envMapIntensity: mesh.material.envMapIntensity,
    transparent: mesh.material.transparent,
    depthTest: mesh.material.depthTest,
    depthWrite: mesh.material.depthWrite,
    map: mesh.material.map || null,
    normalMap: mesh.material.normalMap || null,
    roughnessMap: mesh.material.roughnessMap || null,
    normalScale: mesh.material.normalScale?.clone() || new THREE.Vector2(1, 1),
    renderOrder: mesh.renderOrder,
  };
  if (item.material === "candidate") mesh.renderOrder = 12;
  if (item.material === "classified_region") mesh.renderOrder = 8;
  mesh.userData.materialBaseline.renderOrder = mesh.renderOrder;
  meshes[item.role] = mesh;
  meshItems[item.role] = item;
  group.add(mesh);
  return mesh;
}

const VIEWS = {
  anterior: new THREE.Vector3(0, -1, 0),
  padrao: new THREE.Vector3(-0.45, -0.85, 0.28).normalize(),
  superior: new THREE.Vector3(0, -0.25, 1).normalize(),
  direita: new THREE.Vector3(-1, -0.2, 0.1).normalize(),
};

function fitDistance(radius, margin = 1.12) {
  const verticalFov = THREE.MathUtils.degToRad(camera.fov);
  const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * camera.aspect);
  return Math.max(radius / Math.sin(verticalFov / 2), radius / Math.sin(horizontalFov / 2)) * margin;
}

function applyView(name = "padrao", options = {}) {
  currentView = VIEWS[name] ? name : "padrao";
  currentAnatomicalView = "none";
  updateAnatomicalViewButtons();
  const direction = VIEWS[currentView].clone();
  const distance = fitDistance(sceneRadius);
  const targetPosition = direction.multiplyScalar(distance);
  camera.up.set(0, 0, 1);
  camera.near = Math.max(distance / 1000, 0.01);
  camera.far = distance * 10;
  camera.updateProjectionMatrix();
  const immediate = options.immediate || reducedMotion.matches || sceneRadius <= 1;
  if (immediate) {
    cameraTween = null;
    camera.position.copy(targetPosition);
    orbit.target.set(0, 0, 0);
    orbit.update();
  } else {
    orbit.enabled = false;
    cameraTween = {
      fromPosition: camera.position.clone(),
      toPosition: targetPosition,
      fromTarget: orbit.target.clone(),
      toTarget: new THREE.Vector3(0, 0, 0),
      startedAt: performance.now(),
      duration: 720,
    };
  }
  document.querySelectorAll(".viewbtn").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === currentView);
  });
}

function animateMeshVisibility(mesh, visible) {
  if (!mesh) return;
  if (sceneIntroTween) {
    group.scale.setScalar(1);
    sceneIntroTween.meshes.forEach(({ mesh: introMesh, opacity }) => { introMesh.material.opacity = opacity; });
    sceneIntroTween = null;
  }
  const targetOpacity = Number(mesh.userData.targetOpacity ?? mesh.material.opacity ?? 1);
  if (xrPresentationActive || reducedMotion.matches) {
    meshVisibilityTweens.delete(mesh);
    if (xrPresentationActive) mesh.userData.xrExpectedVisible = Boolean(visible);
    mesh.visible = visible;
    mesh.material.opacity = visible ? targetOpacity : 0;
    return;
  }
  if (visible) mesh.visible = true;
  meshVisibilityTweens.set(mesh, {
    fromOpacity: Number(mesh.material.opacity),
    toOpacity: visible ? targetOpacity : 0,
    hideAfter: !visible,
    startedAt: performance.now(),
    duration: 360,
  });
}

function animateModelEntrance() {
  holder.classList.remove("is-model-loaded");
  void holder.offsetWidth;
  holder.classList.add("is-model-loaded");
  const visibleMeshes = Object.values(meshes)
    .filter((mesh) => mesh.visible)
    .map((mesh) => ({ mesh, opacity: Number(mesh.userData.targetOpacity ?? mesh.material.opacity) }));
  if (reducedMotion.matches) {
    group.scale.setScalar(1);
    visibleMeshes.forEach(({ mesh, opacity }) => { mesh.material.opacity = opacity; });
    return;
  }
  group.scale.setScalar(0.94);
  visibleMeshes.forEach(({ mesh }) => { mesh.material.opacity = 0; });
  sceneIntroTween = { meshes: visibleMeshes, startedAt: performance.now(), duration: 900 };
}

function animateElementFeedback(element, className = "is-changing") {
  if (!element || reducedMotion.matches) return;
  element.classList.remove(className);
  void element.offsetWidth;
  element.classList.add(className);
  const hold = className === "is-feedback" ? 650 : 460;
  window.setTimeout(() => element.classList.remove(className), hold);
}

function frameScene() {
  group.position.set(0, 0, 0);
  group.updateMatrixWorld(true);
  const originalBounds = new THREE.Box3().setFromObject(group);
  if (originalBounds.isEmpty()) return;
  sourceBounds = originalBounds.clone();
  const center = originalBounds.getCenter(new THREE.Vector3());
  group.position.sub(center);
  group.updateMatrixWorld(true);
  sceneBounds = new THREE.Box3().setFromObject(group);
  sceneRadius = sceneBounds.getBoundingSphere(new THREE.Sphere()).radius;
  applyView("padrao");
  updateClipping();
}

window.addEventListener("resize", () => {
  if (sceneRadius > 1) {
    const direction = camera.position.clone().normalize();
    camera.position.copy(direction.multiplyScalar(fitDistance(sceneRadius)));
    camera.updateProjectionMatrix();
    orbit.update();
  }
});

function makeButton(label, className, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.addEventListener("click", handler);
  return button;
}

function meshCategory(item) {
  const material = String(item?.material || "");
  const role = String(item?.role || "");
  if (material === "segment" || role.startsWith("couinaud_")) return "segment";
  if (material === "vessel") return "vessel";
  if (material === "gallbladder") return "gallbladder";
  if (material === "candidate" || role === "candidato") return "candidate";
  if (material === "classified_region") return "classified_region";
  if (material === "lesion" || role === "lesao") return "lesion";
  if (role === "orgao" || material === "organ" || !material) return "organ";
  return "other";
}

function configureMaterialTexture(texture, { color = false, repeat = 5 } = {}) {
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(repeat, repeat);
  texture.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.anisotropy = currentRenderingQualityTier === "stability"
    ? 1 : Math.min(renderer.capabilities.getMaxAnisotropy?.() || 1, 4);
  texture.generateMipmaps = true;
  texture.needsUpdate = true;
  sharedMaterialTextures.add(texture);
  return texture;
}

async function loadRealisticMaterialPack() {
  if (realisticMaterialPack.state === "ready") return realisticMaterialPack.textures;
  if (realisticMaterialPack.promise) return realisticMaterialPack.promise;
  realisticMaterialPack.state = "loading";
  const assets = preferXrAssets ? REALISTIC_MATERIAL_ASSETS.quest : REALISTIC_MATERIAL_ASSETS.desktop;
  realisticMaterialPack.promise = Promise.all([
    textureLoader.loadAsync(assets.albedo),
    textureLoader.loadAsync(assets.normal),
    textureLoader.loadAsync(assets.roughness),
  ]).then(([albedo, normal, roughness]) => {
    realisticMaterialPack.textures = {
      albedo: configureMaterialTexture(albedo, { color: true, repeat: 4.6 }),
      normal: configureMaterialTexture(normal, { repeat: 4.6 }),
      roughness: configureMaterialTexture(roughness, { repeat: 4.6 }),
    };
    realisticMaterialPack.state = "ready";
    realisticMaterialPack.variant = preferXrAssets ? "quest512" : "desktop_1k";
    realisticMaterialPack.error = null;
    return realisticMaterialPack.textures;
  }).catch((error) => {
    realisticMaterialPack.state = "failed";
    realisticMaterialPack.error = error;
    realisticMaterialPack.promise = null;
    throw error;
  });
  return realisticMaterialPack.promise;
}

function ensureSphericalTextureCoordinates(mesh) {
  if (mesh.geometry.getAttribute("uv")) return;
  const positions = mesh.geometry.getAttribute("position");
  mesh.geometry.computeBoundingBox();
  const center = mesh.geometry.boundingBox.getCenter(new THREE.Vector3());
  const uv = new Float32Array(positions.count * 2);
  for (let index = 0; index < positions.count; index += 1) {
    const x = positions.getX(index) - center.x;
    const y = positions.getY(index) - center.y;
    const z = positions.getZ(index) - center.z;
    const radius = Math.max(Math.sqrt((x * x) + (y * y) + (z * z)), 1e-6);
    uv[index * 2] = 0.5 + (Math.atan2(y, x) / (Math.PI * 2));
    uv[(index * 2) + 1] = 0.5 - (Math.asin(THREE.MathUtils.clamp(z / radius, -1, 1)) / Math.PI);
  }
  mesh.geometry.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
}

function restoreMaterialAppearance(mesh) {
  const baseline = mesh?.userData?.materialBaseline;
  if (!baseline) return;
  const material = mesh.material;
  material.color.setHex(baseline.color);
  material.roughness = baseline.roughness;
  material.metalness = baseline.metalness;
  material.clearcoat = baseline.clearcoat;
  material.clearcoatRoughness = baseline.clearcoatRoughness;
  material.sheen = baseline.sheen;
  material.sheenRoughness = baseline.sheenRoughness;
  material.sheenColor.setHex(baseline.sheenColor);
  material.emissive.setHex(baseline.emissive);
  material.emissiveIntensity = baseline.emissiveIntensity;
  material.envMapIntensity = baseline.envMapIntensity;
  material.transparent = baseline.transparent;
  material.depthTest = baseline.depthTest;
  material.depthWrite = baseline.depthWrite;
  material.map = baseline.map || null;
  material.normalMap = baseline.normalMap || null;
  material.roughnessMap = baseline.roughnessMap || null;
  if (baseline.normalScale) material.normalScale.copy(baseline.normalScale);
  mesh.renderOrder = baseline.renderOrder;
  material.vertexColors = false;
  mesh.geometry.deleteAttribute("color");
  material.needsUpdate = true;
}

function applyOrganicVertexTone(mesh, baseHex, lightHex, deepHex, strength = 1) {
  const positions = mesh.geometry.getAttribute("position");
  const colors = new Float32Array(positions.count * 3);
  const base = new THREE.Color(baseHex);
  const light = new THREE.Color(lightHex);
  const deep = new THREE.Color(deepHex);
  const tone = new THREE.Color();
  for (let index = 0; index < positions.count; index += 1) {
    const x = positions.getX(index);
    const y = positions.getY(index);
    const z = positions.getZ(index);
    const variation = 0.5
      + (Math.sin((x * 0.083) + (y * 0.047) + (z * 0.029)) * 0.22 * strength)
      + (Math.sin((x * 0.023) - (y * 0.061) + (z * 0.071)) * 0.10 * strength);
    tone.copy(base);
    if (variation >= 0.5) tone.lerp(light, Math.min((variation - 0.5) * 0.55, 0.20));
    else tone.lerp(deep, Math.min((0.5 - variation) * 0.48, 0.16));
    colors[index * 3] = tone.r;
    colors[(index * 3) + 1] = tone.g;
    colors[(index * 3) + 2] = tone.b;
  }
  mesh.geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  mesh.material.color.setHex(0xffffff);
  mesh.material.vertexColors = true;
}

function applyAnatomicalOverlayAppearance(item, mesh) {
  const category = meshCategory(item);
  const material = mesh.material;
  let baseColor = 0x876b5e;
  if (category === "vessel") {
    if (String(item.role).includes("cava")) {
      baseColor = 0x3d526f;
      applyOrganicVertexTone(mesh, baseColor, 0x637999, 0x202f46, 0.72);
    } else {
      baseColor = 0x356b72;
      applyOrganicVertexTone(mesh, baseColor, 0x5a8c8d, 0x1d4148, 0.72);
    }
  } else if (category === "gallbladder") {
    baseColor = 0x53653d;
    applyOrganicVertexTone(mesh, baseColor, 0x78865a, 0x2c3923, 0.82);
  } else if (category === "candidate") {
    baseColor = 0xa86125;
    applyOrganicVertexTone(mesh, baseColor, 0xc98847, 0x6d3918, 0.58);
  } else if (category === "lesion") {
    baseColor = 0x7e3038;
    applyOrganicVertexTone(mesh, baseColor, 0xa45155, 0x4b1c25, 0.70);
  } else if (category === "classified_region") {
    baseColor = 0x467e8b;
    applyOrganicVertexTone(mesh, baseColor, 0x70a4ad, 0x284b55, 0.46);
  }
  const anatomicalColor = new THREE.Color(baseColor);
  material.metalness = 0;
  material.depthTest = true;
  material.depthWrite = false;
  material.envMapIntensity = 0.72;
  if (category === "vessel") {
    material.roughness = 0.50;
    material.clearcoat = 0.22;
    material.clearcoatRoughness = 0.52;
    material.emissive.copy(anatomicalColor);
    material.emissiveIntensity = 0.10;
    mesh.renderOrder = 10;
  } else if (category === "gallbladder") {
    material.roughness = 0.55;
    material.clearcoat = 0.18;
    material.clearcoatRoughness = 0.58;
    material.emissive.copy(anatomicalColor);
    material.emissiveIntensity = 0.06;
    mesh.renderOrder = 9;
  } else if (["candidate", "lesion"].includes(category)) {
    material.roughness = 0.50;
    material.clearcoat = 0.20;
    material.clearcoatRoughness = 0.52;
    material.emissive.copy(anatomicalColor);
    material.emissiveIntensity = 0.18;
    mesh.renderOrder = 12;
  } else if (category === "classified_region") {
    material.roughness = 0.48;
    material.emissive.copy(anatomicalColor);
    material.emissiveIntensity = 0.48;
    mesh.renderOrder = 11;
  }
  material.needsUpdate = true;
}

function applyHepaticTissueAppearance(mesh) {
  const positions = mesh.geometry.getAttribute("position");
  const colors = new Float32Array(positions.count * 3);
  const base = new THREE.Color(0x84342e);
  const warm = new THREE.Color(0xaa5a46);
  const deep = new THREE.Color(0x541b1c);
  const tone = new THREE.Color();
  for (let index = 0; index < positions.count; index += 1) {
    const x = positions.getX(index);
    const y = positions.getY(index);
    const z = positions.getZ(index);
    const variation = 0.5
      + (Math.sin((x * 0.071) + (y * 0.043) + (z * 0.031)) * 0.25)
      + (Math.sin((x * 0.019) - (y * 0.057) + (z * 0.083)) * 0.12);
    tone.copy(base);
    if (variation >= 0.5) tone.lerp(warm, Math.min((variation - 0.5) * 0.55, 0.22));
    else tone.lerp(deep, Math.min((0.5 - variation) * 0.45, 0.16));
    colors[(index * 3)] = tone.r;
    colors[(index * 3) + 1] = tone.g;
    colors[(index * 3) + 2] = tone.b;
  }
  mesh.geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const material = mesh.material;
  material.color.setHex(0xffffff);
  material.vertexColors = true;
  material.roughness = 0.54;
  material.metalness = 0;
  material.clearcoat = 0.21;
  material.clearcoatRoughness = 0.58;
  material.sheen = 0.34;
  material.sheenRoughness = 0.76;
  material.sheenColor.setHex(0xc98270);
  material.emissive.setHex(0x160404);
  material.emissiveIntensity = 0.025;
  material.envMapIntensity = 0.86;
  material.depthTest = true;
  material.needsUpdate = true;
}

function configureOpacityOcclusion(item, mesh, opacity) {
  const value = THREE.MathUtils.clamp(Number(opacity), 0, 1);
  const category = meshCategory(item);
  const solidSurface = ["organ", "segment", "vessel", "gallbladder"].includes(category);
  const fullyOpaque = solidSurface && value >= 0.999;
  mesh.material.transparent = !fullyOpaque;
  mesh.material.depthTest = true;
  mesh.material.depthWrite = fullyOpaque;
  mesh.material.needsUpdate = true;
}

function applySegmentAtlasAppearance(item, mesh) {
  const source = new THREE.Color(item.color || "#8c7568");
  const muted = source.clone().lerp(new THREE.Color(0x746961), 0.18);
  const light = muted.clone().offsetHSL(0, -0.03, 0.10);
  const deep = muted.clone().offsetHSL(0, 0.01, -0.15);
  applyOrganicVertexTone(mesh, muted.getHex(), light.getHex(), deep.getHex(), 0.52);
  const material = mesh.material;
  material.roughness = 0.54;
  material.metalness = 0;
  material.clearcoat = 0.18;
  material.clearcoatRoughness = 0.58;
  material.sheen = 0.16;
  material.sheenRoughness = 0.80;
  material.sheenColor.copy(light);
  material.emissive.copy(deep);
  material.emissiveIntensity = 0.04;
  material.envMapIntensity = 0.82;
  material.depthTest = true;
  material.depthWrite = true;
  mesh.renderOrder = 4;
  material.needsUpdate = true;
}

function applyScientificCurrentAppearance(presetName, item, mesh) {
  const category = meshCategory(item);
  if (category === "organ") applyHepaticTissueAppearance(mesh);
  else if (presetName === "segments" && category === "segment") applySegmentAtlasAppearance(item, mesh);
  else if (["vessel", "gallbladder", "candidate", "classified_region", "lesion"].includes(category)) {
    applyAnatomicalOverlayAppearance(item, mesh);
  }
}

function applyAnatomicRealisticAppearance(presetName, item, mesh) {
  applyScientificCurrentAppearance(presetName, item, mesh);
  const category = meshCategory(item);
  const material = mesh.material;
  if (category === "vessel") {
    mesh.geometry.deleteAttribute("color");
    material.vertexColors = false;
    material.color.setHex(String(item.role).includes("cava") ? 0x263d68 : 0x315f83);
    material.roughness = 0.31;
    material.clearcoat = 0.52;
    material.clearcoatRoughness = 0.24;
    material.sheen = 0.12;
    material.sheenRoughness = 0.55;
    material.sheenColor.setHex(0x799bb5);
    material.emissive.setHex(0x07111f);
    material.emissiveIntensity = 0.035;
    material.envMapIntensity = 0.82;
    material.needsUpdate = true;
    return;
  }
  if (category === "gallbladder") {
    mesh.geometry.deleteAttribute("color");
    material.vertexColors = false;
    material.color.setHex(0x53612c);
    material.roughness = 0.39;
    material.clearcoat = 0.40;
    material.clearcoatRoughness = 0.32;
    material.sheen = 0.10;
    material.sheenRoughness = 0.62;
    material.sheenColor.setHex(0x8c9966);
    material.emissive.setHex(0x0c1005);
    material.emissiveIntensity = 0.025;
    material.envMapIntensity = 0.70;
    material.needsUpdate = true;
    return;
  }
  if (category !== "organ" || realisticMaterialPack.state !== "ready") return;
  ensureSphericalTextureCoordinates(mesh);
  const textures = realisticMaterialPack.textures;
  mesh.geometry.deleteAttribute("color");
  material.vertexColors = false;
  material.color.setHex(0xffffff);
  material.map = textures.albedo;
  material.normalMap = textures.normal;
  const stability = currentRenderingQualityTier === "stability";
  material.normalScale.set(stability ? 0.27 : 0.58, stability ? 0.27 : 0.58);
  material.roughnessMap = textures.roughness;
  material.roughness = 0.51;
  material.clearcoat = stability ? 0.24 : 0.32;
  material.clearcoatRoughness = 0.34;
  material.sheen = 0.18;
  material.sheenRoughness = 0.64;
  material.sheenColor.setHex(0xc99182);
  material.emissive.setHex(0x210706);
  material.emissiveIntensity = 0.035;
  material.envMapIntensity = 0.68;
  material.needsUpdate = true;
}

function applyMaterialProfile(presetName, item, mesh) {
  restoreMaterialAppearance(mesh);
  if (currentRenderingProfile === ANATOMIC_REALISTIC_PROFILE) {
    applyAnatomicRealisticAppearance(presetName, item, mesh);
  } else {
    applyScientificCurrentAppearance(presetName, item, mesh);
  }
  mesh.userData.renderingProfile = currentRenderingProfile;
}

function syncRenderingProfileControl(message = null) {
  const button = controlsDiv.querySelector(".render-profile-button");
  const status = controlsDiv.querySelector(".render-profile-status");
  const active = currentRenderingProfile === ANATOMIC_REALISTIC_PROFILE;
  if (button) {
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
    button.textContent = active ? "Desativar textura realista" : "Ativar textura realista";
  }
  if (status) status.textContent = message || RENDERING_PROFILES[currentRenderingProfile].description;
}

async function setRenderingProfile(name, options = {}) {
  if (!RENDERING_PROFILES[name]) return false;
  if (name === ANATOMIC_REALISTIC_PROFILE) {
    syncRenderingProfileControl("Carregando pacote de textura anatômica…");
    try {
      await loadRealisticMaterialPack();
    } catch (error) {
      console.warn("Textura anatômica indisponível; baseline restaurado:", error);
      currentRenderingProfile = SCIENTIFIC_CURRENT_PROFILE;
      currentRenderingFallbackReason = "asset_load_error";
      syncRenderingProfileControl("Textura indisponível. Representação atual restaurada com segurança.");
      return false;
    }
  }
  const selectedBefore = selectedRole;
  const selectionContextBefore = selectionContextPreset;
  if (selectedBefore) clearStructureSelection({ hidePanel: false, resetContext: false });
  currentRenderingProfile = name;
  currentRenderingFallbackReason = options.fallbackReason || null;
  Object.entries(meshes).forEach(([role, mesh]) => {
    const item = meshItems[role] || { role };
    const visible = mesh.visible;
    const opacity = THREE.MathUtils.clamp(
      Number(mesh.userData.targetOpacity ?? mesh.material.opacity ?? 1), 0, 1,
    );
    applyMaterialProfile(currentMaterialProfile, item, mesh);
    mesh.userData.targetOpacity = opacity;
    configureOpacityOcclusion(item, mesh, opacity);
    mesh.material.opacity = visible ? opacity : 0;
    mesh.visible = visible;
  });
  if (selectedBefore && meshes[selectedBefore]) {
    selectStructure(selectedBefore, {
      allowHidden: true,
      contextPreset: selectionContextBefore || currentPreset,
    });
  }
  syncRenderingProfileControl(options.message || null);
  renderer.toneMappingExposure = currentRenderingProfile === ANATOMIC_REALISTIC_PROFILE
    ? 1.43 : (currentMaterialProfile === "default" ? 1.28 : 1.35);
  if (!xrPresentationActive) {
    try { renderer.compile(scene, camera); } catch (_error) { /* pré-aquecimento opcional */ }
  }
  renderer.render(scene, camera);
  return true;
}

async function toggleRenderingProfile() {
  const next = currentRenderingProfile === ANATOMIC_REALISTIC_PROFILE
    ? SCIENTIFIC_CURRENT_PROFILE : ANATOMIC_REALISTIC_PROFILE;
  return setRenderingProfile(next);
}

function setRenderingQualityTier(tier = "quality") {
  if (!RENDERING_QUALITY_TIERS.includes(tier)) return false;
  if (currentRenderingQualityTier === tier) return true;
  currentRenderingQualityTier = tier;
  if (realisticMaterialPack.state === "ready") {
    const anisotropy = tier === "stability"
      ? 1 : Math.min(renderer.capabilities.getMaxAnisotropy?.() || 1, 4);
    Object.values(realisticMaterialPack.textures).forEach((texture) => {
      texture.anisotropy = anisotropy;
      texture.needsUpdate = true;
    });
  }
  if (currentRenderingProfile === ANATOMIC_REALISTIC_PROFILE) {
    Object.entries(meshes).forEach(([role, mesh]) => {
      const item = meshItems[role] || { role };
      const visible = mesh.visible;
      const opacity = THREE.MathUtils.clamp(
        Number(mesh.userData.targetOpacity ?? mesh.material.opacity ?? 1), 0, 1,
      );
      applyMaterialProfile(currentMaterialProfile, item, mesh);
      mesh.userData.targetOpacity = opacity;
      configureOpacityOcclusion(item, mesh, opacity);
      mesh.material.opacity = visible ? opacity : 0;
      mesh.visible = visible;
    });
  }
  return true;
}

function presetMeshState(presetName, item) {
  const category = meshCategory(item);
  const defaults = {
    visible: item.default_visible !== false,
    opacity: Number.isFinite(Number(item.opacity)) ? Number(item.opacity) : 0.88,
  };
  if (presetName === "default") {
    const visible = ["organ", "vessel", "gallbladder", "candidate", "lesion"].includes(category);
    const opacity = {
      organ: 1.0, vessel: 1.0, gallbladder: 1.0,
      candidate: 0.84, classified_region: 0.07, lesion: 0.90,
    }[category] ?? defaults.opacity;
    return { visible, opacity };
  }
  if (presetName === "anatomy") {
    const visible = ["organ", "vessel", "gallbladder"].includes(category);
    const opacity = { organ: 0.30, vessel: 1.0, gallbladder: 1.0 }[category] ?? defaults.opacity;
    return { visible, opacity };
  }
  if (presetName === "triage") {
    const visible = ["organ", "candidate", "classified_region", "lesion", "vessel", "gallbladder"].includes(category);
    const opacity = {
      organ: 0.34, candidate: 0.88, classified_region: 0.14,
      lesion: 0.92, vessel: 1.0, gallbladder: 1.0,
    }[category] ?? defaults.opacity;
    return { visible, opacity };
  }
  if (presetName === "segments") {
    const visible = ["segment", "vessel"].includes(category);
    const opacity = {
      segment: 1.0, vessel: 1.0,
    }[category] ?? defaults.opacity;
    return { visible, opacity };
  }
  return defaults;
}

function syncStructureControl(role, visible, opacity) {
  const checkbox = controlsDiv.querySelector(`input[type=checkbox][data-role="${role}"]`);
  const slider = controlsDiv.querySelector(`input[type=range][data-role="${role}"]`);
  if (checkbox) checkbox.checked = visible;
  if (slider) slider.value = String(opacity);
}

function markPreset(name, description) {
  currentPreset = name;
  controlsDiv.querySelectorAll(".preset-button").forEach((button) => {
    const active = button.dataset.preset === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const status = controlsDiv.querySelector(".preset-status");
  if (status) status.textContent = description;
}

function updateAnatomicalViewButtons() {
  document.querySelectorAll(".anatomical-view-button").forEach((button) => {
    const active = button.dataset.anatomicalView === currentAnatomicalView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function markCustomPreset() {
  currentAnatomicalView = "none";
  updateAnatomicalViewButtons();
  markPreset("custom", "Ajuste personalizado. Use um preset para restaurar uma composição padronizada.");
}

function applyPreset(name) {
  const preset = VIEWER_PRESETS[name];
  if (!preset) return false;
  clearStructureSelection();
  const hasSegments = REQUIRED_COUINAUD_ROLES.every((role) => Boolean(meshItems[role] && meshes[role]));
  if (preset.requiresSegments && !hasSegments) return false;
  currentMaterialProfile = name;
  Object.entries(meshes).forEach(([role, mesh]) => {
    const item = meshItems[role] || { role };
    const state = presetMeshState(name, item);
    applyMaterialProfile(name, item, mesh);
    mesh.userData.targetOpacity = state.opacity;
    configureOpacityOcclusion(item, mesh, state.opacity);
    syncStructureControl(role, state.visible, state.opacity);
    animateMeshVisibility(mesh, state.visible);
  });
  markPreset(name, preset.description);
  renderer.toneMappingExposure = name === "default" ? 1.28 : 1.35;
  applyView(name === "segments" ? "anterior" : "padrao");
  return true;
}

function applyInitialPreset(manifest) {
  const requestedRaw = String(
    manifest?.viewer_features?.default_visual_preset || DEFAULT_VISUAL_PRESET,
  );
  const requested = ["realistic", "surface"].includes(requestedRaw) ? DEFAULT_VISUAL_PRESET : requestedRaw;
  const authorized = VIEWER_PRESETS[requested] ? requested : DEFAULT_VISUAL_PRESET;
  const hasLiver = Object.values(meshItems).some((item) => meshCategory(item) === "organ");
  if (!hasLiver || !applyPreset(authorized)) {
    markCustomPreset();
    return "custom";
  }
  return authorized;
}

function buildControls(items) {
  let controlIndex = 0;
  const stagger = (element) => {
    element.style.setProperty("--control-delay", `${Math.min(controlIndex, 8) * 48}ms`);
    controlIndex += 1;
  };
  const appearancePanel = document.createElement("div");
  appearancePanel.className = "row rendering-profile-panel";
  stagger(appearancePanel);
  const appearanceHeading = document.createElement("div");
  appearanceHeading.className = "preset-heading";
  const appearanceTitle = document.createElement("strong");
  appearanceTitle.textContent = "Acabamento anatômico";
  const appearanceHint = document.createElement("span");
  appearanceHint.textContent = "não altera medidas";
  appearanceHeading.append(appearanceTitle, appearanceHint);
  const appearanceButton = makeButton(
    "Ativar textura realista", "render-profile-button secondary-button", toggleRenderingProfile,
  );
  appearanceButton.setAttribute("aria-pressed", "false");
  const appearanceStatus = document.createElement("p");
  appearanceStatus.className = "render-profile-status preset-status";
  appearancePanel.append(appearanceHeading, appearanceButton, appearanceStatus);
  controlsDiv.appendChild(appearancePanel);
  syncRenderingProfileControl();

  const presetPanel = document.createElement("div");
  presetPanel.className = "row preset-panel";
  stagger(presetPanel);
  const presetHeading = document.createElement("div");
  presetHeading.className = "preset-heading";
  const presetTitle = document.createElement("strong");
  presetTitle.textContent = "Composição da cena";
  const presetHint = document.createElement("span");
  presetHint.textContent = "presets de revisão";
  presetHeading.append(presetTitle, presetHint);
  const presetGrid = document.createElement("div");
  presetGrid.className = "preset-grid";
  const hasSegments = REQUIRED_COUINAUD_ROLES.every((role) => Boolean(meshItems[role] && meshes[role]));
  for (const [name, preset] of Object.entries(VIEWER_PRESETS)) {
    const button = makeButton(preset.label, "preset-button", () => applyPreset(name));
    button.dataset.preset = name;
    button.setAttribute("aria-pressed", "false");
    if (preset.requiresSegments && !hasSegments) {
      button.disabled = true;
      button.title = "Segmentos de Couinaud ainda não disponíveis neste exame.";
    }
    presetGrid.appendChild(button);
  }
  const presetStatus = document.createElement("p");
  presetStatus.className = "preset-status";
  presetStatus.textContent = "Exibição original do manifesto. Escolha um preset para organizar a cena.";
  presetPanel.append(presetHeading, presetGrid, presetStatus);
  controlsDiv.appendChild(presetPanel);

  const views = document.createElement("div");
  views.className = "row views";
  stagger(views);
  for (const [name, label] of [
    ["padrao", "Padrão"], ["anterior", "Anterior"],
    ["superior", "Superior"], ["direita", "Direita"],
  ]) {
    const button = makeButton(label, "viewbtn", () => applyView(name));
    button.dataset.view = name;
    views.appendChild(button);
  }
  controlsDiv.appendChild(views);

  const globalActions = document.createElement("div");
  globalActions.className = "structure-actions";
  stagger(globalActions);
  globalActions.append(
    makeButton("Mostrar todas", "secondary-button", () => {
      markCustomPreset();
      Object.values(meshes).forEach((mesh) => animateMeshVisibility(mesh, true));
      controlsDiv.querySelectorAll("input[type=checkbox][data-role]").forEach((box) => { box.checked = true; });
    }),
    makeButton("Ocultar todas", "secondary-button", () => {
      markCustomPreset();
      clearStructureSelection();
      Object.values(meshes).forEach((mesh) => animateMeshVisibility(mesh, false));
      controlsDiv.querySelectorAll("input[type=checkbox][data-role]").forEach((box) => { box.checked = false; });
    }),
  );
  controlsDiv.appendChild(globalActions);

  for (const item of items) {
    if (!meshes[item.role]) continue;
    const row = document.createElement("div");
    row.className = "row structure-row";
    stagger(row);
    const heading = document.createElement("div");
    heading.className = "structure-heading";
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = item.default_visible !== false;
    checkbox.dataset.role = item.role;
    checkbox.addEventListener("change", () => {
      markCustomPreset();
      if (!checkbox.checked && selectedRole === item.role) clearStructureSelection();
      animateMeshVisibility(meshes[item.role], checkbox.checked);
      animateElementFeedback(row);
    });
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = item.color;
    label.append(checkbox, swatch, document.createTextNode(item.label || item.role));
    const isolate = makeButton("Só", "isolate-button", () => {
      markCustomPreset();
      if (selectedRole && selectedRole !== item.role) clearStructureSelection();
      Object.entries(meshes).forEach(([role, mesh]) => animateMeshVisibility(mesh, role === item.role));
      controlsDiv.querySelectorAll("input[type=checkbox][data-role]").forEach((box) => {
        box.checked = box.dataset.role === item.role;
      });
      animateElementFeedback(row);
    });
    heading.append(label, isolate);
    const opacity = document.createElement("input");
    opacity.type = "range";
    opacity.min = "0";
    opacity.max = "1";
    opacity.step = "0.05";
    opacity.value = String(Number.isFinite(Number(item.opacity)) ? Number(item.opacity) : 0.88);
    opacity.dataset.role = item.role;
    opacity.setAttribute("aria-label", `Opacidade de ${item.label || item.role}`);
    opacity.addEventListener("input", () => {
      markCustomPreset();
      const value = Number(opacity.value);
      meshes[item.role].userData.targetOpacity = value;
      configureOpacityOcclusion(item, meshes[item.role], value);
      if (meshes[item.role].visible) meshes[item.role].material.opacity = value;
    });
    row.append(heading, opacity);
    controlsDiv.appendChild(row);
  }
  applyView(currentView);
}

function safeClippingPercent(percent, inverted) {
  const numeric = THREE.MathUtils.clamp(Number(percent), 0, 100);
  // Preserve a small anatomical context at the destructive edge instead of
  // making the complete liver appear missing after moving/inverting a plane.
  return inverted ? Math.max(numeric, 5) : Math.min(numeric, 95);
}

function refreshClippingPlaneWorld() {
  if (!clipEnabled.checked || sourceBounds.isEmpty()) return false;
  group.updateWorldMatrix(true, false);
  clippingNormalMatrix.getNormalMatrix(group.matrixWorld);
  clippingPlane.copy(localClippingPlane).applyMatrix4(group.matrixWorld, clippingNormalMatrix);
  return true;
}

function updateClipping() {
  if (!currentManifest || sourceBounds.isEmpty()) return;
  const enabled = clipEnabled.checked;
  const axis = clipAxis.value;
  const axisIndex = { x: 0, y: 1, z: 2 }[axis];
  const minimum = [sourceBounds.min.x, sourceBounds.min.y, sourceBounds.min.z][axisIndex];
  const maximum = [sourceBounds.max.x, sourceBounds.max.y, sourceBounds.max.z][axisIndex];
  const safePercent = safeClippingPercent(clipPosition.value, clipInvert.checked);
  if (safePercent !== Number(clipPosition.value)) clipPosition.value = String(safePercent);
  const percent = safePercent / 100;
  const coordinate = minimum + (maximum - minimum) * percent;
  const normal = new THREE.Vector3(
    axis === "x" ? 1 : 0,
    axis === "y" ? 1 : 0,
    axis === "z" ? 1 : 0,
  );
  if (clipInvert.checked) normal.multiplyScalar(-1);
  const point = new THREE.Vector3();
  point[axis] = coordinate;
  localClippingPlane.setFromNormalAndCoplanarPoint(normal, point);
  refreshClippingPlaneWorld();
  Object.values(meshes).forEach((mesh) => {
    mesh.material.clippingPlanes = enabled ? [clippingPlane] : [];
    if (mesh.material.userData.clippingEnabled !== enabled) {
      mesh.material.userData.clippingEnabled = enabled;
      mesh.material.needsUpdate = true;
    }
  });
  clipValue.textContent = `${Math.round(percent * 100)}% · ${coordinate.toFixed(1)} mm em LPS`;
}

function markReferenceSyncManual() {
  if (!referenceSync.checked) return;
  referenceSync.checked = false;
  referenceSyncPreviousClippingState = null;
  referenceSyncStatus.textContent = "Sincronização pausada: corte 3D em ajuste manual.";
}

clipEnabled.addEventListener("change", () => { markReferenceSyncManual(); updateClipping(); });
clipAxis.addEventListener("change", () => { markReferenceSyncManual(); updateClipping(); });
clipInvert.addEventListener("change", () => { markReferenceSyncManual(); updateClipping(); });
clipPosition.addEventListener("input", () => { markReferenceSyncManual(); updateClipping(); });

function metric(parent, label, value) {
  const item = document.createElement("div");
  const name = document.createElement("span");
  const content = document.createElement("strong");
  name.textContent = label;
  content.textContent = value;
  item.append(name, content);
  parent.appendChild(item);
}

function structureCategoryLabel(item) {
  return {
    organ: "Órgão segmentado",
    vessel: "Estrutura vascular",
    gallbladder: "Estrutura biliar",
    segment: "Segmento de Couinaud",
    candidate: "Região automática não confirmada",
    classified_region: "Camada usada pela classificação",
    lesion: "Região de lesão no manifesto",
    other: "Estrutura complementar",
  }[meshCategory(item)] || "Estrutura complementar";
}

function clearStructureSelection({ hidePanel = true, resetContext = true } = {}) {
  const mesh = selectedRole ? meshes[selectedRole] : null;
  if (mesh && selectedMaterialState) {
    mesh.material.emissive.setHex(selectedMaterialState.emissive);
    mesh.material.emissiveIntensity = selectedMaterialState.emissiveIntensity;
    mesh.material.clearcoat = selectedMaterialState.clearcoat;
    mesh.material.needsUpdate = true;
  }
  selectedRole = null;
  selectedMaterialState = null;
  selectionIsolated = false;
  if (resetContext) selectionContextPreset = null;
  if (selectionActionStatus) selectionActionStatus.textContent = "";
  if (selectionDimensionsResult) selectionDimensionsResult.hidden = true;
  if (hidePanel && selectionSection) selectionSection.hidden = true;
  applyWireframeState();
}

function selectStructure(role, options = {}) {
  const mesh = meshes[role];
  const item = meshItems[role];
  if (!mesh || !item || (!mesh.visible && options.allowHidden !== true)) return false;
  const contextPreset = options.contextPreset || (
    VIEWER_PRESETS[currentPreset] ? currentPreset : DEFAULT_VISUAL_PRESET
  );
  clearStructureSelection({ hidePanel: false });
  selectedRole = role;
  selectionContextPreset = contextPreset;
  selectedMaterialState = {
    emissive: mesh.material.emissive.getHex(),
    emissiveIntensity: Number(mesh.material.emissiveIntensity),
    clearcoat: Number(mesh.material.clearcoat),
  };
  if (!xrPresentationActive) {
    mesh.material.emissive.setHex(0x2daf79);
    mesh.material.emissiveIntensity = Math.max(selectedMaterialState.emissiveIntensity + 0.24, 0.30);
    mesh.material.clearcoat = Math.max(selectedMaterialState.clearcoat, 0.30);
    mesh.material.needsUpdate = true;
  }
  const metrics = item.metrics || {};
  selectionName.textContent = item.label || role;
  selectionCategory.textContent = structureCategoryLabel(item);
  selectionMetrics.innerHTML = "";
  if (Number.isFinite(Number(metrics.source_mask_volume_ml))) {
    metric(selectionMetrics, "Volume", `${Number(metrics.source_mask_volume_ml).toFixed(1)} mL`);
  }
  if (Number.isFinite(Number(metrics.surface_area_cm2))) {
    metric(selectionMetrics, "Superfície", `${Number(metrics.surface_area_cm2).toFixed(1)} cm²`);
  }
  if (Number.isFinite(Number(metrics.triangles))) {
    metric(selectionMetrics, "Triângulos", Number(metrics.triangles).toLocaleString("pt-BR"));
  }
  const p95 = Number(metrics.surface_deviation_to_source_mask_mm?.p95);
  if (Number.isFinite(p95)) metric(selectionMetrics, "Desvio p95", `${p95.toFixed(2)} mm`);
  metric(selectionMetrics, "Malha fechada", metrics.watertight_and_manifold ? "sim" : "não");
  const warnings = Array.isArray(metrics.warnings) ? metrics.warnings : [];
  const category = meshCategory(item);
  const contextual = ["candidate", "classified_region", "lesion"].includes(category)
    ? "Esta camada é auxiliar e não confirma diagnóstico. " : "";
  selectionWarning.textContent = `${contextual}As métricas medem fidelidade à máscara fonte, não acurácia anatômica.${warnings.length ? ` Alertas: ${warnings.join(", ")}.` : ""}`;
  renderStructureDimensionSummary(role);
  selectionSection.hidden = false;
  if (mesh.visible && options.alignReference !== false) alignReferenceToStructure(item, mesh);
  applyWireframeState();
  if (options.scrollPanel !== false) {
    selectionSection.scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "nearest" });
  }
  return true;
}

function focusMeshRoles(roles, { viewName = "focus", margin = 1.32 } = {}) {
  const targets = roles.map((role) => meshes[role]).filter((mesh) => mesh?.visible);
  if (!targets.length) return false;
  scene.updateMatrixWorld(true);
  const bounds = new THREE.Box3();
  targets.forEach((mesh) => bounds.expandByObject(mesh));
  if (bounds.isEmpty()) return false;
  const sphere = bounds.getBoundingSphere(new THREE.Sphere());
  const radius = Math.max(sphere.radius, sceneRadius * 0.035, 0.5);
  const direction = camera.position.clone().sub(orbit.target);
  if (direction.lengthSq() < 1e-6) direction.copy(VIEWS.padrao);
  direction.normalize();
  const distance = fitDistance(radius, margin);
  const targetPosition = sphere.center.clone().addScaledVector(direction, distance);
  camera.near = Math.max(distance / 1000, 0.01);
  camera.far = Math.max(distance * 12, sceneRadius * 12);
  camera.updateProjectionMatrix();
  currentView = viewName;
  document.querySelectorAll(".viewbtn").forEach((button) => button.classList.remove("active"));
  const immediate = reducedMotion.matches || sceneRadius <= 1;
  if (immediate) {
    cameraTween = null;
    camera.position.copy(targetPosition);
    orbit.target.copy(sphere.center);
    orbit.update();
  } else {
    orbit.enabled = false;
    cameraTween = {
      fromPosition: camera.position.clone(),
      toPosition: targetPosition,
      fromTarget: orbit.target.clone(),
      toTarget: sphere.center.clone(),
      startedAt: performance.now(),
      duration: 650,
    };
  }
  return true;
}

function focusSelectedStructure() {
  if (!selectedRole || !focusMeshRoles([selectedRole])) return false;
  currentAnatomicalView = "none";
  updateAnatomicalViewButtons();
  selectionActionStatus.textContent = "Câmera enquadrada na estrutura selecionada.";
  animateElementFeedback(selectionSection, "is-feedback");
  return true;
}

function isolateSelectedStructure() {
  if (!selectedRole || !meshes[selectedRole]) return false;
  if (!selectionContextPreset) {
    selectionContextPreset = VIEWER_PRESETS[currentPreset] ? currentPreset : DEFAULT_VISUAL_PRESET;
  }
  markCustomPreset();
  Object.entries(meshes).forEach(([role, mesh]) => {
    const visible = role === selectedRole;
    animateMeshVisibility(mesh, visible);
    syncStructureControl(role, visible, Number(mesh.userData.targetOpacity ?? mesh.material.opacity));
  });
  selectionIsolated = true;
  selectionActionStatus.textContent = "Estrutura isolada; use Restaurar contexto para voltar à composição anterior.";
  animateElementFeedback(selectionSection, "is-feedback");
  return true;
}

function restoreSelectedContext() {
  if (!selectedRole) return false;
  const role = selectedRole;
  const preset = VIEWER_PRESETS[selectionContextPreset]
    ? selectionContextPreset : DEFAULT_VISUAL_PRESET;
  if (!applyPreset(preset)) return false;
  selectionIsolated = false;
  if (meshes[role]?.visible) selectStructure(role);
  if (selectionActionStatus) selectionActionStatus.textContent = `Contexto restaurado: ${VIEWER_PRESETS[preset].label}.`;
  return true;
}

function renderStructureDimensionSummary(role) {
  const result = structureMeasurements3d.find((measurement) => measurement.role === role);
  if (!result) {
    selectionDimensionsResult.hidden = true;
    selectionDimensionsMetrics.innerHTML = "";
    return;
  }
  selectionDimensionsMetrics.innerHTML = "";
  metric(selectionDimensionsMetrics, "Largura LR", `${result.left_right_mm.toFixed(1)} mm`);
  metric(selectionDimensionsMetrics, "Profundidade AP", `${result.anterior_posterior_mm.toFixed(1)} mm`);
  metric(selectionDimensionsMetrics, "Extensão SI", `${result.superior_inferior_mm.toFixed(1)} mm`);
  selectionDimensionsResult.hidden = false;
}

function clearStructureDimensionObjects() {
  const dimensionSet = new Set(structureDimensionObjects);
  structureDimensionObjects.forEach((object) => {
    objectScaleTweens.delete(object);
    object.removeFromParent();
    disposeObject(object);
  });
  measurementObjects = measurementObjects.filter((object) => !dimensionSet.has(object));
  structureDimensionObjects = [];
}

function trackDimensionObjects(startIndex) {
  structureDimensionObjects.push(...measurementObjects.slice(startIndex));
}

function dimensionGuide(start, end, color, label) {
  const geometry = new THREE.BufferGeometry().setFromPoints([start, end]);
  const material = new THREE.LineBasicMaterial({ color, depthTest: false, transparent: true, opacity: 0.96 });
  const line = new THREE.Line(geometry, material);
  line.renderOrder = 22;
  measurementGroup.add(line);
  measurementObjects.push(line);
  structureDimensionObjects.push(line);
  let startIndex = measurementObjects.length;
  marker(start, color);
  marker(end, color);
  trackDimensionObjects(startIndex);
  startIndex = measurementObjects.length;
  textSprite(label, start.clone().add(end).multiplyScalar(0.5));
  trackDimensionObjects(startIndex);
}

function measureSelectedStructure3d() {
  const role = selectedRole;
  const mesh = role ? meshes[role] : null;
  const item = role ? meshItems[role] : null;
  if (!mesh || !item || !mesh.visible) return false;
  if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
  const bounds = mesh.geometry.boundingBox?.clone();
  if (!bounds) return false;
  if (bounds.isEmpty()) return false;
  const size = bounds.getSize(new THREE.Vector3());
  const authoritativeDimensions = Array.isArray(item.metrics?.dimensions_mm)
    ? item.metrics.dimensions_mm.map(Number) : [];
  const dimensions = authoritativeDimensions.length === 3
    && authoritativeDimensions.every((value) => Number.isFinite(value) && value > 0)
    ? authoritativeDimensions : [size.x, size.y, size.z];
  if (dimensions.some((value) => !Number.isFinite(value) || value <= 0)) return false;
  const dimensionsFromMask = authoritativeDimensions.length === 3
    && authoritativeDimensions.every((value) => Number.isFinite(value) && value > 0);
  const measurement = {
    role,
    label: item.label || role,
    left_right_mm: Number(size.x.toFixed(3)),
    anterior_posterior_mm: Number(size.y.toFixed(3)),
    superior_inferior_mm: Number(size.z.toFixed(3)),
    method: dimensionsFromMask
      ? "source_binary_mask_axis_aligned_lps_bounding_box"
      : "selected_segmentation_mesh_axis_aligned_lps_bounding_box",
    coordinate_system: "LPS",
    source: dimensionsFromMask ? "source_binary_mask_metrics" : "selected_segmentation_mesh",
    approximate: !dimensionsFromMask,
  };
  structureMeasurements3d = structureMeasurements3d.filter((entry) => entry.role !== role);
  structureMeasurements3d.push(measurement);
  clearStructureDimensionObjects();
  const padding = Math.max(sceneRadius * 0.035, Math.max(...dimensions) * 0.04, 2);
  const xStart = new THREE.Vector3(bounds.min.x, bounds.min.y - padding, bounds.min.z - padding);
  const xEnd = new THREE.Vector3(bounds.max.x, bounds.min.y - padding, bounds.min.z - padding);
  const yStart = new THREE.Vector3(bounds.max.x + padding, bounds.min.y, bounds.min.z - padding);
  const yEnd = new THREE.Vector3(bounds.max.x + padding, bounds.max.y, bounds.min.z - padding);
  const zStart = new THREE.Vector3(bounds.max.x + padding, bounds.max.y + padding, bounds.min.z);
  const zEnd = new THREE.Vector3(bounds.max.x + padding, bounds.max.y + padding, bounds.max.z);
  dimensionGuide(xStart, xEnd, 0xd96b5f, `LR ${measurement.left_right_mm.toFixed(1)} mm`);
  dimensionGuide(yStart, yEnd, 0x2daf79, `AP ${measurement.anterior_posterior_mm.toFixed(1)} mm`);
  dimensionGuide(zStart, zEnd, 0x5f82c7, `SI ${measurement.superior_inferior_mm.toFixed(1)} mm`);
  renderStructureDimensionSummary(role);
  focusMeshRoles([role], { viewName: "focus", margin: 1.58 });
  currentAnatomicalView = "none";
  updateAnatomicalViewButtons();
  selectionActionStatus.textContent = `Dimensões 3D de ${measurement.label} calculadas sobre a malha segmentada.`;
  updateMeasurementStatus();
  animateElementFeedback(selectionDimensionsResult, "is-feedback");
  return true;
}

function anatomicalTargetRoles(name) {
  const definition = ANATOMICAL_VIEWS[name];
  if (!definition) return [];
  return Object.entries(meshItems)
    .filter(([, item]) => definition.targetCategories.includes(meshCategory(item)))
    .map(([role]) => role);
}

function anatomicalViewAvailable(name) {
  if (name === "segments") {
    return REQUIRED_COUINAUD_ROLES.every((role) => Boolean(meshes[role]));
  }
  return anatomicalTargetRoles(name).length > 0;
}

function renderAnatomicalViewControls() {
  anatomicalViewsSection.hidden = false;
  document.querySelectorAll(".anatomical-view-button").forEach((button) => {
    const name = button.dataset.anatomicalView;
    const available = anatomicalViewAvailable(name);
    button.disabled = !available;
    button.title = available ? ANATOMICAL_VIEWS[name].description : "Estrutura não disponível neste exame.";
  });
  updateAnatomicalViewButtons();
  anatomicalViewStatus.textContent = "Escolha um atalho para enquadrar uma camada anatômica sem alterar as malhas.";
  renderSavedViews();
}

function applyAnatomicalView(name) {
  const definition = ANATOMICAL_VIEWS[name];
  const roles = anatomicalTargetRoles(name);
  if (!definition || !anatomicalViewAvailable(name) || !roles.length) return false;
  if (!applyPreset(definition.preset)) return false;
  clipEnabled.checked = false;
  updateClipping();
  currentAnatomicalView = name;
  selectionIsolated = false;
  focusMeshRoles(roles, { viewName: "anatomical", margin: 1.38 });
  updateAnatomicalViewButtons();
  anatomicalViewStatus.textContent = definition.description;
  animateElementFeedback(anatomicalViewsSection, "is-feedback");
  return true;
}

function currentVisibleRoles() {
  return [...controlsDiv.querySelectorAll('input[type="checkbox"][data-role]')]
    .filter((checkbox) => checkbox.checked)
    .map((checkbox) => checkbox.dataset.role);
}

function savedViewPayload(view) {
  return {
    bookmark_id: view.bookmark_id,
    label: view.label,
    active_view: view.active_view,
    active_preset: view.active_preset,
    active_anatomical_view: view.active_anatomical_view,
    material_profile: view.material_profile,
    rendering_profile: view.rendering_profile,
    selected_role: view.selected_role,
    selection_isolated: view.selection_isolated,
    camera_position_mm: view.camera_position_mm,
    camera_target_mm: view.camera_target_mm,
    reference_sync_enabled: view.reference_sync_enabled,
    reference_view: view.reference_view,
    reference_frame_index: view.reference_frame_index,
    clipping: view.clipping,
    visible_roles: view.visible_roles,
    opacity_by_role: view.opacity_by_role,
  };
}

function saveCurrentView() {
  if (!viewerReadyForReview) {
    savedViewStatus.textContent = "Aguarde o carregamento completo antes de salvar uma vista.";
    return false;
  }
  if (savedViews.length >= MAX_SAVED_VIEWS) {
    savedViewStatus.textContent = `Limite de ${MAX_SAVED_VIEWS} marcadores por revisão atingido.`;
    return false;
  }
  savedViewSequence += 1;
  const selectedLabel = selectedRole ? (meshItems[selectedRole]?.label || selectedRole) : null;
  const anatomicalLabel = ANATOMICAL_VIEWS[currentAnatomicalView]?.label;
  const label = `Vista ${savedViewSequence} · ${selectedLabel || anatomicalLabel || "Cena 3D"}`;
  const opacityByRole = {};
  Object.entries(meshes).forEach(([role, mesh]) => {
    opacityByRole[role] = Number(mesh.userData.targetOpacity ?? mesh.material.opacity);
  });
  renderer.render(scene, camera);
  let snapshotDataUrl = "";
  try {
    snapshotDataUrl = renderer.domElement.toDataURL("image/png");
  } catch (error) {
    console.warn("Captura comparativa indisponível:", error);
  }
  savedViews.push({
    bookmark_id: `view-${String(savedViewSequence).padStart(3, "0")}`,
    label,
    active_view: currentView,
    active_preset: currentPreset,
    active_anatomical_view: currentAnatomicalView,
    material_profile: currentMaterialProfile,
    rendering_profile: currentRenderingProfile,
    selected_role: selectedRole,
    selection_isolated: selectionIsolated,
    camera_position_mm: camera.position.toArray().map((value) => Number(value.toFixed(4))),
    camera_target_mm: orbit.target.toArray().map((value) => Number(value.toFixed(4))),
    reference_sync_enabled: referenceSync.checked,
    reference_view: referenceView,
    reference_frame_index: Number(referenceSlider.value),
    clipping: {
      enabled: clipEnabled.checked,
      axis: clipAxis.value,
      position_percent: Number(clipPosition.value),
      inverted: clipInvert.checked,
    },
    visible_roles: currentVisibleRoles(),
    opacity_by_role: opacityByRole,
    snapshot_data_url: snapshotDataUrl,
  });
  renderSavedViews();
  savedViewStatus.textContent = `${label} salva para esta revisão.`;
  return true;
}

function restoreSavedView(bookmarkId) {
  const view = savedViews.find((candidate) => candidate.bookmark_id === bookmarkId);
  if (!view) return false;
  clearStructureSelection();
  currentMaterialProfile = VIEWER_PRESETS[view.material_profile]
    ? view.material_profile : DEFAULT_VISUAL_PRESET;
  currentRenderingProfile = RENDERING_PROFILES[view.rendering_profile]
    ? view.rendering_profile : SCIENTIFIC_CURRENT_PROFILE;
  Object.entries(meshes).forEach(([role, mesh]) => {
    const item = meshItems[role] || { role };
    const opacity = THREE.MathUtils.clamp(Number(view.opacity_by_role[role] ?? 1), 0, 1);
    const visible = view.visible_roles.includes(role);
    applyMaterialProfile(currentMaterialProfile, item, mesh);
    mesh.userData.targetOpacity = opacity;
    configureOpacityOcclusion(item, mesh, opacity);
    syncStructureControl(role, visible, opacity);
    animateMeshVisibility(mesh, visible);
  });
  const preset = VIEWER_PRESETS[view.active_preset];
  syncRenderingProfileControl();
  markPreset(view.active_preset, preset?.description || "Composição personalizada restaurada de um marcador.");
  currentAnatomicalView = ANATOMICAL_VIEWS[view.active_anatomical_view]
    ? view.active_anatomical_view : "none";
  updateAnatomicalViewButtons();
  anatomicalViewStatus.textContent = ANATOMICAL_VIEWS[currentAnatomicalView]?.description
    || "Vista personalizada restaurada de um marcador de revisão.";
  if (currentManifest?.reference_images?.views?.[view.reference_view]?.frames?.length) {
    selectReferenceView(view.reference_view, { sync: false });
    const maximum = Number(referenceSlider.max);
    referenceSlider.value = String(Math.min(Math.max(view.reference_frame_index, 0), maximum));
    renderReferenceFrame();
  }
  referenceSync.checked = view.reference_sync_enabled;
  clipEnabled.checked = view.clipping.enabled;
  clipAxis.value = view.clipping.axis;
  clipPosition.value = String(view.clipping.position_percent);
  clipInvert.checked = view.clipping.inverted;
  updateClipping();
  const targetPosition = new THREE.Vector3().fromArray(view.camera_position_mm);
  const targetOrbit = new THREE.Vector3().fromArray(view.camera_target_mm);
  const distance = Math.max(targetPosition.distanceTo(targetOrbit), 1);
  camera.near = Math.max(distance / 1000, 0.01);
  camera.far = Math.max(distance * 12, sceneRadius * 12);
  camera.updateProjectionMatrix();
  currentView = "saved";
  document.querySelectorAll(".viewbtn").forEach((button) => button.classList.remove("active"));
  if (reducedMotion.matches) {
    cameraTween = null;
    camera.position.copy(targetPosition);
    orbit.target.copy(targetOrbit);
    orbit.update();
  } else {
    orbit.enabled = false;
    cameraTween = {
      fromPosition: camera.position.clone(),
      toPosition: targetPosition,
      fromTarget: orbit.target.clone(),
      toTarget: targetOrbit,
      startedAt: performance.now(),
      duration: 650,
    };
  }
  selectionIsolated = view.selection_isolated;
  if (view.selected_role && view.visible_roles.includes(view.selected_role)) {
    selectStructure(view.selected_role, {
      alignReference: false,
      scrollPanel: false,
      contextPreset: VIEWER_PRESETS[view.active_preset] ? view.active_preset : DEFAULT_VISUAL_PRESET,
    });
    selectionIsolated = view.selection_isolated;
  }
  savedViewStatus.textContent = `${view.label} restaurada com câmera, corte e opacidades salvos.`;
  animateElementFeedback(anatomicalViewsSection, "is-feedback");
  return true;
}

function removeSavedView(bookmarkId) {
  const previousLength = savedViews.length;
  savedViews = savedViews.filter((view) => view.bookmark_id !== bookmarkId);
  comparedSavedViewIds = comparedSavedViewIds.filter((id) => id !== bookmarkId);
  renderSavedViews();
  savedViewStatus.textContent = savedViews.length === previousLength
    ? "Marcador não encontrado." : "Marcador removido desta revisão.";
}

function toggleSavedViewComparison(bookmarkId) {
  if (comparedSavedViewIds.includes(bookmarkId)) {
    comparedSavedViewIds = comparedSavedViewIds.filter((id) => id !== bookmarkId);
  } else if (comparedSavedViewIds.length < 2) {
    comparedSavedViewIds.push(bookmarkId);
  } else {
    savedViewComparisonStatus.textContent = "Remova A ou B antes de escolher outra vista.";
    animateElementFeedback(savedViewComparison, "is-feedback");
    return false;
  }
  renderSavedViews();
  return true;
}

function renderSavedViewComparison() {
  const selected = comparedSavedViewIds
    .map((id) => savedViews.find((view) => view.bookmark_id === id))
    .filter(Boolean);
  savedViewComparison.hidden = savedViews.length < 2;
  savedViewComparisonGrid.innerHTML = "";
  selected.forEach((view, index) => {
    const figure = document.createElement("figure");
    figure.tabIndex = 0;
    figure.setAttribute("role", "button");
    figure.setAttribute("aria-label", `Abrir comparação ${index === 0 ? "A" : "B"}: ${view.label}`);
    const image = document.createElement("img");
    image.src = view.snapshot_data_url;
    image.alt = `Captura 3D ${index === 0 ? "A" : "B"} — ${view.label}`;
    const caption = document.createElement("figcaption");
    caption.textContent = `${index === 0 ? "A" : "B"} · ${view.label}`;
    figure.append(image, caption);
    figure.addEventListener("click", () => restoreSavedView(view.bookmark_id));
    figure.addEventListener("keydown", (event) => {
      if (["Enter", " "].includes(event.key)) {
        event.preventDefault();
        restoreSavedView(view.bookmark_id);
      }
    });
    savedViewComparisonGrid.appendChild(figure);
  });
  if (selected.length === 2) {
    savedViewComparisonStatus.textContent = "Comparação pronta. Clique em A ou B para restaurar essa cena 3D.";
  } else if (savedViews.length >= 2) {
    savedViewComparisonStatus.textContent = `Selecione ${2 - selected.length} vista(s) adicional(is) para comparar.`;
  } else {
    savedViewComparisonStatus.textContent = "Salve pelo menos duas vistas para iniciar a comparação.";
  }
}

function renderSavedViews() {
  if (!savedViewsDiv) return;
  savedViewsDiv.innerHTML = "";
  savedViews.forEach((view) => {
    const row = document.createElement("div");
    row.className = "saved-view-row";
    const label = document.createElement("span");
    label.textContent = view.label;
    const compareIndex = comparedSavedViewIds.indexOf(view.bookmark_id);
    const compare = makeButton(
      compareIndex >= 0 ? (compareIndex === 0 ? "A" : "B") : "Comparar",
      "secondary-button compare-view-button",
      () => toggleSavedViewComparison(view.bookmark_id),
    );
    compare.classList.toggle("active", compareIndex >= 0);
    compare.setAttribute("aria-pressed", String(compareIndex >= 0));
    const open = makeButton("Abrir", "secondary-button", () => restoreSavedView(view.bookmark_id));
    const remove = makeButton("Excluir", "secondary-button", () => removeSavedView(view.bookmark_id));
    row.append(label, compare, open, remove);
    savedViewsDiv.appendChild(row);
  });
  if (!savedViews.length) savedViewStatus.textContent = "Nenhuma vista salva.";
  renderSavedViewComparison();
}

function renderQuality(items, manifest) {
  const section = $("quality-section");
  const cards = $("quality-cards");
  const summary = $("quality-summary");
  cards.innerHTML = "";
  summary.textContent = manifest.quality_scope || "";
  const measured = items.filter((item) => item.metrics);
  section.hidden = measured.length === 0;
  for (const item of measured) {
    const metrics = item.metrics;
    const card = document.createElement("article");
    card.className = `quality-card ${metrics.reconstruction_quality_gate_passed ? "pass" : "warning"}`;
    const title = document.createElement("header");
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = item.color;
    const name = document.createElement("strong");
    name.textContent = item.label || item.role;
    const status = document.createElement("em");
    status.textContent = metrics.reconstruction_quality_gate_passed ? "coerente" : "verificar";
    title.append(swatch, name, status);
    const grid = document.createElement("div");
    grid.className = "metric-grid";
    metric(grid, "Máscara", `${Number(metrics.source_mask_volume_ml).toFixed(1)} mL`);
    metric(grid, "Erro de volume", `${Number(metrics.mesh_volume_error_percent).toFixed(2)}%`);
    metric(grid, "Desvio p95", `${Number(metrics.surface_deviation_to_source_mask_mm?.p95 || 0).toFixed(2)} mm`);
    metric(grid, "Superfície", `${Number(metrics.surface_area_cm2).toFixed(1)} cm²`);
    metric(grid, "Triângulos", Number(metrics.triangles).toLocaleString("pt-BR"));
    metric(grid, "Fechada", metrics.watertight_and_manifold ? "sim" : "não");
    card.append(title, grid);
    if (metrics.warnings?.length) {
      const warning = document.createElement("p");
      warning.textContent = `Alertas técnicos: ${metrics.warnings.join(", ")}`;
      card.appendChild(warning);
    }
    cards.appendChild(card);
  }
}

function volumetryArtifactUrl(filename, fileMap, baseUrl) {
  if (fileMap?.[filename]) {
    const mime = filename.endsWith(".csv") ? "text/csv" : "application/json";
    const url = URL.createObjectURL(new Blob([fileMap[filename]], { type: mime }));
    referenceObjectUrls.push(url);
    return url;
  }
  return baseUrl ? remoteArtifactUrl(baseUrl, filename) : "";
}

function renderVolumetry(manifest, fileMap, baseUrl = "") {
  const section = $("volumetry-section");
  const payload = manifest.volumetry;
  const summary = payload?.whole_liver_summary;
  const volume = Number(summary?.volume_ml);
  if (!payload || !Number.isFinite(volume)) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  const quality = summary.quality || {};
  const grade = String(quality.grade || "B").toUpperCase();
  $("volumetry-hero").innerHTML = "";
  const primary = document.createElement("div");
  primary.className = "volumetry-primary";
  const value = document.createElement("strong");
  value.textContent = `${volume.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mL`;
  const label = document.createElement("span");
  label.textContent = "volume hepático total segmentado";
  primary.append(value, label);
  const badge = document.createElement("span");
  badge.className = `volumetry-grade grade-${grade.toLowerCase()}`;
  badge.title = quality.label || "qualidade técnica";
  badge.textContent = grade;
  $("volumetry-hero").append(primary, badge);

  const range = summary.technical_range_ml;
  $("volumetry-range").textContent = range && Number(range.source_count) > 1
    ? `Faixa técnica entre máscaras: ${Number(range.lower_ml).toFixed(1)}–${Number(range.upper_ml).toFixed(1)} mL · variação ${Number(range.spread_percent_of_reported).toFixed(1)}%`
    : "Faixa entre máscaras indisponível: medida derivada de uma única máscara aprovada.";

  const structureContainer = $("volumetry-structures");
  structureContainer.innerHTML = "";
  (payload.structures || [])
    .filter((item) => item.role !== "orgao")
    .forEach((item) => {
      const hasMesh = Boolean(meshes[item.role]);
      const row = document.createElement(hasMesh ? "button" : "div");
      row.className = "volumetry-row";
      if (hasMesh) {
        row.type = "button";
        row.title = "Selecionar esta estrutura no modelo 3D";
        row.addEventListener("click", () => selectStructure(item.role));
      }
      const name = document.createElement("span");
      name.textContent = item.label || item.role;
      const measured = document.createElement("strong");
      const usable = item.technical_quality?.usable !== false;
      measured.textContent = usable
        ? `${Number(item.volume_ml).toFixed(1)} mL${item.percent_of_whole_liver == null ? "" : ` · ${Number(item.percent_of_whole_liver).toFixed(1)}%`}`
        : "não publicável";
      row.append(name, measured);
      structureContainer.appendChild(row);
    });

  const partition = payload.couinaud_partition || {};
  const partitionNode = $("volumetry-partition");
  partitionNode.classList.toggle("warning", Boolean(partition.available && !partition.gate_passed));
  partitionNode.textContent = !partition.available
    ? "Segmentos de Couinaud não disponíveis neste exame."
    : partition.gate_passed
      ? "Couinaud: oito segmentos formam uma partição exata do fígado; volumes liberados."
      : `Couinaud não liberado para volumetria: cobertura ${Number(partition.liver_coverage_percent || 0).toFixed(1)}%, com lacunas ou voxels externos à máscara hepática.`;

  const downloads = $("volumetry-downloads");
  downloads.innerHTML = "";
  [[payload.artifacts?.json, "Baixar JSON"], [payload.artifacts?.csv, "Baixar CSV"]]
    .forEach(([filename, text]) => {
      const url = filename && volumetryArtifactUrl(filename, fileMap, baseUrl);
      if (!url) return;
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.textContent = text;
      downloads.appendChild(link);
    });
}

function renderRelationships(manifest) {
  const section = $("relationships-section");
  const container = $("relationships");
  container.innerHTML = "";
  const relationships = manifest.spatial_relationships || [];
  const context = manifest.lesion_context || manifest.candidate_context;
  if (!relationships.length && !context) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  const labels = Object.fromEntries((manifest.meshes || []).map((item) => [item.role, item.label || item.role]));
  if (context?.dominant_segment_role) {
    const row = document.createElement("div");
    row.className = "relationship-row";
    const sourceLabel = manifest.lesion_context ? "lesão" : "região candidata";
    row.textContent = `Maior sobreposição da ${sourceLabel}: ${labels[context.dominant_segment_role] || context.dominant_segment_role}`;
    container.appendChild(row);
  }
  for (const relationship of relationships) {
    const row = document.createElement("div");
    row.className = "relationship-row";
    const source = labels[relationship.source_role] || relationship.source_role || "Região";
    row.textContent = `${source} ↔ ${labels[relationship.target_role] || relationship.target_role}: ${Number(relationship.minimum_surface_distance_mm).toFixed(1)} mm`;
    container.appendChild(row);
  }
  const note = document.createElement("p");
  note.className = "section-note";
  note.textContent = "Distâncias aproximadas entre vértices das malhas; não representam margem cirúrgica.";
  container.appendChild(note);
}

function renderCandidate(manifest) {
  const section = $("candidate-section");
  const summary = $("candidate-summary");
  const receipt = manifest.candidate_region;
  const present = Boolean(receipt?.candidate_present && meshes.candidato);
  section.hidden = !receipt;
  $("review-candidate-row").hidden = !present;
  $("candidate-decision-row").hidden = !present;
  $("review-candidate").checked = false;
  $("candidate-decision").value = "";
  if (!receipt) return;
  const namedFinding = receipt.request?.subtype_label
    ? ` · categoria sugerida pela triagem: ${receipt.request.subtype_label}` : "";
  summary.textContent = present
    ? `${Number(receipt.component_count || 0)} componente(s) · ${(Number(receipt.total_candidate_volume_mm3 || 0) / 1000).toFixed(1)} mL${namedFinding} · revisão humana obrigatória`
    : "O localizador foi executado, mas não encontrou região candidata dentro do fígado.";
}

function remoteArtifactUrl(base, filename) {
  const safePath = String(filename).split("/").map(encodeURIComponent).join("/");
  return `${base}/${safePath}`;
}

function referenceFrameUrl(filename) {
  const buffer = referenceFiles[filename];
  if (buffer) {
    const url = URL.createObjectURL(new Blob([buffer], { type: "image/png" }));
    referenceObjectUrls.push(url);
    return url;
  }
  if (!referenceBaseUrl) return "";
  return remoteArtifactUrl(referenceBaseUrl, filename);
}

function renderReferenceFrame() {
  const view = currentManifest?.reference_images?.views?.[referenceView];
  if (!view?.frames?.length) return;
  const index = Math.min(Number(referenceSlider.value), view.frames.length - 1);
  const frame = view.frames[index];
  referenceImage.classList.remove("is-ready");
  referenceImage.classList.add("is-changing");
  referenceImage.addEventListener("load", () => {
    referenceImage.classList.remove("is-changing");
    referenceImage.classList.add("is-ready");
  }, { once: true });
  referenceImage.src = referenceFrameUrl(frame.file);
  const labels = view.orientation_labels || {};
  $("orientation-top").textContent = labels.top || "";
  $("orientation-bottom").textContent = labels.bottom || "";
  $("orientation-left").textContent = labels.left || "";
  $("orientation-right").textContent = labels.right || "";
  const position = frame.position_lps_mm == null ? "" : ` · ${Number(frame.position_lps_mm).toFixed(1)} mm LPS`;
  referenceMeta.textContent = `${referenceView} · plano ${index + 1}/${view.frames.length} · índice ${frame.index}${position}`;
}

const REFERENCE_CLIP_AXES = Object.freeze({ axial: "z", coronal: "y", sagittal: "x" });

function currentReferenceFrame() {
  const view = currentManifest?.reference_images?.views?.[referenceView];
  if (!view?.frames?.length) return null;
  const index = Math.min(Number(referenceSlider.value), view.frames.length - 1);
  return { frame: view.frames[index], index, view };
}

function syncReferenceToClipping({ activate = true } = {}) {
  if (!referenceSync.checked || !currentManifest || sceneBounds.isEmpty() || sourceBounds.isEmpty()) return false;
  const selected = currentReferenceFrame();
  const axis = REFERENCE_CLIP_AXES[referenceView];
  const rawPositionLps = selected?.frame?.position_lps_mm;
  const positionLps = Number(rawPositionLps);
  if (!selected || !axis || rawPositionLps == null || !Number.isFinite(positionLps)) {
    referenceSyncStatus.textContent = "Sincronização indisponível: plano sem coordenada LPS.";
    return false;
  }
  const minimumLps = sourceBounds.min[axis];
  const maximumLps = sourceBounds.max[axis];
  const span = maximumLps - minimumLps;
  if (!(span > 0)) {
    referenceSyncStatus.textContent = "Sincronização indisponível: limites 3D inválidos.";
    return false;
  }
  const percent = THREE.MathUtils.clamp(((positionLps - minimumLps) / span) * 100, 0, 100);
  clipAxis.value = axis;
  clipPosition.value = String(percent);
  clipInvert.checked = false;
  if (activate) clipEnabled.checked = true;
  updateClipping();
  const appliedPercent = Number(clipPosition.value);
  const constrained = Math.abs(appliedPercent - percent) > 0.01;
  const orientation = { axial: "Axial", coronal: "Coronal", sagittal: "Sagital" }[referenceView];
  referenceSyncStatus.textContent = `${orientation} sincronizado · ${positionLps.toFixed(1)} mm LPS · ${Math.round(appliedPercent)}% do volume${constrained ? " · limite seguro aplicado" : ""}.`;
  return true;
}

function structureCenterLps(mesh) {
  if (!mesh?.geometry) return null;
  if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
  if (!mesh.geometry.boundingBox || mesh.geometry.boundingBox.isEmpty()) return null;
  return mesh.geometry.boundingBox.getCenter(new THREE.Vector3());
}

function alignReferenceToStructure(item, mesh) {
  const view = currentManifest?.reference_images?.views?.[referenceView];
  const axis = REFERENCE_CLIP_AXES[referenceView];
  const centerLps = structureCenterLps(mesh);
  if (!view?.frames?.length || !axis || !centerLps) return false;
  const coordinateLps = Number(centerLps[axis]);
  const candidates = view.frames
    .map((frame, index) => ({ frame, index, position: Number(frame.position_lps_mm) }))
    .filter(({ frame, position }) => frame.position_lps_mm != null && Number.isFinite(position));
  if (!candidates.length || !Number.isFinite(coordinateLps)) return false;
  const nearest = candidates.reduce((best, candidate) => (
    Math.abs(candidate.position - coordinateLps) < Math.abs(best.position - coordinateLps)
      ? candidate : best
  ));
  referenceSlider.value = String(nearest.index);
  renderReferenceFrame();
  const clippingAligned = referenceSync.checked && syncReferenceToClipping();
  const orientation = { axial: "Axial", coronal: "Coronal", sagittal: "Sagital" }[referenceView];
  referenceSyncStatus.textContent = `${orientation} alinhado a ${item.label || item.role} · centro ${coordinateLps.toFixed(1)} mm LPS · plano ${nearest.index + 1}/${view.frames.length}${clippingAligned ? " · corte 3D ativo" : ""}.`;
  animateElementFeedback(referenceDock, "is-feedback");
  return true;
}

function selectReferenceView(viewName, { sync = true } = {}) {
  const view = currentManifest?.reference_images?.views?.[viewName];
  if (!view?.frames?.length) return;
  referenceView = viewName;
  referenceSlider.min = "0";
  referenceSlider.max = String(view.frames.length - 1);
  const declaredDefault = Number(view.default_frame_index);
  const defaultIndex = Number.isInteger(declaredDefault)
    ? THREE.MathUtils.clamp(declaredDefault, 0, view.frames.length - 1)
    : (viewName === "axial" ? Math.floor((view.frames.length - 1) / 2) : 0);
  referenceSlider.value = String(defaultIndex);
  document.querySelectorAll("#reference-tabs button").forEach((button) => {
    const selected = button.dataset.view === viewName;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
  });
  renderReferenceFrame();
  if (sync) syncReferenceToClipping();
}

function setupReferences(manifest, fileMap, { baseUrl = "" } = {}) {
  referenceFiles = fileMap;
  referenceBaseUrl = baseUrl;
  const views = manifest.reference_images?.views;
  const available = views && Object.values(views).some((view) => view?.frames?.length);
  referenceDock.hidden = !available;
  $("review-2d").disabled = !available;
  if (!available) return;
  referenceSync.checked = true;
  referenceSyncStatus.textContent = "Pronto para sincronizar ao mover o plano.";
  selectReferenceView(views.axial?.frames?.length ? "axial" : Object.keys(views)[0], { sync: false });
}
document.querySelectorAll("#reference-tabs button").forEach((button) => {
  button.addEventListener("click", () => selectReferenceView(button.dataset.view));
});
referenceSlider.addEventListener("input", () => { renderReferenceFrame(); syncReferenceToClipping(); });
referenceSync.addEventListener("change", () => {
  setReferenceSyncEnabled(referenceSync.checked);
});

function setReferenceViewForXR(viewName) {
  const view = currentManifest?.reference_images?.views?.[viewName];
  if (!view?.frames?.length) return false;
  selectReferenceView(viewName, { sync: false });
  if (referenceSync.checked) syncReferenceToClipping();
  return true;
}

function stepReferenceFrame(delta) {
  const maximum = Number(referenceSlider.max);
  if (!Number.isFinite(maximum) || maximum < 0) return false;
  const next = THREE.MathUtils.clamp(Number(referenceSlider.value) + Number(delta || 0), 0, maximum);
  referenceSlider.value = String(next);
  renderReferenceFrame();
  if (referenceSync.checked) syncReferenceToClipping();
  return true;
}

function setReferenceSyncEnabled(enabled) {
  const requested = Boolean(enabled);
  if (requested) {
    if (!referenceSync.checked || referenceSyncPreviousClippingState == null) {
      referenceSyncPreviousClippingState = getClippingState();
    }
    referenceSync.checked = true;
    if (!syncReferenceToClipping()) {
      referenceSync.checked = false;
      referenceSyncPreviousClippingState = null;
    }
  } else {
    referenceSync.checked = false;
    if (referenceSyncPreviousClippingState) {
      const previous = referenceSyncPreviousClippingState;
      referenceSyncPreviousClippingState = null;
      if (typeof previous.enabled === "boolean") clipEnabled.checked = previous.enabled;
      if (["x", "y", "z"].includes(previous.axis)) clipAxis.value = previous.axis;
      if (Number.isFinite(previous.position_percent)) clipPosition.value = String(previous.position_percent);
      clipInvert.checked = Boolean(previous.inverted);
      updateClipping();
    }
    referenceSyncStatus.textContent = "Sincronização 2D/3D desativada; corte anterior restaurado.";
  }
  return referenceSync.checked;
}

function getReferenceState() {
  const selected = currentReferenceFrame();
  return {
    available: Boolean(selected),
    view: referenceView,
    frame_index: Number(referenceSlider.value),
    frame_count: selected?.view?.frames?.length || 0,
    sync_enabled: referenceSync.checked,
    image_src: referenceImage.currentSrc || referenceImage.src || "",
    metadata: referenceMeta.textContent || "",
  };
}
$("reference-collapse").addEventListener("click", () => {
  const collapsed = !referenceBody.hidden;
  referenceBody.hidden = collapsed;
  $("reference-collapse").textContent = collapsed ? "Expandir" : "Recolher";
  $("reference-collapse").setAttribute("aria-expanded", String(!collapsed));
});

function renderMetadata(manifest) {
  const acquisition = manifest.acquisition || {};
  const spacing = acquisition.source_spacing_mm?.map((value) => Number(value).toFixed(2)).join(" × ") || "não informado";
  metaDiv.textContent = [
    `caso: ${manifest.case_id || "não informado"}`,
    `órgão: ${manifest.organ || "não informado"}`,
    `coordenadas: ${manifest.coordinate_system || "LPS"}`,
    `estado: ${manifest.regulatory_state || "PESQUISA"}`,
    `spacing da RM: ${spacing} mm`,
    `planos axiais com fígado: ${acquisition.liver_axial_planes ?? "não informado"}`,
    `grade da malha: ${acquisition.mesh_isotropic_spacing_mm ?? "não informado"} mm`,
    `suavização do campo: ${acquisition.mesh_smoothing_sigma_mm ?? "não informado"} mm`,
    acquisition.interpolation_disclosure || "",
    manifest.disclaimer || "",
  ].filter(Boolean).join("\n");
}

function finalizeManifestPresentation(manifest, fileMap, options = {}) {
  currentManifest = manifest;
  if (!Object.keys(meshes).length) throw new Error("Nenhuma malha do manifesto foi carregada.");
  frameScene();
  controlsDiv.innerHTML = "";
  buildControls(manifest.meshes);
  applyInitialPreset(manifest);
  renderQuality(manifest.meshes, manifest);
  renderVolumetry(manifest, fileMap, options.referenceBaseUrl || "");
  renderRelationships(manifest);
  renderCandidate(manifest);
  renderMetadata(manifest);
  setupReferences(
    manifest,
    options.referenceFileMap ?? fileMap,
    { baseUrl: options.referenceBaseUrl || "" },
  );
  renderAnatomicalViewControls();
  clipSection.hidden = manifest.viewer_features?.orthogonal_clipping === false;
  clipEnabled.checked = false;
  clipPosition.value = "50";
  clipInvert.checked = false;
  updateClipping();
  viewerReadyForReview = options.complete !== false;
  if (jobId) {
    approveButton.disabled = !viewerReadyForReview;
    revisionButton.disabled = !viewerReadyForReview;
  }
  if (viewerReadyForReview) {
    drop.classList.add("loaded");
    drop.innerHTML = `<b>${manifest.case_id || "Caso"}</b><br/>${options.referenceBaseUrl ? "modelo carregado · referências 2D sob demanda" : "modelo e referências carregados"}`;
  }
  document.querySelectorAll(".panel-section:not([hidden])").forEach((section) => {
    section.classList.remove("is-populated");
    void section.offsetWidth;
    section.classList.add("is-populated");
  });
  if (options.animate !== false) animateModelEntrance();
}

function renderManifest(manifest, fileMap, options = {}) {
  if (!manifest || !Array.isArray(manifest.meshes) || !manifest.meshes.length) {
    throw new Error("Manifesto sem coleção de malhas.");
  }
  clearScene();
  currentManifest = manifest;
  for (const item of manifest.meshes) {
    const buffer = fileMap[item.stl];
    if (!buffer) {
      console.warn("STL ausente:", item.stl);
      continue;
    }
    addMesh(item, loader.parse(buffer));
  }
  finalizeManifestPresentation(manifest, fileMap, options);
}

function updateMeasurementStatus() {
  if (!measurementEnabled) {
    const totalMeasurements = measurementValues.length + structureMeasurements3d.length;
    measurementStatus.textContent = totalMeasurements
      ? `${totalMeasurements} medição(ões), incluindo ${structureMeasurements3d.length} tridimensional(is) · régua manual desativada.`
      : "Régua desativada.";
    animateElementFeedback(measurementStatus, "is-feedback");
    return;
  }
  if (measurePendingPoint) {
    measurementStatus.textContent = "Primeiro ponto marcado. Clique no segundo ponto.";
  } else {
    measurementStatus.textContent = "Régua ativa. Clique em dois pontos de superfícies visíveis.";
  }
  animateElementFeedback(measurementStatus, "is-feedback");
}

function setMeasurementEnabled(enabled) {
  measurementEnabled = Boolean(enabled);
  if (!measurementEnabled) measurePendingPoint = null;
  orbit.enabled = !measurementEnabled;
  $("measure").classList.toggle("active", measurementEnabled);
  $("measure").setAttribute("aria-pressed", String(measurementEnabled));
  renderer.domElement.classList.toggle("measuring", measurementEnabled);
  updateMeasurementStatus();
}

function marker(point, color = 0x0ea575) {
  const geometry = new THREE.SphereGeometry(Math.max(sceneRadius * 0.009, 0.7), 16, 12);
  const material = new THREE.MeshBasicMaterial({ color, depthTest: false });
  const object = new THREE.Mesh(geometry, material);
  object.position.copy(point);
  object.renderOrder = 20;
  measurementGroup.add(object);
  measurementObjects.push(object);
  if (!reducedMotion.matches) {
    object.scale.setScalar(0.05);
    objectScaleTweens.set(object, { startedAt: performance.now(), duration: 340 });
  }
}

function handleMeasurementPoint(point) {
  const selectedPoint = point.clone();
  if (![selectedPoint.x, selectedPoint.y, selectedPoint.z].every(Number.isFinite)) return null;
  marker(selectedPoint);
  if (!measurePendingPoint) {
    measurePendingPoint = selectedPoint;
    updateMeasurementStatus();
    return null;
  }
  const start = measurePendingPoint;
  const distance = start.distanceTo(selectedPoint);
  const geometry = new THREE.BufferGeometry().setFromPoints([start, selectedPoint]);
  const material = new THREE.LineBasicMaterial({ color: 0x0a7f61, depthTest: false });
  const line = new THREE.Line(geometry, material);
  line.renderOrder = 19;
  measurementGroup.add(line);
  measurementObjects.push(line);
  textSprite(`${distance.toFixed(1)} mm`, start.clone().add(selectedPoint).multiplyScalar(0.5));
  measurementValues.push(Number(distance.toFixed(3)));
  measurePendingPoint = null;
  updateMeasurementStatus();
  return distance;
}

function worldPointToModelPoint(point) {
  if (!point?.isVector3) return null;
  group.updateWorldMatrix(true, false);
  return group.worldToLocal(point.clone());
}

function isWorldPointVisibleByClipping(point, toleranceMm = 0.25) {
  if (!clipEnabled.checked || !point?.isVector3) return true;
  refreshClippingPlaneWorld();
  const modelScale = new THREE.Vector3();
  group.getWorldScale(modelScale);
  const worldTolerance = Math.max(
    Math.abs(modelScale.x), Math.abs(modelScale.y), Math.abs(modelScale.z), 1e-6,
  ) * Math.max(Number(toleranceMm) || 0, 0);
  return clippingPlane.distanceToPoint(point) >= -worldTolerance;
}

function textSprite(text, point) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 128;
  const context = canvas.getContext("2d");
  context.fillStyle = "rgba(10, 34, 27, 0.90)";
  context.roundRect(4, 4, 504, 120, 24);
  context.fill();
  context.fillStyle = "#ffffff";
  context.font = "700 48px sans-serif";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(text, 256, 64);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const material = new THREE.SpriteMaterial({ map: texture, depthTest: false });
  const sprite = new THREE.Sprite(material);
  sprite.position.copy(point);
  sprite.scale.set(sceneRadius * 0.24, sceneRadius * 0.06, 1);
  sprite.renderOrder = 21;
  measurementGroup.add(sprite);
  measurementObjects.push(sprite);
}

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let pointerDown = null;
renderer.domElement.addEventListener("pointerdown", (event) => {
  pointerDown = { x: event.clientX, y: event.clientY };
});
renderer.domElement.addEventListener("pointerup", (event) => {
  if (!pointerDown) return;
  const moved = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
  pointerDown = null;
  if (moved > 5) return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  // Force current transforms before ray casting.  This matters immediately
  // after a named-view change or a responsive resize on high-DPI displays.
  scene.updateMatrixWorld(true);
  camera.updateMatrixWorld(true);
  raycaster.setFromCamera(pointer, camera);
  const intersections = raycaster.intersectObject(group, true)
    .filter((intersection) => intersection.object?.isMesh
      && Boolean(meshItems[intersection.object.userData.role])
      && intersection.object.visible
      && Number(intersection.object.material?.opacity ?? 1) > 0.02
      && isWorldPointVisibleByClipping(intersection.point));
  if (!measurementEnabled) {
    if (!intersections.length) {
      clearStructureSelection();
      return;
    }
    const first = intersections[0];
    const firstItem = meshItems[first.object.userData.role];
    const organIsTransparent = meshCategory(firstItem) === "organ"
      && Number(first.object.material.opacity) < 0.999;
    const selected = organIsTransparent
      ? (intersections.find((intersection) => meshCategory(
        meshItems[intersection.object.userData.role],
      ) !== "organ") || first)
      : first;
    selectStructure(selected.object.userData.role);
    return;
  }
  if (!intersections.length) {
    measurementStatus.textContent = "Nenhuma superfície visível nesse ponto.";
    animateElementFeedback(measurementStatus, "is-feedback");
    return;
  }
  const modelPoint = worldPointToModelPoint(intersections[0].point);
  if (modelPoint) handleMeasurementPoint(modelPoint);
});

$("measure").addEventListener("click", () => setMeasurementEnabled(!measurementEnabled));
$("clear-measures").addEventListener("click", clearMeasurements);
$("selection-clear").addEventListener("click", () => clearStructureSelection());
$("selection-focus").addEventListener("click", focusSelectedStructure);
$("selection-isolate").addEventListener("click", isolateSelectedStructure);
$("selection-dimensions").addEventListener("click", measureSelectedStructure3d);
$("selection-context").addEventListener("click", restoreSelectedContext);
document.querySelectorAll(".anatomical-view-button").forEach((button) => {
  button.addEventListener("click", () => applyAnatomicalView(button.dataset.anatomicalView));
});
$("save-current-view").addEventListener("click", saveCurrentView);
$("reset-view").addEventListener("click", () => applyView("padrao"));
$("wireframe").addEventListener("click", () => {
  wireframeEnabled = !wireframeEnabled;
  Object.values(meshes).forEach((mesh) => { mesh.material.wireframe = wireframeEnabled; });
  $("wireframe").classList.toggle("active", wireframeEnabled);
  $("wireframe").setAttribute("aria-pressed", String(wireframeEnabled));
});
$("snapshot").addEventListener("click", () => {
  renderer.render(scene, camera);
  const link = document.createElement("a");
  const safeCase = String(currentManifest?.case_id || "caso").replace(/[^a-z0-9_-]/gi, "_");
  link.download = `oren_${safeCase}_3d.png`;
  link.href = renderer.domElement.toDataURL("image/png");
  link.click();
});
$("fullscreen").addEventListener("click", async () => {
  if (document.fullscreenElement) await document.exitFullscreen();
  else await holder.requestFullscreen();
});

function reviewPayload(status) {
  return {
    status,
    checklist: {
      inspected_3d_contour: $("review-3d").checked,
      compared_2d_reference: $("review-2d").checked,
      reviewed_candidate_against_mr: $("review-candidate").checked,
      acknowledged_research_only: $("review-research").checked,
    },
    candidate_review_decision: $("candidate-decision-row").hidden
      ? null : ($("candidate-decision").value || null),
    viewer_state: {
      active_view: currentView,
      active_preset: currentPreset,
      active_anatomical_view: currentAnatomicalView,
      rendering_profile: currentRenderingProfile,
      rendering_quality_tier: currentRenderingQualityTier,
      material_pack_id: currentRenderingProfile === ANATOMIC_REALISTIC_PROFILE
        ? REALISTIC_MATERIAL_PACK_ID : null,
      material_pack_variant: currentRenderingProfile === ANATOMIC_REALISTIC_PROFILE
        ? (realisticMaterialPack.variant || null) : null,
      rendering_fallback_reason: currentRenderingFallbackReason,
      reference_sync_enabled: referenceSync.checked,
      reference_view: referenceView,
      reference_frame_index: Number(referenceSlider.value),
      selected_role: selectedRole,
      selection_isolated: selectionIsolated,
      saved_views: savedViews.slice(0, MAX_SAVED_VIEWS).map(savedViewPayload),
      compared_saved_view_ids: comparedSavedViewIds.slice(0, 2),
      wireframe_enabled: wireframeEnabled,
      clipping: {
        enabled: clipEnabled.checked,
        axis: clipAxis.value,
        position_percent: Number(clipPosition.value),
        inverted: clipInvert.checked,
      },
      measurements_mm: measurementValues.slice(0, 20),
      structure_dimensions_3d: structureMeasurements3d.slice(0, 16),
      visible_roles: Object.entries(meshes).filter(([, mesh]) => mesh.visible).map(([role]) => role),
    },
  };
}

const params = new URLSearchParams(location.search);
const casePath = params.get("case");
const jobId = params.get("job");
const preferXrAssets = params.get("xr") === "1"
  || /OculusBrowser|Quest/i.test(navigator.userAgent || "");
const xrToken = new URLSearchParams(location.hash.slice(1)).get("xr_token");
let rgbPanelCatalogPromise = null;

async function getRgbPanelCatalog() {
  if (!jobId) return { schema: "oren-rgb-panel-catalog-v1", count: 0, panels: [] };
  if (!rgbPanelCatalogPromise) {
    rgbPanelCatalogPromise = fetch(`/api/jobs/${encodeURIComponent(jobId)}/rgb-panels`)
      .then((response) => {
        if (!response.ok) throw new Error(`Painéis RGB indisponíveis (${response.status}).`);
        return response.json();
      })
      .then((catalog) => ({
        ...catalog,
        panels: Array.isArray(catalog.panels) ? catalog.panels : [],
      }))
      .catch((error) => {
        rgbPanelCatalogPromise = null;
        throw error;
      });
  }
  return rgbPanelCatalogPromise;
}

function renderArtifactName(item) {
  const xr = item?.xr_asset;
  if (preferXrAssets && xr?.fidelity_gate_passed && typeof xr.stl === "string") {
    return xr.stl;
  }
  return item.stl;
}

async function submitApproval(status) {
  if (!viewerReadyForReview) {
    approvalStatus.textContent = "Aguarde o carregamento completo das estruturas 3D.";
    return;
  }
  const payload = reviewPayload(status);
  if (status === "approved") {
    const baseRequired = [
      payload.checklist.inspected_3d_contour,
      payload.checklist.compared_2d_reference,
      payload.checklist.acknowledged_research_only,
    ];
    const candidateRequired = !$("candidate-decision-row").hidden;
    if (baseRequired.some((value) => !value)
        || (candidateRequired && (!payload.checklist.reviewed_candidate_against_mr
          || !["accepted_as_region_of_interest", "rejected"].includes(payload.candidate_review_decision)))) {
      approvalStatus.textContent = "Conclua o checklist e registre uma decisão técnica sobre o candidato.";
      return;
    }
  }
  approveButton.disabled = true;
  revisionButton.disabled = true;
  approvalStatus.textContent = "Registrando revisão...";
  try {
    const approvalEndpoint = xrToken
      ? `/api/jobs/${encodeURIComponent(jobId)}/xr-session/${encodeURIComponent(xrToken)}/approval`
      : `/api/jobs/${encodeURIComponent(jobId)}/approval`;
    const response = await fetch(approvalEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Falha ao registrar revisão");
    approvalStatus.textContent = data.status === "approved"
      ? "Revisão técnica registrada. Aceitar uma região de interesse não confirma diagnóstico."
      : "Solicitação de revisão registrada.";
  } catch (error) {
    approvalStatus.textContent = error.message;
    approveButton.disabled = false;
    revisionButton.disabled = false;
  }
}

function setReviewChecklistItem(item, checked) {
  const ids = {
    inspected_3d_contour: "review-3d",
    compared_2d_reference: "review-2d",
    reviewed_candidate_against_mr: "review-candidate",
    acknowledged_research_only: "review-research",
  };
  const node = $(ids[item]);
  if (!node || node.disabled) return false;
  node.checked = Boolean(checked);
  return node.checked;
}

function setCandidateReviewDecision(value) {
  const allowed = ["", "accepted_as_region_of_interest", "rejected", "needs_correction"];
  if (!allowed.includes(value) || $("candidate-decision-row").hidden) return false;
  $("candidate-decision").value = value;
  return true;
}

function getReviewState() {
  const payload = reviewPayload("pending");
  return {
    checklist: payload.checklist,
    candidate_review_decision: payload.candidate_review_decision,
    candidate_available: !$("candidate-decision-row").hidden,
    status: approvalStatus.textContent || "",
  };
}

if (jobId) {
  approvalDiv.style.display = "block";
  approveButton.addEventListener("click", () => submitApproval("approved"));
  revisionButton.addEventListener("click", () => submitApproval("revision_requested"));
}

async function fetchBuffer(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Falha ao carregar ${url} (${response.status}).`);
  return response.arrayBuffer();
}

function setLoadProgress(phase, completed, total) {
  loadingState.phase = phase;
  loadingState.completed = completed;
  loadingState.total = total;
  loadingState.ready = false;
  drop.classList.remove("loaded");
  const title = document.createElement("b");
  title.textContent = phase;
  const detail = document.createElement("span");
  detail.textContent = `${completed}/${total} estruturas`;
  const progress = document.createElement("progress");
  progress.max = Math.max(total, 1);
  progress.value = completed;
  progress.setAttribute("aria-label", "Progresso do carregamento do modelo 3D");
  drop.replaceChildren(title, document.createElement("br"), detail, progress);
}

function meshPriority(item) {
  const category = meshCategory(item);
  return {
    organ: 0, vessel: 1, gallbladder: 1, candidate: 1, lesion: 1,
    classified_region: 2, segment: 3, other: 4,
  }[category] ?? 4;
}

async function fetchMeshBuffersBounded(base, items, target, concurrency = 3) {
  let nextIndex = 0;
  async function worker() {
    while (nextIndex < items.length) {
      const item = items[nextIndex];
      nextIndex += 1;
      target[item.stl] = await fetchBuffer(remoteArtifactUrl(base, renderArtifactName(item)));
    }
  }
  const workerCount = Math.min(Math.max(concurrency, 1), items.length);
  await Promise.all(Array.from({ length: workerCount }, () => worker()));
}

function nextAnimationFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

function prepareIncrementalMesh(item, buffer) {
  const mesh = addMesh(item, loader.parse(buffer));
  const presetName = VIEWER_PRESETS[currentPreset] ? currentPreset : DEFAULT_VISUAL_PRESET;
  const state = presetMeshState(presetName, item);
  applyMaterialProfile(presetName, item, mesh);
  mesh.userData.targetOpacity = state.opacity;
  configureOpacityOcclusion(item, mesh, state.opacity);
  mesh.visible = state.visible;
  mesh.material.opacity = state.opacity;
}

async function loadRemoteManifestProgressively(base, manifest) {
  if (!Array.isArray(manifest.meshes) || !manifest.meshes.length) {
    throw new Error("Manifesto sem coleção de malhas.");
  }
  loadingState.startedAt = performance.now();
  loadingState.firstOrganMs = null;
  loadingState.readyMs = null;
  const ordered = manifest.meshes
    .map((item, index) => ({ item, index }))
    .sort((left, right) => meshPriority(left.item) - meshPriority(right.item) || left.index - right.index)
    .map(({ item }) => item);
  const organ = ordered.find((item) => meshCategory(item) === "organ");
  if (!organ) throw new Error("Manifesto sem malha hepática prioritária.");
  const total = ordered.length;
  const fileMap = {};
  setLoadProgress("Carregando fígado", 0, total);
  fileMap[organ.stl] = await fetchBuffer(remoteArtifactUrl(base, renderArtifactName(organ)));
  loadingState.firstOrganMs = performance.now() - loadingState.startedAt;
  const coreManifest = {
    ...manifest,
    meshes: [organ],
    reference_images: null,
    spatial_relationships: [],
    candidate_context: null,
    candidate_region: null,
  };
  renderManifest(coreManifest, { [organ.stl]: fileMap[organ.stl] }, { complete: false });
  setLoadProgress("Fígado disponível · carregando anatomia", 1, total);
  const remaining = ordered.filter((item) => item !== organ);
  await fetchMeshBuffersBounded(base, remaining, fileMap);
  let prepared = 1;
  for (const item of remaining) {
    await nextAnimationFrame();
    prepareIncrementalMesh(item, fileMap[item.stl]);
    delete fileMap[item.stl];
    prepared += 1;
    setLoadProgress("Preparando anatomia sem bloquear a cena", prepared, total);
    await nextAnimationFrame();
  }
  finalizeManifestPresentation(manifest, {}, {
    complete: true,
    referenceBaseUrl: base,
    referenceFileMap: {},
    animate: false,
  });
  loadingState.phase = "ready";
  loadingState.completed = total;
  loadingState.total = total;
  loadingState.ready = true;
  loadingState.readyMs = performance.now() - loadingState.startedAt;
}

if (casePath) {
  (async () => {
    const base = casePath.replace(/\/$/, "");
    const response = await fetch(`${base}/viewer_manifest.json`);
    if (!response.ok) throw new Error("Manifesto do modelo não disponível.");
    const manifest = await response.json();
    await loadRemoteManifestProgressively(base, manifest);
  })().catch((error) => {
    loadingState.phase = "failed";
    loadingState.ready = false;
    viewerReadyForReview = false;
    console.error(error);
    alert(`Falha ao carregar o modelo: ${error.message}`);
  });
}

drop.addEventListener("dragover", (event) => { event.preventDefault(); drop.classList.add("hover"); });
drop.addEventListener("dragleave", () => drop.classList.remove("hover"));
drop.addEventListener("drop", async (event) => {
  event.preventDefault();
  drop.classList.remove("hover");
  const buffers = {};
  let manifest = null;
  for (const file of [...event.dataTransfer.files]) {
    const buffer = await file.arrayBuffer();
    if (file.name === "viewer_manifest.json") manifest = JSON.parse(new TextDecoder().decode(buffer));
    else buffers[file.name] = buffer;
  }
  if (!manifest) {
    alert("Inclua o viewer_manifest.json no conjunto arrastado.");
    return;
  }
  try { renderManifest(manifest, buffers); } catch (error) { alert(error.message); }
});

window.addEventListener("keydown", (event) => {
  if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
  const key = event.key.toLowerCase();
  if (key === "0") applyView("padrao");
  else if (key === "1") applyView("anterior");
  else if (key === "2") applyView("superior");
  else if (key === "3") applyView("direita");
  else if (key === "m") setMeasurementEnabled(!measurementEnabled);
  else if (key === "c") { clipEnabled.checked = !clipEnabled.checked; markReferenceSyncManual(); updateClipping(); }
  else if (key === "escape") setMeasurementEnabled(false);
});

function setStructureVisibility(role, visible) {
  const mesh = meshes[role];
  if (!mesh) return false;
  animateMeshVisibility(mesh, Boolean(visible));
  syncStructureControl(
    role,
    Boolean(visible),
    Number(mesh.userData.targetOpacity ?? mesh.material.opacity),
  );
  markCustomPreset();
  applyWireframeState();
  return true;
}

function setStructureOpacity(role, opacity) {
  const mesh = meshes[role];
  const item = meshItems[role];
  if (!mesh || !item) return false;
  const value = THREE.MathUtils.clamp(Number(opacity), 0, 1);
  mesh.userData.targetOpacity = value;
  configureOpacityOcclusion(item, mesh, value);
  if (mesh.visible) mesh.material.opacity = value;
  syncStructureControl(role, mesh.visible, value);
  markCustomPreset();
  return true;
}

function setClippingState(state = {}) {
  if (typeof state.enabled === "boolean") clipEnabled.checked = state.enabled;
  if (["x", "y", "z"].includes(state.axis)) clipAxis.value = state.axis;
  if (Number.isFinite(Number(state.position_percent))) {
    clipPosition.value = String(THREE.MathUtils.clamp(Number(state.position_percent), 0, 100));
  }
  if (typeof state.inverted === "boolean") clipInvert.checked = state.inverted;
  markReferenceSyncManual();
  updateClipping();
}

function getClippingState() {
  return {
    enabled: Boolean(clipEnabled.checked),
    axis: clipAxis.value,
    position_percent: Number(clipPosition.value),
    inverted: Boolean(clipInvert.checked),
  };
}

const XR_WIREFRAME_TRIANGLE_LIMIT = 75_000;

function meshTriangleCount(role) {
  const item = meshItems[role];
  const geometry = meshes[role]?.geometry;
  const rendered = geometry?.index
    ? geometry.index.count / 3 : Number(geometry?.getAttribute("position")?.count || 0) / 3;
  return Number.isFinite(rendered) && rendered > 0
    ? Math.round(rendered) : Number(item?.xr_asset?.triangles || item?.metrics?.triangles || 0);
}

function wireframeRoleForCurrentContext() {
  const visibleRoles = Object.keys(meshes).filter((role) => meshes[role]?.visible);
  const ordered = selectedRole && meshes[selectedRole]?.visible
    ? [selectedRole, ...visibleRoles.filter((role) => role !== selectedRole)] : visibleRoles;
  if (!xrPresentationActive) return null;
  return ordered.find((role) => meshTriangleCount(role) <= XR_WIREFRAME_TRIANGLE_LIMIT) || null;
}

function applyWireframeState() {
  const targetRole = wireframeEnabled ? wireframeRoleForCurrentContext() : null;
  Object.entries(meshes).forEach(([role, mesh]) => {
    const requested = wireframeEnabled && (!xrPresentationActive || role === targetRole);
    if (mesh.material.wireframe !== requested) {
      mesh.material.wireframe = requested;
      mesh.material.needsUpdate = true;
    }
  });
  if (!wireframeEnabled) wireframeStatus = { enabled: false, role: null, reason: null };
  else if (xrPresentationActive && !targetRole) {
    wireframeEnabled = false;
    wireframeStatus = {
      enabled: false, role: null,
      reason: "Malha técnica indisponível: nenhuma estrutura está dentro do orçamento gráfico seguro do Meta Quest.",
    };
  } else {
    wireframeStatus = {
      enabled: true,
      role: xrPresentationActive ? targetRole : "all_visible",
      reason: null,
    };
  }
  return wireframeEnabled;
}

function setWireframeEnabled(enabled) {
  wireframeEnabled = Boolean(enabled);
  applyWireframeState();
  $("wireframe").classList.toggle("active", wireframeEnabled);
  $("wireframe").setAttribute("aria-pressed", String(wireframeEnabled));
  return wireframeEnabled;
}

function getXrReady() {
  if (loadingState.phase === "failed") return false;
  if (viewerReadyForReview) return true;
  return Object.entries(meshes).some(([role, mesh]) => (
    mesh?.visible && meshItems[role] && meshCategory(meshItems[role]) === "organ"
  ));
}

window.__argos = {
  meshes, scene, renderer, camera, THREE,
  group, measurementGroup, meshItems,
  applyView, applyPreset, applyInitialPreset, applyAnatomicalView,
  saveCurrentView, restoreSavedView, measureSelectedStructure3d,
  focusSelectedStructure, isolateSelectedStructure, restoreSelectedContext,
  clearMeasurements, updateClipping, syncReferenceToClipping,
  selectStructure, clearStructureSelection, handleMeasurementPoint,
  worldPointToModelPoint, isWorldPointVisibleByClipping, refreshClippingPlaneWorld,
  setMeasurementEnabled, setStructureVisibility, setStructureOpacity, setClippingState, getClippingState,
  setRenderingProfile, toggleRenderingProfile, setRenderingQualityTier,
  setXrPresentationActive, stabilizeXrScene,
  setWireframeEnabled, setReferenceViewForXR, stepReferenceFrame, setReferenceSyncEnabled,
  getReferenceState, setReviewChecklistItem, setCandidateReviewDecision, getReviewState,
  submitApproval,
  getMeasurementEnabled: () => measurementEnabled,
  getWireframeEnabled: () => wireframeEnabled,
  getWireframeStatus: () => ({ ...wireframeStatus }),
  getSelectedRole: () => selectedRole,
  getRenderingProfile: () => currentRenderingProfile,
  getRenderingQualityTier: () => currentRenderingQualityTier,
  getRenderingMaterialPackId: () => currentRenderingProfile === ANATOMIC_REALISTIC_PROFILE
    ? REALISTIC_MATERIAL_PACK_ID : null,
  getRenderingMaterialPackVariant: () => currentRenderingProfile === ANATOMIC_REALISTIC_PROFILE
    ? (realisticMaterialPack.variant || null) : null,
  getRenderingFallbackReason: () => currentRenderingFallbackReason,
  getStructureRoles: () => Object.keys(meshes),
  getStructureLabel: (role) => meshItems[role]?.label || role,
  getStructureCategory: (role) => meshItems[role] ? meshCategory(meshItems[role]) : null,
  isStructureVisible: (role) => Boolean(meshes[role]?.visible),
  getSavedViews: () => savedViews.slice(0, MAX_SAVED_VIEWS).map(savedViewPayload),
  getManifest: () => currentManifest,
  getRgbPanelCatalog,
  getSceneRadius: () => sceneRadius,
  getSceneBounds: () => sceneBounds.clone(),
  getViewerReady: () => viewerReadyForReview,
  getXrReady,
  setOrbitEnabled: (enabled) => { orbit.enabled = Boolean(enabled); },
  getLoadingState: () => ({ ...loadingState }),
  VIEWER_PRESETS, DEFAULT_VISUAL_PRESET, RENDERING_PROFILES, REALISTIC_MATERIAL_PACK_ID,
};

initializeOrenXR(window.__argos).catch((error) => {
  console.warn("WebXR opcional indisponível:", error);
  const entry = document.getElementById("xr-entry");
  const status = document.getElementById("xr-status");
  if (entry) {
    entry.hidden = false;
    entry.disabled = false;
    entry.textContent = "Recarregar acesso ao Meta Quest";
    entry.addEventListener("click", () => window.location.reload(), { once: true });
  }
  if (status) status.textContent = `Falha ao preparar WebXR: ${error.message}. Toque para recarregar.`;
  const job = new URLSearchParams(location.search).get("job");
  if (job) fetch(`/api/jobs/${encodeURIComponent(job)}/xr-client-event`, {
    method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
    body: JSON.stringify({
      event: "session_failed", mode: "unknown", error_name: String(error?.name || "InitError").slice(0, 80),
      message: String(error?.message || error).slice(0, 300),
    }),
  }).catch(() => {});
});
