# 🦴 JointSense — AI-Assisted Early Osteoarthritis Detection System

> AI-powered, ESP32-S3 based real-time knee health screening system with multimodal sensor fusion and machine learning inference.

[![Live Website](https://img.shields.io/badge/Render-Live%20Website-brightgreen?style=for-the-badge&logo=render)](https://jointsense-jmkt.onrender.com)
[![GitHub Actions](https://img.shields.io/badge/Android%20App-Build%20Status-blue?style=for-the-badge&logo=android)](https://github.com/Ritesh12911/osteoarthirithis_detect/actions)

### 🌐 Live Production Website & PWA
**[https://jointsense-jmkt.onrender.com](https://jointsense-jmkt.onrender.com)**

* **Web Application**: Live sensor telemetry, risk assessment gauge, radar comparison, patient cohort analytics, and AI clinical report generation.
* **Mobile App (PWA)**: Open the link above in Chrome (Android) or Safari (iOS) and tap **"Install App"** to install JointSense natively on your phone.
* **Android APK**: Native Android build powered by Capacitor in `/android`.

---

## 🏗️ System Architecture

```
ESP32-S3 (OsteoBelt Hub) ──(WiFi/BLE)──▶  Render Cloud / Flask  ──(WebSocket)──▶  JointSense Dashboard
  INMP441 Microphone (Crepitus)              ML Inference (KL 0-4)                  Live 3D & Charts
  DS18B20 (Skin Temperature)                SQLite DB                              Risk Gauge
  Dual MPU6050 IMU (Thigh + Shank)          REST API                               Cohort Analytics
  Flex Sensor ADC (Stiffness)               ReportLab PDF                          Mobile App (PWA / APK)
```

---

## 📁 Project Structure

```
osteoarthirithis_detect/
├── android/                    ← Native Android application (Capacitor)
├── backend/
│   ├── app.py                  ← Flask + Socket.IO production server
│   ├── database.py             ← SQLite database & session storage
│   ├── inference.py            ← ML model inference engine (KL grading)
│   ├── llm_service.py          ← AI clinical advisory service
│   ├── report_generator.py     ← PDF clinical report generator
│   └── requirements.txt        ← Backend dependencies
├── dashboard/
│   ├── index.html              ← Responsive medical dashboard
│   ├── app.js                  ← Real-time telemetry, charts & WebSockets
│   ├── style.css               ← Dark glassmorphism interface
│   ├── jointsense-logo.png     ← Brand logo
│   └── manifest.json           ← PWA configuration
├── firmware/
│   └── esp32_oa_sensor_ble_wifi/
│       └── esp32_oa_sensor_ble_wifi.ino  ← OsteoBelt v3.0 firmware
├── ml/
│   ├── generate_dataset.py     ← Synthetic dataset generator
│   ├── train_model.py          ← Model training pipeline
│   └── models/                 ← Pre-trained models (KL & binary)
└── Procfile / railway.json     ← Cloud deployment configuration
```

---

## 🔌 Hardware Pin Mapping (OsteoBelt Hub PCB · XIAO ESP32-S3)

| Sensor / Component | Module | Interface | Pins |
|--------------------|--------|-----------|------|
| Acoustic Crepitus | INMP441 Mic | I2S | BCLK=GPIO1, WS=GPIO2, SD=GPIO3 |
| Knee Joint Temperature | DS18B20 | 1-Wire | GPIO5 (4.7kΩ pull-up) |
| Motion & Knee Angle | Dual MPU6050 | I2C | SDA=GPIO8, SCL=GPIO9 (Thigh `0x68`, Shank `0x69`) |
| Joint Flexion / Stiffness | Flex Sensor | ADC1 | GPIO4 (10kΩ divider) |
| Status / Risk Indicator | On-board LED / AUX | GPIO | GPIO21 (active LOW) / GPIO6 (WS2812) |
| Calibrate / Zero Button | Push Button | GPIO | GPIO44 (to GND) |
| Battery Monitoring | Resistor Divider | ADC1 | GPIO7 (1:2 divider) |

---

## 🚀 Quick Start (Local Development)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Backend & Dashboard
```bash
python backend/app.py
# Server runs at http://localhost:5000
```

### 3. Flash ESP32-S3 Firmware
Open `firmware/esp32_oa_sensor_ble_wifi/esp32_oa_sensor_ble_wifi.ino` in Arduino IDE:
* Board: `XIAO_ESP32S3`
* Cloud Server URL: `https://jointsense-jmkt.onrender.com/api/data`

---

## 📡 Cloud API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/data` | ESP32 telemetry ingestion |
| `GET` | `/api/stats` | Live detection counts & risk metrics |
| `GET` | `/api/patients` | Patient profiles & KL staging |
| `GET` | `/api/cohort` | Multi-patient clinical statistics |
| `POST` | `/api/report/generate` | Generate clinical PDF report |
| `POST` | `/api/demo/start` | Start live sensor stream simulation |
