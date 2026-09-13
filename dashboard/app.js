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
  if (!el) return;
  setInterval(() => {
    el.textContent = new Date().toLocaleString('en-IN', {
      weekday: 'short', year: 'numeric', month: 'short',
      day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  }, 1000);
}

// ── INIT ON LOAD ───────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  initCharts();
  drawGauge(0);
  initThreeKnee();
  connectSocket();
  startClock();

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

  console.log('[APP] OA Detect 3D initialized with Glassmorphism, WebGL, and Real Hardware Connectors');
});

// Expose handlers globally
window.toggleDemo          = toggleDemo;
window.switchChart         = switchChart;
window.clearLog            = clearLog;
window.setPalette          = setPalette;
window.connectWebSerial    = connectWebSerial;
window.connectWebBluetooth = connectWebBluetooth;
window.reconnectWebSocket  = reconnectWebSocket;
