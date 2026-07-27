// Three.js vendorizado em viewer/vendor/ (sem CDN — funciona offline na
// apresentação). O bare specifier "three" é resolvido pelo importmap de index.html.
import * as THREE from "three";
import { STLLoader } from "./vendor/STLLoader.js";
import { OrbitControls } from "./vendor/OrbitControls.js";

const holder = document.getElementById("canvas-holder");
const controlsDiv = document.getElementById("controls");
const metaDiv = document.getElementById("meta");
const drop = document.getElementById("drop");
const approvalDiv = document.getElementById("approval");
const approvalStatus = document.getElementById("approval-status");
const approveButton = document.getElementById("approve");
const revisionButton = document.getElementById("request-revision");

// Ambiente de estúdio procedural (gradiente claro->escuro) usado como
// image-based lighting. Dá reflexos suaves e sensação de superfície úmida sem
// depender de nenhum arquivo HDR externo — 100% offline.
function makeStudioEnvironment(renderer) {
  const canvas = document.createElement("canvas");
  canvas.width = 16; canvas.height = 256;
  const ctx = canvas.getContext("2d");
  const grad = ctx.createLinearGradient(0, 0, 0, canvas.height);
  grad.addColorStop(0.0, "#ffffff");  // topo: luz de cima
  grad.addColorStop(0.5, "#c9d2d6");
  grad.addColorStop(1.0, "#3a3f45");  // base: chão escuro
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const equirect = new THREE.CanvasTexture(canvas);
  equirect.mapping = THREE.EquirectangularReflectionMapping;
  equirect.colorSpace = THREE.SRGBColorSpace;
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envMap = pmrem.fromEquirectangular(equirect).texture;
  equirect.dispose();
  pmrem.dispose();
  return envMap;
}

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xedf6f1);
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
camera.position.set(120, 120, 120);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;
holder.appendChild(renderer.domElement);

scene.environment = makeStudioEnvironment(renderer);
// Rig de três pontos: preenchimento hemisférico suave + luz principal quente +
// luz de contorno fria por trás para destacar o volume do órgão.
scene.add(new THREE.HemisphereLight(0xffffff, 0x40454b, 0.5));
const keyLight = new THREE.DirectionalLight(0xfff4e6, 1.1);
keyLight.position.set(1, 1.2, 0.8);
scene.add(keyLight);
const rimLight = new THREE.DirectionalLight(0xdfe9ff, 0.5);
rimLight.position.set(-1, 0.4, -1);
scene.add(rimLight);

const orbit = new OrbitControls(camera, renderer.domElement);
const group = new THREE.Group();
scene.add(group);

function resize() {
  const w = holder.clientWidth, h = holder.clientHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener("resize", resize);
resize();
(function loop() { requestAnimationFrame(loop); orbit.update(); renderer.render(scene, camera); })();

const loader = new STLLoader();
const meshes = {};

function clearScene() {
  for (const k of Object.keys(meshes)) { group.remove(meshes[k]); delete meshes[k]; }
  controlsDiv.innerHTML = "";
}

// STLLoader devolve geometria não-indexada: cada triângulo tem seus próprios 3
// vértices, sem compartilhar com os vizinhos. computeVertexNormals() nessa
// geometria só reproduz a normal plana de cada face (flat shading) — é por
// isso que a malha aparece "facetada"/"de cubos". Fundir vértices coincidentes
// numa geometria indexada permite normais médias entre faces adjacentes
// (smooth shading real), sem depender de nenhum asset extra.
function mergeVerticesByPosition(geometry, precisionDecimals = 4) {
  const position = geometry.getAttribute("position");
  const scale = 10 ** precisionDecimals;
  const hashToIndex = new Map();
  const positions = [];
  const indices = new Array(position.count);

  for (let i = 0; i < position.count; i++) {
    const x = Math.round(position.getX(i) * scale);
    const y = Math.round(position.getY(i) * scale);
    const z = Math.round(position.getZ(i) * scale);
    const key = `${x}_${y}_${z}`;
    let index = hashToIndex.get(key);
    if (index === undefined) {
      index = positions.length / 3;
      hashToIndex.set(key, index);
      positions.push(position.getX(i), position.getY(i), position.getZ(i));
    }
    indices[i] = index;
  }

  const merged = new THREE.BufferGeometry();
  merged.setIndex(indices);
  merged.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return merged;
}

function tissueMaterial(item) {
  const color = new THREE.Color(item.color);
  const material = item.material || (item.role === "lesao" ? "lesion" : "organ");
  const opacity = Number.isFinite(Number(item.opacity)) ? Number(item.opacity) : 0.5;
  if (material === "lesion") {
    // Lesão: opaca, levemente emissiva para continuar visível por dentro do
    // parênquima semitransparente do órgão.
    return new THREE.MeshPhysicalMaterial({
      color, transparent: true, opacity, roughness: 0.5, metalness: 0.0,
      clearcoat: 0.3, clearcoatRoughness: 0.4,
      emissive: color, emissiveIntensity: 0.08,
    });
  }
  if (material === "segment") {
    return new THREE.MeshPhysicalMaterial({
      color, transparent: true, opacity, roughness: 0.5, metalness: 0.0,
      clearcoat: 0.25, clearcoatRoughness: 0.5, envMapIntensity: 0.55,
    });
  }
  if (material === "vessel") {
    return new THREE.MeshPhysicalMaterial({
      color, transparent: true, opacity, roughness: 0.28, metalness: 0.0,
      clearcoat: 0.65, clearcoatRoughness: 0.2, envMapIntensity: 0.8,
    });
  }
  if (material === "gallbladder") {
    return new THREE.MeshPhysicalMaterial({
      color, transparent: true, opacity, roughness: 0.36, metalness: 0.0,
      clearcoat: 0.55, clearcoatRoughness: 0.3, envMapIntensity: 0.7,
    });
  }
  // Órgão: parênquima úmido — clearcoat dá o brilho de superfície molhada e o
  // sheen simula o espalhamento suave do tecido; semitransparente para deixar
  // ver a lesão por dentro.
  return new THREE.MeshPhysicalMaterial({
    color, transparent: true, opacity,
    roughness: 0.45, metalness: 0.0,
    clearcoat: 0.6, clearcoatRoughness: 0.35,
    sheen: 0.5, sheenRoughness: 0.6, sheenColor: new THREE.Color(0x8a3b2e),
    envMapIntensity: 0.9,
  });
}

function addMesh(item, geometry) {
  const merged = mergeVerticesByPosition(geometry);
  merged.computeVertexNormals();
  const mesh = new THREE.Mesh(merged, tissueMaterial(item));
  mesh.visible = item.default_visible !== false;
  meshes[item.role] = mesh;
  group.add(mesh);
}

function frameScene() {
  const box = new THREE.Box3().setFromObject(group);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3()).length();
  group.position.sub(center);
  camera.position.set(size, size, size);
  camera.near = size / 100; camera.far = size * 10; camera.updateProjectionMatrix();
  orbit.target.set(0, 0, 0); orbit.update();
}

function buildControls(items) {
  for (const it of items) {
    const row = document.createElement("div"); row.className = "row";
    const label = document.createElement("label");
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = it.default_visible !== false;
    cb.onchange = () => { if (meshes[it.role]) meshes[it.role].visible = cb.checked; };
    const sw = document.createElement("span"); sw.className = "swatch"; sw.style.background = it.color;
    label.append(cb, sw, document.createTextNode(" " + (it.label || it.role)));
    row.appendChild(label);
    const op = document.createElement("input");
    op.type = "range"; op.min = "0"; op.max = "1"; op.step = "0.05";
    op.value = String(Number.isFinite(Number(it.opacity)) ? Number(it.opacity) : (it.role === "lesao" ? 1 : 0.5));
    op.oninput = () => { if (meshes[it.role]) meshes[it.role].material.opacity = parseFloat(op.value); };
    row.appendChild(op);
    controlsDiv.appendChild(row);
  }
}

// fileMap: role -> ArrayBuffer ; manifest object
function render(manifest, fileMap) {
  clearScene();
  for (const it of manifest.meshes) {
    const buf = fileMap[it.stl];
    if (!buf) { console.warn("STL ausente:", it.stl); continue; }
    addMesh(it, loader.parse(buf));
  }
  frameScene();
  buildControls(manifest.meshes);
  metaDiv.textContent =
    `caso: ${manifest.case_id}\norgão: ${manifest.organ}\n` +
    `coordenadas: ${manifest.coordinate_system}\nestado: ${manifest.regulatory_state}\n` +
    `${manifest.disclaimer || ""}`;
}

// --- Drag & drop of the outputs/ folder (or its files) ---
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("hover"); });
drop.addEventListener("dragleave", () => drop.classList.remove("hover"));
drop.addEventListener("drop", async (e) => {
  e.preventDefault(); drop.classList.remove("hover");
  const files = [...e.dataTransfer.files];
  const byName = {};
  let manifest = null;
  for (const f of files) {
    const buf = await f.arrayBuffer();
    if (f.name.endsWith(".json")) manifest = JSON.parse(new TextDecoder().decode(buf));
    else byName[f.name] = buf;
  }
  if (!manifest) { alert("Inclua o viewer_manifest.json no que foi arrastado."); return; }
  render(manifest, byName);
});

// --- Optional ?case=<path> when served over http ---
const params = new URLSearchParams(location.search);
const casePath = params.get("case");
const jobId = params.get("job");

async function submitApproval(status) {
  approveButton.disabled = true;
  revisionButton.disabled = true;
  approvalStatus.textContent = "Registrando revisão...";
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/approval`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Falha ao registrar revisão");
    }
    const data = await response.json();
    approvalStatus.textContent = data.status === "approved"
      ? "Segmentação aprovada e registrada."
      : "Solicitação de revisão registrada.";
  } catch (err) {
    approvalStatus.textContent = err.message;
    approveButton.disabled = false;
    revisionButton.disabled = false;
  }
}

if (jobId) {
  approvalDiv.style.display = "block";
  approveButton.onclick = () => submitApproval("approved");
  revisionButton.onclick = () => submitApproval("revision_requested");
}
if (casePath) {
  (async () => {
    const base = casePath.replace(/\/$/, "");
    const manifest = await (await fetch(`${base}/viewer_manifest.json`)).json();
    const fileMap = {};
    for (const it of manifest.meshes) {
      fileMap[it.stl] = await (await fetch(`${base}/${it.stl}`)).arrayBuffer();
    }
    render(manifest, fileMap);
  })().catch((err) => { console.error(err); alert("Falha ao carregar via ?case: " + err.message); });
}
