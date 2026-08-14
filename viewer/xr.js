import * as THREE from "three";

const XR_SCHEMA = "oren-webxr-viewer-v2";
const FRAME_BUDGET_MS = 13.9;
const PANEL_WIDTH = 1024;
const PANEL_HEIGHT = 1280;
const XR_UI_TEXTURE_SCALE = 1.25;
const XR_FONT_FAMILY = '"Roboto", "Noto Sans", "Helvetica Neue", Arial, sans-serif';
const HAND_RAY_LENGTH = 1.6;
const HAND_RAY_SMOOTHING = 0.32;
const GRAB_FOLLOW = 0.58;
const PINCH_DEBOUNCE_MS = 240;
const EXIT_HOLD_MS = 900;
const PINCH_CLOSE_MIN_M = 0.014;
const PINCH_CLOSE_MAX_M = 0.021;
const PINCH_RELEASE_GAP_M = 0.011;
const PINCH_COMMIT_MS = 42;
const PINCH_RELEASE_MS = 34;
const HOVER_STABILITY_MS = 65;
const DIRECT_TOUCH_DEPTH_M = 0.048;
const TABLET_TOUCH_DEPTH_M = 0.026;
const TABLET_TOUCH_COMMIT_MS = 38;
const TABLET_GRAB_FOLLOW = 0.64;
const XR_FRAMEBUFFER_SCALE = 0.86;
const XR_SCENE_INTEGRITY_INTERVAL_MS = 180;
const POINTER_RAYCAST_INTERVAL_MS = 32;
const HAND_VISUAL_INTERVAL_MS = 40;
const PERF_WINDOW_FRAMES = 180;
const PERF_EVALUATION_INTERVAL_FRAMES = 90;
const PERF_STABILITY_THRESHOLD_MS = 18;
const XR_ENTRY_CALIBRATION_FRAMES = 8;
const XR_ENTRY_CALIBRATION_TIMEOUT_MS = 1500;
const XR_ENTRY_WARMUP_MS = 1400;
const XR_SPATIAL_THEME = Object.freeze({
  panelTop: "rgba(46,49,47,.94)",
  panelMiddle: "rgba(31,35,33,.95)",
  panelBottom: "rgba(19,23,21,.96)",
  surface: "rgba(43,48,45,.94)",
  surfaceRaised: "rgba(54,60,56,.95)",
  surfaceActive: "rgba(48,78,65,.96)",
  border: "rgba(226,237,231,.24)",
  borderSoft: "rgba(199,215,207,.15)",
  text: "#f4f7f5",
  textMuted: "#c4cdc8",
  textSoft: "#98a39d",
  accent: "#78b99b",
  accentStrong: "#8bc8ac",
  warning: "#d8b57a",
});
const XR_PAGE_CONTEXT = Object.freeze({
  model: ["ANATOMIA DIGITAL", "Composição do fígado", "Camadas, opacidade e volumetria do modelo."],
  views: ["NAVEGAÇÃO ESPACIAL", "Vistas anatômicas", "Enquadre estruturas e preserve pontos de revisão."],
  tools: ["FERRAMENTAS CLÍNICAS", "Medição e planos", "Operações em LPS sem alterar a segmentação."],
  structures: ["CONTEXTO ANATÔMICO", "Estrutura selecionada", "Foque, isole e ajuste somente a camada ativa."],
  reference: ["REFERÊNCIA MULTIPLANAR", "RM 2D sincronizada", "Compare axial, coronal e sagital com o modelo."],
  rgb: ["EVIDÊNCIA DO PIPELINE", "Painéis RGB", "Navegue pelas fusões publicadas para o caso."],
  review: ["GATE HUMANO", "Revisão técnica", "Confirme evidências antes de concluir a análise."],
});
const XR_ACTION_HINTS = Object.freeze({
  opacity: "alternar nível", volume: "máscara de origem", reset: "escala anatômica",
  render_realism: "textura ilustrativa",
  tablet_reset: "campo de visão", save_view: "guardar estado", restore_view: "última vista",
  measure: "dois pontos LPS", clear_measure: "remover réguas", dimensions: "caixa 3D LPS",
  wireframe: "uma estrutura segura", cut: "plano ortogonal", cut_position: "avançar 10%",
  cut_axis: "LR · AP · SI", cut_invert: "trocar hemispaço", structure_next: "seleção seguinte",
  structure_focus: "recentralizar", structure_isolate: "ocultar contexto", structure_restore: "mostrar contexto",
  structure_visibility: "alternar camada", structure_opacity: "alternar nível", reference_previous: "plano anterior",
  reference_next: "plano seguinte", reference_sync: "vincular ao corte", reference_reset: "campo de visão",
  rgb_previous: "painel anterior", rgb_next: "painel seguinte", rgb_first: "voltar ao início",
  rgb_reset: "campo de visão", review_approve: "finalizar gate", review_revision: "devolver para revisão",
});

const HAND_BONES = Object.freeze([
  ["wrist", "thumb-metacarpal"],
  ["thumb-metacarpal", "thumb-phalanx-proximal"],
  ["thumb-phalanx-proximal", "thumb-phalanx-distal"],
  ["thumb-phalanx-distal", "thumb-tip"],
  ["wrist", "index-finger-metacarpal"],
  ["index-finger-metacarpal", "index-finger-phalanx-proximal"],
  ["index-finger-phalanx-proximal", "index-finger-phalanx-intermediate"],
  ["index-finger-phalanx-intermediate", "index-finger-phalanx-distal"],
  ["index-finger-phalanx-distal", "index-finger-tip"],
  ["wrist", "middle-finger-metacarpal"],
  ["middle-finger-metacarpal", "middle-finger-phalanx-proximal"],
  ["middle-finger-phalanx-proximal", "middle-finger-phalanx-intermediate"],
  ["middle-finger-phalanx-intermediate", "middle-finger-phalanx-distal"],
  ["middle-finger-phalanx-distal", "middle-finger-tip"],
  ["wrist", "ring-finger-metacarpal"],
  ["ring-finger-metacarpal", "ring-finger-phalanx-proximal"],
  ["ring-finger-phalanx-proximal", "ring-finger-phalanx-intermediate"],
  ["ring-finger-phalanx-intermediate", "ring-finger-phalanx-distal"],
  ["ring-finger-phalanx-distal", "ring-finger-tip"],
  ["wrist", "pinky-finger-metacarpal"],
  ["pinky-finger-metacarpal", "pinky-finger-phalanx-proximal"],
  ["pinky-finger-phalanx-proximal", "pinky-finger-phalanx-intermediate"],
  ["pinky-finger-phalanx-intermediate", "pinky-finger-phalanx-distal"],
  ["pinky-finger-phalanx-distal", "pinky-finger-tip"],
  ["index-finger-metacarpal", "middle-finger-metacarpal"],
  ["middle-finger-metacarpal", "ring-finger-metacarpal"],
  ["ring-finger-metacarpal", "pinky-finger-metacarpal"],
]);

const PANEL_PAGES = Object.freeze({
  model: {
    label: "Modelo",
    actions: [
      ["default", "Fígado"], ["anatomy", "Anatomia"],
      ["triage", "Triagem"], ["segments", "Segmentos"],
      ["opacity", "Opacidade fígado"], ["volume", "Volumetria"],
      ["render_realism", "Textura realista"], ["reset", "Recentrar fígado"],
      ["tablet_reset", "Recentrar tablet"],
    ],
  },
  views: {
    label: "Vistas",
    actions: [
      ["view_default", "Vista padrão"], ["view_anterior", "Anterior"],
      ["view_superior", "Superior"], ["view_right", "Direita"],
      ["anatomical_liver", "Foco fígado"], ["anatomical_segments", "Foco segmentos"],
      ["anatomical_vascular", "Foco vasos"], ["anatomical_candidate", "Foco candidato"],
      ["save_view", "Salvar vista"], ["restore_view", "Restaurar vista"],
    ],
  },
  tools: {
    label: "Ferramentas",
    actions: [
      ["measure", "Medir 2 pontos"], ["clear_measure", "Limpar medidas"],
      ["dimensions", "Dimensões 3D"], ["wireframe", "Malha técnica"],
      ["cut", "Ativar corte"], ["cut_position", "Mover corte"],
      ["cut_axis", "Eixo do corte"], ["cut_invert", "Inverter corte"],
    ],
  },
  structures: {
    label: "Estruturas",
    actions: [
      ["structure_next", "Próxima estrutura"], ["structure_focus", "Enquadrar seleção"],
      ["structure_isolate", "Isolar seleção"], ["structure_restore", "Restaurar contexto"],
      ["structure_visibility", "Exibir/ocultar"], ["structure_opacity", "Opacidade seleção"],
    ],
  },
  reference: {
    label: "RM 2D",
    actions: [
      ["reference_axial", "Axial"], ["reference_coronal", "Coronal"],
      ["reference_sagittal", "Sagital"], ["reference_previous", "Plano anterior"],
      ["reference_next", "Próximo plano"], ["reference_sync", "Sincronizar 2D/3D"],
      ["reference_reset", "Recentrar painel 2D"],
    ],
  },
  rgb: {
    label: "Painéis RGB",
    actions: [
      ["rgb_previous", "Painel anterior"], ["rgb_next", "Próximo painel"],
      ["rgb_first", "Primeiro painel"], ["rgb_reset", "Recentrar painel RGB"],
    ],
  },
  review: {
    label: "Revisão",
    clinicianOnly: true,
    actions: [
      ["review_3d", "Contorno 3D revisto"], ["review_2d", "Referência 2D revista"],
      ["review_candidate", "Candidato revisto"], ["review_research", "Uso em pesquisa"],
      ["candidate_decision", "Decisão candidato"], ["review_approve", "Concluir revisão"],
      ["review_revision", "Solicitar revisão"],
    ],
  },
});

function roundRect(context, x, y, width, height, radius) {
  context.beginPath();
  context.roundRect(x, y, width, height, radius);
  context.fill();
}

function strokeRoundRect(context, x, y, width, height, radius) {
  context.beginPath();
  context.roundRect(x, y, width, height, radius);
  context.stroke();
}

function canvasFont(weight, size) {
  return `${weight} ${size}px ${XR_FONT_FAMILY}`;
}

function fitCanvasText(context, text, maxWidth) {
  const value = String(text || "");
  if (context.measureText(value).width <= maxWidth) return value;
  let compact = value;
  while (compact.length > 2 && context.measureText(`${compact}…`).width > maxWidth) compact = compact.slice(0, -1);
  return `${compact}…`;
}

function drawStatusDot(context, x, y, color = XR_SPATIAL_THEME.accentStrong) {
  context.save();
  context.fillStyle = color;
  context.shadowColor = color;
  context.shadowBlur = 4;
  context.beginPath(); context.arc(x, y, 6, 0, Math.PI * 2); context.fill();
  context.restore();
}

function roundedPanelGeometry(width, height, depth, radius) {
  const halfWidth = width / 2;
  const halfHeight = height / 2;
  const shape = new THREE.Shape();
  shape.moveTo(-halfWidth + radius, -halfHeight);
  shape.lineTo(halfWidth - radius, -halfHeight);
  shape.quadraticCurveTo(halfWidth, -halfHeight, halfWidth, -halfHeight + radius);
  shape.lineTo(halfWidth, halfHeight - radius);
  shape.quadraticCurveTo(halfWidth, halfHeight, halfWidth - radius, halfHeight);
  shape.lineTo(-halfWidth + radius, halfHeight);
  shape.quadraticCurveTo(-halfWidth, halfHeight, -halfWidth, halfHeight - radius);
  shape.lineTo(-halfWidth, -halfHeight + radius);
  shape.quadraticCurveTo(-halfWidth, -halfHeight, -halfWidth + radius, -halfHeight);
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth, bevelEnabled: true, bevelSegments: 3, bevelSize: 0.004,
    bevelThickness: 0.003, curveSegments: 8,
  });
  geometry.translate(0, 0, -depth / 2);
  return geometry;
}

function drawOrenCore(context, x, y, radius, phase = 0) {
  context.save();
  context.translate(x, y);
  context.lineCap = "round";
  [[1, 0.18, Math.PI * 1.42], [0.70, 1.9, Math.PI * 1.06]].forEach(([scale, start, span], index) => {
    context.beginPath();
    context.strokeStyle = index === 1 ? "rgba(120,185,155,.28)" : "rgba(120,185,155,.72)";
    context.lineWidth = index === 0 ? 4 : 2;
    context.arc(0, 0, radius * scale, start + phase, start + phase + span);
    context.stroke();
  });
  context.fillStyle = "rgba(139,200,172,.88)";
  context.shadowColor = "rgba(139,200,172,.14)";
  context.shadowBlur = 4;
  context.beginPath(); context.arc(0, 0, radius * 0.13, 0, Math.PI * 2); context.fill();
  context.restore();
}

function makeRay(color = 0x59d6ff) {
  const geometry = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0, -1),
  ]);
  const material = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.82 });
  const line = new THREE.Line(geometry, material);
  line.name = "oren-xr-ray";
  line.scale.z = HAND_RAY_LENGTH;
  return line;
}

function controllerRay(controller, raycaster) {
  const rotation = new THREE.Matrix4().extractRotation(controller.matrixWorld);
  raycaster.ray.origin.setFromMatrixPosition(controller.matrixWorld);
  raycaster.ray.direction.set(0, 0, -1).applyMatrix4(rotation).normalize();
  return true;
}

function handRay(hand, raycaster) {
  const state = hand.userData.orenRayState || {
    initialized: false,
    origin: new THREE.Vector3(), direction: new THREE.Vector3(), source: "fallback",
    platformRay: new THREE.Raycaster(), rawOrigin: new THREE.Vector3(),
    rawDirection: new THREE.Vector3(), eye: new THREE.Vector3(),
  };
  hand.userData.orenRayState = state;
  const targetRay = hand.userData.targetRay;
  if (targetRay?.visible && targetRay.userData.inputSource?.hand) {
    controllerRay(targetRay, state.platformRay);
    const smoothing = state.source === "platform" ? 0.48 : 0.72;
    if (!state.initialized) {
      state.origin.copy(state.platformRay.ray.origin); state.direction.copy(state.platformRay.ray.direction); state.initialized = true;
    } else {
      state.origin.lerp(state.platformRay.ray.origin, smoothing);
      state.direction.lerp(state.platformRay.ray.direction, smoothing).normalize();
    }
    state.source = "platform";
    raycaster.ray.origin.copy(state.origin);
    raycaster.ray.direction.copy(state.direction);
    return true;
  }
  const tip = hand.joints?.["index-finger-tip"];
  const wrist = hand.joints?.wrist;
  if (!tip?.visible || !wrist?.visible) return false;
  tip.getWorldPosition(state.rawOrigin);
  apiCameraWorldPosition(hand, state.eye);
  state.rawDirection.copy(state.rawOrigin).sub(state.eye);
  if (state.rawDirection.lengthSq() < 1e-7) return false;
  state.rawDirection.normalize();
  if (!state.initialized) {
    state.origin.copy(state.rawOrigin); state.direction.copy(state.rawDirection); state.initialized = true;
  } else {
    state.origin.lerp(state.rawOrigin, HAND_RAY_SMOOTHING);
    state.direction.lerp(state.rawDirection, HAND_RAY_SMOOTHING).normalize();
  }
  state.source = "fallback";
  raycaster.ray.origin.copy(state.origin);
  raycaster.ray.direction.copy(state.direction);
  return true;
}

function apiCameraWorldPosition(hand, target) {
  const camera = hand.userData.xrCamera;
  if (camera) camera.getWorldPosition(target);
  else hand.joints.wrist.getWorldPosition(target);
  return target;
}

function haptic(inputSource, intensity = 0.3, duration = 35) {
  const actuator = inputSource?.gamepad?.hapticActuators?.[0];
  if (actuator?.pulse) actuator.pulse(intensity, duration).catch(() => {});
}

function createSpatialPanel() {
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(PANEL_WIDTH * XR_UI_TEXTURE_SCALE);
  canvas.height = Math.round(PANEL_HEIGHT * XR_UI_TEXTURE_SCALE);
  const context = canvas.getContext("2d");
  context.scale(XR_UI_TEXTURE_SCALE, XR_UI_TEXTURE_SCALE);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.generateMipmaps = false;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  const material = new THREE.MeshBasicMaterial({
    map: texture, transparent: true, side: THREE.DoubleSide, depthTest: true,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(0.58, 0.725), material);
  mesh.name = "oren-xr-panel";
  mesh.position.set(-0.53, 1.34, -0.74);
  mesh.rotation.y = 0.18;
  mesh.renderOrder = 100;
  const buttons = [];

  const draw = (state = {}) => {
    const profile = state.profile === "patient" ? "patient" : "clinician";
    const pages = Object.entries(PANEL_PAGES).filter(([, page]) => !page.clinicianOnly || profile === "clinician");
    const pageName = PANEL_PAGES[state.page] && (!PANEL_PAGES[state.page].clinicianOnly || profile === "clinician")
      ? state.page : "model";
    context.clearRect(0, 0, PANEL_WIDTH, PANEL_HEIGHT);
    const glass = context.createLinearGradient(0, 0, PANEL_WIDTH, PANEL_HEIGHT);
    glass.addColorStop(0, "rgba(18,65,48,.98)");
    glass.addColorStop(0.55, "rgba(11,48,35,.97)");
    glass.addColorStop(1, "rgba(7,35,25,.96)");
    context.fillStyle = glass;
    roundRect(context, 8, 8, 1008, 1264, 54);

    context.save();
    context.beginPath(); context.roundRect(8, 8, 1008, 1264, 54); context.clip();
    const glow = context.createRadialGradient(120, 80, 8, 120, 80, 360);
    glow.addColorStop(0, "rgba(66,230,170,.20)");
    glow.addColorStop(1, "rgba(45,175,121,0)");
    context.fillStyle = glow; context.fillRect(0, 0, 520, 430);
    const lowerGlow = context.createRadialGradient(930, 1160, 20, 930, 1160, 420);
    lowerGlow.addColorStop(0, "rgba(21,151,107,.16)");
    lowerGlow.addColorStop(1, "rgba(21,116,90,0)");
    context.fillStyle = lowerGlow; context.fillRect(500, 760, 524, 520);
    context.restore();

    context.strokeStyle = "rgba(100,244,192,.50)";
    context.lineWidth = 2;
    strokeRoundRect(context, 10, 10, 1004, 1260, 52);
    context.strokeStyle = "rgba(102,219,175,.22)";
    context.lineWidth = 1;
    strokeRoundRect(context, 23, 23, 978, 1234, 43);
    drawOrenCore(context, 88, 85, 34);

    context.fillStyle = "#f1fff8";
    context.font = canvasFont(700, 46);
    context.fillText("OREN", 144, 80);
    context.fillStyle = "#b7d7c8";
    context.font = canvasFont(600, 22);
    context.fillText("Digital Twin hepático", 145, 111);
    context.fillStyle = "#58e5ad";
    context.font = canvasFont(700, 21);
    context.fillText(profile === "patient" ? "VISUALIZAÇÃO DO PACIENTE" : "REVISÃO MÉDICA · MÃOS ATIVAS", 54, 151);
    context.fillStyle = "rgba(20,90,65,.96)";
    roundRect(context, 54, 166, 916, 52, 24);
    context.strokeStyle = "rgba(82,229,170,.30)";
    strokeRoundRect(context, 54, 166, 916, 52, 24);
    context.fillStyle = "#effff7";
    context.font = canvasFont(600, 24);
    context.fillText((state.status || "Toque para selecionar").slice(0, 72), 78, 199);
    context.fillStyle = "#4ff0ae";
    context.beginPath(); context.arc(934, 192, 6, 0, Math.PI * 2); context.fill();
    buttons.length = 0;

    const tabGap = 10;
    const tabColumns = 4;
    const tabWidth = Math.floor((916 - tabGap * (tabColumns - 1)) / tabColumns);
    pages.forEach(([name, page], index) => {
      const column = index % tabColumns;
      const row = Math.floor(index / tabColumns);
      const x = 54 + column * (tabWidth + tabGap);
      const y = 230 + row * 68;
      const selected = name === pageName;
      context.shadowColor = selected ? "rgba(55,226,161,.28)" : "transparent";
      context.shadowBlur = selected ? 18 : 0;
      context.shadowOffsetY = selected ? 6 : 0;
      context.fillStyle = selected ? "rgba(25,145,102,.98)" : "rgba(13,65,46,.97)";
      roundRect(context, x, y, tabWidth, 58, 22);
      context.shadowColor = "transparent"; context.shadowBlur = 0; context.shadowOffsetY = 0;
      context.strokeStyle = selected ? "rgba(101,244,190,.66)" : "rgba(99,202,162,.24)";
      context.lineWidth = 1;
      strokeRoundRect(context, x, y, tabWidth, 58, 22);
      context.fillStyle = selected ? "#ffffff" : "#d9f4e7";
      context.font = canvasFont(700, 22);
      context.textAlign = "center";
      context.fillText(page.label, x + tabWidth / 2, y + 37);
      context.textAlign = "left";
      buttons.push({ action: `page_${name}`, x, y, width: tabWidth, height: 58 });
    });

    const actions = PANEL_PAGES[pageName].actions.filter(([action]) => (
      profile === "clinician" || !["triage", "measure", "dimensions", "cut", "cut_position", "cut_axis", "cut_invert"].includes(action)
    ));
    actions.forEach(([action, label], index) => {
      const column = index % 2;
      const row = Math.floor(index / 2);
      const x = 54 + column * 470;
      const y = 382 + row * 101;
      const active = state.active === action || state.activeActions?.includes(action);
      const hovered = state.hovered === action;
      const buttonGradient = context.createLinearGradient(x, y, x, y + 78);
      buttonGradient.addColorStop(0, active ? "rgba(28,158,111,.99)" : hovered ? "rgba(25,116,83,.99)" : "rgba(14,76,54,.97)");
      buttonGradient.addColorStop(1, active ? "rgba(14,108,76,.99)" : hovered ? "rgba(14,83,59,.99)" : "rgba(9,53,38,.97)");
      context.fillStyle = buttonGradient;
      context.shadowColor = active ? "rgba(61,235,170,.30)" : "rgba(0,0,0,.22)";
      context.shadowBlur = active ? 20 : 12; context.shadowOffsetY = 5;
      roundRect(context, x, y, 420, 78, 24);
      context.shadowColor = "transparent"; context.shadowBlur = 0; context.shadowOffsetY = 0;
      context.strokeStyle = active ? "rgba(109,255,201,.72)" : hovered ? "rgba(76,231,172,.58)" : "rgba(89,190,151,.26)";
      strokeRoundRect(context, x, y, 420, 78, 24);
      context.fillStyle = active ? "#ffffff" : hovered ? "#f3fff9" : "#d9f4e7";
      context.font = canvasFont(700, 28);
      context.textAlign = "center";
      context.fillText(label, x + 210, y + 49);
      context.textAlign = "left";
      buttons.push({ action, x, y, width: 420, height: 78 });
    });

    context.strokeStyle = "rgba(97,205,162,.26)";
    context.beginPath(); context.moveTo(54, 1116); context.lineTo(970, 1116); context.stroke();
    context.fillStyle = "#5aeab1";
    context.font = canvasFont(700, 21);
    context.fillText("Toque", 54, 1150);
    context.fillText("Gestos", 54, 1187);
    context.fillStyle = "#e2f7ec";
    context.font = canvasFont(600, 22);
    context.fillText("Indicador seleciona · pinça inferior move o painel", 143, 1150);
    context.fillText("Pinça move o fígado · duas mãos ajustam escala e rotação", 143, 1187);
    context.fillStyle = "#a9cabb";
    context.font = canvasFont(600, 19);
    context.fillText("Pesquisa · revisão humana obrigatória", 54, 1230);
    context.fillStyle = "#4ff0ae";
    context.beginPath(); context.arc(944, 1224, 6, 0, Math.PI * 2); context.fill();
    texture.needsUpdate = true;
  };
  draw();
  return { mesh, buttons, draw };
}

function createSpatialPanelV2() {
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(PANEL_WIDTH * XR_UI_TEXTURE_SCALE);
  canvas.height = Math.round(PANEL_HEIGHT * XR_UI_TEXTURE_SCALE);
  const context = canvas.getContext("2d");
  context.scale(XR_UI_TEXTURE_SCALE, XR_UI_TEXTURE_SCALE);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.generateMipmaps = false;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  const material = new THREE.MeshBasicMaterial({
    map: texture, transparent: true, side: THREE.DoubleSide, depthTest: true, toneMapped: false,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(0.58, 0.725), material);
  mesh.name = "oren-xr-panel";
  mesh.position.set(-0.53, 1.34, -0.74);
  mesh.rotation.y = 0.18;
  mesh.renderOrder = 100;
  const buttons = [];
  let lastDrawSignature = "";
  let textureUploadCount = 0;

  const draw = (state = {}) => {
    const profile = state.profile === "patient" ? "patient" : "clinician";
    const pages = Object.entries(PANEL_PAGES).filter(([, page]) => !page.clinicianOnly || profile === "clinician");
    const pageName = PANEL_PAGES[state.page] && (!PANEL_PAGES[state.page].clinicianOnly || profile === "clinician")
      ? state.page : "model";
    const selection = state.selection?.role ? state.selection : null;
    const signature = JSON.stringify({
      profile, pageName, status: state.status || "", active: state.active || "",
      activeActions: state.activeActions || [], hovered: state.hovered || "",
      performanceTier: state.performanceTier || "", selection,
    });
    if (signature === lastDrawSignature) return false;
    lastDrawSignature = signature;

    context.clearRect(0, 0, PANEL_WIDTH, PANEL_HEIGHT);
    const glass = context.createLinearGradient(0, 0, PANEL_WIDTH, PANEL_HEIGHT);
    glass.addColorStop(0, XR_SPATIAL_THEME.panelTop);
    glass.addColorStop(0.55, XR_SPATIAL_THEME.panelMiddle);
    glass.addColorStop(1, XR_SPATIAL_THEME.panelBottom);
    context.fillStyle = glass;
    roundRect(context, 8, 8, 1008, 1264, 54);

    context.save();
    context.beginPath(); context.roundRect(8, 8, 1008, 1264, 54); context.clip();
    const glow = context.createRadialGradient(120, 80, 8, 120, 80, 360);
    glow.addColorStop(0, "rgba(185,213,200,.08)");
    glow.addColorStop(1, "rgba(185,213,200,0)");
    context.fillStyle = glow; context.fillRect(0, 0, 520, 430);
    const lowerGlow = context.createRadialGradient(930, 1160, 20, 930, 1160, 420);
    lowerGlow.addColorStop(0, "rgba(122,175,151,.07)");
    lowerGlow.addColorStop(1, "rgba(122,175,151,0)");
    context.fillStyle = lowerGlow; context.fillRect(500, 760, 524, 520);
    context.restore();

    context.strokeStyle = XR_SPATIAL_THEME.border;
    context.lineWidth = 2;
    strokeRoundRect(context, 10, 10, 1004, 1260, 52);
    context.strokeStyle = "rgba(210,225,217,.11)";
    context.lineWidth = 1;
    strokeRoundRect(context, 23, 23, 978, 1234, 43);
    drawOrenCore(context, 88, 85, 34);

    context.fillStyle = XR_SPATIAL_THEME.text;
    context.font = canvasFont(700, 46);
    context.fillText("OREN", 144, 80);
    context.fillStyle = XR_SPATIAL_THEME.textMuted;
    context.font = canvasFont(600, 22);
    context.fillText("Digital Twin hepático", 145, 111);
    context.fillStyle = XR_SPATIAL_THEME.accent;
    context.font = canvasFont(700, 21);
    context.fillText(profile === "patient" ? "VISUALIZAÇÃO DO PACIENTE" : "REVISÃO MÉDICA · INTERFACE ESPACIAL", 54, 151);

    context.fillStyle = "rgba(48,53,50,.95)";
    roundRect(context, 54, 166, 916, 52, 24);
    context.strokeStyle = "rgba(202,219,210,.16)";
    strokeRoundRect(context, 54, 166, 916, 52, 24);
    context.fillStyle = XR_SPATIAL_THEME.text;
    context.font = canvasFont(600, 24);
    context.fillText(fitCanvasText(context, state.status || "Toque para selecionar", 820), 78, 199);
    drawStatusDot(context, 934, 192);
    buttons.length = 0;

    const tabGap = 10;
    const tabColumns = 4;
    const tabWidth = Math.floor((916 - tabGap * (tabColumns - 1)) / tabColumns);
    pages.forEach(([name, page], index) => {
      const column = index % tabColumns;
      const row = Math.floor(index / tabColumns);
      const x = 54 + column * (tabWidth + tabGap);
      const y = 230 + row * 66;
      const selected = name === pageName;
      context.shadowColor = selected ? "rgba(139,200,172,.12)" : "transparent";
      context.shadowBlur = selected ? 8 : 0;
      context.shadowOffsetY = selected ? 4 : 0;
      context.fillStyle = selected ? XR_SPATIAL_THEME.surfaceActive : XR_SPATIAL_THEME.surface;
      roundRect(context, x, y, tabWidth, 58, 22);
      context.shadowColor = "transparent"; context.shadowBlur = 0; context.shadowOffsetY = 0;
      context.strokeStyle = selected ? "rgba(139,200,172,.42)" : XR_SPATIAL_THEME.borderSoft;
      strokeRoundRect(context, x, y, tabWidth, 58, 22);
      context.fillStyle = selected ? XR_SPATIAL_THEME.text : XR_SPATIAL_THEME.textMuted;
      context.font = canvasFont(700, 22);
      context.textAlign = "center";
      context.fillText(page.label, x + tabWidth / 2, y + 37);
      context.textAlign = "left";
      buttons.push({ action: `page_${name}`, x, y, width: tabWidth, height: 58 });
    });

    const [eyebrow, title, description] = XR_PAGE_CONTEXT[pageName];
    context.fillStyle = "rgba(26,30,28,.78)";
    roundRect(context, 54, 365, 916, 112, 28);
    context.strokeStyle = "rgba(208,222,214,.12)";
    strokeRoundRect(context, 54, 365, 916, 112, 28);
    context.fillStyle = XR_SPATIAL_THEME.accent;
    context.font = canvasFont(700, 17);
    context.fillText(eyebrow, 82, 393);
    context.fillStyle = XR_SPATIAL_THEME.text;
    context.font = canvasFont(700, 31);
    context.fillText(fitCanvasText(context, selection?.label || title, 560), 82, 430);
    context.fillStyle = XR_SPATIAL_THEME.textMuted;
    context.font = canvasFont(500, 19);
    context.fillText(fitCanvasText(context, selection ? `${selection.category} · ${selection.visible ? "visível" : "oculta"}` : description, 610), 82, 458);
    context.fillStyle = selection ? "rgba(49,78,65,.94)" : "rgba(43,48,45,.92)";
    roundRect(context, 742, 391, 196, 56, 20);
    context.strokeStyle = selection ? "rgba(139,200,172,.38)" : "rgba(208,222,214,.12)";
    strokeRoundRect(context, 742, 391, 196, 56, 20);
    context.fillStyle = selection ? XR_SPATIAL_THEME.text : XR_SPATIAL_THEME.textMuted;
    context.font = canvasFont(700, 18);
    context.textAlign = "center";
    context.fillText(selection ? "SELECIONADA" : "OREN SPATIAL", 840, 426);
    context.textAlign = "left";

    const actions = PANEL_PAGES[pageName].actions.filter(([action]) => (
      profile === "clinician" || !["triage", "measure", "dimensions", "cut", "cut_position", "cut_axis", "cut_invert"].includes(action)
    ));
    actions.forEach(([action, label], index) => {
      const column = index % 2;
      const row = Math.floor(index / 2);
      const x = 54 + column * 470;
      const y = 500 + row * 92;
      const active = state.active === action || state.activeActions?.includes(action);
      const hovered = state.hovered === action;
      const buttonGradient = context.createLinearGradient(x, y, x, y + 76);
      buttonGradient.addColorStop(0, active ? "rgba(55,88,73,.98)" : hovered ? "rgba(58,64,61,.97)" : "rgba(47,52,49,.95)");
      buttonGradient.addColorStop(1, active ? "rgba(38,63,52,.98)" : hovered ? "rgba(42,47,44,.97)" : "rgba(32,36,34,.96)");
      context.fillStyle = buttonGradient;
      context.shadowColor = active ? "rgba(139,200,172,.14)" : "rgba(0,0,0,.14)";
      context.shadowBlur = active ? 8 : 5; context.shadowOffsetY = 3;
      roundRect(context, x, y, 420, 76, 24);
      context.shadowColor = "transparent"; context.shadowBlur = 0; context.shadowOffsetY = 0;
      context.strokeStyle = active ? "rgba(139,200,172,.46)" : hovered ? "rgba(218,228,223,.25)" : "rgba(208,222,214,.13)";
      strokeRoundRect(context, x, y, 420, 76, 24);
      context.fillStyle = active ? "rgba(139,200,172,.18)" : "rgba(218,228,223,.08)";
      context.beginPath(); context.arc(x + 37, y + 38, 19, 0, Math.PI * 2); context.fill();
      context.fillStyle = active ? XR_SPATIAL_THEME.text : hovered ? "#eef2f0" : XR_SPATIAL_THEME.textMuted;
      context.font = canvasFont(700, 22);
      context.fillText(fitCanvasText(context, label, 318), x + 70, y + 31);
      context.fillStyle = active ? "#dce8e1" : XR_SPATIAL_THEME.textSoft;
      context.font = canvasFont(500, 15);
      context.fillText(fitCanvasText(context, XR_ACTION_HINTS[action] || (active ? "ativo" : "toque para executar"), 318), x + 70, y + 56);
      if (active) drawStatusDot(context, x + 37, y + 38, XR_SPATIAL_THEME.accentStrong);
      buttons.push({ action, x, y, width: 420, height: 76 });
    });

    context.strokeStyle = "rgba(208,222,214,.14)";
    context.beginPath(); context.moveTo(54, 1052); context.lineTo(970, 1052); context.stroke();
    context.fillStyle = XR_SPATIAL_THEME.accent;
    context.font = canvasFont(700, 19);
    context.fillText("TOQUE", 54, 1086);
    context.fillText("GESTOS", 54, 1122);
    context.fillStyle = XR_SPATIAL_THEME.text;
    context.font = canvasFont(600, 20);
    context.fillText("Indicador seleciona · barra inferior move o painel", 150, 1086);
    context.fillText("Pinça move o fígado · duas mãos escalam e giram", 150, 1122);
    context.fillStyle = "rgba(39,44,41,.90)";
    roundRect(context, 54, 1150, 916, 54, 22);
    context.fillStyle = XR_SPATIAL_THEME.textMuted;
    context.font = canvasFont(600, 18);
    context.fillText(`Quest 3S · ${state.performanceTier === "stability" ? "modo estabilidade" : "qualidade adaptativa"}`, 78, 1184);
    context.fillStyle = XR_SPATIAL_THEME.textSoft;
    context.font = canvasFont(600, 18);
    context.fillText("Pesquisa · revisão humana obrigatória", 54, 1240);
    drawStatusDot(context, 944, 1234);
    texture.needsUpdate = true;
    textureUploadCount += 1;
    return true;
  };
  draw();
  return { mesh, buttons, draw, getPerformanceStats: () => ({ texture_uploads: textureUploadCount }) };
}

function createExitButton() {
  const canvas = document.createElement("canvas");
  canvas.width = 768;
  canvas.height = 220;
  const context = canvas.getContext("2d");
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.generateMipmaps = false;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(0.31, 0.089),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true, side: THREE.DoubleSide, depthTest: false }),
  );
  mesh.name = "oren-xr-exit-button";
  mesh.position.set(0, 1.7, -0.68);
  mesh.renderOrder = 120;
  let lastDrawSignature = "";
  const draw = ({ hovered = false, progress = 0, closing = false } = {}) => {
    const displayProgress = Math.round(Math.min(Math.max(progress, 0), 1) * 24) / 24;
    const signature = `${hovered}:${closing}:${displayProgress}`;
    if (signature === lastDrawSignature) return false;
    lastDrawSignature = signature;
    context.clearRect(0, 0, canvas.width, canvas.height);
    const exitGlass = context.createLinearGradient(0, 0, 768, 220);
    exitGlass.addColorStop(0, closing ? "rgba(99,39,31,.98)" : hovered ? "rgba(55,88,73,.98)" : "rgba(47,52,49,.96)");
    exitGlass.addColorStop(1, closing ? "rgba(61,24,20,.98)" : "rgba(30,34,32,.97)");
    context.fillStyle = exitGlass;
    roundRect(context, 8, 8, 752, 204, 34);
    context.strokeStyle = closing ? "rgba(255,155,126,.66)" : hovered ? "rgba(139,200,172,.46)" : "rgba(208,222,214,.18)";
    context.lineWidth = 2;
    strokeRoundRect(context, 10, 10, 748, 200, 32);
    if (displayProgress > 0) {
      context.fillStyle = "rgba(185,110,84,.36)";
      roundRect(context, 22, 176, 724 * displayProgress, 17, 8);
    }
    context.fillStyle = closing ? "#ffd8cd" : XR_SPATIAL_THEME.text;
    context.font = canvasFont(600, 43);
    context.textAlign = "center";
    context.fillText(closing ? "Voltando ao webapp…" : "⌂  Voltar ao webapp", 384, 103);
    context.font = canvasFont(500, 27);
    context.fillStyle = closing ? "#ffbba8" : hovered ? XR_SPATIAL_THEME.accentStrong : XR_SPATIAL_THEME.textMuted;
    context.fillText(displayProgress > 0 && !closing ? "Mantenha a pinça" : "Saída segura", 384, 151);
    context.textAlign = "left";
    texture.needsUpdate = true;
    return true;
  };
  draw();
  return { mesh, draw };
}

function createTabletAssembly(panelMesh) {
  const root = new THREE.Group();
  root.name = "oren-xr-tablet-root";
  root.position.copy(panelMesh.position);
  root.quaternion.copy(panelMesh.quaternion);
  panelMesh.position.set(0, 0, 0);
  panelMesh.quaternion.identity();

  const frame = new THREE.Mesh(
    roundedPanelGeometry(0.615, 0.815, 0.014, 0.035),
    new THREE.MeshStandardMaterial({
      color: 0x282d2a, emissive: 0x0b110e, emissiveIntensity: 0.12,
      roughness: 0.68, metalness: 0.08, transparent: false, opacity: 1,
    }),
  );
  frame.name = "oren-xr-tablet-frame";
  frame.position.z = -0.011;
  frame.renderOrder = 96;
  const frameEdges = new THREE.LineSegments(
    new THREE.EdgesGeometry(frame.geometry),
    new THREE.LineBasicMaterial({ color: 0x87ad9a, transparent: true, opacity: 0.34 }),
  );
  frameEdges.name = "oren-xr-tablet-hud-edges";
  frameEdges.position.copy(frame.position);
  frameEdges.renderOrder = 103;

  const handleCanvas = document.createElement("canvas");
  handleCanvas.width = 768; handleCanvas.height = 144;
  const handleContext = handleCanvas.getContext("2d");
  const handleTexture = new THREE.CanvasTexture(handleCanvas);
  handleTexture.colorSpace = THREE.SRGBColorSpace;
  handleTexture.generateMipmaps = false;
  handleTexture.minFilter = THREE.LinearFilter;
  handleTexture.magFilter = THREE.LinearFilter;
  const handle = new THREE.Mesh(
    new THREE.PlaneGeometry(0.55, 0.075),
    new THREE.MeshBasicMaterial({ map: handleTexture, transparent: true, side: THREE.DoubleSide, depthTest: false }),
  );
  handle.name = "oren-xr-tablet-handle";
  handle.position.set(0, -0.397, 0.004);
  handle.renderOrder = 104;
  let lastHandleSignature = "";
  const drawHandle = ({ hovered = false, grabbed = false } = {}) => {
    const signature = `${hovered}:${grabbed}`;
    if (signature === lastHandleSignature) return false;
    lastHandleSignature = signature;
    handleContext.clearRect(0, 0, 768, 144);
    const handleGlass = handleContext.createLinearGradient(0, 0, 768, 144);
    handleGlass.addColorStop(0, grabbed ? "rgba(54,91,75,.98)" : hovered ? "rgba(57,73,65,.98)" : "rgba(50,56,52,.98)");
    handleGlass.addColorStop(1, grabbed ? "rgba(38,65,53,.98)" : "rgba(31,36,33,.98)");
    handleContext.fillStyle = handleGlass;
    roundRect(handleContext, 5, 5, 758, 134, 26);
    handleContext.strokeStyle = grabbed ? "rgba(139,200,172,.46)" : hovered ? "rgba(218,228,223,.25)" : "rgba(208,222,214,.16)";
    handleContext.lineWidth = 2;
    strokeRoundRect(handleContext, 7, 7, 754, 130, 24);
    drawOrenCore(handleContext, 72, 72, 27, grabbed ? 0.7 : 0);
    handleContext.fillStyle = XR_SPATIAL_THEME.text;
    handleContext.textAlign = "center";
    handleContext.font = canvasFont(600, 30);
    handleContext.fillText(grabbed ? "Tablet seguro · mova a mão" : "Pinça inferior · mover tablet", 430, 64);
    handleContext.font = canvasFont(500, 20);
    handleContext.fillStyle = grabbed ? "rgba(255,255,255,.88)" : XR_SPATIAL_THEME.textMuted;
    handleContext.fillText("Toque direto com o indicador", 430, 102);
    handleContext.textAlign = "left";
    handleTexture.needsUpdate = true;
    return true;
  };
  drawHandle();

  const touchCursor = new THREE.Mesh(
    new THREE.RingGeometry(0.012, 0.018, 28),
    new THREE.MeshBasicMaterial({
      color: 0x78b99b, transparent: true, opacity: 0.88, side: THREE.DoubleSide,
      depthTest: false,
    }),
  );
  touchCursor.name = "oren-xr-tablet-touch-cursor";
  touchCursor.position.z = 0.006;
  touchCursor.visible = false;
  touchCursor.renderOrder = 118;

  root.add(frame, frameEdges, panelMesh, handle, touchCursor);
  return { root, frame, frameEdges, handle, touchCursor, drawHandle, label: "Tablet de controles" };
}

function createReferencePanel() {
  const referenceWidth = 768;
  const referenceHeight = 896;
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(referenceWidth * XR_UI_TEXTURE_SCALE);
  canvas.height = Math.round(referenceHeight * XR_UI_TEXTURE_SCALE);
  const context = canvas.getContext("2d");
  context.scale(XR_UI_TEXTURE_SCALE, XR_UI_TEXTURE_SCALE);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.generateMipmaps = false;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(0.50, 0.583),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true, side: THREE.DoubleSide, toneMapped: false }),
  );
  mesh.name = "oren-xr-reference-panel";
  mesh.position.set(0.50, 1.34, -0.74);
  mesh.rotation.y = -0.18;
  mesh.renderOrder = 99;
  const rgbImage = new Image();
  let rgbSource = "";
  let lastState = {};
  let lastDrawSignature = "";
  let textureUploadCount = 0;
  rgbImage.decoding = "async";
  rgbImage.addEventListener("load", () => { lastDrawSignature = ""; draw(lastState); });
  const draw = (state = {}) => {
    lastState = state;
    const rgbMode = state.mode === "rgb";
    const signature = JSON.stringify({
      mode: rgbMode ? "rgb" : "reference",
      image_src: state.image_src || "",
      metadata: state.metadata || "",
      image_ready: rgbMode ? Boolean(rgbImage.complete && rgbImage.naturalWidth) : Boolean(document.getElementById("reference-image")?.complete),
    });
    if (signature === lastDrawSignature) return false;
    lastDrawSignature = signature;
    context.clearRect(0, 0, referenceWidth, referenceHeight);
    const glass = context.createLinearGradient(0, 0, referenceWidth, referenceHeight);
    glass.addColorStop(0, XR_SPATIAL_THEME.panelTop);
    glass.addColorStop(1, XR_SPATIAL_THEME.panelBottom);
    context.fillStyle = glass;
    roundRect(context, 4, 4, referenceWidth - 8, referenceHeight - 8, 46);
    context.strokeStyle = XR_SPATIAL_THEME.border;
    context.lineWidth = 2;
    strokeRoundRect(context, 12, 12, 744, 872, 38);
    drawOrenCore(context, 48, 47, 22);
    context.fillStyle = XR_SPATIAL_THEME.text;
    context.font = canvasFont(700, 30);
    context.fillText(rgbMode ? "Painéis RGB do caso" : "Referência RM 2D", 86, 54);
    context.fillStyle = rgbMode ? "rgba(216,181,122,.16)" : "rgba(139,200,172,.13)";
    roundRect(context, 612, 24, 116, 38, 16);
    context.fillStyle = rgbMode ? XR_SPATIAL_THEME.warning : XR_SPATIAL_THEME.accentStrong;
    context.font = canvasFont(700, 16);
    context.textAlign = "center";
    context.fillText(rgbMode ? "RGB" : "MPR", 670, 49);
    context.textAlign = "left";
    context.fillStyle = "rgba(208,222,214,.14)";
    context.fillRect(34, 68, 700, 1);
    if (rgbMode && state.image_src && state.image_src !== rgbSource) {
      rgbSource = state.image_src;
      rgbImage.src = rgbSource;
    }
    const image = rgbMode ? rgbImage : document.getElementById("reference-image");
    if (image?.complete && image.naturalWidth) {
      const box = { x: 34, y: 76, width: 700, height: 700 };
      const scale = Math.min(box.width / image.naturalWidth, box.height / image.naturalHeight);
      const width = image.naturalWidth * scale;
      const height = image.naturalHeight * scale;
      context.save();
      context.beginPath(); context.roundRect(box.x, box.y, box.width, box.height, 28); context.clip();
      context.drawImage(image, box.x + (box.width - width) / 2, box.y + (box.height - height) / 2, width, height);
      context.restore();
    } else {
      context.fillStyle = "#0e1110";
      roundRect(context, 34, 76, 700, 700, 28);
      context.fillStyle = XR_SPATIAL_THEME.textMuted;
      context.font = canvasFont(500, 28);
      context.fillText(rgbMode ? "Carregando painel RGB…" : "Imagem de referência indisponível", 130, 430);
    }
    context.strokeStyle = "rgba(208,222,214,.18)";
    strokeRoundRect(context, 34, 76, 700, 700, 28);
    context.fillStyle = "rgba(39,44,41,.92)";
    roundRect(context, 24, 790, 720, 86, 24);
    context.fillStyle = XR_SPATIAL_THEME.textMuted;
    context.font = canvasFont(600, 21);
    context.fillText((state.metadata || "").slice(0, 62), 34, 825);
    context.fillText(
      rgbMode ? "Fusão RGB original usada como evidência pelo pipeline." : "Use a aba RM 2D para navegar e sincronizar o corte.",
      34, 862,
    );
    texture.needsUpdate = true;
    textureUploadCount += 1;
    return true;
  };
  draw();
  return { mesh, draw, getPerformanceStats: () => ({ texture_uploads: textureUploadCount }) };
}

function createReferencePanelAssembly(panelMesh) {
  const root = new THREE.Group();
  root.name = "oren-xr-reference-root";
  root.position.copy(panelMesh.position);
  root.quaternion.copy(panelMesh.quaternion);
  panelMesh.position.set(0, 0, 0);
  panelMesh.quaternion.identity();

  const frame = new THREE.Mesh(
    roundedPanelGeometry(0.535, 0.665, 0.012, 0.032),
    new THREE.MeshStandardMaterial({
      color: 0x282d2a, emissive: 0x0b110e, emissiveIntensity: 0.12,
      roughness: 0.68, metalness: 0.08, transparent: false, opacity: 1,
    }),
  );
  frame.name = "oren-xr-reference-frame";
  frame.position.z = -0.01;
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(frame.geometry),
    new THREE.LineBasicMaterial({ color: 0x87ad9a, transparent: true, opacity: 0.34 }),
  );
  edges.name = "oren-xr-reference-hud-edges";
  edges.position.copy(frame.position);

  const canvas = document.createElement("canvas");
  canvas.width = 720; canvas.height = 128;
  const context = canvas.getContext("2d");
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.generateMipmaps = false;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  const handle = new THREE.Mesh(
    new THREE.PlaneGeometry(0.46, 0.072),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true, side: THREE.DoubleSide, depthTest: false }),
  );
  handle.name = "oren-xr-reference-handle";
  handle.position.set(0, -0.323, 0.004);
  handle.renderOrder = 105;
  let lastHandleSignature = "";
  const drawHandle = ({ hovered = false, grabbed = false, mode = "reference" } = {}) => {
    const signature = `${hovered}:${grabbed}:${mode}`;
    if (signature === lastHandleSignature) return false;
    lastHandleSignature = signature;
    context.clearRect(0, 0, canvas.width, canvas.height);
    const glass = context.createLinearGradient(0, 0, canvas.width, canvas.height);
    glass.addColorStop(0, grabbed ? "rgba(54,91,75,.98)" : hovered ? "rgba(57,73,65,.98)" : "rgba(50,56,52,.98)");
    glass.addColorStop(1, grabbed ? "rgba(38,65,53,.98)" : "rgba(31,36,33,.98)");
    context.fillStyle = glass; roundRect(context, 5, 5, 710, 118, 22);
    context.strokeStyle = grabbed ? "rgba(139,200,172,.46)" : hovered ? "rgba(218,228,223,.25)" : "rgba(208,222,214,.16)";
    context.lineWidth = 2; strokeRoundRect(context, 7, 7, 706, 114, 20);
    context.fillStyle = XR_SPATIAL_THEME.text; context.textAlign = "center";
    context.font = canvasFont(600, 27);
    const panelName = mode === "rgb" ? "painel RGB" : "RM 2D";
    context.fillText(grabbed ? `${panelName} seguro` : `Pinça inferior · mover ${panelName}`, 360, 57);
    context.fillStyle = grabbed ? "rgba(255,255,255,.88)" : XR_SPATIAL_THEME.textMuted;
    context.font = canvasFont(500, 18);
    context.fillText("Solte para fixar no ambiente", 360, 91);
    context.textAlign = "left"; texture.needsUpdate = true;
    return true;
  };
  drawHandle();
  root.add(frame, edges, panelMesh, handle);
  return { root, frame, edges, panelMesh, handle, drawHandle, label: "Painel RM 2D" };
}

function panelAction(intersection, panel) {
  if (!intersection?.uv) return null;
  const x = intersection.uv.x * PANEL_WIDTH;
  const y = (1 - intersection.uv.y) * PANEL_HEIGHT;
  return panel.buttons.find((button) => (
    x >= button.x && x <= button.x + button.width
    && y >= button.y && y <= button.y + button.height
  ))?.action || null;
}

function pinchMidpoint(hand, target = new THREE.Vector3()) {
  const thumb = hand.joints?.["thumb-tip"];
  const index = hand.joints?.["index-finger-tip"];
  if (!thumb?.visible || !index?.visible) return null;
  const a = new THREE.Vector3(); const b = new THREE.Vector3();
  thumb.getWorldPosition(a); index.getWorldPosition(b);
  return target.copy(a).add(b).multiplyScalar(0.5);
}

function directPlaneHit(hand, mesh, depth = DIRECT_TOUCH_DEPTH_M) {
  if (!mesh?.visible) return null;
  const point = pinchMidpoint(hand);
  if (!point) return null;
  mesh.updateMatrixWorld(true);
  const local = mesh.worldToLocal(point.clone());
  const width = Number(mesh.geometry?.parameters?.width || 0);
  const height = Number(mesh.geometry?.parameters?.height || 0);
  if (!(width > 0 && height > 0) || Math.abs(local.z) > depth
      || Math.abs(local.x) > width / 2 || Math.abs(local.y) > height / 2) return null;
  return {
    distance: Math.abs(local.z), object: mesh, point,
    uv: new THREE.Vector2((local.x / width) + 0.5, (local.y / height) + 0.5),
    direct: true,
  };
}

function fingertipPlaneHit(hand, mesh, depth = TABLET_TOUCH_DEPTH_M) {
  if (!mesh?.visible) return null;
  const fingertip = hand.joints?.["index-finger-tip"];
  if (!fingertip?.visible) return null;
  const point = new THREE.Vector3();
  fingertip.getWorldPosition(point);
  mesh.updateMatrixWorld(true);
  const local = mesh.worldToLocal(point.clone());
  const width = Number(mesh.geometry?.parameters?.width || 0);
  const height = Number(mesh.geometry?.parameters?.height || 0);
  if (!(width > 0 && height > 0) || Math.abs(local.z) > depth
      || Math.abs(local.x) > width / 2 || Math.abs(local.y) > height / 2) return null;
  return {
    distance: Math.abs(local.z), object: mesh, point, local,
    uv: new THREE.Vector2((local.x / width) + 0.5, (local.y / height) + 0.5),
    direct: true, fingertip: true,
  };
}

export async function initializeOrenXR(api) {
  const entry = document.getElementById("xr-entry");
  const statusNode = document.getElementById("xr-status");
  const profileSelect = document.getElementById("xr-profile");
  const profileRow = document.getElementById("xr-profile-row");
  const mixedRealityRow = document.getElementById("xr-mixed-reality-row");
  if (!entry || !statusNode) return;
  const questBrowser = /OculusBrowser|Quest/i.test(navigator.userAgent || "");
  const secure = window.isSecureContext;
  const hasWebXR = Boolean(navigator.xr);
  const supportsVr = Boolean(secure && hasWebXR
    && await navigator.xr.isSessionSupported("immersive-vr").catch(() => false));
  const supportsAr = Boolean(secure && hasWebXR
    && await navigator.xr.isSessionSupported("immersive-ar").catch(() => false));
  const supported = supportsVr || supportsAr;
  // No Quest o botão nunca deve sumir silenciosamente. Quando a origem HTTP
  // perdeu a autorização após uma troca de IP, ele continua visível e explica
  // exatamente o gate bloqueado; no desktop incompatível permanece progressivo.
  entry.hidden = !(supported || questBrowser);
  profileRow.hidden = !(supported || questBrowser);
  mixedRealityRow.hidden = !(supportsAr || questBrowser);
  if (supportsAr) document.getElementById("xr-mixed-reality").checked = true;
  statusNode.textContent = supported
    ? "Meta Quest/WebXR disponível. Aguarde o modelo e entre no modo imersivo."
    : questBrowser && !secure
      ? `WebXR bloqueado para ${location.origin}. Autorize este endereço em chrome://flags e reinicie o Quest Browser.`
      : questBrowser
        ? "WebXR não foi liberado pelo Quest Browser. Reinicie o navegador e tente novamente."
        : secure ? "WebXR imersivo não foi detectado neste dispositivo."
          : "WebXR requer contexto seguro. Use o launcher Quest do OREN.";
  if (!supported) {
    if (questBrowser) {
      entry.textContent = "Ativar realidade aumentada";
      entry.addEventListener("click", () => {
        // Preserve o fragmento com o segredo apenas no storage da mesma origem;
        // ele não vira query string nem é enviado ao servidor de ajuda.
        try { sessionStorage.setItem("oren:xr-return-url", location.href); } catch (_error) { /* opcional */ }
        window.location.assign("/quest/setup/");
      });
    }
    return;
  }

  const query = new URLSearchParams(location.search);
  const requestedRole = query.get("xr_role");
  const jobId = query.get("job");
  const token = new URLSearchParams(location.hash.slice(1)).get("xr_token");
  const reportClientEvent = (event, details = {}) => {
    if (!jobId) return;
    fetch(`/api/jobs/${encodeURIComponent(jobId)}/xr-client-event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, mode: "unknown", ...details }),
      keepalive: true,
    }).catch(() => {});
  };
  if (["patient", "clinician"].includes(requestedRole)) profileSelect.value = requestedRole;
  if (token && query.get("job")) {
    const validation = await fetch(`/api/jobs/${encodeURIComponent(query.get("job"))}/xr-session/${encodeURIComponent(token)}`);
    if (!validation.ok) {
      entry.hidden = false;
      entry.textContent = "Gerar novo link para o Quest";
      profileRow.hidden = true;
      mixedRealityRow.hidden = true;
      statusNode.textContent = "A sessão expirou. Gere automaticamente um novo link para este caso.";
      entry.addEventListener("click", () => window.location.replace("/quest/"), { once: true });
      return;
    }
    const sessionInfo = await validation.json();
    profileSelect.value = sessionInfo.role === "patient" ? "patient" : "clinician";
    profileSelect.disabled = true;
  }

  const renderer = api.renderer;
  renderer.xr.enabled = true;
  renderer.xr.setReferenceSpaceType("local-floor");
  const xrRoot = new THREE.Group();
  xrRoot.name = "oren-xr-anatomy-root";
  api.scene.add(xrRoot);
  const panel = createSpatialPanelV2();
  const tablet = createTabletAssembly(panel.mesh);
  const referencePanel = createReferencePanel();
  const referenceTablet = createReferencePanelAssembly(referencePanel.mesh);
  const exitButton = createExitButton();
  tablet.root.visible = false;
  referenceTablet.root.visible = false;
  exitButton.mesh.visible = false;
  api.scene.add(tablet.root, referenceTablet.root, exitButton.mesh);
  const raycaster = new THREE.Raycaster();
  raycaster.far = HAND_RAY_LENGTH;
  const controllers = [];
  const hands = [];
  const activeGrabs = new Map();
  const frameTimes = [];
  let interactiveMeshes = [];
  let lastFrame = 0;
  let frameCounter = 0;
  let performanceTier = "quality";
  let performanceStressWindows = 0;
  let realismFallbackActive = false;
  let session = null;
  let twoHandStart = null;
  let tabletGrab = null;
  let organOpacityIndex = 0;
  let selectedOpacityIndex = 0;
  let structureCursor = -1;
  let cutPosition = 50;
  let cutAxisIndex = 2;
  let cutInverted = false;
  let activePage = "model";
  let lastSavedViewId = null;
  let savedXrPose = null;
  let exitHold = null;
  let exitToWebappRequested = false;
  let hoveredAction = null;
  let lastPanelMessage = "Aponte e faça uma pinça";
  let lastPanelActive = null;
  let profile = profileSelect.value === "patient" ? "patient" : "clinician";
  let originalModelState = null;
  let lastSceneIntegrityAt = 0;
  let viewerReadinessTimer = null;
  let lastReferenceKey = "";
  let rgbCatalog = null;
  let rgbPanelIndex = 0;
  let entryCalibration = null;
  let entryWarmupUntil = 0;
  const poseStorageKey = `oren:xr-pose:${query.get("job") || "local"}`;
  const anatomyDefaultPosition = new THREE.Vector3(0, 1.24, -0.68);
  const anatomyDefaultQuaternion = new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0));
  const tabletDefaultPosition = tablet.root.position.clone();
  const tabletDefaultQuaternion = tablet.root.quaternion.clone();
  const referenceDefaultPosition = referenceTablet.root.position.clone();
  const referenceDefaultQuaternion = referenceTablet.root.quaternion.clone();

  function activePanelActions() {
    const result = [];
    if (api.getMeasurementEnabled()) result.push("measure");
    if (api.getWireframeEnabled()) result.push("wireframe");
    if (panel.mesh.userData.cutEnabled) result.push("cut");
    if (api.getReferenceState?.().sync_enabled) result.push("reference_sync");
    if (api.getRenderingProfile?.() === "anatomic_realistic_v1") result.push("render_realism");
    const review = api.getReviewState?.();
    if (review?.checklist?.inspected_3d_contour) result.push("review_3d");
    if (review?.checklist?.compared_2d_reference) result.push("review_2d");
    if (review?.checklist?.reviewed_candidate_against_mr) result.push("review_candidate");
    if (review?.checklist?.acknowledged_research_only) result.push("review_research");
    return result;
  }

  const drawPanel = () => {
    const selectedRole = api.getSelectedRole?.() || null;
    panel.draw({
      profile, status: lastPanelMessage, active: lastPanelActive, page: activePage,
      activeActions: activePanelActions(), hovered: hoveredAction,
      performanceTier,
      selection: selectedRole ? {
        role: selectedRole,
        label: api.getStructureLabel?.(selectedRole) || selectedRole,
        category: api.getStructureCategory?.(selectedRole) || "estrutura",
        visible: api.isStructureVisible?.(selectedRole) !== false,
      } : null,
    });
  };

  const updatePanel = (message, active = null) => {
    lastPanelMessage = message;
    lastPanelActive = active;
    drawPanel();
    statusNode.textContent = message;
    referenceTablet.root.visible = Boolean(session && !entryCalibration && ["reference", "rgb"].includes(activePage));
  };

  function refreshHoverVisuals() {
    const nextAction = hands.map((hand) => hand.userData.hoverAction).find(Boolean) || null;
    if (nextAction !== hoveredAction) {
      hoveredAction = nextAction;
      drawPanel();
    }
    const exitHovered = nextAction === "exit_to_webapp";
    if (!exitHold) exitButton.draw({ hovered: exitHovered });
    tablet.drawHandle({
      hovered: nextAction === "tablet_handle",
      grabbed: Boolean(tabletGrab?.assembly === tablet),
    });
    referenceTablet.drawHandle({
      hovered: nextAction === "reference_handle",
      grabbed: Boolean(tabletGrab?.assembly === referenceTablet),
      mode: activePage === "rgb" ? "rgb" : "reference",
    });
  }

  function requestExitToWebapp() {
    exitToWebappRequested = true;
    exitHold = null;
    exitButton.draw({ closing: true, progress: 1 });
    updatePanel("Encerrando a realidade aumentada e voltando ao webapp…", "exit");
    if (session) session.end().catch(() => window.location.replace("/"));
    else window.location.replace("/");
  }

  function beginExitHold(source, isHand) {
    if (!isHand) { requestExitToWebapp(); return; }
    exitHold = { source, startedAt: performance.now() };
    exitButton.draw({ hovered: true, progress: 0.02 });
    updatePanel("Mantenha a pinça por um instante para voltar ao webapp.", "exit");
  }

  function cancelExitHold(source) {
    if (!exitHold || (source && exitHold.source !== source)) return;
    exitHold = null;
    exitButton.draw({ hovered: hoveredAction === "exit_to_webapp" });
    updatePanel("Saída cancelada. Continue a exploração normalmente.");
  }

  function updateExitHold(time) {
    if (!exitHold) return;
    if (!exitHold.source.userData.precisionPinch?.pinching) { cancelExitHold(exitHold.source); return; }
    const progress = (time - exitHold.startedAt) / EXIT_HOLD_MS;
    exitButton.draw({ hovered: true, progress });
    if (progress >= 1) requestExitToWebapp();
  }

  function persistPose() {
    try {
      localStorage.setItem(poseStorageKey, JSON.stringify({
        schema: "oren-xr-pose-v1",
        position: xrRoot.position.toArray(), quaternion: xrRoot.quaternion.toArray(), scale: xrRoot.scale.x,
      }));
    } catch (_error) { /* persistência local opcional */ }
  }

  function restorePose() {
    try {
      const saved = JSON.parse(localStorage.getItem(poseStorageKey) || "null");
      const scale = Number(saved?.scale);
      if (saved?.schema !== "oren-xr-pose-v1" || !Array.isArray(saved.position)
          || !Array.isArray(saved.quaternion) || !Number.isFinite(scale)
          || scale < 0.00045 || scale > 0.0024) return false;
      xrRoot.position.fromArray(saved.position);
      xrRoot.quaternion.fromArray(saved.quaternion).normalize();
      xrRoot.scale.setScalar(scale);
      return true;
    } catch (_error) { return false; }
  }

  function applyHeadRelativeLayout(headPosition, headForward) {
    const forward = headForward.clone();
    forward.y = 0;
    if (forward.lengthSq() < 1e-6) forward.set(0, 0, -1);
    forward.normalize();
    const up = new THREE.Vector3(0, 1, 0);
    const right = new THREE.Vector3().crossVectors(forward, up).normalize();
    const yaw = Math.atan2(-forward.x, -forward.z);
    const yawQuaternion = new THREE.Quaternion().setFromAxisAngle(up, yaw);
    const anatomicalQuaternion = new THREE.Quaternion()
      .setFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0));

    anatomyDefaultPosition.copy(headPosition).addScaledVector(forward, 0.72);
    anatomyDefaultPosition.y = headPosition.y - 0.18;
    anatomyDefaultQuaternion.copy(yawQuaternion).multiply(anatomicalQuaternion);

    tablet.root.position.copy(headPosition)
      .addScaledVector(forward, 0.70).addScaledVector(right, -0.50);
    tablet.root.position.y = headPosition.y - 0.16;
    tablet.root.lookAt(headPosition.x, tablet.root.position.y, headPosition.z);
    tabletDefaultPosition.copy(tablet.root.position);
    tabletDefaultQuaternion.copy(tablet.root.quaternion);

    referenceTablet.root.position.copy(headPosition)
      .addScaledVector(forward, 0.70).addScaledVector(right, 0.48);
    referenceTablet.root.position.y = headPosition.y - 0.16;
    referenceTablet.root.lookAt(headPosition.x, referenceTablet.root.position.y, headPosition.z);
    referenceDefaultPosition.copy(referenceTablet.root.position);
    referenceDefaultQuaternion.copy(referenceTablet.root.quaternion);

    exitButton.mesh.position.copy(headPosition).addScaledVector(forward, 0.62);
    exitButton.mesh.position.y = headPosition.y + 0.25;
    exitButton.mesh.lookAt(headPosition.x, exitButton.mesh.position.y, headPosition.z);
  }

  function beginEntryCalibration(time = performance.now()) {
    entryCalibration = {
      frames: 0, startedAt: time, position: new THREE.Vector3(),
      forward: new THREE.Vector3(), samplePosition: new THREE.Vector3(),
      sampleQuaternion: new THREE.Quaternion(), sampleForward: new THREE.Vector3(),
    };
    xrRoot.visible = false;
    tablet.root.visible = false;
    referenceTablet.root.visible = false;
    exitButton.mesh.visible = false;
    statusNode.textContent = "Calibrando o campo de visão do headset…";
  }

  function updateEntryCalibration(time) {
    if (!entryCalibration) return true;
    const xrCamera = renderer.xr.getCamera(api.camera);
    xrCamera.getWorldPosition(entryCalibration.samplePosition);
    xrCamera.getWorldQuaternion(entryCalibration.sampleQuaternion);
    entryCalibration.sampleForward.set(0, 0, -1)
      .applyQuaternion(entryCalibration.sampleQuaternion);
    entryCalibration.sampleForward.y = 0;
    const poseValid = Number.isFinite(entryCalibration.samplePosition.x)
      && Number.isFinite(entryCalibration.samplePosition.y)
      && entryCalibration.samplePosition.y >= 0.45
      && entryCalibration.samplePosition.y <= 2.6
      && entryCalibration.sampleForward.lengthSq() >= 1e-6;
    if (!poseValid) {
      if (time - entryCalibration.startedAt < XR_ENTRY_CALIBRATION_TIMEOUT_MS) return false;
      entryCalibration.samplePosition.set(0, 1.55, 0);
      entryCalibration.sampleForward.set(0, 0, -1);
      entryCalibration.frames = Math.max(entryCalibration.frames, XR_ENTRY_CALIBRATION_FRAMES - 1);
    }
    entryCalibration.sampleForward.normalize();
    if (entryCalibration.frames === 0) {
      entryCalibration.position.copy(entryCalibration.samplePosition);
      entryCalibration.forward.copy(entryCalibration.sampleForward);
    } else {
      entryCalibration.position.lerp(entryCalibration.samplePosition, 0.34);
      entryCalibration.forward.lerp(entryCalibration.sampleForward, 0.34).normalize();
    }
    entryCalibration.frames += 1;
    if (entryCalibration.frames < XR_ENTRY_CALIBRATION_FRAMES) return false;

    applyHeadRelativeLayout(entryCalibration.position, entryCalibration.forward);
    xrRoot.position.copy(anatomyDefaultPosition);
    xrRoot.quaternion.copy(anatomyDefaultQuaternion);
    xrRoot.scale.setScalar(0.001);
    tablet.root.position.copy(tabletDefaultPosition);
    tablet.root.quaternion.copy(tabletDefaultQuaternion);
    tablet.root.scale.setScalar(1);
    referenceTablet.root.position.copy(referenceDefaultPosition);
    referenceTablet.root.quaternion.copy(referenceDefaultQuaternion);
    referenceTablet.root.scale.setScalar(1);
    entryCalibration = null;
    entryWarmupUntil = time + XR_ENTRY_WARMUP_MS;
    performanceTier = "stability";
    renderer.xr.setFoveation?.(0.9);
    frameTimes.length = 0; frameCounter = 0; lastFrame = 0;
    xrRoot.visible = true;
    tablet.root.visible = true;
    referenceTablet.root.visible = ["reference", "rgb"].includes(activePage);
    exitButton.mesh.visible = true;
    exitButton.draw();
    const handCount = [...(session?.inputSources || [])].filter((source) => source.hand).length;
    updatePanel(`Campo de visão calibrado${handCount ? ` · ${handCount === 2 ? "duas mãos detectadas" : "uma mão detectada"}` : ""}.`);
    return true;
  }

  function resetAnatomy() {
    xrRoot.position.copy(anatomyDefaultPosition);
    xrRoot.quaternion.copy(anatomyDefaultQuaternion);
    xrRoot.scale.setScalar(0.001);
    updatePanel("Fígado recentrado em escala anatômica.", "reset");
  }

  function resetTablet() {
    if (tabletGrab?.assembly === tablet) tabletGrab = null;
    tablet.root.position.copy(tabletDefaultPosition);
    tablet.root.quaternion.copy(tabletDefaultQuaternion);
    tablet.root.scale.setScalar(1);
    tablet.drawHandle();
    updatePanel("Tablet recentrado no campo de visão.", "tablet_reset");
  }

  function resetReferenceTablet() {
    if (tabletGrab?.assembly === referenceTablet) tabletGrab = null;
    referenceTablet.root.position.copy(referenceDefaultPosition);
    referenceTablet.root.quaternion.copy(referenceDefaultQuaternion);
    referenceTablet.root.scale.setScalar(1);
    referenceTablet.drawHandle();
    updatePanel("Painel RM 2D recentrado.", "reference_reset");
  }

  function setXrView(name) {
    const rotations = {
      default: new THREE.Euler(-Math.PI / 2, 0, -0.42),
      anterior: new THREE.Euler(-Math.PI / 2, 0, 0),
      superior: new THREE.Euler(0, 0, 0),
      right: new THREE.Euler(-Math.PI / 2, 0, Math.PI / 2),
    };
    xrRoot.quaternion.setFromEuler(rotations[name] || rotations.default);
    updatePanel(`Vista ${name} aplicada.`, `view_${name}`);
  }

  function selectedStructureMessage(prefix = "Estrutura") {
    const role = api.getSelectedRole();
    return role ? `${prefix}: ${api.getStructureLabel(role)}.` : "Selecione primeiro uma estrutura.";
  }

  function focusXrRoles(roles) {
    const visible = roles.map((role) => api.meshes[role]).filter((mesh) => mesh?.visible);
    if (!visible.length) return false;
    api.scene.updateMatrixWorld(true);
    const bounds = new THREE.Box3();
    visible.forEach((mesh) => bounds.expandByObject(mesh));
    if (bounds.isEmpty()) return false;
    const center = bounds.getCenter(new THREE.Vector3());
    xrRoot.position.add(new THREE.Vector3(0, 1.24, -0.68).sub(center));
    return true;
  }

  function refreshReferencePanel() {
    const state = api.getReferenceState?.() || {};
    const key = `${state.view}:${state.frame_index}:${state.image_src}`;
    if (key === lastReferenceKey) return;
    lastReferenceKey = key;
    const image = document.getElementById("reference-image");
    if (image && !image.complete) image.addEventListener("load", () => referencePanel.draw(api.getReferenceState()), { once: true });
    referencePanel.draw(state);
  }

  async function refreshRgbPanel(delta = 0, first = false) {
    try {
      rgbCatalog ||= await api.getRgbPanelCatalog?.();
      const panels = rgbCatalog?.panels || [];
      if (!panels.length) {
        referencePanel.draw({ mode: "rgb", metadata: "Nenhum painel RGB disponível neste caso." });
        updatePanel("Este caso não possui painéis RGB publicados.");
        return false;
      }
      rgbPanelIndex = first ? 0 : (rgbPanelIndex + delta + panels.length) % panels.length;
      const selected = panels[rgbPanelIndex];
      referencePanel.draw({
        mode: "rgb",
        image_src: selected.url,
        metadata: `Painel ${rgbPanelIndex + 1}/${panels.length} · ${selected.filename}`,
      });
      updatePanel(`Painel RGB ${rgbPanelIndex + 1}/${panels.length}.`);
      return true;
    } catch (error) {
      referencePanel.draw({ mode: "rgb", metadata: "Falha ao carregar o catálogo RGB." });
      updatePanel(`Painéis RGB indisponíveis: ${error.message}`);
      return false;
    }
  }

  async function performAction(action) {
    if (!action) return;
    if (action.startsWith("page_")) {
      const requested = action.slice(5);
      if (PANEL_PAGES[requested] && (!PANEL_PAGES[requested].clinicianOnly || profile === "clinician")) activePage = requested;
      referenceTablet.label = activePage === "rgb" ? "Painel RGB" : "Painel RM 2D";
      referenceTablet.drawHandle({ mode: activePage === "rgb" ? "rgb" : "reference" });
      refreshReferencePanel();
      if (activePage === "rgb") refreshRgbPanel();
      updatePanel(`Aba ${PANEL_PAGES[activePage].label} aberta.`, action);
      return;
    }
    if (["default", "anatomy", "triage", "segments"].includes(action)) {
      api.applyPreset(action);
      updatePanel(`Composição ${action} aplicada.`, action);
    } else if (action === "opacity") {
      const values = [1, 0.7, 0.4, 0.2];
      organOpacityIndex = (organOpacityIndex + 1) % values.length;
      api.setStructureOpacity("orgao", values[organOpacityIndex]);
      updatePanel(`Opacidade do fígado: ${Math.round(values[organOpacityIndex] * 100)}%.`, action);
    } else if (action === "volume") {
      const volume = api.getManifest()?.volumetry?.whole_liver_summary?.volume_ml;
      updatePanel(Number.isFinite(Number(volume)) ? `Volume hepático: ${Number(volume).toFixed(1)} mL.` : "Volumetria indisponível.", action);
    } else if (action === "render_realism") {
      const enabled = api.getRenderingProfile?.() !== "anatomic_realistic_v1";
      if (enabled) realismFallbackActive = false;
      updatePanel(enabled ? "Carregando textura anatômica…" : "Restaurando representação atual…", action);
      const applied = await api.setRenderingProfile?.(
        enabled ? "anatomic_realistic_v1" : "scientific_current_v1",
      );
      updatePanel(
        applied
          ? (enabled ? "Representação anatômica realista ativada." : "Representação atual restaurada.")
          : "Não foi possível trocar o acabamento anatômico.",
        action,
      );
    } else if (action === "reset") resetAnatomy();
    else if (action === "tablet_reset") resetTablet();
    else if (action === "exit") requestExitToWebapp();
    else if (action.startsWith("view_")) setXrView(action.slice(5));
    else if (action.startsWith("anatomical_")) {
      const name = action.slice(11);
      const applied = api.applyAnatomicalView(name);
      const categories = { liver: ["organ"], segments: ["segment"], vascular: ["vessel"], candidate: ["candidate", "lesion"] }[name] || [];
      const focused = focusXrRoles(api.getStructureRoles().filter((role) => categories.includes(api.getStructureCategory(role))));
      updatePanel(applied && focused ? `Camada ${name} destacada e centralizada.` : `Camada ${name} indisponível.`, action);
    } else if (action === "save_view") {
      if (api.saveCurrentView()) {
        const views = api.getSavedViews?.() || [];
        lastSavedViewId = views.at(-1)?.bookmark_id || null;
        savedXrPose = {
          position: xrRoot.position.clone(), quaternion: xrRoot.quaternion.clone(), scale: xrRoot.scale.x,
        };
        updatePanel("Vista atual salva.", action);
      } else updatePanel("Não foi possível salvar a vista.", action);
    } else if (action === "restore_view") {
      const restored = lastSavedViewId && savedXrPose && api.restoreSavedView(lastSavedViewId);
      if (restored) {
        xrRoot.position.copy(savedXrPose.position);
        xrRoot.quaternion.copy(savedXrPose.quaternion);
        xrRoot.scale.setScalar(savedXrPose.scale);
      }
      updatePanel(restored ? "Última vista XR restaurada." : "Nenhuma vista XR salva.", action);
    } else if (action === "measure") {
      api.setMeasurementEnabled(!api.getMeasurementEnabled());
      updatePanel(api.getMeasurementEnabled() ? "Medição ativa: pinça em dois pontos." : "Medição desativada.", action);
    } else if (action === "clear_measure") {
      api.clearMeasurements(); updatePanel("Medições removidas.", action);
    } else if (action === "dimensions") {
      updatePanel(api.measureSelectedStructure3d() ? selectedStructureMessage("Dimensões calculadas para") : "Selecione uma estrutura visível.", action);
    } else if (action === "wireframe") {
      const enabled = api.setWireframeEnabled(!api.getWireframeEnabled());
      const status = api.getWireframeStatus?.();
      updatePanel(enabled
        ? `Malha técnica otimizada: ${api.getStructureLabel(status?.role) || "estrutura visível"}.`
        : (status?.reason || "Malha técnica desativada."), action);
    } else if (action === "cut") {
      panel.mesh.userData.cutEnabled = !panel.mesh.userData.cutEnabled;
      api.setClippingState({ enabled: panel.mesh.userData.cutEnabled, axis: ["x", "y", "z"][cutAxisIndex], position_percent: cutPosition, inverted: cutInverted });
      updatePanel(panel.mesh.userData.cutEnabled ? "Plano de corte ativado." : "Plano de corte desativado.", action);
    } else if (action === "cut_position") {
      cutPosition = cutPosition >= 80 ? 20 : cutPosition + 20;
      panel.mesh.userData.cutEnabled = true;
      api.setClippingState({ enabled: true, axis: ["x", "y", "z"][cutAxisIndex], position_percent: cutPosition, inverted: cutInverted });
      updatePanel(`Plano de corte em ${cutPosition}%.`, action);
    } else if (action === "cut_axis") {
      cutAxisIndex = (cutAxisIndex + 1) % 3;
      api.setClippingState({ enabled: true, axis: ["x", "y", "z"][cutAxisIndex], position_percent: cutPosition, inverted: cutInverted });
      panel.mesh.userData.cutEnabled = true;
      updatePanel(`Eixo de corte: ${["LR", "AP", "SI"][cutAxisIndex]}.`, action);
    } else if (action === "cut_invert") {
      cutInverted = !cutInverted;
      api.setClippingState({ enabled: true, axis: ["x", "y", "z"][cutAxisIndex], position_percent: cutPosition, inverted: cutInverted });
      panel.mesh.userData.cutEnabled = true;
      updatePanel(`Corte ${cutInverted ? "invertido" : "normal"}.`, action);
    } else if (action === "structure_next") {
      const roles = api.getStructureRoles();
      if (!roles.length) updatePanel("Nenhuma estrutura disponível.", action);
      else {
        const currentIndex = roles.indexOf(api.getSelectedRole());
        structureCursor = ((currentIndex >= 0 ? currentIndex : structureCursor) + 1) % roles.length;
        const role = roles[structureCursor];
        api.selectStructure(role, { allowHidden: true, alignReference: false });
        updatePanel(`${selectedStructureMessage("Selecionada")}${api.isStructureVisible(role) ? "" : " · oculta"}.`, action);
      }
    } else if (action === "structure_focus") {
      const role = api.getSelectedRole();
      if (role && !api.isStructureVisible(role)) api.setStructureVisibility(role, true);
      updatePanel(role && focusXrRoles([role]) ? selectedStructureMessage("Enquadrada no XR") : "Selecione uma estrutura.", action);
    } else if (action === "structure_isolate") {
      updatePanel(api.isolateSelectedStructure() ? selectedStructureMessage("Isolada") : "Selecione uma estrutura.", action);
    } else if (action === "structure_restore") {
      updatePanel(api.restoreSelectedContext() ? "Contexto anatômico restaurado." : "Não há contexto isolado.", action);
    } else if (action === "structure_visibility") {
      const role = api.getSelectedRole();
      updatePanel(role && api.setStructureVisibility(role, !api.meshes[role].visible) ? selectedStructureMessage("Visibilidade alterada") : "Selecione uma estrutura.", action);
    } else if (action === "structure_opacity") {
      const role = api.getSelectedRole();
      const values = [1, 0.7, 0.4, 0.2];
      selectedOpacityIndex = (selectedOpacityIndex + 1) % values.length;
      updatePanel(role && api.setStructureOpacity(role, values[selectedOpacityIndex])
        ? `${api.getStructureLabel(role)}: ${Math.round(values[selectedOpacityIndex] * 100)}%.` : "Selecione uma estrutura.", action);
    } else if (action.startsWith("rgb_")) {
      if (action === "rgb_reset") resetReferenceTablet();
      else if (action === "rgb_first") refreshRgbPanel(0, true);
      else refreshRgbPanel(action === "rgb_previous" ? -1 : 1);
    } else if (action.startsWith("reference_")) {
      if (action === "reference_reset") {
        resetReferenceTablet();
        return;
      } else if (["reference_axial", "reference_coronal", "reference_sagittal"].includes(action)) {
        api.setReferenceViewForXR(action.slice(10));
      } else if (action === "reference_previous") api.stepReferenceFrame(-1);
      else if (action === "reference_next") api.stepReferenceFrame(1);
      else if (action === "reference_sync") api.setReferenceSyncEnabled(!api.getReferenceState().sync_enabled);
      refreshReferencePanel();
      const state = api.getReferenceState();
      updatePanel(state.available ? `${state.view} · plano ${state.frame_index + 1}/${state.frame_count}.` : "Referência 2D indisponível.", action);
    } else if (action.startsWith("review_")) {
      const map = {
        review_3d: "inspected_3d_contour", review_2d: "compared_2d_reference",
        review_candidate: "reviewed_candidate_against_mr", review_research: "acknowledged_research_only",
      };
      if (map[action]) {
        const state = api.getReviewState();
        const checked = !state.checklist[map[action]];
        const changed = api.setReviewChecklistItem(map[action], checked);
        updatePanel(changed === false && checked ? "Item indisponível neste exame." : `Checklist ${checked ? "marcado" : "desmarcado"}.`, action);
      } else if (action === "review_approve") {
        api.submitApproval("approved").then(() => updatePanel(api.getReviewState().status, action));
      } else if (action === "review_revision") {
        api.submitApproval("revision_requested").then(() => updatePanel(api.getReviewState().status, action));
      }
    } else if (action === "candidate_decision") {
      const state = api.getReviewState();
      const values = ["accepted_as_region_of_interest", "rejected", "needs_correction"];
      const next = values[(values.indexOf(state.candidate_review_decision) + 1) % values.length];
      updatePanel(api.setCandidateReviewDecision(next) ? `Decisão: ${next.replaceAll("_", " ")}.` : "Candidato indisponível.", action);
    }
  }

  function startTabletGrab(source, hand = null, assembly = tablet) {
    if (!source?.visible || tabletGrab) return false;
    stopGrab(source);
    source.updateMatrixWorld(true);
    assembly.root.updateMatrixWorld(true);
    const sourcePosition = new THREE.Vector3();
    const sourceQuaternion = new THREE.Quaternion();
    source.getWorldPosition(sourcePosition);
    source.getWorldQuaternion(sourceQuaternion);
    const rootPosition = new THREE.Vector3();
    const rootQuaternion = new THREE.Quaternion();
    assembly.root.getWorldPosition(rootPosition);
    assembly.root.getWorldQuaternion(rootQuaternion);
    const inverseSource = sourceQuaternion.clone().invert();
    tabletGrab = {
      source, hand, assembly,
      positionOffset: rootPosition.clone().sub(sourcePosition).applyQuaternion(inverseSource),
      rotationOffset: inverseSource.multiply(rootQuaternion),
    };
    tablet.touchCursor.visible = false;
    assembly.drawHandle({ grabbed: true, mode: activePage === "rgb" ? "rgb" : "reference" });
    updatePanel(`${assembly.label || "Tablet"} seguro. Mova e gire a mão; solte a pinça para posicionar.`,
      assembly === tablet ? "tablet_handle" : "reference_handle");
    return true;
  }

  function stopTabletGrab(source = null) {
    if (!tabletGrab || (source && tabletGrab.source !== source)) return false;
    const assembly = tabletGrab.assembly;
    tabletGrab = null;
    assembly.drawHandle({
      hovered: hoveredAction === (assembly === tablet ? "tablet_handle" : "reference_handle"),
      mode: activePage === "rgb" ? "rgb" : "reference",
    });
    updatePanel(`${assembly.label || "Tablet"} posicionado.`);
    return true;
  }

  function updateTabletGrab() {
    if (!tabletGrab?.source?.visible) return;
    tabletGrab.source.updateMatrixWorld(true);
    const sourcePosition = new THREE.Vector3();
    const sourceQuaternion = new THREE.Quaternion();
    tabletGrab.source.getWorldPosition(sourcePosition);
    tabletGrab.source.getWorldQuaternion(sourceQuaternion);
    const targetPosition = tabletGrab.positionOffset.clone().applyQuaternion(sourceQuaternion).add(sourcePosition);
    const targetQuaternion = sourceQuaternion.clone().multiply(tabletGrab.rotationOffset);
    tabletGrab.assembly.root.position.lerp(targetPosition, TABLET_GRAB_FOLLOW);
    tabletGrab.assembly.root.quaternion.slerp(targetQuaternion, TABLET_GRAB_FOLLOW);
  }

  function resetTabletTouch(hand) {
    hand.userData.tabletTouch = null;
    if (!hands.some((candidate) => candidate !== hand && candidate.userData.tabletTouch?.action)) {
      tablet.touchCursor.visible = false;
    }
  }

  function updateTabletTouch(hand, time) {
    if (tabletGrab || hand.userData.precisionPinch?.pinching) {
      resetTabletTouch(hand);
      return;
    }
    const hit = fingertipPlaneHit(hand, panel.mesh);
    const action = panelAction(hit, panel);
    if (!hit || !action) {
      resetTabletTouch(hand);
      return;
    }
    tablet.touchCursor.position.set(hit.local.x, hit.local.y, 0.008);
    tablet.touchCursor.visible = true;
    const state = hand.userData.tabletTouch;
    if (!state || state.action !== action) {
      hand.userData.tabletTouch = { action, since: time, committed: false };
      hand.userData.hoverAction = action;
      hand.userData.hoverSince = time;
      refreshHoverVisuals();
      return;
    }
    if (!state.committed && time - state.since >= TABLET_TOUCH_COMMIT_MS) {
      state.committed = true;
      performAction(action);
      haptic(hand.userData.inputSource, 0.22, 28);
    }
  }

  function intersections(source, hand = false, rayReady = false) {
    const directExitHit = hand ? directPlaneHit(source, exitButton.mesh, 0.055) : null;
    const directTabletHandleHit = hand ? directPlaneHit(source, tablet.handle, 0.055) : null;
    const directReferenceHandleHit = hand && referenceTablet.root.visible
      ? directPlaneHit(source, referenceTablet.handle, 0.055) : null;
    const directPanelHit = hand ? directPlaneHit(source, panel.mesh) : null;
    if (directExitHit) return { exitHit: directExitHit, tabletHandleHit: null, panelHit: null, modelHits: [] };
    if (directTabletHandleHit) return { exitHit: null, tabletHandleHit: directTabletHandleHit, panelHit: null, modelHits: [] };
    if (directReferenceHandleHit) return {
      exitHit: null, tabletHandleHit: null, referenceHandleHit: directReferenceHandleHit,
      panelHit: null, modelHits: [],
    };
    if (directPanelHit) return { exitHit: null, tabletHandleHit: null, panelHit: directPanelHit, modelHits: [] };
    const valid = rayReady || (hand ? handRay(source, raycaster) : controllerRay(source, raycaster));
    if (!valid) return {
      exitHit: null, tabletHandleHit: null, referenceHandleHit: null, panelHit: null, modelHits: [],
    };
    const exitHit = exitButton.mesh.visible ? raycaster.intersectObject(exitButton.mesh, false)[0] : null;
    if (exitHit) return { exitHit, tabletHandleHit: null, panelHit: null, modelHits: [] };
    const tabletHandleHit = tablet.handle.visible ? raycaster.intersectObject(tablet.handle, false)[0] : null;
    if (tabletHandleHit) return { exitHit: null, tabletHandleHit, panelHit: null, modelHits: [] };
    const referenceHandleHit = referenceTablet.root.visible
      ? raycaster.intersectObject(referenceTablet.handle, false)[0] : null;
    if (referenceHandleHit) return {
      exitHit: null, tabletHandleHit: null, referenceHandleHit, panelHit: null, modelHits: [],
    };
    const panelHit = panel.mesh.visible ? raycaster.intersectObject(panel.mesh, false)[0] : null;
    if (panelHit) return { exitHit: null, tabletHandleHit: null, panelHit, modelHits: [] };
    const modelHits = raycaster.intersectObjects(interactiveMeshes, false)
      .filter((hit) => hit.object.visible && Number(hit.object.material?.opacity ?? 1) > 0.02);
    return { exitHit: null, tabletHandleHit: null, panelHit: null, modelHits };
  }

  function startGrab(source) {
    source.updateMatrixWorld(true);
    const position = new THREE.Vector3(); const quaternion = new THREE.Quaternion();
    source.getWorldPosition(position); source.getWorldQuaternion(quaternion);
    activeGrabs.set(source, {
      startPosition: position, startQuaternion: quaternion,
      rootPosition: xrRoot.position.clone(), rootQuaternion: xrRoot.quaternion.clone(), rootScale: xrRoot.scale.x,
    });
    if (activeGrabs.size === 2) {
      const pair = [...activeGrabs.keys()].slice(0, 2);
      const left = new THREE.Vector3(); const right = new THREE.Vector3();
      pair[0].getWorldPosition(left); pair[1].getWorldPosition(right);
      twoHandStart = {
        pair, midpoint: left.clone().add(right).multiplyScalar(0.5), vector: right.clone().sub(left),
        rootPosition: xrRoot.position.clone(), rootQuaternion: xrRoot.quaternion.clone(), rootScale: xrRoot.scale.x,
      };
    }
  }

  function stopGrab(source) {
    activeGrabs.delete(source);
    twoHandStart = null;
    if (activeGrabs.size === 1) {
      const remaining = [...activeGrabs.keys()][0];
      activeGrabs.delete(remaining); startGrab(remaining);
    }
  }

  function updateGrab() {
    if (activeGrabs.size >= 2 && twoHandStart) {
      const [first, second] = twoHandStart.pair;
      const a = new THREE.Vector3(); const b = new THREE.Vector3();
      first.getWorldPosition(a); second.getWorldPosition(b);
      const midpoint = a.clone().add(b).multiplyScalar(0.5);
      const vector = b.clone().sub(a);
      const ratio = THREE.MathUtils.clamp(vector.length() / Math.max(twoHandStart.vector.length(), 1e-5), 0.45, 2.4);
      const rotation = new THREE.Quaternion().setFromUnitVectors(twoHandStart.vector.clone().normalize(), vector.clone().normalize());
      const targetPosition = twoHandStart.rootPosition.clone().add(midpoint.sub(twoHandStart.midpoint));
      const targetQuaternion = rotation.multiply(twoHandStart.rootQuaternion);
      const targetScale = THREE.MathUtils.clamp(twoHandStart.rootScale * ratio, 0.00045, 0.0024);
      xrRoot.position.lerp(targetPosition, GRAB_FOLLOW);
      xrRoot.quaternion.slerp(targetQuaternion, GRAB_FOLLOW);
      xrRoot.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), GRAB_FOLLOW);
      return;
    }
    if (activeGrabs.size !== 1) return;
    const [source, grab] = [...activeGrabs.entries()][0];
    const position = new THREE.Vector3(); const quaternion = new THREE.Quaternion();
    source.getWorldPosition(position); source.getWorldQuaternion(quaternion);
    const rotation = quaternion.clone().multiply(grab.startQuaternion.clone().invert());
    const targetPosition = grab.rootPosition.clone().add(position.sub(grab.startPosition));
    const targetQuaternion = rotation.multiply(grab.rootQuaternion);
    xrRoot.position.lerp(targetPosition, GRAB_FOLLOW);
    xrRoot.quaternion.slerp(targetQuaternion, GRAB_FOLLOW);
  }

  function activateIntersection(source, inputSource, isHand) {
    if (isHand) {
      const now = performance.now();
      if (now - Number(source.userData.lastPinchAt || 0) < PINCH_DEBOUNCE_MS) return;
      source.userData.lastPinchAt = now;
    }
    const { exitHit, tabletHandleHit, referenceHandleHit, panelHit, modelHits } = intersections(source, isHand);
    if (exitHit) {
      beginExitHold(source, isHand);
      haptic(inputSource, 0.45, 55);
      return;
    }
    if (tabletHandleHit && isHand) {
      startTabletGrab(source.userData.grabSource, source, tablet);
      haptic(inputSource, 0.38, 45);
      return;
    }
    if (referenceHandleHit && isHand) {
      startTabletGrab(source.userData.grabSource, source, referenceTablet);
      haptic(inputSource, 0.38, 45);
      return;
    }
    if (panelHit) {
      performAction(panelAction(panelHit, panel)); haptic(inputSource); return;
    }
    if (!modelHits.length) return;
    const hit = modelHits.find((candidate) => (
      api.isWorldPointVisibleByClipping?.(candidate.point) !== false
    ));
    if (!hit) {
      updatePanel("Aponte para uma superfície visível do corte.", "measure");
      return;
    }
    api.selectStructure(hit.object.userData.role);
    if (api.getMeasurementEnabled()) {
      const modelPoint = api.worldPointToModelPoint?.(hit.point);
      if (modelPoint) {
        api.handleMeasurementPoint(modelPoint);
        updatePanel("Ponto de medição registrado em coordenadas LPS.", "measure");
      }
    } else if (isHand) {
      startGrab(source.userData.grabSource || source);
      updatePanel("Fígado seguro pela pinça. Use duas mãos para escala e rotação.");
    } else updatePanel(`${hit.object.userData.role} selecionado.`);
    haptic(inputSource);
  }

  function onSelectStart(event) {
    if (event.data?.hand) return;
    activateIntersection(event.target, event.data, false);
  }

  const handJointGeometry = new THREE.SphereGeometry(1, 8, 6);
  function ensureHandVisual(hand, index) {
    if (hand.userData.visual?.jointInstances) return;
    const jointNames = Object.keys(hand.joints || {});
    if (!jointNames.length) return;
    const color = index === 0 ? 0x65e8ff : 0x79f2b2;
    const material = hand.userData.jointMaterial || new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.68, depthTest: true });
    hand.userData.jointMaterial = material;
    const jointInstances = new THREE.InstancedMesh(handJointGeometry, material, jointNames.length);
    jointInstances.name = `oren-hand-joints-instanced-${index}`;
    jointInstances.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    jointInstances.renderOrder = 110;
    jointInstances.frustumCulled = false;
    jointInstances.visible = false;
    api.scene.add(jointInstances);
    hand.userData.visual.jointInstances = jointInstances;
    hand.userData.visual.jointNames = jointNames;
    hand.userData.visualScratch = {
      positions: Object.fromEntries(jointNames.map((name) => [name, new THREE.Vector3()])),
      scale: new THREE.Vector3(), matrix: new THREE.Matrix4(),
      identity: new THREE.Quaternion(), zero: new THREE.Vector3(),
    };
  }

  function updateHandBones(hand, time) {
    const bones = hand.userData.visual?.bones;
    const instances = hand.userData.visual?.jointInstances;
    if (!bones || !instances) return;
    if (performanceTier === "stability") {
      bones.visible = false; instances.visible = false;
      return;
    }
    if (time - Number(hand.userData.lastVisualUpdateAt || 0) < HAND_VISUAL_INTERVAL_MS) return;
    hand.userData.lastVisualUpdateAt = time;
    const names = hand.userData.visual.jointNames;
    const scratch = hand.userData.visualScratch;
    let visibleJoints = 0;
    names.forEach((name, index) => {
      const joint = hand.joints?.[name];
      const position = scratch.positions[name];
      const visible = Boolean(joint?.visible);
      if (visible) {
        joint.getWorldPosition(position);
        const radius = THREE.MathUtils.clamp(Number(joint.jointRadius || 0.007), 0.0035, 0.012);
        scratch.scale.setScalar(radius);
        visibleJoints += 1;
      } else {
        position.copy(scratch.zero);
        scratch.scale.setScalar(0);
      }
      scratch.matrix.compose(position, scratch.identity, scratch.scale);
      instances.setMatrixAt(index, scratch.matrix);
    });
    instances.instanceMatrix.needsUpdate = true;
    instances.visible = visibleJoints > names.length * 0.7;
    const attribute = bones.geometry.attributes.position;
    let visibleSegments = 0;
    HAND_BONES.forEach(([fromName, toName], index) => {
      const from = hand.joints?.[fromName]; const to = hand.joints?.[toName];
      if (from?.visible && to?.visible) {
        const a = scratch.positions[fromName]; const b = scratch.positions[toName];
        attribute.setXYZ(index * 2, a.x, a.y, a.z);
        attribute.setXYZ(index * 2 + 1, b.x, b.y, b.z);
        visibleSegments += 1;
      } else {
        attribute.setXYZ(index * 2, 0, 0, 0);
        attribute.setXYZ(index * 2 + 1, 0, 0, 0);
      }
    });
    attribute.needsUpdate = true;
    bones.visible = visibleSegments > HAND_BONES.length * 0.7;
  }

  function pinchMetrics(hand) {
    const thumb = hand.joints?.["thumb-tip"];
    const index = hand.joints?.["index-finger-tip"];
    const wrist = hand.joints?.wrist;
    const middle = hand.joints?.["middle-finger-metacarpal"];
    if (!thumb?.visible || !index?.visible || !wrist?.visible || !middle?.visible) return null;
    const scratch = hand.userData.pinchScratch || {
      thumb: new THREE.Vector3(), index: new THREE.Vector3(),
      wrist: new THREE.Vector3(), middle: new THREE.Vector3(),
      midpoint: new THREE.Vector3(), metrics: {},
    };
    hand.userData.pinchScratch = scratch;
    const thumbPosition = scratch.thumb; const indexPosition = scratch.index;
    const wristPosition = scratch.wrist; const middlePosition = scratch.middle;
    thumb.getWorldPosition(thumbPosition); index.getWorldPosition(indexPosition);
    wrist.getWorldPosition(wristPosition); middle.getWorldPosition(middlePosition);
    const palmLength = wristPosition.distanceTo(middlePosition);
    const close = THREE.MathUtils.clamp(palmLength * 0.22, PINCH_CLOSE_MIN_M, PINCH_CLOSE_MAX_M);
    const metrics = scratch.metrics;
    metrics.distance = thumbPosition.distanceTo(indexPosition);
    metrics.close = close;
    metrics.release = close + PINCH_RELEASE_GAP_M;
    metrics.midpoint = scratch.midpoint.copy(thumbPosition).add(indexPosition).multiplyScalar(0.5);
    return metrics;
  }

  function finishPrecisionPinch(hand) {
    const state = hand.userData.precisionPinch;
    if (!state?.pinching) return;
    state.pinching = false; state.nativePinching = false;
    state.candidateSince = null; state.releaseSince = null;
    cancelExitHold(hand);
    stopTabletGrab(hand.userData.grabSource);
    stopGrab(hand.userData.grabSource);
  }

  function updatePrecisionPinch(hand, time) {
    const metrics = pinchMetrics(hand);
    const state = hand.userData.precisionPinch || {
      pinching: false, candidateSince: null, releaseSince: null, nativePinching: false,
    };
    hand.userData.precisionPinch = state;
    const orb = hand.userData.visual?.pinchOrb;
    if (!metrics) {
      if (orb) orb.visible = false;
      finishPrecisionPinch(hand);
      return;
    }
    if (orb) {
      orb.position.copy(metrics.midpoint);
      const readiness = THREE.MathUtils.clamp(1 - ((metrics.distance - metrics.close) / 0.035), 0, 1);
      orb.scale.setScalar(0.55 + readiness * 0.75);
      orb.material.color.setHex(state.pinching ? 0x55f2aa : readiness > 0.7 ? 0xffd27d : 0x9bdbea);
      orb.material.opacity = 0.25 + readiness * 0.65;
      orb.visible = metrics.distance < metrics.release + 0.03;
    }
    const closeDetected = metrics.distance <= metrics.close || state.nativePinching;
    if (!state.pinching) {
      if (!closeDetected) { state.candidateSince = null; return; }
      if (state.candidateSince == null) state.candidateSince = time;
      const hoverStable = !hand.userData.hoverAction
        || time - Number(hand.userData.hoverSince || 0) >= HOVER_STABILITY_MS;
      if (time - state.candidateSince >= PINCH_COMMIT_MS && hoverStable) {
        state.pinching = true; state.releaseSince = null;
        activateIntersection(hand, hand.userData.inputSource, true);
      }
      return;
    }
    const released = metrics.distance >= metrics.release && !state.nativePinching;
    if (!released) { state.releaseSince = null; return; }
    if (state.releaseSince == null) state.releaseSince = time;
    if (time - state.releaseSince >= PINCH_RELEASE_MS) finishPrecisionPinch(hand);
  }

  function updateHandPointer(hand, time) {
    const visual = hand.userData.visual;
    if (!visual) return;
    const valid = handRay(hand, raycaster);
    visual.ray.visible = Boolean(valid && session);
    visual.cursor.visible = false;
    if (!valid) {
      if (hand.userData.hoverAction) {
        hand.userData.hoverAction = null;
        refreshHoverVisuals();
      }
      return;
    }
    const scratch = hand.userData.pointerScratch || { end: new THREE.Vector3() };
    hand.userData.pointerScratch = scratch;
    const origin = raycaster.ray.origin;
    const end = scratch.end.copy(origin).addScaledVector(raycaster.ray.direction, HAND_RAY_LENGTH);
    const positions = visual.ray.geometry.attributes.position;
    positions.setXYZ(0, origin.x, origin.y, origin.z);
    positions.setXYZ(1, end.x, end.y, end.z);
    positions.needsUpdate = true;
    if (tabletGrab || activeGrabs.size) {
      visual.cursor.visible = false;
      return;
    }
    const elapsed = time - Number(hand.userData.lastPointerRaycastAt || 0);
    const raycastInterval = performanceTier === "stability"
      ? POINTER_RAYCAST_INTERVAL_MS * 1.5 : POINTER_RAYCAST_INTERVAL_MS;
    if (elapsed < raycastInterval) {
      const distance = Number(hand.userData.pointerHitDistance);
      if (Number.isFinite(distance)) {
        visual.cursor.position.copy(origin).addScaledVector(raycaster.ray.direction, distance);
        visual.cursor.visible = true;
      }
      return;
    }
    hand.userData.lastPointerRaycastAt = time;
    const { exitHit, tabletHandleHit, referenceHandleHit, panelHit, modelHits } = intersections(hand, true, true);
    const hit = exitHit || tabletHandleHit || referenceHandleHit || panelHit || modelHits[0];
    const action = exitHit ? "exit_to_webapp"
      : tabletHandleHit ? "tablet_handle"
        : referenceHandleHit ? "reference_handle"
        : panelHit ? panelAction(panelHit, panel) : null;
    if (hand.userData.hoverCandidate !== action) {
      hand.userData.hoverCandidate = action;
      hand.userData.hoverCandidateSince = time;
    } else if (hand.userData.hoverAction !== action
        && time - Number(hand.userData.hoverCandidateSince || 0) >= HOVER_STABILITY_MS) {
      hand.userData.hoverAction = action;
      hand.userData.hoverSince = time;
      refreshHoverVisuals();
    }
    if (hit) {
      hand.userData.pointerHitDistance = origin.distanceTo(hit.point);
      visual.cursor.position.copy(hit.point);
      visual.cursor.visible = true;
      visual.cursor.material.color.setHex(exitHit ? 0xff8d8d
        : tabletHandleHit || referenceHandleHit ? 0x72f2cc : panelHit ? 0x79f2b2 : 0xffd27d);
      visual.cursor.scale.setScalar(exitHit ? 1.45
        : tabletHandleHit || referenceHandleHit ? 1.35 : panelHit ? 1.2 : 1);
    } else hand.userData.pointerHitDistance = null;
  }

  function updateHandGrabSource(hand) {
    const proxy = hand.userData.grabSource;
    const thumb = hand.joints?.["thumb-tip"];
    const index = hand.joints?.["index-finger-tip"];
    const wrist = hand.joints?.wrist;
    if (!proxy || !thumb?.visible || !index?.visible) {
      if (proxy) proxy.visible = false;
      return;
    }
    const scratch = hand.userData.grabScratch || { a: new THREE.Vector3(), b: new THREE.Vector3() };
    hand.userData.grabScratch = scratch;
    const a = scratch.a; const b = scratch.b;
    thumb.getWorldPosition(a); index.getWorldPosition(b);
    proxy.position.copy(a).add(b).multiplyScalar(0.5);
    if (wrist?.visible) wrist.getWorldQuaternion(proxy.quaternion);
    else index.getWorldQuaternion(proxy.quaternion);
    proxy.visible = true;
    proxy.updateMatrixWorld(true);
  }

  function bindController(index) {
    const controller = renderer.xr.getController(index);
    controller.add(makeRay());
    controller.userData.inputSource = null;
    controller.addEventListener("connected", (event) => {
      controller.userData.inputSource = event.data;
      controller.children.forEach((child) => { if (child.name === "oren-xr-ray") child.visible = !event.data?.hand; });
    });
    controller.addEventListener("disconnected", () => { stopGrab(controller); controller.userData.inputSource = null; });
    controller.addEventListener("selectstart", onSelectStart);
    controller.addEventListener("squeezestart", () => { startGrab(controller); updatePanel("Modelo seguro pelo controle."); });
    controller.addEventListener("squeezeend", () => stopGrab(controller));
    api.scene.add(controller);
    controllers.push(controller);
  }

  function bindHand(index) {
    const hand = renderer.xr.getHand(index);
    hand.name = `oren-xr-hand-${index}`;
    hand.userData.inputSource = null;
    const ray = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
      new THREE.LineBasicMaterial({ color: index === 0 ? 0x65e8ff : 0x79f2b2, transparent: true, opacity: 0.55 }),
    );
    ray.name = `oren-hand-ray-${index}`; ray.visible = false; ray.renderOrder = 109; ray.frustumCulled = false;
    const cursor = new THREE.Mesh(
      new THREE.SphereGeometry(0.009, 14, 10),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.92, depthTest: false }),
    );
    cursor.name = `oren-hand-cursor-${index}`; cursor.visible = false; cursor.renderOrder = 112;
    const bonePositions = new Float32Array(HAND_BONES.length * 2 * 3);
    const bones = new THREE.LineSegments(
      new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(bonePositions, 3)),
      new THREE.LineBasicMaterial({
        color: index === 0 ? 0x5fcde8 : 0x64dda3, transparent: true, opacity: 0.5, depthTest: true,
      }),
    );
    bones.name = `oren-hand-bones-${index}`; bones.visible = false; bones.renderOrder = 108; bones.frustumCulled = false;
    const pinchOrb = new THREE.Mesh(
      new THREE.SphereGeometry(0.011, 16, 12),
      new THREE.MeshBasicMaterial({ color: 0x9bdbea, transparent: true, opacity: 0.4, depthTest: false }),
    );
    pinchOrb.name = `oren-pinch-confidence-${index}`; pinchOrb.visible = false; pinchOrb.renderOrder = 113;
    const grabSource = new THREE.Object3D();
    grabSource.name = `oren-hand-grab-source-${index}`;
    grabSource.visible = false;
    api.scene.add(ray, cursor, bones, pinchOrb, grabSource);
    hand.userData.visual = { ray, cursor, bones, pinchOrb };
    hand.userData.grabSource = grabSource;
    hand.userData.targetRay = controllers[index];
    hand.userData.xrCamera = api.camera;
    hand.addEventListener("connected", (event) => { hand.userData.inputSource = event.data; ensureHandVisual(hand, index); });
    hand.addEventListener("disconnected", () => {
      cancelExitHold(hand);
      finishPrecisionPinch(hand);
      stopTabletGrab(grabSource);
      stopGrab(grabSource); resetTabletTouch(hand); hand.userData.inputSource = null; ray.visible = false; cursor.visible = false;
      bones.visible = false; pinchOrb.visible = false;
      if (hand.userData.visual?.jointInstances) hand.userData.visual.jointInstances.visible = false;
      hand.userData.hoverAction = null; hand.userData.orenRayState = null; refreshHoverVisuals();
    });
    hand.addEventListener("pinchstart", () => {
      const state = hand.userData.precisionPinch || { pinching: false };
      state.nativePinching = true; hand.userData.precisionPinch = state;
    });
    hand.addEventListener("pinchend", () => {
      const state = hand.userData.precisionPinch || { pinching: false };
      state.nativePinching = false; hand.userData.precisionPinch = state;
    });
    api.scene.add(hand);
    hands.push(hand);
  }

  bindController(0); bindController(1); bindHand(0); bindHand(1);

  function applyPerformanceTier(nextTier, p95 = null) {
    if (performanceTier === nextTier) return;
    performanceTier = nextTier;
    api.setRenderingQualityTier?.(nextTier);
    const showDecorativeEdges = nextTier !== "stability";
    tablet.frameEdges.visible = showDecorativeEdges;
    referenceTablet.edges.visible = showDecorativeEdges;
    hands.forEach((hand) => {
      if (nextTier === "stability" && hand.userData.visual?.jointInstances) {
        hand.userData.visual.jointInstances.visible = false;
        hand.userData.visual.bones.visible = false;
      }
    });
    renderer.xr.setFoveation?.(nextTier === "stability" ? 1 : 0.55);
    const suffix = Number.isFinite(p95) ? ` · p95 ${p95.toFixed(1)} ms` : "";
    updatePanel(nextTier === "stability"
      ? `XR fluido · detalhes auxiliares das mãos reduzidos${suffix}.`
      : `XR fluido · qualidade visual completa restaurada${suffix}.`);
  }

  function enforceRealismPerformanceFallback(p95) {
    if (realismFallbackActive || api.getRenderingProfile?.() !== "anatomic_realistic_v1") return;
    realismFallbackActive = true;
    void Promise.resolve(api.setRenderingProfile?.("scientific_current_v1", {
      fallbackReason: "performance_budget_exceeded",
      message: `Modo científico restaurado para manter fluidez · p95 ${p95.toFixed(1)} ms.`,
    })).then(() => {
      updatePanel(`Textura realista pausada para manter fluidez · p95 ${p95.toFixed(1)} ms.`);
    });
  }

  window.__orenXrFrame = (time) => {
    if (!session) return;
    if (entryCalibration && !updateEntryCalibration(time)) {
      api.stabilizeXrScene?.();
      return;
    }
    xrRoot.visible = true;
    if (time - lastSceneIntegrityAt >= XR_SCENE_INTEGRITY_INTERVAL_MS) {
      api.stabilizeXrScene?.();
      lastSceneIntegrityAt = time;
    }
    hands.forEach((hand, index) => {
      hand.userData.xrCamera = renderer.xr.getCamera(api.camera);
      ensureHandVisual(hand, index);
      updateHandBones(hand, time);
      updateHandGrabSource(hand);
      updateHandPointer(hand, time);
      updateTabletTouch(hand, time);
      updatePrecisionPinch(hand, time);
    });
    updateExitHold(time);
    updateTabletGrab();
    updateGrab();
    api.refreshClippingPlaneWorld?.();
    refreshReferencePanel();
    if (lastFrame) {
      const frameTime = time - lastFrame;
      if (frameTime > 0 && frameTime < 100) frameTimes.push(frameTime);
      if (frameTimes.length > PERF_WINDOW_FRAMES) frameTimes.shift();
      frameCounter += 1;
      if (frameTimes.length === PERF_WINDOW_FRAMES
          && frameCounter % PERF_EVALUATION_INTERVAL_FRAMES === 0) {
        const sorted = [...frameTimes].sort((a, b) => a - b);
        const p95 = sorted[Math.floor(sorted.length * 0.95)];
        panel.mesh.userData.frameP95 = p95;
        if (p95 > PERF_STABILITY_THRESHOLD_MS) {
          performanceStressWindows += 1;
          applyPerformanceTier("stability", p95);
          if (performanceStressWindows >= 3) enforceRealismPerformanceFallback(p95);
        } else if (time >= entryWarmupUntil && p95 <= FRAME_BUDGET_MS * 1.08) {
          performanceStressWindows = 0;
          applyPerformanceTier("quality", p95);
        } else {
          performanceStressWindows = 0;
        }
      }
    }
    lastFrame = time;
  };

  function cleanupXrSession(endedSession = session, message = "Sessão XR encerrada; visualizador desktop restaurado.") {
    if (endedSession && session && endedSession !== session) return;
    if (originalModelState) persistPose();
    activeGrabs.clear(); twoHandStart = null; tabletGrab = null;
    lastFrame = 0; frameCounter = 0; frameTimes.length = 0; performanceTier = "quality";
    performanceStressWindows = 0; realismFallbackActive = false;
    api.setRenderingQualityTier?.("quality");
    tablet.frameEdges.visible = true; referenceTablet.edges.visible = true;
    entryCalibration = null; entryWarmupUntil = 0;
    interactiveMeshes = [];
    tablet.root.visible = false; tablet.touchCursor.visible = false;
    referenceTablet.root.visible = false; exitButton.mesh.visible = false;
    exitHold = null; hoveredAction = null;
    hands.forEach((hand) => {
      if (hand.userData.visual) {
        hand.userData.visual.ray.visible = false;
        hand.userData.visual.cursor.visible = false;
        hand.userData.visual.bones.visible = false;
        hand.userData.visual.pinchOrb.visible = false;
        if (hand.userData.visual.jointInstances) hand.userData.visual.jointInstances.visible = false;
      }
      hand.userData.precisionPinch = null;
      hand.userData.tabletTouch = null;
      hand.userData.orenRayState = null;
      hand.userData.pointerHitDistance = null;
    });
    if (originalModelState) {
      originalModelState.parent.add(api.group);
      api.group.position.copy(originalModelState.position);
      api.group.quaternion.copy(originalModelState.quaternion);
      api.group.scale.copy(originalModelState.scale);
      originalModelState.measurementParent.add(api.measurementGroup);
      api.camera.near = originalModelState.cameraNear;
      api.camera.far = originalModelState.cameraFar;
      api.camera.updateProjectionMatrix();
      if (originalModelState.clipping) api.setClippingState?.(originalModelState.clipping);
      originalModelState = null;
    }
    api.setXrPresentationActive?.(false);
    api.setOrbitEnabled(true);
    entry.textContent = "Entrar no Meta Quest";
    entry.disabled = false;
    statusNode.textContent = message;
    if (!endedSession || session === endedSession) session = null;
    if (exitToWebappRequested) {
      exitToWebappRequested = false;
      window.setTimeout(() => window.location.replace("/"), 80);
    }
  }

  async function enter() {
    reportClientEvent("entry_click");
    if (!(api.getXrReady?.() ?? api.getViewerReady())) {
      statusNode.textContent = "O modelo ainda está carregando. Aguarde o botão ficar verde para entrar.";
      entry.textContent = "Carregando modelo 3D…";
      entry.disabled = true;
      return;
    }
    entry.disabled = true;
    entry.textContent = "Iniciando realidade aumentada…";
    profile = profileSelect.value === "patient" ? "patient" : "clinician";
    const wantsMixedReality = document.getElementById("xr-mixed-reality")?.checked;
    const mode = supportsAr && (wantsMixedReality || !supportsVr) ? "immersive-ar" : "immersive-vr";
    renderer.xr.setFramebufferScaleFactor?.(XR_FRAMEBUFFER_SCALE);
    reportClientEvent("session_requested", { mode });
    const createdSession = await navigator.xr.requestSession(mode, {
      optionalFeatures: ["local-floor", "bounded-floor", "hand-tracking"],
    });
    session = createdSession;
    const requestedSession = createdSession;
    requestedSession.addEventListener("end", () => cleanupXrSession(requestedSession), { once: true });
    requestedSession.addEventListener("visibilitychange", () => {
      if (requestedSession.visibilityState === "visible") {
        api.setXrPresentationActive?.(true);
        api.stabilizeXrScene?.();
        interactiveMeshes = Object.values(api.meshes);
        if (entryCalibration) statusNode.textContent = "Sessão retomada · recalibrando pelo seu olhar.";
        else updatePanel("Sessão retomada · modelo e controles prontos.");
      } else {
        statusNode.textContent = "Sessão XR pausada pelo sistema.";
      }
    });
    originalModelState = {
      parent: api.group.parent, position: api.group.position.clone(), quaternion: api.group.quaternion.clone(),
      scale: api.group.scale.clone(), measurementParent: api.measurementGroup.parent,
      cameraNear: api.camera.near, cameraFar: api.camera.far,
      clipping: api.getClippingState?.(),
    };
    api.setXrPresentationActive?.(true);
    api.setRenderingQualityTier?.("stability");
    api.setClippingState?.({ enabled: false });
    api.camera.near = 0.01;
    api.camera.far = 20;
    api.camera.updateProjectionMatrix();
    interactiveMeshes = Object.values(api.meshes);
    xrRoot.add(api.group);
    api.setOrbitEnabled(false);
    await renderer.xr.setSession(session);
    beginEntryCalibration(performance.now());
    renderer.xr.setFoveation?.(0.9);
    reportClientEvent("session_started", { mode });
    entry.textContent = "Encerrar modo imersivo";
    entry.disabled = false;
    statusNode.textContent = `${mode === "immersive-ar" ? "Mixed reality" : "VR"} ativo · calibrando pelo seu olhar.`;
    const announceInputs = () => {
      if (entryCalibration) return;
      const handCount = [...requestedSession.inputSources].filter((source) => source.hand).length;
      if (handCount) updatePanel(`${handCount === 2 ? "Duas mãos" : "Uma mão"} detectada${handCount === 2 ? "s" : ""} · faça pinça para interagir.`);
    };
    requestedSession.addEventListener("inputsourceschange", announceInputs);
    announceInputs();
  }

  entry.addEventListener("click", () => session ? session.end() : enter().catch(async (error) => {
    const failedSession = session;
    if (failedSession) await failedSession.end().catch(() => {});
    if (session === failedSession) cleanupXrSession(failedSession, `Não foi possível iniciar WebXR: ${error.message}`);
    entry.disabled = false;
    entry.textContent = "Corrigir acesso à realidade aumentada";
    statusNode.textContent = `Não foi possível iniciar WebXR: ${error.message}`;
    reportClientEvent("session_failed", {
      mode: supportsAr ? "immersive-ar" : supportsVr ? "immersive-vr" : "unknown",
      error_name: String(error?.name || "Error").slice(0, 80),
      message: String(error?.message || error || "Falha desconhecida").slice(0, 300),
    });
    if (["SecurityError", "NotSupportedError"].includes(error?.name)) {
      try { sessionStorage.setItem("oren:xr-return-url", location.href); } catch (_storageError) { /* opcional */ }
      window.location.assign("/quest/setup/");
    }
  }));
  const refreshEntryReadiness = () => {
    if (session || !supported) return;
    const ready = Boolean(api.getXrReady?.() ?? api.getViewerReady());
    entry.disabled = !ready;
    entry.textContent = ready ? "Entrar na realidade aumentada" : "Carregando modelo 3D…";
    if (ready) {
      statusNode.textContent = "Modelo pronto. Toque no botão para entrar em mixed reality.";
      reportClientEvent("viewer_ready");
      if (viewerReadinessTimer) window.clearInterval(viewerReadinessTimer);
      viewerReadinessTimer = null;
    }
  };
  refreshEntryReadiness();
  if (!(api.getXrReady?.() ?? api.getViewerReady())) {
    viewerReadinessTimer = window.setInterval(refreshEntryReadiness, 250);
  }
  profileSelect.addEventListener("change", () => {
    profile = profileSelect.value === "patient" ? "patient" : "clinician";
    if (profile === "patient" && activePage === "review") activePage = "model";
    updatePanel(profile === "patient" ? "Perfil do paciente selecionado." : "Perfil médico selecionado.");
    document.body.dataset.xrProfile = profile;
  });
  window.__argosXR = {
    schema: XR_SCHEMA, supported: true, enter, getSession: () => session,
    getHandState: () => hands.map((hand) => ({
      connected: Boolean(hand.userData.inputSource),
      pinching: Boolean(hand.userData.precisionPinch?.pinching),
      native_pinching: Boolean(hand.userData.precisionPinch?.nativePinching),
      tablet_touch: hand.userData.tabletTouch?.action || null,
      tablet_grab: Boolean(tabletGrab?.hand === hand),
      ray_source: hand.userData.orenRayState?.source || null,
      hover_action: hand.userData.hoverAction || null,
    })),
    getPerformance: () => ({
      p95_ms: panel.mesh.userData.frameP95 ?? null,
      frame_budget_ms: FRAME_BUDGET_MS,
      tier: performanceTier,
      framebuffer_scale: XR_FRAMEBUFFER_SCALE,
      pointer_raycast_interval_ms: performanceTier === "stability"
        ? POINTER_RAYCAST_INTERVAL_MS * 1.5 : POINTER_RAYCAST_INTERVAL_MS,
      panel_texture_uploads: panel.getPerformanceStats?.().texture_uploads ?? null,
      reference_texture_uploads: referencePanel.getPerformanceStats?.().texture_uploads ?? null,
    }),
  };
}

export { XR_SCHEMA };
