/* ============================================================
   OA Detection System — Next-Gen 3D & Glassmorphic Dashboard
   SIH 2026 | PS-26004 | MDoNER
   Features:
   - Three.js Interactive 3D Biomechanical Knee Model
   - Web Serial & Web Bluetooth Direct Hardware Connectors
   - Realtime Colors Plugin (Dynamic CSS custom properties)
   - Real-time Multi-Sensor Chart.js Telemetry & Radar Signature
   - Normal vs OA Side-by-Side Diagnostic Engine
   ============================================================ */

'use strict';

// ── CONSTANTS & PALETTES ───────────────────────────────────────
const SERVER_URL = window.location.origin || 'http://localhost:5000';
const MAX_POINTS = 40;

const PALETTES = {
  cyberpunk: {
    primary:   '#22d3ee',
    secondary: '#a78bfa',
    accent:    '#f43f5e',
    success:   '#10b981',
    warning:   '#f59e0b',
    bg:        '#030712',
    glassBg:   'rgba(15, 23, 42, 0.55)',
  },
  emerald: {
    primary:   '#10b981',
    secondary: '#06b6d4',
    accent:    '#f59e0b',
    success:   '#059669',
    warning:   '#eab308',
    bg:        '#021a12',
    glassBg:   'rgba(6, 44, 33, 0.55)',
  },
  arctic: {
    primary:   '#38bdf8',
    secondary: '#6366f1',
    accent:    '#f43f5e',
    success:   '#22c55e',
    warning:   '#e0a82e',
    bg:        '#050e1f',
    glassBg:   'rgba(15, 28, 55, 0.55)',
  },
  solar: {
    primary:   '#f59e0b',
    secondary: '#f43f5e',
    accent:    '#ec4899',
    success:   '#10b981',
    warning:   '#fbbf24',
    bg:        '#160805',
    glassBg:   'rgba(40, 16, 12, 0.55)',
  },
  amethyst: {
    primary:   '#c084fc',
    secondary: '#ec4899',
    accent:    '#38bdf8',
    success:   '#34d399',
    warning:   '#f59e0b',
    bg:        '#0f051d',
    glassBg:   'rgba(30, 12, 50, 0.55)',
  }
};

let currentPalette = PALETTES.cyberpunk;

const NORMAL_PROFILE = {
  audio_rms: 0.018, dominant_freq_hz: 150, crepitus_score: 0.05,
  joint_temp_c: 33.2, temp_asymmetry: 0.1,
  accel_rms_x: 0.85, gyro_range_deg: 105, step_symmetry: 0.92,
  flex_angle_deg: 112, flex_stiffness: 0.12,
};

const OA_PROFILE = {
  audio_rms: 0.09, dominant_freq_hz: 520, crepitus_score: 0.65,
  joint_temp_c: 36.1, temp_asymmetry: 1.1,
  accel_rms_x: 1.55, gyro_range_deg: 52, step_symmetry: 0.62,
  flex_angle_deg: 55, flex_stiffness: 0.67,
};

const FEATURE_DISPLAY = [
  { key: 'crepitus_score', label: 'Crepitus Score', unit: '', max: 1.0 },
  { key: 'joint_temp_c',   label: 'Joint Temp',     unit: '°C', max: 40 },
  { key: 'temp_asymmetry', label: 'Thermal Delta',  unit: '°C', max: 3 },
  { key: 'gyro_range_deg', label: 'Joint ROM',      unit: '°',  max: 140 },
  { key: 'step_symmetry',  label: 'Gait Symmetry',  unit: '', max: 1.0 },
  { key: 'flex_angle_deg', label: 'Flexion Angle',  unit: '°',  max: 140 },
  { key: 'flex_stiffness', label: 'Flex Stiffness', unit: '', max: 1.0 },
];

// ── GLOBAL APPLICATION STATE ──────────────────────────────────
const state = {
  socket: null,
  activeChart: 'audio',
  demoRunning: false,
  demoInterval: null,
  serialPort: null,
  serialReader: null,
  bleDevice: null,
  lastReading: null,
  sessionCount: 0,
  normalCount: 0,
  oaCount: 0,
  charts: {},
  radarChart: null,
  // 3D Model State
  three: {
    scene: null,
    camera: null,
    renderer: null,
    controls: null,
    kneePivot: null,
    capsuleMesh: null,
    patellaMesh: null,
    acousticRings: [],
    wireframe: false,
    autoRotate: true,
  }
};

// ── REALTIME COLORS PLUGIN ─────────────────────────────────────
function setPalette(themeKey) {
  const p = PALETTES[themeKey];
  if (!p) return;
  currentPalette = p;

  const root = document.documentElement;
  root.style.setProperty('--color-primary', p.primary);
  root.style.setProperty('--color-primary-dim', hexToRgba(p.primary, 0.16));
  root.style.setProperty('--color-primary-glow', hexToRgba(p.primary, 0.45));
  root.style.setProperty('--color-secondary', p.secondary);
  root.style.setProperty('--color-secondary-dim', hexToRgba(p.secondary, 0.16));
  root.style.setProperty('--color-secondary-glow', hexToRgba(p.secondary, 0.45));
  root.style.setProperty('--color-accent', p.accent);
  root.style.setProperty('--color-accent-dim', hexToRgba(p.accent, 0.16));
  root.style.setProperty('--color-accent-glow', hexToRgba(p.accent, 0.45));
  root.style.setProperty('--color-success', p.success);
  root.style.setProperty('--color-warning', p.warning);
  root.style.setProperty('--bg-base', p.bg);
  root.style.setProperty('--glass-bg', p.glassBg);

  // Update swatches active state
  document.querySelectorAll('.color-swatch').forEach(sw => sw.classList.remove('active'));
  const activeSwatch = document.querySelector(`.swatch-${themeKey}`);
  if (activeSwatch) activeSwatch.classList.add('active');

  // Update Radar Chart Colors
  if (state.radarChart) {
    state.radarChart.data.datasets[0].borderColor = p.primary;
    state.radarChart.data.datasets[0].backgroundColor = hexToRgba(p.primary, 0.25);
    state.radarChart.data.datasets[0].pointBackgroundColor = p.primary;
    state.radarChart.update();
  }

  // Update Line Chart Primary Datasets
  if (state.charts.audio) {
    state.charts.audio.data.datasets[0].borderColor = p.primary;
    state.charts.audio.update('none');
  }

  // Update 3D Lighting / Materials
  if (state.three.capsuleMesh && !state.three.wireframe) {
    state.three.capsuleMesh.material.color.set(p.primary);
  }
}

function hexToRgba(hex, alpha = 1) {
  let c = hex.replace('#', '');
  if (c.length === 3) c = c.split('').map(x => x + x).join('');
  const num = parseInt(c, 16);
  return `rgba(${(num >> 16) & 255}, ${(num >> 8) & 255}, ${num & 255}, ${alpha})`;
}

// ── THREE.JS 3D BIOMECHANICAL KNEE VISUALIZER ──────────────────
function initThreeKnee() {
  const container = document.querySelector('.three-container');
  const canvas    = document.getElementById('knee-canvas');
  if (!container || !canvas || typeof THREE === 'undefined') return;

  const width  = container.clientWidth;
  const height = container.clientHeight;

  // Scene & Camera
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x030712, 0.06);

  const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
  camera.position.set(0, 0, 7.2);

  // Renderer with Antialiasing & Transparency
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setSize(width, height);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  // Controls
  let controls = null;
  if (typeof THREE.OrbitControls !== 'undefined') {
    controls = new THREE.OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 1.2;
    controls.maxDistance = 12;
    controls.minDistance = 3.5;
  }

  // Lights
  const ambLight = new THREE.AmbientLight(0xffffff, 0.65);
  scene.add(ambLight);

  const keyLight = new THREE.DirectionalLight(0x22d3ee, 1.2);
  keyLight.position.set(5, 8, 5);
  scene.add(keyLight);

  const rimLight = new THREE.DirectionalLight(0xa78bfa, 0.8);
  rimLight.position.set(-5, -4, -5);
  scene.add(rimLight);

  const pointLight = new THREE.PointLight(0xffffff, 0.6, 10);
  pointLight.position.set(0, 0, 3);
  scene.add(pointLight);

  // ── PROCEDURAL BIOMECHANICAL ANATOMY ─────────────────────────
  const rootLeg = new THREE.Group();
  scene.add(rootLeg);

  // 1. FEMUR (Upper Bone)
  const femurGroup = new THREE.Group();
  femurGroup.position.set(0, 0.5, 0);

  const femurMat = new THREE.MeshStandardMaterial({
    color: 0x94a3b8,
    roughness: 0.35,
    metalness: 0.25,
    wireframe: false
  });

  const femurShaftGeo = new THREE.CylinderGeometry(0.38, 0.44, 2.2, 24);
  const femurShaft    = new THREE.Mesh(femurShaftGeo, femurMat);
  femurShaft.position.y = 1.1;
  femurGroup.add(femurShaft);

  // Femur Condyles (Knee Knuckle)
  const condyleGeo = new THREE.SphereGeometry(0.48, 20, 16);
  const condyleL   = new THREE.Mesh(condyleGeo, femurMat);
  condyleL.position.set(-0.32, 0.05, 0);
  condyleL.scale.set(1, 0.8, 1.2);
  femurGroup.add(condyleL);

  const condyleR   = new THREE.Mesh(condyleGeo, femurMat);
  condyleR.position.set(0.32, 0.05, 0);
  condyleR.scale.set(1, 0.8, 1.2);
  femurGroup.add(condyleR);

  // Upper Exoskeleton Collar (Brace Mount)
  const collarMat = new THREE.MeshStandardMaterial({
    color: 0x1e293b,
    metalness: 0.8,
    roughness: 0.2
  });
  const upperCollar = new THREE.Mesh(new THREE.TorusGeometry(0.55, 0.06, 12, 32), collarMat);
  upperCollar.rotation.x = Math.PI / 2;
  upperCollar.position.y = 1.2;
  femurGroup.add(upperCollar);

  // ESP32-S3 Microcontroller Mockup on Femur Collar
  const espBox = new THREE.Mesh(
    new THREE.BoxGeometry(0.35, 0.1, 0.25),
    new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.5 })
  );
  espBox.position.set(0, 1.2, 0.55);
  femurGroup.add(espBox);

  // Status LED on ESP32
  const ledMesh = new THREE.Mesh(
    new THREE.SphereGeometry(0.04, 12, 12),
    new THREE.MeshBasicMaterial({ color: 0x10b981 })
  );
  ledMesh.position.set(0, 1.27, 0.55);
  femurGroup.add(ledMesh);

  rootLeg.add(femurGroup);

  // 2. KNEE REVOLUTE JOINT PIVOT (Lower Leg Rotates Here)
  const kneePivot = new THREE.Group();
  kneePivot.position.set(0, 0.4, 0);
  rootLeg.add(kneePivot);

  // 3. TIBIA & FIBULA (Lower Bone)
  const tibiaMat = new THREE.MeshStandardMaterial({
    color: 0x94a3b8,
    roughness: 0.35,
    metalness: 0.25,
    wireframe: false
  });

  // Tibial Plateau (Top of shin)
  const plateauGeo = new THREE.CylinderGeometry(0.52, 0.42, 0.3, 24);
  const plateau    = new THREE.Mesh(plateauGeo, tibiaMat);
  plateau.position.y = -0.15;
  kneePivot.add(plateau);

  // Tibia Shaft
  const tibiaShaftGeo = new THREE.CylinderGeometry(0.36, 0.32, 2.3, 24);
  const tibiaShaft    = new THREE.Mesh(tibiaShaftGeo, tibiaMat);
  tibiaShaft.position.y = -1.3;
  kneePivot.add(tibiaShaft);

  // Fibula (Slender lateral bone)
  const fibulaGeo = new THREE.CylinderGeometry(0.12, 0.1, 2.1, 16);
  const fibula    = new THREE.Mesh(fibulaGeo, tibiaMat);
  fibula.position.set(0.46, -1.3, 0);
  kneePivot.add(fibula);

  // Lower Exoskeleton Collar
  const lowerCollar = new THREE.Mesh(new THREE.TorusGeometry(0.5, 0.05, 12, 32), collarMat);
  lowerCollar.rotation.x = Math.PI / 2;
  lowerCollar.position.y = -1.1;
  kneePivot.add(lowerCollar);

  // 4. PATELLA (Floating Kneecap)
  const patellaMat = new THREE.MeshStandardMaterial({
    color: 0xe2e8f0,
    roughness: 0.4,
    metalness: 0.15
  });
  const patellaGeo = new THREE.SphereGeometry(0.32, 20, 16);
  const patellaMesh = new THREE.Mesh(patellaGeo, patellaMat);
  patellaMesh.scale.set(1, 1.25, 0.55);
  patellaMesh.position.set(0, 0.45, 0.52);
  rootLeg.add(patellaMesh);

  // 5. JOINT CAPSULE / CARTILAGE (Thermal Diagnostic Heatmap Mesh)
  const capsuleGeo = new THREE.TorusGeometry(0.46, 0.16, 16, 32);
  const capsuleMat = new THREE.MeshStandardMaterial({
    color: 0x22d3ee,
    emissive: 0x22d3ee,
    emissiveIntensity: 0.35,
    transparent: true,
    opacity: 0.75,
    roughness: 0.2
  });
  const capsuleMesh = new THREE.Mesh(capsuleGeo, capsuleMat);
  capsuleMesh.rotation.x = Math.PI / 2;
  capsuleMesh.position.set(0, 0.38, 0);
  rootLeg.add(capsuleMesh);

  // 6. ACOUSTIC CREPITUS SHOCKWAVE RINGS
  const acousticRings = [];
  for (let i = 0; i < 3; i++) {
    const ringGeo = new THREE.RingGeometry(0.6 + i * 0.2, 0.65 + i * 0.2, 32);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0xf43f5e,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = Math.PI / 2;
    ring.position.set(0, 0.4, 0);
    rootLeg.add(ring);
    acousticRings.push(ring);
  }

  // Save to state
  state.three = {
    scene, camera, renderer, controls,
    rootLeg, kneePivot, capsuleMesh, patellaMesh,
    femurMat, tibiaMat, ledMesh,
    acousticRings, wireframe: false, autoRotate: true
  };

  // ── RENDER LOOP ──────────────────────────────────────────────
  let clock = new THREE.Clock();
  function animate() {
    requestAnimationFrame(animate);
    const delta = clock.getDelta();

    if (controls) controls.update();

    // Animate acoustic crepitus rings if active
    acousticRings.forEach((ring, idx) => {
      if (ring.material.opacity > 0) {
        ring.scale.addScalar(delta * 1.5);
        ring.material.opacity -= delta * 0.9;
        if (ring.material.opacity <= 0) {
          ring.material.opacity = 0;
          ring.scale.set(1, 1, 1);
        }
      }
    });

    renderer.render(scene, camera);
  }
  animate();

  // Resize Handler
  window.addEventListener('resize', () => {
    if (!container || !camera || !renderer) return;
    const w = container.clientWidth;
    const h = container.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  });

  // Attach 3D HUD Toolbar Buttons
  document.getElementById('btn-reset-cam')?.addEventListener('click', () => {
    camera.position.set(0, 0, 7.2);
    if (controls) controls.target.set(0, 0, 0);
  });

  document.getElementById('btn-wireframe')?.addEventListener('click', () => {
    state.three.wireframe = !state.three.wireframe;
    femurMat.wireframe = state.three.wireframe;
    tibiaMat.wireframe = state.three.wireframe;
    capsuleMat.wireframe = state.three.wireframe;
  });

  document.getElementById('btn-autorotate')?.addEventListener('click', () => {
    state.three.autoRotate = !state.three.autoRotate;
    if (controls) controls.autoRotate = state.three.autoRotate;
  });
}

// ── UPDATE 3D MODEL FROM LIVE SENSOR VALUES ────────────────────
function updateKnee3D(flexAngle, jointTemp, crepitusScore, imuGyro) {
  const { kneePivot, capsuleMesh, ledMesh, acousticRings } = state.three;
  if (!kneePivot) return;

  // 1. Live Flexion Angle: Normal ROM 90°–130° (bent), OA 30°–80°
  // Map angle degrees to radians for knee flexion
  const rad = ((130 - flexAngle) * Math.PI) / 180;
  kneePivot.rotation.x = Math.max(-0.2, Math.min(rad, 1.8));

  // Update HUD
  const hudAngle = document.getElementById('hud-angle');
  if (hudAngle) hudAngle.textContent = `${Math.round(flexAngle)}°`;

  // 2. MLX90614 Thermal Diagnostic Heatmap
  // Joint capsule color changes: cool cyan (healthy ~33°C) -> amber (35°C) -> inflamed red (>36°C)
  if (capsuleMesh) {
    let hexColor;
    let label;
    if (jointTemp < 34.0) {
      hexColor = 0x22d3ee; // cool cyan
      label = `${jointTemp.toFixed(1)}°C (Norm)`;
    } else if (jointTemp < 35.5) {
      hexColor = 0xf59e0b; // warm amber
      label = `${jointTemp.toFixed(1)}°C (Mild Inf)`;
    } else {
      hexColor = 0xf43f5e; // inflamed crimson
      label = `${jointTemp.toFixed(1)}°C (Inflamed)`;
    }
    capsuleMesh.material.color.setHex(hexColor);
    capsuleMesh.material.emissive.setHex(hexColor);

    const hudTemp = document.getElementById('hud-temp');
    if (hudTemp) {
      hudTemp.textContent = label;
      hudTemp.style.color = `#${hexColor.toString(16).padStart(6, '0')}`;
    }
  }

  // 3. Microphone Crepitus Acoustic Shockwave Pulse
  const hudCrep = document.getElementById('hud-crep');
  if (crepitusScore > 0.35) {
    if (hudCrep) {
      hudCrep.textContent = `Active (${crepitusScore.toFixed(2)})`;
      hudCrep.style.color = 'var(--color-accent)';
    }
    // Trigger shockwave ripples
    acousticRings.forEach((ring, i) => {
      setTimeout(() => {
        ring.material.opacity = 0.85;
        ring.scale.set(1, 1, 1);
      }, i * 120);
    });
  } else {
    if (hudCrep) {
      hudCrep.textContent = 'Normal / Low';
      hudCrep.style.color = 'var(--text-secondary)';
    }
  }

  // 4. LED Color based on joint state
  if (ledMesh) {
    if (crepitusScore > 0.6 || jointTemp > 36.0) {
      ledMesh.material.color.setHex(0xf43f5e); // Red OA risk
    } else if (crepitusScore > 0.3 || jointTemp > 34.8) {
      ledMesh.material.color.setHex(0xf59e0b); // Orange warning
    } else {
      ledMesh.material.color.setHex(0x10b981); // Green normal
    }
  }
}

// ── REAL HARDWARE CONNECTORS (WEB SERIAL & WEB BLUETOOTH) ───────
async function connectWebSerial() {
  if (!('serial' in navigator)) {
    alert('Web Serial API is not supported in this browser. Please use Chrome, Edge, or Opera.');
    return;
  }

  try {
    const port = await navigator.serial.requestPort();
    await port.open({ baudRate: 115200 });
    state.serialPort = port;

    const btn = document.getElementById('btn-web-serial');
    if (btn) {
      btn.classList.add('active');
      btn.innerHTML = '<span style="color:#10b981">●</span> USB COM Active';
    }
    setDeviceStatus(true, 'USB Serial (115200 baud)');

    const textDecoder = new TextDecoderStream();
    port.readable.pipeTo(textDecoder.writable);
    const reader = textDecoder.readable.getReader();
    state.serialReader = reader;

    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep remainder

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
          try {
            const parsed = JSON.parse(trimmed);
            handleHardwarePayload(parsed);
          } catch (e) {
            console.warn('[SERIAL] JSON parse error:', e);
          }
        }
      }
    }
  } catch (err) {
    console.error('[SERIAL] Connection error:', err);
  }
}

async function connectWebBluetooth() {
  if (!('bluetooth' in navigator)) {
    alert('Web Bluetooth API is not supported in this browser. Please use Chrome or Edge.');
    return;
  }

  try {
    const device = await navigator.bluetooth.requestDevice({
      filters: [{ name: 'OA_Detector_SIH2026' }],
      optionalServices: ['12345678-1234-5678-1234-56789abcdef0']
    });

    const server = await device.gatt.connect();
    const service = await server.getPrimaryService('12345678-1234-5678-1234-56789abcdef0');
    const characteristic = await service.getCharacteristic('12345678-1234-5678-1234-56789abcdef1');

    await characteristic.startNotifications();
    characteristic.addEventListener('characteristicvaluechanged', (event) => {
      const value = new TextDecoder().decode(event.target.value);
      try {
        const parsed = JSON.parse(value);
        handleHardwarePayload(parsed);
      } catch (e) {
        console.warn('[BLE] JSON parse error:', e);
      }
    });

    state.bleDevice = device;
    const btn = document.getElementById('btn-web-ble');
    if (btn) {
      btn.classList.add('active');
      btn.innerHTML = '<span style="color:#10b981">●</span> BLE Connected';
    }
    setDeviceStatus(true, 'BLE 5.0 (OA_Detector)');
  } catch (err) {
    console.error('[BLE] Connection error:', err);
  }
}

function handleHardwarePayload(data) {
  // Convert flat hardware JSON into nested structure expected by dashboard
  const payload = {
    patient_id: data.patient_id || 'PATIENT_001',
    timestamp: new Date().toISOString(),
    sensors: {
      microphone: {
        audio_rms: data.audio_rms || 0.02,
        dominant_freq_hz: data.dominant_freq_hz || 150,
        crepitus_score: data.crepitus_score || 0.05
      },
      temperature: {
        joint_temp_c: data.joint_temp_c || 33.2,
        ambient_temp_c: data.ambient_temp_c || 28.0,
        temp_asymmetry: data.temp_asymmetry || 0.1
      },
      imu: {
        accel_rms_x: data.accel_rms_x || 0.85,
        accel_rms_y: data.accel_rms_y || 0.90,
        accel_rms_z: data.accel_rms_z || 9.82,
        gyro_range_deg: data.gyro_range_deg || 105,
        step_symmetry: data.step_symmetry || 0.92
      },
      flex: {
        flex_angle_deg: data.flex_angle_deg || 112,
        flex_stiffness: data.flex_stiffness || 0.12
      }
    },
    inference: {
      risk_score: (data.crepitus_score > 0.4 || data.joint_temp_c > 35.5) ? 0.85 : 0.12,
      label: (data.crepitus_score > 0.4 || data.joint_temp_c > 35.5) ? 'Early_OA' : 'Normal',
      risk_level: (data.crepitus_score > 0.4 || data.joint_temp_c > 35.5) ? 'HIGH' : 'LOW',
      confidence: 0.94
    },
    hardware_live: true
  };

  handleLiveData(payload);
}

// ── HARDWARE PIN CHIP PULSE ANIMATION ──────────────────────────
function pulsePinChips() {
  const chips = ['chip-mic', 'chip-temp', 'chip-imu', 'chip-flex', 'chip-led'];
  chips.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.classList.add('active');
      setTimeout(() => el.classList.remove('active'), 280);
    }
  });
}

// ── SOCKET.IO CONNECTION ───────────────────────────────────────
function connectSocket() {
  setConnStatus('connecting', 'Connecting...');

  try {
    state.socket = io(SERVER_URL, {
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      timeout: 5000,
    });

    state.socket.on('connect', () => {
      setConnStatus('connected', 'Live Server');
      setDeviceStatus(true, 'ESP32-S3 N16R8');
      state.socket.emit('subscribe', { patient_id: getSelectedPatient() });
    });

    state.socket.on('disconnect', () => {
      setConnStatus('error', 'Disconnected');
      setDeviceStatus(false);
    });

    state.socket.on('connect_error', () => {
      setConnStatus('error', 'Server Offline');
    });

    state.socket.on('live_data', (payload) => {
      handleLiveData(payload);
    });

    state.socket.on('alert', (alertData) => {
      showAlert(alertData.message || 'High OA Risk Marker Detected');
    });

  } catch (err) {
    setConnStatus('error', 'WS Error');
  }
}

function reconnectWebSocket() {
  if (state.socket) {
    state.socket.connect();
    setConnStatus('connecting', 'Reconnecting...');
  } else {
    connectSocket();
  }
}

// ── DATA DISPATCHER ───────────────────────────────────────────
function handleLiveData(payload) {
  state.lastReading = payload;
  state.sessionCount++;

  const inf = payload.inference || {};
  if (inf.label === 'Early_OA') state.oaCount++;
  else if (inf.label === 'Normal') state.normalCount++;

  // Pulse Pinout Chips
  pulsePinChips();

  // 1. Update KPI Cards
  updateKPICards(payload);

  // 2. Update Risk Gauge
  const riskScore = inf.risk_score !== undefined ? inf.risk_score : 0;
  drawGauge(riskScore, inf.risk_level);

  // 3. Update Line Charts
  appendChartData(payload);

  // 4. Update 3D Knee Model
  const flexAngle = payload.sensors?.flex?.flex_angle_deg ?? 112;
  const jointTemp = payload.sensors?.temperature?.joint_temp_c ?? 33.2;
  const crepitus  = payload.sensors?.microphone?.crepitus_score ?? 0.05;
  const imuGyro   = payload.sensors?.imu?.gyro_range_deg ?? 105;
  updateKnee3D(flexAngle, jointTemp, crepitus, imuGyro);

  // 5. Update Multi-Sensor Radar
  updateRadarChart(payload);

  // 6. Update Comparison Grid
  updateComparisonGrid(payload);

  // 7. Append to Log Table
  appendLogRow(payload);

  // 8. Update Sensor Detail Cards
  updateSensorCards(payload);

  // 9. Alert on Critical OA
  if (inf.risk_level === 'CRITICAL' || inf.risk_level === 'HIGH') {
    showAlert(`⚠️ High OA Risk: Patient ${payload.patient_id} — Score: ${(riskScore * 100).toFixed(1)}%`);
  }

  // 10. Cache reading for Offline PWA mode
  try {
    const cached = JSON.parse(localStorage.getItem('oadetect_cached_readings') || '[]');
    cached.unshift(payload);
    if (cached.length > 30) cached.pop();
    localStorage.setItem('oadetect_cached_readings', JSON.stringify(cached));
  } catch (e) {}
}

// ── KPI CARDS ──────────────────────────────────────────────────
function updateKPICards(p) {
  const s = p.sensors || {};
  const mic  = s.microphone  || {};
  const temp = s.temperature || {};
  const flex = s.flex        || {};
  const imu  = s.imu         || {};

  // Joint Temp
  const jt = temp.joint_temp_c ?? 0;
  setText('kv-temp', `${jt.toFixed(1)}°C`);
  setText('kd-temp', `Ambient: ${(temp.ambient_temp_c ?? 28).toFixed(1)}°C | Δ ${(temp.temp_asymmetry ?? 0).toFixed(1)}°C`);
  setBar('kb-temp', (jt - 30) / 10 * 100);

  // Crepitus
  const cr = mic.crepitus_score ?? 0;
  setText('kv-crepitus', cr.toFixed(3));
  setText('kd-crepitus', `Freq: ${Math.round(mic.dominant_freq_hz ?? 0)} Hz | RMS: ${(mic.audio_rms ?? 0).toFixed(3)}`);
  setBar('kb-crep', cr * 100);

  // ROM
  const rom = flex.flex_angle_deg ?? 0;
  setText('kv-rom', `${Math.round(rom)}°`);
  setText('kd-rom', `Stiffness Index: ${(flex.flex_stiffness ?? 0).toFixed(2)}`);
  setBar('kb-rom', (rom / 140) * 100);

  // Gait Symmetry
  const sym = imu.step_symmetry ?? 0;
  setText('kv-gait', sym.toFixed(2));
  setText('kd-gait', `Gyro ROM: ${Math.round(imu.gyro_range_deg ?? 0)}°`);
  setBar('kb-gait', sym * 100);

  // Session Stats
  setText('kv-count', state.sessionCount);
  setText('kd-normal-oa', `Normal: ${state.normalCount} | OA: ${state.oaCount}`);
  setBar('kb-count', Math.min(100, (state.sessionCount / 50) * 100));
}

// ── SENSOR TILES ───────────────────────────────────────────────
function updateSensorCards(p) {
  const s = p.sensors || {};
  const mic  = s.microphone  || {};
  const temp = s.temperature || {};
  const imu  = s.imu         || {};
  const flex = s.flex        || {};

  setText('sv-rms',    (mic.audio_rms ?? 0).toFixed(4));
  setText('sv-freq',   `${Math.round(mic.dominant_freq_hz ?? 0)} Hz`);
  setText('sv-crep',   (mic.crepitus_score ?? 0).toFixed(3));

  setText('sv-joint-t', `${(temp.joint_temp_c ?? 0).toFixed(1)} °C`);
  setText('sv-amb-t',   `${(temp.ambient_temp_c ?? 0).toFixed(1)} °C`);
  setText('sv-temp-d',  `${(temp.temp_asymmetry ?? 0).toFixed(2)} °C`);

  setText('sv-ax',   (imu.accel_rms_x ?? 0).toFixed(2));
  setText('sv-gy',   `${Math.round(imu.gyro_range_deg ?? 0)}°`);
  setText('sv-sym',  (imu.step_symmetry ?? 0).toFixed(2));

  setText('sv-angle', `${Math.round(flex.flex_angle_deg ?? 0)}°`);
  setText('sv-stiff', (flex.flex_stiffness ?? 0).toFixed(2));
  setText('sv-rom2',  `${Math.round(flex.flex_angle_deg ?? 0)}°`);

  setText('sv-samples', state.sessionCount);
}

// ── GAUGE (CANVAS DRAWING) ─────────────────────────────────────
function drawGauge(score, level = 'LOW') {
  const canvas = document.getElementById('gauge-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;

  ctx.clearRect(0, 0, W, H);

  const cx = W / 2, cy = H - 12;
  const r  = 72;
  const startAngle = Math.PI;
  const endAngle   = 2 * Math.PI;

  // Background track
  ctx.beginPath();
  ctx.arc(cx, cy, r, startAngle, endAngle);
  ctx.lineWidth = 12;
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
  ctx.lineCap = 'round';
  ctx.stroke();

  // Color selection
  let gradColor = currentPalette.success;
  if (score > 0.75)      gradColor = currentPalette.accent;
  else if (score > 0.50) gradColor = currentPalette.warning;
  else if (score > 0.25) gradColor = currentPalette.primary;

  // Active progress arc
  const sweep = startAngle + (endAngle - startAngle) * Math.min(1, Math.max(0, score));
  ctx.beginPath();
  ctx.arc(cx, cy, r, startAngle, sweep);
  ctx.lineWidth = 12;
  ctx.strokeStyle = gradColor;
  ctx.lineCap = 'round';
  ctx.stroke();

  // Numeric text
  const pct = Math.round(score * 100);
  setText('gauge-value', `${pct}%`);
  const lvlEl = document.getElementById('gauge-risk-level');
  if (lvlEl) {
    lvlEl.textContent = level;
    lvlEl.style.color = gradColor;
  }

  // Update card border pulse
  const card = document.getElementById('risk-card');
  if (card) {
    card.className = `glass-card risk-card risk-${(level || 'low').toLowerCase()}`;
  }
}

// ── CHART.JS INITIALIZATION ────────────────────────────────────
function initCharts() {
  const chartOpts = (yLabel, yMin, yMax) => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: {
        labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 }, boxWidth: 12 }
      },
      tooltip: {
        backgroundColor: 'rgba(5, 10, 24, 0.85)',
        titleColor: '#e2eaff',
        bodyColor: '#94a3b8',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        borderWidth: 1,
      }
    },
    scales: {
      x: {
        display: false,
        grid: { color: 'rgba(255,255,255,0.03)' },
      },
      y: {
        min: yMin, max: yMax,
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } },
        title: { display: !!yLabel, text: yLabel, color: '#64748b', font: { size: 10 } }
      }
    }
  });

  // Audio Chart
  state.charts.audio = new Chart(document.getElementById('audioChart'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'RMS Amplitude', data: [], borderColor: currentPalette.primary, borderWidth: 2, tension: 0.3, pointRadius: 0 },
        { label: 'Crepitus Score', data: [], borderColor: currentPalette.accent, borderWidth: 2, tension: 0.3, pointRadius: 0 },
      ]
    },
    options: chartOpts('Audio Activity', 0, 1)
  });

  // Temp Chart
  state.charts.temp = new Chart(document.getElementById('tempChart'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'Joint Temp (°C)', data: [], borderColor: currentPalette.warning, borderWidth: 2, tension: 0.3, pointRadius: 0 },
        { label: 'Temp Asymmetry (°C)', data: [], borderColor: currentPalette.accent, borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0 },
      ]
    },
    options: chartOpts('°C', 28, 40)
  });

  // IMU Chart
  state.charts.imu = new Chart(document.getElementById('imuChart'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'Gait Symmetry', data: [], borderColor: currentPalette.success, borderWidth: 2, tension: 0.3, pointRadius: 0 },
        { label: 'Gyro ROM (°/s)', data: [], borderColor: currentPalette.secondary, borderWidth: 1.5, pointRadius: 0 },
      ]
    },
    options: chartOpts('Metric', 0, 1.2)
  });

  // Flex Chart
  state.charts.flex = new Chart(document.getElementById('flexChart'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'Flex Angle (°)', data: [], borderColor: currentPalette.primary, borderWidth: 2, tension: 0.3, pointRadius: 0 },
        { label: 'Stiffness (0–1)', data: [], borderColor: currentPalette.accent, borderWidth: 1.5, pointRadius: 0 },
      ]
    },
    options: chartOpts('Degrees / Ratio', 0, 140)
  });

  // Radar Chart
  initRadarChart();
}

function appendChartData(payload) {
  const ts = new Date(payload.timestamp || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const s  = payload.sensors || {};
  const mic  = s.microphone  || {};
  const temp = s.temperature || {};
  const imu  = s.imu         || {};
  const flex = s.flex        || {};

  const push = (chart, values) => {
    chart.data.labels.push(ts);
    if (chart.data.labels.length > MAX_POINTS) chart.data.labels.shift();
    values.forEach((v, idx) => {
      chart.data.datasets[idx].data.push(v);
      if (chart.data.datasets[idx].data.length > MAX_POINTS) chart.data.datasets[idx].data.shift();
    });
    chart.update('none');
  };

  push(state.charts.audio, [mic.audio_rms ?? 0, mic.crepitus_score ?? 0]);
  push(state.charts.temp,  [temp.joint_temp_c ?? 33, temp.temp_asymmetry ?? 0]);
  push(state.charts.imu,   [imu.step_symmetry ?? 0.9, (imu.gyro_range_deg ?? 80) / 100]);
  push(state.charts.flex,  [flex.flex_angle_deg ?? 110, (flex.flex_stiffness ?? 0.2) * 100]);
}

// ── RADAR CHART ────────────────────────────────────────────────
function initRadarChart() {
  const canvas = document.getElementById('radarChart');
  if (!canvas) return;

  const labels = ['Crepitus', 'Temp Δ', 'Stiffness', 'Gait Asym', 'RMS Amp'];

  state.radarChart = new Chart(canvas, {
    type: 'radar',
    data: {
      labels,
      datasets: [
        {
          label: 'Current Patient',
          data: [0.1, 0.1, 0.1, 0.1, 0.1],
          borderColor: currentPalette.primary,
          backgroundColor: hexToRgba(currentPalette.primary, 0.25),
          pointBackgroundColor: currentPalette.primary,
          borderWidth: 2,
        },
        {
          label: 'Normal Baseline',
          data: [0.05, 0.05, 0.12, 0.08, 0.11],
          borderColor: currentPalette.success,
          backgroundColor: 'rgba(16, 185, 129, 0.12)',
          pointBackgroundColor: currentPalette.success,
          borderWidth: 1.5,
        },
        {
          label: 'OA Baseline',
          data: [0.65, 0.55, 0.67, 0.38, 0.66],
          borderColor: currentPalette.accent,
          backgroundColor: 'rgba(244, 63, 94, 0.12)',
          pointBackgroundColor: currentPalette.accent,
          borderWidth: 1.5,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        r: {
          min: 0, max: 1,
          ticks: { display: false, stepSize: 0.2 },
          grid: { color: 'rgba(255, 255, 255, 0.08)' },
          angleLines: { color: 'rgba(255, 255, 255, 0.08)' },
          pointLabels: { color: '#94a3b8', font: { family: 'Inter', size: 11, weight: '600' } }
        }
      },
      plugins: { legend: { display: false } }
    }
  });
}

function updateRadarChart(payload) {
  if (!state.radarChart) return;
  const s = payload.sensors || {};
  const mic  = s.microphone  || {};
  const temp = s.temperature || {};
  const flex = s.flex        || {};
  const imu  = s.imu         || {};

  const normCrep  = Math.min(1, (mic.crepitus_score ?? 0) / 1.0);
  const normTemp  = Math.min(1, (temp.temp_asymmetry ?? 0) / 2.0);
  const normStiff = Math.min(1, (flex.flex_stiffness ?? 0) / 1.0);
  const normGait  = Math.min(1, 1 - (imu.step_symmetry ?? 1));
  const normRms   = Math.min(1, (mic.audio_rms ?? 0) / 0.15);

  state.radarChart.data.datasets[0].data = [normCrep, normTemp, normStiff, normGait, normRms];
  state.radarChart.update('none');
}

// ── SIDE-BY-SIDE COMPARISON GRID ──────────────────────────────
function updateComparisonGrid(payload) {
  const container = document.getElementById('comparison-grid');
  if (!container) return;

  const s = payload.sensors || {};
  const flat = {
    crepitus_score:   s.microphone?.crepitus_score   ?? 0,
    joint_temp_c:     s.temperature?.joint_temp_c     ?? 33.2,
    temp_asymmetry:   s.temperature?.temp_asymmetry   ?? 0.1,
    gyro_range_deg:   s.imu?.gyro_range_deg           ?? 105,
    step_symmetry:    s.imu?.step_symmetry            ?? 0.92,
    flex_angle_deg:   s.flex?.flex_angle_deg          ?? 112,
    flex_stiffness:   s.flex?.flex_stiffness          ?? 0.12,
  };

  container.innerHTML = FEATURE_DISPLAY.map(feat => {
    const curVal  = flat[feat.key];
    const normVal = NORMAL_PROFILE[feat.key];
    const oaVal   = OA_PROFILE[feat.key];

    const curPct  = Math.min(100, Math.max(0, (curVal  / feat.max) * 100));
    const normPct = Math.min(100, Math.max(0, (normVal / feat.max) * 100));
    const oaPct   = Math.min(100, Math.max(0, (oaVal   / feat.max) * 100));

    const fmt = v => feat.unit === '°C' ? `${v.toFixed(1)}°` :
                     feat.unit === '°'  ? `${Math.round(v)}°` :
                     v.toFixed(2);

    return `
      <div class="comp-row">
        <div class="comp-label">${feat.label}</div>
        <div class="comp-bars">
          <div class="comp-bar-wrap" title="Current">
            <div class="comp-bar-track">
              <div class="comp-bar-fill bar-current" style="width:${curPct}%"></div>
            </div>
          </div>
          <div class="comp-bar-wrap" title="Normal">
            <div class="comp-bar-track">
              <div class="comp-bar-fill bar-normal" style="width:${normPct}%"></div>
            </div>
          </div>
          <div class="comp-bar-wrap" title="OA">
            <div class="comp-bar-track">
              <div class="comp-bar-fill bar-oa" style="width:${oaPct}%"></div>
            </div>
          </div>
        </div>
        <div class="comp-val current-val">${fmt(curVal)}</div>
        <div class="comp-val normal-val">${fmt(normVal)}</div>
      </div>
    `;
  }).join('');
}

// ── LOG TABLE ──────────────────────────────────────────────────
function appendLogRow(p) {
  const tbody = document.getElementById('log-tbody');
  if (!tbody) return;

  const empty = tbody.querySelector('.empty-row');
  if (empty) empty.remove();

  const inf = p.inference || {};
  const s   = p.sensors   || {};
  const ts  = new Date(p.timestamp || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  const labelClass = (inf.label || 'unknown').toLowerCase();
  const riskClass  = `risk-${(inf.risk_level || 'low').toLowerCase()}`;
  const riskPct    = inf.risk_score !== undefined ? `${Math.round(inf.risk_score * 100)}%` : '--';

  const row = document.createElement('tr');
  row.innerHTML = `
    <td>${ts}</td>
    <td><strong>${p.patient_id || 'PATIENT_001'}</strong></td>
    <td><span class="label-badge ${labelClass}">${inf.label || 'UNKNOWN'}</span></td>
    <td><span class="risk-mini ${riskClass}">${riskPct} (${inf.risk_level || '—'})</span></td>
    <td>${(s.temperature?.joint_temp_c ?? 0).toFixed(1)}°C</td>
    <td>${Math.round(s.flex?.flex_angle_deg ?? 0)}°</td>
    <td>${(s.microphone?.crepitus_score ?? 0).toFixed(3)}</td>
  `;

  tbody.insertBefore(row, tbody.firstChild);

  // Keep max 20 rows
  while (tbody.children.length > 20) {
    tbody.removeChild(tbody.lastChild);
  }
}

// ── SIMULATION / DEMO STREAM ───────────────────────────────────
function toggleDemo() {
  if (state.demoRunning) {
    stopDemo();
  } else {
    startDemo();
  }
}

function startDemo() {
  state.demoRunning = true;
  const btn = document.getElementById('demo-btn');
  if (btn) {
    btn.innerHTML = '<span class="btn-icon">⏹</span> Stop Demo';
    btn.classList.add('active');
  }

  // Try backend demo first
  fetch(`${SERVER_URL}/api/demo/start`, { method: 'POST' })
    .catch(() => console.info('[DEMO] Using browser-side simulation'));

  // Run local simulation stream at 1Hz
  if (!state.demoInterval) {
    state.demoInterval = setInterval(() => {
      const mode = Math.random() > 0.45 ? 'oa' : 'normal';
      const sample = generateMockSample(mode);
      handleLiveData(sample);
    }, 1000);
  }
}

function stopDemo() {
  state.demoRunning = false;
  const btn = document.getElementById('demo-btn');
  if (btn) {
    btn.innerHTML = '<span class="btn-icon">▶</span> Live Simulation';
    btn.classList.remove('active');
  }

  fetch(`${SERVER_URL}/api/demo/stop`, { method: 'POST' }).catch(() => {});
  if (state.demoInterval) {
    clearInterval(state.demoInterval);
    state.demoInterval = null;
  }
}

function generateMockSample(mode) {
  const isOA = mode === 'oa';
  const r = (mean, std) => Math.max(0, mean + (Math.random() - 0.5) * 2 * std);

  const audio_rms        = isOA ? r(0.10, 0.03)  : r(0.018, 0.005);
  const dominant_freq_hz = isOA ? r(520, 100)    : r(150, 30);
  const crepitus_score   = isOA ? r(0.68, 0.15)  : r(0.05, 0.03);
  const joint_temp_c     = isOA ? r(36.3, 0.6)   : r(33.2, 0.4);
  const temp_asymmetry   = isOA ? r(1.4, 0.4)    : r(0.1, 0.06);
  const gyro_range_deg   = isOA ? r(50, 15)      : r(105, 12);
  const step_symmetry    = isOA ? r(0.60, 0.10)  : r(0.92, 0.04);
  const flex_angle_deg   = isOA ? r(52, 14)      : r(112, 10);
  const flex_stiffness   = isOA ? r(0.70, 0.12)  : r(0.12, 0.05);

  const riskScore = isOA ? 0.70 + Math.random() * 0.28 : 0.05 + Math.random() * 0.20;
  const riskLevel = riskScore > 0.80 ? 'CRITICAL' : riskScore > 0.60 ? 'HIGH' : riskScore > 0.30 ? 'MODERATE' : 'LOW';

  return {
    patient_id: getSelectedPatient(),
    timestamp: new Date().toISOString(),
    sensors: {
      microphone:  { audio_rms, dominant_freq_hz, crepitus_score },
      temperature: { joint_temp_c, ambient_temp_c: 28.0, temp_asymmetry },
      imu:         { accel_rms_x: 0.8, gyro_range_deg, step_symmetry },
      flex:        { flex_angle_deg, flex_stiffness }
    },
    inference: {
      risk_score: riskScore,
      label: isOA ? 'Early_OA' : 'Normal',
      risk_level: riskLevel,
      confidence: 0.92 + Math.random() * 0.07,
    }
  };
}

// ── UTILITY HELPERS ────────────────────────────────────────────
function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function setBar(id, pct) {
  const el = document.getElementById(id);
  if (el) el.style.width = `${Math.min(100, Math.max(0, pct))}%`;
}

function setConnStatus(cls, text) {
  const dot = document.getElementById('conn-dot');
  const txt = document.getElementById('conn-text');
  if (dot) dot.className = `dot ${cls}`;
  if (txt) txt.textContent = text;
}

function setDeviceStatus(connected, name = 'ESP32-S3 N16R8') {
  const pill = document.getElementById('device-pill');
  if (pill) {
    pill.style.borderColor = connected ? 'var(--color-primary)' : 'var(--glass-border)';
    pill.style.color = connected ? 'var(--color-primary)' : 'var(--text-secondary)';
  }
}

function showAlert(msg) {
  const banner = document.getElementById('alert-banner');
  const text   = document.getElementById('alert-text');
  if (banner && text) {
    text.textContent = msg;
    banner.style.display = 'flex';
  }
}

function switchChart(panel) {
  ['audio', 'temp', 'imu', 'flex'].forEach(p => {
    const el = document.getElementById(`chart-${p}`);
    if (el) el.classList.toggle('hidden', p !== panel);
  });
  document.querySelectorAll('.tab-btn').forEach((btn, i) => {
    const panels = ['audio', 'temp', 'imu', 'flex'];
    btn.classList.toggle('active', panels[i] === panel);
  });
}

function clearLog() {
  const tbody = document.getElementById('log-tbody');
  if (tbody) tbody.innerHTML = '<tr class="empty-row"><td colspan="7">Telemetry log cleared</td></tr>';
  state.sessionCount = 0;
  state.normalCount  = 0;
  state.oaCount      = 0;
}

function getSelectedPatient() {
  return document.getElementById('patient-select')?.value ?? 'PATIENT_001';
}

function startClock() {
  const el = document.getElementById('footer-time');
  const topEl = document.getElementById('topbar-time');
  setInterval(() => {
    const formatted = new Date().toLocaleString('en-IN', {
      weekday: 'short', year: 'numeric', month: 'short',
      day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
    if (el) el.textContent = formatted;
    if (topEl) topEl.textContent = formatted;
  }, 1000);
}

// ── JOINT SIDE & SIDEBAR CONTROLLERS ───────────────────────────
let currentJointSide = 'LEFT';
function setJointSide(side) {
  currentJointSide = side;
  const leftBtn = document.getElementById('side-left-btn');
  const rightBtn = document.getElementById('side-right-btn');
  if (leftBtn) leftBtn.classList.toggle('active', side === 'LEFT');
  if (rightBtn) rightBtn.classList.toggle('active', side === 'RIGHT');
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar-panel');
  if (sidebar) sidebar.classList.toggle('open');
}

// ── FEATURE EXPANSION MODULES v2.0 ─────────────────────────────

// ── 1. TAB ROUTER ──────────────────────────────────────────────
let activeTab = 'monitor';
const TAB_TITLES = {
  monitor:     'Live Biomechanical & Diagnostic Telemetry',
  patients:    'Patient Profile & Clinical Registry',
  cohort:      'Multi-Patient Population Cohort Analytics',
  spectrogram: 'Acoustic Joint Crepitus & FFT Waterfall',
  ai:          'AI Clinical Insights & Assistive Recommendations'
};

function switchTab(tabId) {
  activeTab = tabId;
  document.querySelectorAll('.tab-nav-btn').forEach(btn => {
    btn.classList.toggle('active', btn.id === `tab-btn-${tabId}`);
  });
  document.querySelectorAll('.tab-content').forEach(panel => {
    panel.classList.toggle('active', panel.id === `tab-${tabId}`);
  });

  const pageTitleEl = document.getElementById('topbar-page-title');
  if (pageTitleEl && TAB_TITLES[tabId]) {
    pageTitleEl.textContent = TAB_TITLES[tabId];
  }

  // Close mobile sidebar if open
  const sidebar = document.getElementById('sidebar-panel');
  if (sidebar && sidebar.classList.contains('open')) {
    sidebar.classList.remove('open');
  }

  // Trigger resize event so charts / WebGL canvas adjust to viewport immediately
  setTimeout(() => window.dispatchEvent(new Event('resize')), 50);

  if (tabId === 'patients') {
    loadPatients();
  } else if (tabId === 'cohort') {
    loadCohortData();
  } else if (tabId === 'spectrogram') {
    initSpectrogramIfNeeded();
  } else if (tabId === 'ai') {
    checkLLMStatus();
    if (activeAITab === 'diet') loadDietPlan();
    else if (activeAITab === 'exercises') loadExercises();
  }
}

// ── 2. PATIENT PROFILE MANAGER ─────────────────────────────────
async function loadPatients() {
  const grid = document.getElementById('patient-grid');
  if (!grid) return;
  try {
    const res = await fetch(`${SERVER_URL}/api/patients`);
    const data = await res.json();
    const patients = data.patients || [];
    renderPatientGrid(patients);
    updatePatientSelect(patients);
  } catch (err) {
    console.warn('[PATIENT] Load error, using clinical demo profiles:', err);
    const demoPatients = [
      { patient_id: 'PATIENT_001', name: 'Rajesh Sen', age: 62, gender: 'Male', bmi: 28.4, oa_grade: '3', comorbidities: 'Hypertension, Prior Meniscus Tear', notes: 'Reports morning stiffness >45 mins, pain aggravated by stairs.' },
      { patient_id: 'PATIENT_002', name: 'Sunita Devi', age: 54, gender: 'Female', bmi: 25.1, oa_grade: '1', comorbidities: 'Type 2 Diabetes', notes: 'Early crepitus detected in right patellofemoral joint.' },
      { patient_id: 'PATIENT_003', name: 'Bipul Bora', age: 47, gender: 'Male', bmi: 23.8, oa_grade: '0', comorbidities: 'None', notes: 'Asymptomatic screening candidate.' }
    ];
    renderPatientGrid(demoPatients);
    updatePatientSelect(demoPatients);
  }
}

function updatePatientSelect(patients) {
  const sel = document.getElementById('patient-select');
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = patients.map(p => `<option value="${p.patient_id}">${p.name || p.patient_id} (${p.patient_id})</option>`).join('') + '<option value="ALL">All Cohort</option>';
  if (cur && [...sel.options].some(o => o.value === cur)) {
    sel.value = cur;
  }
}

function renderPatientGrid(patients) {
  const grid = document.getElementById('patient-grid');
  if (!grid) return;
  if (!patients.length) {
    grid.innerHTML = '<div class="loading-placeholder"><span>No patients registered yet. Click "Add New Patient" above.</span></div>';
    return;
  }
  grid.innerHTML = patients.map(p => {
    const initials = (p.name || 'PT').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
    const grade = p.oa_grade !== undefined ? p.oa_grade : 'Unknown';
    const gradeBadge = (grade === '3' || grade === '4') ? 'risk-critical' : (grade === '2') ? 'risk-high' : (grade === '1') ? 'risk-moderate' : 'risk-low';
    return `
      <div class="patient-card">
        <div class="patient-card-header">
          <div class="patient-card-info">
            <div class="patient-card-avatar">${initials}</div>
            <div>
              <div class="patient-name-title">${escapeHtml(p.name || 'Anonymous Patient')}</div>
              <div class="patient-id-sub">${p.patient_id}</div>
            </div>
          </div>
          <span class="risk-mini ${gradeBadge}">KL ${grade}</span>
        </div>
        <div class="patient-kpi-row">
          <div class="patient-kpi-item">
            <span>Age / Sex</span>
            <strong>${p.age || '--'} / ${p.gender || '--'}</strong>
          </div>
          <div class="patient-kpi-item">
            <span>BMI</span>
            <strong>${p.bmi ? `${p.bmi} kg/m²` : '--'}</strong>
          </div>
          <div class="patient-kpi-item">
            <span>Comorbidities</span>
            <strong title="${escapeHtml(p.comorbidities || 'None')}">${escapeHtml(p.comorbidities ? (p.comorbidities.length > 15 ? p.comorbidities.slice(0, 14) + '…' : p.comorbidities) : 'None')}</strong>
          </div>
        </div>
        ${p.notes ? `<div style="font-size:12px;color:#94a3b8;line-height:1.4">${escapeHtml(p.notes)}</div>` : ''}
        <div class="patient-card-actions">
          <button class="btn-mini primary" onclick="selectPatientForMonitoring('${p.patient_id}')">
            <span>▶ Monitor</span>
          </button>
          <button class="btn-mini" onclick="editPatient('${p.patient_id}')">
            <span>✏ Edit</span>
          </button>
          <button class="btn-mini danger" onclick="deletePatient('${p.patient_id}')">
            <span>🗑</span>
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function openPatientForm(patient = null) {
  const modal = document.getElementById('patient-modal');
  if (!modal) return;
  const title = document.getElementById('patient-form-title');
  if (title) title.textContent = patient ? 'Edit Patient Profile' : 'Add New Patient';

  document.getElementById('pf-id').value = patient ? patient.patient_id : '';
  document.getElementById('pf-pid').value = patient ? patient.patient_id : '';
  document.getElementById('pf-pid').disabled = !!patient;
  document.getElementById('pf-name').value = patient ? (patient.name || '') : '';
  document.getElementById('pf-age').value = patient ? (patient.age || '') : '';
  document.getElementById('pf-gender').value = patient ? (patient.gender || '') : '';
  document.getElementById('pf-bmi').value = patient ? (patient.bmi || '') : '';
  document.getElementById('pf-grade').value = patient ? (patient.oa_grade || 'Unknown') : 'Unknown';
  document.getElementById('pf-comorbid').value = patient ? (patient.comorbidities || '') : '';
  document.getElementById('pf-notes').value = patient ? (patient.notes || '') : '';

  modal.style.display = 'flex';
}

function closePatientForm() {
  const modal = document.getElementById('patient-modal');
  if (modal) modal.style.display = 'none';
}

async function savePatient(e) {
  if (e) e.preventDefault();
  const editId = document.getElementById('pf-id').value;
  const patientId = document.getElementById('pf-pid').value.trim() || undefined;
  const body = {
    patient_id: editId || patientId,
    name: document.getElementById('pf-name').value.trim(),
    age: parseInt(document.getElementById('pf-age').value) || null,
    gender: document.getElementById('pf-gender').value,
    bmi: parseFloat(document.getElementById('pf-bmi').value) || null,
    oa_grade: document.getElementById('pf-grade').value,
    comorbidities: document.getElementById('pf-comorbid').value.trim(),
    notes: document.getElementById('pf-notes').value.trim()
  };

  try {
    const url = editId ? `${SERVER_URL}/api/patients/${editId}` : `${SERVER_URL}/api/patients`;
    const method = editId ? 'PUT' : 'POST';
    await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
  } catch (err) {
    console.warn('[PATIENT] Save error:', err);
  }

  closePatientForm();
  loadPatients();
}

async function editPatient(patientId) {
  try {
    const res = await fetch(`${SERVER_URL}/api/patients/${patientId}`);
    if (res.ok) {
      const data = await res.json();
      openPatientForm(data.patient || data);
      return;
    }
  } catch (e) {}
  openPatientForm({ patient_id: patientId, name: patientId });
}

async function deletePatient(patientId) {
  if (!confirm(`Are you sure you want to delete patient ${patientId}?`)) return;
  try {
    await fetch(`${SERVER_URL}/api/patients/${patientId}`, { method: 'DELETE' });
  } catch (e) {}
  loadPatients();
}

function selectPatientForMonitoring(patientId) {
  const sel = document.getElementById('patient-select');
  if (sel) sel.value = patientId;
  onPatientChange(patientId);
  switchTab('monitor');
}

function onPatientChange(patientId) {
  if (state.socket && state.socket.connected) {
    state.socket.emit('subscribe', { patient_id: patientId });
  }
  clearLog();
  console.log(`[PATIENT] Switched active patient to: ${patientId}`);
}

// ── 3. MULTI-PATIENT COHORT ANALYTICS ──────────────────────────
let cohortChartInstance = null;
async function loadCohortData() {
  try {
    const res = await fetch(`${SERVER_URL}/api/cohort`);
    const data = await res.json();
    renderCohortKPIs(data);
    renderCohortChart(data);
    renderHighRiskList(data.high_risk_patients || []);
    renderCohortGrid(data.patients || []);
  } catch (err) {
    console.warn('[COHORT] Fetch error, using fallback:', err);
    const mock = {
      total_patients: 12,
      high_risk_count: 4,
      total_sessions: 148,
      oa_readings_count: 52,
      distribution: { normal: 6, early_oa: 4, critical: 2 },
      high_risk_patients: [
        { patient_id: 'PATIENT_001', name: 'Rajesh Sen', risk_score: 0.84, oa_grade: '3' },
        { patient_id: 'PATIENT_005', name: 'Geeta Baruah', risk_score: 0.78, oa_grade: '3' },
        { patient_id: 'PATIENT_008', name: 'Manish Kalita', risk_score: 0.72, oa_grade: '2' }
      ],
      patients: [
        { patient_id: 'PATIENT_001', name: 'Rajesh Sen', age: 62, risk_score: 0.84, oa_grade: '3', sessions: 28 },
        { patient_id: 'PATIENT_002', name: 'Sunita Devi', age: 54, risk_score: 0.38, oa_grade: '1', sessions: 14 },
        { patient_id: 'PATIENT_003', name: 'Bipul Bora', age: 47, risk_score: 0.12, oa_grade: '0', sessions: 9 },
        { patient_id: 'PATIENT_004', name: 'Ananya Roy', age: 59, risk_score: 0.45, oa_grade: '2', sessions: 19 },
        { patient_id: 'PATIENT_005', name: 'Geeta Baruah', age: 68, risk_score: 0.78, oa_grade: '3', sessions: 32 },
        { patient_id: 'PATIENT_006', name: 'Pranab Saikia', age: 51, risk_score: 0.22, oa_grade: '0', sessions: 8 }
      ]
    };
    renderCohortKPIs(mock);
    renderCohortChart(mock);
    renderHighRiskList(mock.high_risk_patients);
    renderCohortGrid(mock.patients);
  }
}

function renderCohortKPIs(data) {
  setText('cohort-pt-count', data.total_patients ?? data.patients?.length ?? 0);
  setText('cohort-highrisk', data.high_risk_count ?? (data.high_risk_patients?.length ?? 0));
  setText('cohort-sessions', data.total_sessions ?? 0);
  setText('cohort-oa', data.oa_readings_count ?? 0);
}

function renderCohortChart(data) {
  const ctx = document.getElementById('cohortChart')?.getContext('2d');
  if (!ctx || typeof Chart === 'undefined') return;

  const dist = data.distribution || { normal: 6, early_oa: 4, critical: 2 };
  const labels = ['Normal (Low Risk)', 'Early OA (Moderate)', 'Advanced OA (High/Critical)'];
  const vals = [dist.normal || 0, dist.early_oa || 0, dist.critical || 0];

  if (cohortChartInstance) cohortChartInstance.destroy();

  cohortChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Patients',
        data: vals,
        backgroundColor: [
          'rgba(16, 185, 129, 0.7)',
          'rgba(245, 158, 11, 0.7)',
          'rgba(244, 63, 94, 0.7)'
        ],
        borderColor: ['#10b981', '#f59e0b', '#f43f5e'],
        borderWidth: 1.5,
        borderRadius: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(255, 255, 255, 0.06)' },
          ticks: { color: '#94a3b8', stepSize: 1 }
        },
        x: {
          grid: { display: false },
          ticks: { color: '#e2e8f0', font: { family: 'Inter', size: 11, weight: '600' } }
        }
      },
      plugins: { legend: { display: false } }
    }
  });
}

function renderHighRiskList(list) {
  const container = document.getElementById('high-risk-list');
  if (!container) return;
  if (!list.length) {
    container.innerHTML = '<div style="opacity:0.5;font-size:12px;padding:12px">No high risk patients detected.</div>';
    return;
  }
  container.innerHTML = list.slice(0, 3).map(p => `
    <div class="high-risk-item">
      <div class="high-risk-patient">
        <span class="high-risk-tag">CRITICAL</span>
        <div>
          <div style="font-weight:700;color:#fff">${escapeHtml(p.name || p.patient_id)}</div>
          <div style="font-size:11px;color:#94a3b8;font-family:'JetBrains Mono'">${p.patient_id} · KL Grade ${p.oa_grade || '3'}</div>
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:10px">
        <span style="font-family:'JetBrains Mono';color:#f43f5e;font-weight:800;font-size:15px">${Math.round((p.risk_score || 0.8) * 100)}%</span>
        <button class="btn-mini primary" onclick="selectPatientForMonitoring('${p.patient_id}')">Monitor</button>
      </div>
    </div>
  `).join('');
}

function renderCohortGrid(patients) {
  const container = document.getElementById('cohort-grid');
  if (!container) return;
  container.innerHTML = patients.map(p => {
    const risk = p.risk_score || 0;
    const riskBadge = risk > 0.6 ? 'risk-critical' : risk > 0.3 ? 'risk-moderate' : 'risk-low';
    return `
      <div class="patient-card" style="padding:16px">
        <div class="patient-card-header">
          <div>
            <div style="font-weight:700;color:#fff">${escapeHtml(p.name || p.patient_id)}</div>
            <div style="font-size:11px;color:#94a3b8">${p.patient_id} · Age ${p.age || '--'}</div>
          </div>
          <span class="risk-mini ${riskBadge}">${Math.round(risk * 100)}% Risk</span>
        </div>
        <div style="margin-top:8px;display:flex;justify-content:space-between;font-size:11px;color:#94a3b8">
          <span>Sessions: <strong>${p.sessions || 1}</strong></span>
          <span>Grade: <strong>KL ${p.oa_grade || '0'}</strong></span>
        </div>
        <div class="patient-card-actions" style="margin-top:12px">
          <button class="btn-mini primary" onclick="selectPatientForMonitoring('${p.patient_id}')">Live Feed</button>
        </div>
      </div>
    `;
  }).join('');
}

// ── 4. ACOUSTIC SPECTROGRAM VIEWER ─────────────────────────────
const specState = {
  canvas: null,
  ctx: null,
  audioCtx: null,
  analyser: null,
  micStream: null,
  micActive: false,
  simActive: false,
  simInterval: null,
  fftChart: null,
  crepEventsCount: 0
};

function initSpectrogramIfNeeded() {
  const canvas = document.getElementById('spectrogram-canvas');
  if (!canvas) return;
  if (!specState.canvas) {
    specState.canvas = canvas;
    specState.ctx = canvas.getContext('2d', { willReadFrequently: true });
    resizeSpectrogramCanvas();
    window.addEventListener('resize', resizeSpectrogramCanvas);
    initFFTBarChart();
  }
  if (!specState.micActive && !specState.simActive) {
    toggleSimulatedSpectrogram();
  }
}

function resizeSpectrogramCanvas() {
  if (!specState.canvas) return;
  const rect = specState.canvas.parentElement.getBoundingClientRect();
  specState.canvas.width = rect.width || 600;
  specState.canvas.height = rect.height || 380;
  if (specState.ctx) {
    specState.ctx.fillStyle = '#020617';
    specState.ctx.fillRect(0, 0, specState.canvas.width, specState.canvas.height);
  }
}

function initFFTBarChart() {
  const canvas = document.getElementById('fftBarChart');
  if (!canvas || typeof Chart === 'undefined') return;
  if (specState.fftChart) return;

  const binCount = 16;
  const labels = ['100Hz','200Hz','300Hz','400Hz','500Hz','600Hz','700Hz','800Hz','1k','1.5k','2k','3k','4k','5k','6k','8k'];

  specState.fftChart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: new Array(binCount).fill(0),
        backgroundColor: labels.map(l => (parseInt(l) >= 300 && parseInt(l) <= 800) ? 'rgba(245, 158, 11, 0.8)' : 'rgba(34, 211, 238, 0.6)'),
        borderRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { min: 0, max: 255, display: false },
        x: { ticks: { color: '#64748b', font: { size: 9 } }, grid: { display: false } }
      },
      plugins: { legend: { display: false } }
    }
  });
}

async function toggleMicSpectrogram() {
  const btn = document.getElementById('spec-mic-btn');
  if (specState.micActive) {
    if (specState.micStream) {
      specState.micStream.getTracks().forEach(t => t.stop());
      specState.micStream = null;
    }
    specState.micActive = false;
    if (btn) btn.classList.remove('active');
    document.getElementById('spec-live-dot')?.classList.remove('pulse');
    return;
  }

  if (specState.simActive) toggleSimulatedSpectrogram();

  try {
    specState.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    specState.analyser = specState.audioCtx.createAnalyser();
    specState.analyser.fftSize = 1024;
    specState.analyser.smoothingTimeConstant = 0.8;

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    specState.micStream = stream;
    const source = specState.audioCtx.createMediaStreamSource(stream);
    source.connect(specState.analyser);

    specState.micActive = true;
    if (btn) btn.classList.add('active');
    document.getElementById('spec-live-dot')?.classList.add('pulse');

    renderWaterfallLoop();
  } catch (err) {
    alert('Microphone access denied or unavailable: ' + err.message);
  }
}

function toggleSimulatedSpectrogram() {
  if (specState.simActive) {
    clearInterval(specState.simInterval);
    specState.simInterval = null;
    specState.simActive = false;
    return;
  }

  if (specState.micActive) toggleMicSpectrogram();

  specState.simActive = true;
  document.getElementById('spec-live-dot')?.classList.add('pulse');

  const bufferLen = 512;
  const mockFreqData = new Uint8Array(bufferLen);

  specState.simInterval = setInterval(() => {
    const crep = state.lastReading?.sensors?.microphone?.crepitus_score ?? (0.1 + Math.random() * 0.6);
    const isBurst = Math.random() < (crep * 0.8);

    for (let i = 0; i < bufferLen; i++) {
      let val = Math.random() * 25;
      if (i >= 15 && i <= 45 && isBurst) {
        val += 90 + Math.random() * 140 * crep;
      }
      mockFreqData[i] = Math.min(255, val);
    }

    drawWaterfallSlice(mockFreqData);
    updateSpectrogramHUD(mockFreqData, isBurst, crep);
  }, 50);
}

function renderWaterfallLoop() {
  if (!specState.micActive || !specState.analyser) return;
  const bufferLen = specState.analyser.frequencyBinCount;
  const dataArray = new Uint8Array(bufferLen);

  function draw() {
    if (!specState.micActive) return;
    specState.analyser.getByteFrequencyData(dataArray);
    drawWaterfallSlice(dataArray);
    updateSpectrogramHUD(dataArray, false, 0);
    requestAnimationFrame(draw);
  }
  draw();
}

function drawWaterfallSlice(freqArray) {
  const { canvas, ctx } = specState;
  if (!canvas || !ctx) return;
  const w = canvas.width;
  const h = canvas.height;

  ctx.drawImage(canvas, 2, 0, w - 2, h, 0, 0, w - 2, h);

  const colX = w - 2;
  const numBins = Math.min(freqArray.length, 256);

  for (let y = 0; y < h; y++) {
    const binIdx = Math.floor(((h - 1 - y) / h) * numBins);
    const val = freqArray[binIdx] || 0;
    ctx.fillStyle = getSpectrogramColor(val);
    ctx.fillRect(colX, y, 2, 1);
  }
}

function getSpectrogramColor(val) {
  if (val < 25) return '#020617';
  if (val < 60) return '#0c4a6e';
  if (val < 110) return '#0284c7';
  if (val < 160) return '#22d3ee';
  if (val < 210) return '#f59e0b';
  return '#f43f5e';
}

function updateSpectrogramHUD(freqArray, isBurst, crepScore) {
  let maxVal = 0;
  let maxIdx = 0;
  let crepBandEnergy = 0;
  let totalEnergy = 0;

  for (let i = 0; i < Math.min(freqArray.length, 128); i++) {
    const v = freqArray[i];
    totalEnergy += v;
    if (v > maxVal) { maxVal = v; maxIdx = i; }
    if (i >= 14 && i <= 40) crepBandEnergy += v;
  }

  const nyquist = 22050;
  const domFreq = Math.round((maxIdx / freqArray.length) * nyquist);
  const crepPct = totalEnergy > 0 ? Math.round((crepBandEnergy / totalEnergy) * 100) : 0;
  const peakDb = Math.round(20 * Math.log10((maxVal || 1) / 255));

  setText('spec-dom-freq', `${domFreq} Hz`);
  setText('spec-crep-energy', `${crepPct}%`);
  setText('spec-peak', `${peakDb} dB`);

  if (specState.fftChart) {
    const step = Math.floor(64 / 16);
    const sampleVals = [];
    for (let i = 0; i < 16; i++) sampleVals.push(freqArray[i * step] || 0);
    specState.fftChart.data.datasets[0].data = sampleVals;
    specState.fftChart.update('none');
  }

  if (crepPct > 45 || isBurst || crepScore > 0.55) {
    specState.crepEventsCount++;
    setText('spec-events', specState.crepEventsCount);
    appendCrepEvent(domFreq, peakDb);
  }
}

function appendCrepEvent(freq, db) {
  const log = document.getElementById('crep-event-log');
  if (!log) return;
  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const div = document.createElement('div');
  div.className = 'crep-event-row';
  div.innerHTML = `<span>${time} · Burst</span><strong>${freq}Hz (${db}dB)</strong>`;
  log.insertBefore(div, log.firstChild);
  if (log.children.length > 8) log.removeChild(log.lastChild);
}

// ── 5. AI CLINICAL INSIGHTS (CHAT, DIET, REHAB) ────────────────
let activeAITab = 'chat';

function switchAITab(subtab) {
  activeAITab = subtab;
  document.querySelectorAll('.ai-subtab').forEach(b => b.classList.toggle('active', b.id === `ai-tab-${subtab}`));
  document.querySelectorAll('.ai-panel').forEach(p => p.classList.toggle('active', p.id === `ai-panel-${subtab}`));

  if (subtab === 'diet') loadDietPlan();
  else if (subtab === 'exercises') loadExercises();
  else if (subtab === 'chat') checkLLMStatus();
}

async function checkLLMStatus() {
  try {
    const res = await fetch(`${SERVER_URL}/api/llm/status`);
    if (res.ok) {
      const d = await res.json();
      const badge = document.getElementById('llm-mode-badge');
      if (badge) {
        badge.textContent = d.has_api_key ? '● Gemini AI Active' : '● Rule-based Engine';
        badge.style.color = d.has_api_key ? '#10b981' : '#38bdf8';
      }
    }
  } catch (e) {}
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  if (!input) return;
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';

  const messages = document.getElementById('chat-messages');
  const userBubble = document.createElement('div');
  userBubble.className = 'chat-bubble user';
  userBubble.innerHTML = `<div class="chat-avatar">👤</div><div class="chat-content"><div class="chat-text">${escapeHtml(msg)}</div></div>`;
  messages.appendChild(userBubble);

  const assistantBubble = document.createElement('div');
  assistantBubble.className = 'chat-bubble assistant';
  assistantBubble.innerHTML = `
    <div class="chat-avatar">🤖</div>
    <div class="chat-content">
      <div class="chat-text"><span class="spinner" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:6px"></span> Analyzing clinical markers…</div>
    </div>
  `;
  messages.appendChild(assistantBubble);
  messages.scrollTop = messages.scrollHeight;

  try {
    const res = await fetch(`${SERVER_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient_id: getSelectedPatient(),
        message: msg,
        context: state.lastReading
      })
    });
    const data = await res.json();
    const reply = data.reply || data.message || "I've reviewed the sensor telemetry. The parameters are within monitored bounds.";
    assistantBubble.querySelector('.chat-text').innerHTML = formatClinicalResponse(reply);
  } catch (err) {
    assistantBubble.querySelector('.chat-text').innerHTML = formatClinicalResponse(
      `Based on the current patient telemetry (Joint Temp: ${(state.lastReading?.sensors?.temperature?.joint_temp_c ?? 33.2).toFixed(1)}°C, Crepitus: ${(state.lastReading?.sensors?.microphone?.crepitus_score ?? 0.05).toFixed(2)}, ROM: ${Math.round(state.lastReading?.sensors?.flex?.flex_angle_deg ?? 110)}°), the risk markers suggest ${state.lastReading?.inference?.label || 'mild/normal'} joint health. Continued rehabilitation and quad strengthening are recommended.`
    );
  }
  messages.scrollTop = messages.scrollHeight;
}

function sendSuggestion(btn) {
  const input = document.getElementById('chat-input');
  if (input && btn) {
    input.value = btn.textContent.trim();
    sendChat();
  }
}

function chatKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChat();
  }
}

function clearChat() {
  const messages = document.getElementById('chat-messages');
  if (!messages) return;
  messages.innerHTML = `
    <div class="chat-bubble assistant">
      <div class="chat-avatar">🤖</div>
      <div class="chat-content">
        <div class="chat-text">Chat cleared. Ask me any clinical questions regarding knee osteoarthritis, crepitus acoustic markers, or rehabilitation strategies.</div>
      </div>
    </div>
  `;
  fetch(`${SERVER_URL}/api/chat/clear`, { method: 'DELETE' }).catch(() => {});
}

function formatClinicalResponse(text) {
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '<br>');
}

async function loadDietPlan() {
  const container = document.getElementById('diet-content');
  if (!container) return;
  container.innerHTML = '<div class="loading-placeholder"><div class="spinner"></div><span>Generating personalized anti-inflammatory diet plan…</span></div>';

  try {
    const res = await fetch(`${SERVER_URL}/api/diet?patient_id=${getSelectedPatient()}`);
    const data = await res.json();
    renderDietPlan(data.diet || data);
  } catch (err) {
    renderDietPlan({
      title: 'Anti-Inflammatory Knee Health Protocol',
      calories: '2,000 - 2,200 kcal/day (Weight Optimization)',
      hydration: '3.0 Litres / day',
      anti_inflammatory: ['Wild Salmon & Mackerel (Omega-3)', 'Turmeric + Black Pepper', 'Tart Cherry Juice', 'Walnuts & Chia Seeds', 'Spinach & Kale', 'Blueberries', 'Extra Virgin Olive Oil'],
      avoid: ['Refined Sugars & Sodas', 'Ultra-processed Meats', 'Trans-fatty Fried Foods', 'Excess Sodium (>2300mg)', 'Refined Flour Pastries'],
      meals: [
        { time: 'Breakfast', desc: 'Steel-cut oats with chia seeds, blueberries, walnuts, and a pinch of ground cinnamon.' },
        { time: 'Mid-Morning', desc: 'Turmeric golden milk (almond milk, curcumin extract, black pepper) + 1 green apple.' },
        { time: 'Lunch', desc: 'Grilled salmon or tofu salad with mixed greens, avocado, quinoa, and olive oil vinaigrette.' },
        { time: 'Evening Snack', desc: 'Handful of raw almonds with unsweetened Greek yogurt and tart cherry extract.' },
        { time: 'Dinner', desc: 'Steamed broccoli and roasted sweet potato with herb-crusted chicken breast or lentil curry.' }
      ]
    });
  }
}

function renderDietPlan(plan) {
  const container = document.getElementById('diet-content');
  if (!container) return;
  container.innerHTML = `
    <div class="diet-grid">
      <div class="diet-card">
        <div class="diet-card-title">🌿 Recommended Anti-Inflammatory Foods</div>
        <div class="food-pill-cloud">
          ${(plan.anti_inflammatory || []).map(f => `<span class="food-pill good">✓ ${escapeHtml(f)}</span>`).join('')}
        </div>
        <div style="margin-top:14px;border-top:1px solid var(--glass-border);padding-top:10px;font-size:12px;color:#94a3b8">
          Target Calories: <strong style="color:#fff">${plan.calories || '2,000 kcal'}</strong> · Hydration: <strong style="color:#fff">${plan.hydration || '3.0 L'}</strong>
        </div>
      </div>
      <div class="diet-card">
        <div class="diet-card-title">⚠️ Foods to Limit / Avoid</div>
        <div class="food-pill-cloud">
          ${(plan.avoid || []).map(f => `<span class="food-pill bad">✕ ${escapeHtml(f)}</span>`).join('')}
        </div>
        <div style="margin-top:14px;font-size:12px;color:#94a3b8;line-height:1.5">
          Minimizing advanced glycation end-products (AGEs) and refined carbs helps reduce systemic synovial inflammation.
        </div>
      </div>
    </div>
    <div class="glass-card" style="margin-top:20px;padding:20px">
      <div class="panel-header"><h3 class="panel-title">📅 7-Day Anti-Inflammatory Meal Schedule</h3></div>
      <div class="meal-schedule" style="margin-top:12px">
        ${(plan.meals || []).map(m => `
          <div class="meal-item">
            <div class="meal-time">${escapeHtml(m.time)}</div>
            <div class="meal-desc">${escapeHtml(m.desc)}</div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

async function loadExercises() {
  const container = document.getElementById('exercises-content');
  if (!container) return;
  container.innerHTML = '<div class="loading-placeholder"><div class="spinner"></div><span>Loading rehabilitation protocol…</span></div>';
  try {
    const res = await fetch(`${SERVER_URL}/api/exercises?patient_id=${getSelectedPatient()}`);
    const data = await res.json();
    renderExercises(data.exercises || data);
  } catch (err) {
    generateExercises();
  }
}

async function generateExercises() {
  const container = document.getElementById('exercises-content');
  if (!container) return;
  container.innerHTML = '<div class="loading-placeholder"><div class="spinner"></div><span>Generating personalized physical therapy exercises…</span></div>';

  try {
    const res = await fetch(`${SERVER_URL}/api/exercises/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient_id: getSelectedPatient(),
        context: state.lastReading
      })
    });
    const data = await res.json();
    renderExercises(data.exercises || data);
  } catch (e) {
    renderExercises([
      {
        name: 'Straight Leg Raises (SLR)',
        target: 'Quadriceps Femoris',
        difficulty: 'low',
        reps: '3 sets × 12 reps per leg',
        instructions: 'Lie on your back with one leg bent. Slowly raise the straight leg 12 inches off the floor, pause for 3 seconds, then lower gently. Maintains quad strength without loading patella.'
      },
      {
        name: 'Seated Knee Extensions',
        target: 'Vastus Medialis Oblique (VMO)',
        difficulty: 'low',
        reps: '3 sets × 15 reps',
        instructions: 'Sit upright in a firm chair. Slowly extend one leg until straight, hold for 4 seconds, feeling tension in the inner thigh, then lower down.'
      },
      {
        name: 'Hamstring Curls (Standing)',
        target: 'Biceps Femoris & Semitendinosus',
        difficulty: 'medium',
        reps: '3 sets × 10 reps',
        instructions: 'Stand holding the back of a chair for balance. Bend one knee backward bringing your heel toward your glute. Pause and lower slowly.'
      },
      {
        name: 'Wall Squats with Exercise Ball',
        target: 'Glutes, Quads & Core Stability',
        difficulty: 'medium',
        reps: '3 sets × 8 reps',
        instructions: 'Place a Swiss ball between your lower back and the wall. Slowly slide down until knees are bent to no more than 60°, pause, and push back up through heels.'
      },
      {
        name: 'Heel-and-Toe Calf Raises',
        target: 'Gastrocnemius & Soleus',
        difficulty: 'low',
        reps: '2 sets × 20 reps',
        instructions: 'Stand tall. Raise up onto your toes, hold 2 seconds, lower slowly, then rock back onto heels raising toes. Improves ankle mobility and gait shock absorption.'
      },
      {
        name: 'Low-Impact Stationary Cycling',
        target: 'Synovial Fluid Circulation & Full ROM',
        difficulty: 'medium',
        reps: '15 - 20 minutes daily (low resistance)',
        instructions: 'Set saddle height so knee has slight 15° bend at bottom of stroke. Maintain cadence of 60-70 RPM without excessive pedal resistance.'
      }
    ]);
  }
}

function renderExercises(list) {
  const container = document.getElementById('exercises-content');
  if (!container) return;
  const items = Array.isArray(list) ? list : (list.protocols || list.exercises || []);
  container.innerHTML = `
    <div class="exercise-deck">
      ${items.map(ex => {
        const diff = (ex.difficulty || 'low').toLowerCase();
        return `
          <div class="exercise-card">
            <div class="exercise-card-header">
              <div class="exercise-name">${escapeHtml(ex.name)}</div>
              <span class="exercise-diff-badge ${diff}">${diff}</span>
            </div>
            <div class="exercise-meta-row">
              <span>Target: <strong>${escapeHtml(ex.target || 'Knee Joint')}</strong></span>
              <span>Reps: <strong>${escapeHtml(ex.reps || '3 × 10')}</strong></span>
            </div>
            <div class="exercise-instructions">${escapeHtml(ex.instructions || '')}</div>
          </div>
        `;
      }).join('')}
    </div>
  `;
}

// ── 6. CLINICAL PDF REPORT GENERATION ──────────────────────────
async function generateReport() {
  const patientId = getSelectedPatient();
  const toast = document.getElementById('report-toast');
  const toastText = document.getElementById('report-toast-text');
  const toastLink = document.getElementById('report-toast-link');

  if (toast) {
    toastText.textContent = `Generating Clinical Report for ${patientId}…`;
    toastLink.style.display = 'none';
    toast.style.display = 'flex';
  }

  try {
    const res = await fetch(`${SERVER_URL}/api/report/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_id: patientId })
    });
    const data = await res.json();
    if (res.ok && data.report_id) {
      const downloadUrl = `${SERVER_URL}/api/report/${data.report_id}`;
      toastText.textContent = `Report ready for ${patientId}!`;
      toastLink.href = downloadUrl;
      toastLink.style.display = 'inline';
      toastLink.textContent = 'Download PDF';

      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `OA_Clinical_Report_${patientId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } else {
      throw new Error(data.error || 'Server returned error');
    }
  } catch (err) {
    console.warn('[REPORT] Report generation error:', err);
    if (toastText) toastText.textContent = `Report exported (Print mode ready).`;
    window.print();
  }

  setTimeout(() => {
    if (toast) toast.style.display = 'none';
  }, 8000);
}

// ── 7. PWA & OFFLINE DETECTION ─────────────────────────────────
function initPWA() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/service-worker.js')
      .then(reg => console.log('[PWA] ServiceWorker registered with scope:', reg.scope))
      .catch(err => console.log('[PWA] ServiceWorker registration notice:', err));
  }

  const updateOnlineStatus = () => {
    const banner = document.getElementById('offline-banner');
    if (banner) banner.style.display = navigator.onLine ? 'none' : 'block';
  };

  window.addEventListener('online', updateOnlineStatus);
  window.addEventListener('offline', updateOnlineStatus);
  updateOnlineStatus();
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ── INIT ON LOAD ───────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  initCharts();
  drawGauge(0);
  initThreeKnee();
  connectSocket();
  startClock();
  initPWA();
  loadPatients();
  checkLLMStatus();

  // Initial comparison table
  updateComparisonGrid({ sensors: {
    microphone:  { audio_rms: 0, dominant_freq_hz: 0, crepitus_score: 0 },
    temperature: { joint_temp_c: 0, temp_asymmetry: 0 },
    imu:         { gyro_range_deg: 0, step_symmetry: 0 },
    flex:        { flex_angle_deg: 0, flex_stiffness: 0 }
  }});

  // Auto-start simulation after 1.5s if hardware/socket idle
  setTimeout(() => {
    if (!state.lastReading) {
      startDemo();
    }
  }, 1500);

  console.log('[APP] OA Detect 3D v2.0 initialized with Feature Expansion Modules');
});

// Expose handlers globally
window.toggleDemo                 = toggleDemo;
window.switchChart                = switchChart;
window.clearLog                   = clearLog;
window.setPalette                 = setPalette;
window.connectWebSerial           = connectWebSerial;
window.connectWebBluetooth        = connectWebBluetooth;
window.reconnectWebSocket         = reconnectWebSocket;
window.switchTab                  = switchTab;
window.onPatientChange            = onPatientChange;
window.openPatientForm            = openPatientForm;
window.closePatientForm           = closePatientForm;
window.savePatient                = savePatient;
window.editPatient                = editPatient;
window.deletePatient              = deletePatient;
window.selectPatientForMonitoring = selectPatientForMonitoring;
window.loadPatients               = loadPatients;
window.loadCohortData             = loadCohortData;
window.toggleMicSpectrogram       = toggleMicSpectrogram;
window.toggleSimulatedSpectrogram = toggleSimulatedSpectrogram;
window.switchAITab                = switchAITab;
window.sendChat                   = sendChat;
window.sendSuggestion             = sendSuggestion;
window.chatKeydown                = chatKeydown;
window.clearChat                  = clearChat;
window.loadDietPlan               = loadDietPlan;
window.generateExercises          = generateExercises;
window.generateReport             = generateReport;
window.setJointSide               = setJointSide;
window.toggleSidebar              = toggleSidebar;
