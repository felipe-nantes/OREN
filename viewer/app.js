// Visualizador offline do OREN. Three.js e loaders ficam vendorizados; nenhuma
// imagem, malha ou decisão de revisão deixa o computador por este módulo.
import * as THREE from "three";
import { STLLoader } from "./vendor/STLLoader.js";
import { OrbitControls } from "./vendor/OrbitControls.js";

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
const clipSection = $("clip-section");
const clipEnabled = $("clip-enabled");
const clipAxis = $("clip-axis");
const clipInvert = $("clip-invert");
const clipPosition = $("clip-position");
const clipValue = $("clip-value");

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
const loader = new STLLoader();
const meshes = {};
const meshItems = {};
const clippingPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
let sceneBounds = new THREE.Box3();
let sceneRadius = 1;
let currentManifest = null;
let currentView = "padrao";
let wireframeEnabled = false;
let measurementEnabled = false;
let measurePendingPoint = null;
let measurementValues = [];
let measurementObjects = [];
let referenceView = "axial";
let referenceFiles = {};
let referenceObjectUrls = [];
let cameraTween = null;
let sceneIntroTween = null;
const meshVisibilityTweens = new Map();
const objectScaleTweens = new Map();
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

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
(function loop() {
  requestAnimationFrame(loop);
  updateOrenAnimations(performance.now());
  orbit.update();
  repositionLights();
  renderer.render(scene, camera);
}());

function disposeObject(object) {
  if (object.geometry) object.geometry.dispose();
  if (object.material) {
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of materials) {
      if (material.map) material.map.dispose();
      material.dispose();
    }
  }
}

function clearMeasurements() {
  for (const object of measurementObjects) {
    objectScaleTweens.delete(object);
    scene.remove(object);
    disposeObject(object);
  }
  measurementObjects = [];
  measurementValues = [];
  measurePendingPoint = null;
  updateMeasurementStatus();
}

function clearScene() {
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
  if (item.material === "candidate") mesh.renderOrder = 12;
  if (item.material === "classified_region") mesh.renderOrder = 8;
  meshes[item.role] = mesh;
  meshItems[item.role] = item;
  group.add(mesh);
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
  if (reducedMotion.matches) {
    meshVisibilityTweens.delete(mesh);
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

function buildControls(items) {
  let controlIndex = 0;
  const stagger = (element) => {
    element.style.setProperty("--control-delay", `${Math.min(controlIndex, 8) * 48}ms`);
    controlIndex += 1;
  };
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
      Object.values(meshes).forEach((mesh) => animateMeshVisibility(mesh, true));
      controlsDiv.querySelectorAll("input[type=checkbox][data-role]").forEach((box) => { box.checked = true; });
    }),
    makeButton("Ocultar todas", "secondary-button", () => {
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
      animateMeshVisibility(meshes[item.role], checkbox.checked);
      animateElementFeedback(row);
    });
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = item.color;
    label.append(checkbox, swatch, document.createTextNode(item.label || item.role));
    const isolate = makeButton("Só", "isolate-button", () => {
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
    opacity.setAttribute("aria-label", `Opacidade de ${item.label || item.role}`);
    opacity.addEventListener("input", () => {
      const value = Number(opacity.value);
      meshes[item.role].userData.targetOpacity = value;
      if (meshes[item.role].visible) meshes[item.role].material.opacity = value;
    });
    row.append(heading, opacity);
    controlsDiv.appendChild(row);
  }
  applyView(currentView);
}

function updateClipping() {
  if (!currentManifest || sceneBounds.isEmpty()) return;
  const enabled = clipEnabled.checked;
  const axis = clipAxis.value;
  const axisIndex = { x: 0, y: 1, z: 2 }[axis];
  const minimum = [sceneBounds.min.x, sceneBounds.min.y, sceneBounds.min.z][axisIndex];
  const maximum = [sceneBounds.max.x, sceneBounds.max.y, sceneBounds.max.z][axisIndex];
  const percent = Number(clipPosition.value) / 100;
  const coordinate = minimum + (maximum - minimum) * percent;
  const normal = new THREE.Vector3(
    axis === "x" ? 1 : 0,
    axis === "y" ? 1 : 0,
    axis === "z" ? 1 : 0,
  );
  if (clipInvert.checked) normal.multiplyScalar(-1);
  const point = new THREE.Vector3();
  point[axis] = coordinate;
  clippingPlane.setFromNormalAndCoplanarPoint(normal, point);
  Object.values(meshes).forEach((mesh) => {
    mesh.material.clippingPlanes = enabled ? [clippingPlane] : [];
    mesh.material.needsUpdate = true;
  });
  clipValue.textContent = `${Math.round(percent * 100)}% · ${coordinate.toFixed(1)} mm em LPS`;
}
clipEnabled.addEventListener("change", updateClipping);
clipAxis.addEventListener("change", updateClipping);
clipInvert.addEventListener("change", updateClipping);
clipPosition.addEventListener("input", updateClipping);

function metric(parent, label, value) {
  const item = document.createElement("div");
  const name = document.createElement("span");
  const content = document.createElement("strong");
  name.textContent = label;
  content.textContent = value;
  item.append(name, content);
  parent.appendChild(item);
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

function referenceFrameUrl(filename) {
  const buffer = referenceFiles[filename];
  if (!buffer) return "";
  const url = URL.createObjectURL(new Blob([buffer], { type: "image/png" }));
  referenceObjectUrls.push(url);
  return url;
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

function selectReferenceView(viewName) {
  const view = currentManifest?.reference_images?.views?.[viewName];
  if (!view?.frames?.length) return;
  referenceView = viewName;
  referenceSlider.min = "0";
  referenceSlider.max = String(view.frames.length - 1);
  referenceSlider.value = viewName === "axial" ? String(Math.floor((view.frames.length - 1) / 2)) : "0";
  document.querySelectorAll("#reference-tabs button").forEach((button) => {
    const selected = button.dataset.view === viewName;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
  });
  renderReferenceFrame();
}

function setupReferences(manifest, fileMap) {
  referenceFiles = fileMap;
  const views = manifest.reference_images?.views;
  const available = views && Object.values(views).some((view) => view?.frames?.length);
  referenceDock.hidden = !available;
  $("review-2d").disabled = !available;
  if (!available) return;
  selectReferenceView(views.axial?.frames?.length ? "axial" : Object.keys(views)[0]);
}
document.querySelectorAll("#reference-tabs button").forEach((button) => {
  button.addEventListener("click", () => selectReferenceView(button.dataset.view));
});
referenceSlider.addEventListener("input", renderReferenceFrame);
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

function renderManifest(manifest, fileMap) {
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
  if (!Object.keys(meshes).length) throw new Error("Nenhuma malha do manifesto foi carregada.");
  frameScene();
  buildControls(manifest.meshes);
  renderQuality(manifest.meshes, manifest);
  renderRelationships(manifest);
  renderCandidate(manifest);
  renderMetadata(manifest);
  setupReferences(manifest, fileMap);
  clipSection.hidden = manifest.viewer_features?.orthogonal_clipping === false;
  clipEnabled.checked = false;
  clipPosition.value = "50";
  clipInvert.checked = false;
  updateClipping();
  drop.classList.add("loaded");
  drop.innerHTML = `<b>${manifest.case_id || "Caso"}</b><br/>modelo e referências carregados`;
  document.querySelectorAll(".panel-section:not([hidden])").forEach((section) => {
    section.classList.remove("is-populated");
    void section.offsetWidth;
    section.classList.add("is-populated");
  });
  animateModelEntrance();
}

function updateMeasurementStatus() {
  if (!measurementEnabled) {
    measurementStatus.textContent = measurementValues.length
      ? `${measurementValues.length} medição(ões) · régua desativada.`
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
  scene.add(object);
  measurementObjects.push(object);
  if (!reducedMotion.matches) {
    object.scale.setScalar(0.05);
    objectScaleTweens.set(object, { startedAt: performance.now(), duration: 340 });
  }
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
  scene.add(sprite);
  measurementObjects.push(sprite);
}

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let pointerDown = null;
renderer.domElement.addEventListener("pointerdown", (event) => {
  pointerDown = { x: event.clientX, y: event.clientY };
});
renderer.domElement.addEventListener("pointerup", (event) => {
  if (!measurementEnabled || !pointerDown) return;
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
    .filter((intersection) => intersection.object?.isMesh && intersection.object.visible);
  if (!intersections.length) {
    measurementStatus.textContent = "Nenhuma superfície visível nesse ponto.";
    animateElementFeedback(measurementStatus, "is-feedback");
    return;
  }
  const point = intersections[0].point.clone();
  marker(point);
  if (!measurePendingPoint) {
    measurePendingPoint = point;
    updateMeasurementStatus();
    return;
  }
  const start = measurePendingPoint;
  const distance = start.distanceTo(point);
  const geometry = new THREE.BufferGeometry().setFromPoints([start, point]);
  const material = new THREE.LineBasicMaterial({ color: 0x0a7f61, depthTest: false });
  const line = new THREE.Line(geometry, material);
  line.renderOrder = 19;
  scene.add(line);
  measurementObjects.push(line);
  textSprite(`${distance.toFixed(1)} mm`, start.clone().add(point).multiplyScalar(0.5));
  measurementValues.push(Number(distance.toFixed(3)));
  measurePendingPoint = null;
  measurementStatus.textContent = `Distância: ${distance.toFixed(1)} mm · clique para iniciar outra medição.`;
  animateElementFeedback(measurementStatus, "is-feedback");
});

$("measure").addEventListener("click", () => setMeasurementEnabled(!measurementEnabled));
$("clear-measures").addEventListener("click", clearMeasurements);
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
      wireframe_enabled: wireframeEnabled,
      clipping: {
        enabled: clipEnabled.checked,
        axis: clipAxis.value,
        position_percent: Number(clipPosition.value),
        inverted: clipInvert.checked,
      },
      measurements_mm: measurementValues.slice(0, 20),
      visible_roles: Object.entries(meshes).filter(([, mesh]) => mesh.visible).map(([role]) => role),
    },
  };
}

const params = new URLSearchParams(location.search);
const casePath = params.get("case");
const jobId = params.get("job");

async function submitApproval(status) {
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
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/approval`, {
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

if (jobId) {
  approvalDiv.style.display = "block";
  approveButton.addEventListener("click", () => submitApproval("approved"));
  revisionButton.addEventListener("click", () => submitApproval("revision_requested"));
}

function referenceFilenames(manifest) {
  const files = [];
  for (const view of Object.values(manifest.reference_images?.views || {})) {
    for (const frame of view?.frames || []) if (frame.file) files.push(frame.file);
  }
  return [...new Set(files)];
}

async function fetchBuffer(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Falha ao carregar ${url} (${response.status}).`);
  return response.arrayBuffer();
}

if (casePath) {
  (async () => {
    const base = casePath.replace(/\/$/, "");
    const response = await fetch(`${base}/viewer_manifest.json`);
    if (!response.ok) throw new Error("Manifesto do modelo não disponível.");
    const manifest = await response.json();
    const files = [...manifest.meshes.map((item) => item.stl), ...referenceFilenames(manifest)];
    const buffers = await Promise.all(files.map((filename) => fetchBuffer(`${base}/${filename}`)));
    renderManifest(manifest, Object.fromEntries(files.map((filename, index) => [filename, buffers[index]])));
  })().catch((error) => { console.error(error); alert(`Falha ao carregar o modelo: ${error.message}`); });
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
  else if (key === "c") { clipEnabled.checked = !clipEnabled.checked; updateClipping(); }
  else if (key === "escape") setMeasurementEnabled(false);
});

window.__argos = {
  meshes, scene, renderer, camera, THREE,
  applyView, clearMeasurements, updateClipping,
};
