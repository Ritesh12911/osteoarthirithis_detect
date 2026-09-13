# 🦴 AI-Assisted Early Osteoarthritis Detection System
### SIH 2026 · Problem Statement 26004 · MDoNER

> AI-powered, ESP32-S3 based real-time knee health screening system for the North Eastern Region of India.

---

## 🏗️ Architecture

```
ESP32-S3 N16R8  ──(WiFi/BLE)──▶  Flask Backend  ──(WebSocket)──▶  Web Dashboard
  INMP441 Mic                       ML Inference                   Live Charts
  MLX90614 IR Temp                  SQLite DB                      Risk Gauge
  MPU6050 IMU                       REST API                       Comparison Panel
  Flex Sensor ADC                                                   Session Log
```

---

## 📁 Project Structure

```
oa-detection-system/
├── firmware/
│   └── esp32_oa_sensor.ino     ← ESP32-S3 Arduino sketch
├── ml/
│   ├── generate_dataset.py     ← Synthetic Normal + OA data generator
│   ├── train_model.py          ← Ensemble ML training pipeline
│   ├── models/                 ← oa_model.pkl, scaler.pkl (after training)
│   └── plots/                  ← Confusion matrix, ROC, feature importance
├── backend/
│   ├── app.py                  ← Flask + Socket.IO server
│   ├── inference.py            ← ML inference engine
│   ├── database.py             ← SQLite session storage
│   └── requirements.txt
└── dashboard/
    ├── index.html              ← Main dashboard
    ├── style.css               ← Glassmorphism dark theme
    └── app.js                  ← Real-time charts + WebSocket client
```

---

## 🔌 Hardware Wiring (ESP32-S3 N16R8)

| Sensor | Model | Interface | Pins |
|--------|-------|-----------|------|
| Microphone | INMP441 | I2S | SCK=GPIO1, WS=GPIO2, SD=GPIO3 |
| IR Temperature | MLX90614 | I2C | SDA=GPIO8, SCL=GPIO9 |
| IMU (6-axis) | MPU6050 | I2C | SDA=GPIO8, SCL=GPIO9 (shared) |
| Flex Sensor | Resistive | ADC | GPIO4 (10kΩ pull-down) |
| Status LED | NeoPixel/RGB | GPIO | GPIO48 |

---

## 🚀 Quick Start

### 1. Install Python dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Train the ML model
```bash
cd ml
python generate_dataset.py   # Creates oa_dataset.csv
python train_model.py        # Trains & saves model, generates plots
```

### 3. Start the backend server
```bash
cd backend
python app.py
# Server starts at http://localhost:5000
```

### 4. Open the dashboard
Open browser → `http://localhost:5000`

Or open `dashboard/index.html` directly (auto-starts local simulation if backend unavailable)

### 5. Flash ESP32-S3 firmware
- Install [Arduino IDE](https://www.arduino.cc/en/software) with ESP32-S3 board package
- Install libraries: `Adafruit MLX90614`, `Adafruit MPU6050`, `ArduinoJson`, `NimBLE-Arduino`
- Edit `firmware/esp32_oa_sensor.ino`:
  ```cpp
  const char* WIFI_SSID  = "YOUR_WIFI_SSID";
  const char* WIFI_PASS  = "YOUR_WIFI_PASSWORD";
  const char* SERVER_URL = "http://YOUR_PC_IP:5000/api/data";
  ```
- Flash to ESP32-S3 N16R8

---

## 🧠 ML Features (12 sensor features)

| Feature | Sensor | Clinical Significance |
|---------|--------|----------------------|
| `audio_rms` | INMP441 Mic | Crepitus (joint crackling) amplitude |
| `dominant_freq_hz` | INMP441 Mic | Frequency of joint sounds |
| `crepitus_score` | INMP441 Mic | Abnormal sound energy (>300Hz) |
| `joint_temp_c` | MLX90614 | Synovial inflammation (↑ in OA) |
| `temp_asymmetry` | MLX90614 | L-R knee temperature difference |
| `accel_rms_x/y/z` | MPU6050 | Gait irregularity (antalgic gait) |
| `gyro_range_deg` | MPU6050 | Range of motion (↓ in OA) |
| `step_symmetry` | MPU6050 | Left-right gait balance |
| `flex_angle_deg` | Flex Sensor | Knee bend angle (↓ in OA) |
| `flex_stiffness` | Flex Sensor | Resistance to bending (↑ in OA) |

---

## 📊 Dashboard Features

- **Risk Gauge** — 0–100% OA risk score with animated needle
- **Live Charts** — Real-time line charts for all 4 sensors (rolling 40-point window)
- **Radar Chart** — Multi-axis comparison: Current vs Normal vs OA reference
- **Comparison Bars** — Side-by-side feature comparison vs reference profiles
- **Session Log** — Timestamped history of readings with risk classification
- **Sensor Cards** — Live hardware status for each sensor
- **Demo Mode** — Auto-simulates both Normal and OA patients (no hardware needed)
- **Alert System** — Real-time high-risk alerts

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/data` | ESP32 sends sensor readings |
| GET | `/api/history` | Session history |
| GET | `/api/reference` | Normal + OA reference profiles |
| GET | `/api/stats` | Summary statistics |
| GET | `/api/timeseries?patient_id=X` | Patient time series |
| GET | `/api/compare?patient_id=X` | Comparison data |
| GET | `/api/model_info` | ML model metadata |
| POST | `/api/demo/start` | Start demo simulation |
| POST | `/api/demo/stop` | Stop demo simulation |

---

## 🎯 Expected Model Performance

| Model | Accuracy | F1 Score | AUC |
|-------|----------|----------|-----|
| Random Forest | ~92% | ~0.92 | ~0.97 |
| Gradient Boosting | ~91% | ~0.91 | ~0.96 |
| SVM (RBF) | ~88% | ~0.88 | ~0.94 |
| **Ensemble (Voting)** | **~93%** | **~0.93** | **~0.97** |

---

## ⚠️ Important Notes

1. **Real Patient Data**: The ML model uses synthetic data. Replace with actual clinical data from hospital partners for deployment.
2. **Medical Disclaimer**: This is a screening aid, not a diagnostic tool. Consult an orthopedic specialist for diagnosis.
3. **BLE Mode**: Uncomment `#define USE_BLE` in firmware to use BLE instead of WiFi.
4. **IP Address**: Update `SERVER_URL` in firmware to your PC's local IP (run `ipconfig` to find it).
