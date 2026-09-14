# 🦴 AI-Assisted Osteoarthritis Detection System
### SIH 2026 · Problem Statement 26004 · MDoNER

> ESP32-S3 based knee-health **screening research prototype**. It is not clinically validated and must not be used as a standalone diagnostic system.

## Safety / validation status

- The ML pipeline currently uses synthetic/internal data. Reported accuracy, F1, AUC and confidence values are **not clinical validation**.
- Sensor-derived values such as crepitus, gait symmetry, temperature asymmetry, ROM and stiffness are engineering proxies and require clinical validation.
- The system should be used for research/demo screening only until prospective patient-level and external validation are completed.

## Architecture

```text
ESP32-S3 sensors → validated API → feature/inference layer → SQLite → WebSocket → dashboard
```

## Project structure

```text
firmware/esp32_oa_sensor.ino   ESP32-S3 firmware
backend/app.py                 Flask + Socket.IO API
backend/inference.py           validated inference layer
backend/database.py            SQLite persistence
backend/llm_service.py         optional AI assistant + fallback
ml/                            dataset/training pipeline and model artifacts
dashboard/                     web dashboard
```

## Quick start

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000`.

For ESP32, set Wi-Fi credentials and `SERVER_URL` in the firmware. `SERVER_URL` must point to the computer's LAN IP, not `localhost`.

## Hardware

| Sensor | Interface | Pins |
|---|---|---|
| INMP441 | I2S | SCK 1, WS 2, SD 3 |
| MLX90614 | I2C | SDA 8, SCL 9 |
| MPU6050 | I2C | SDA 8, SCL 9 |
| Flex sensor | ADC | GPIO 4 |

## API

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/data` | validated sensor reading |
| GET | `/api/history` | session history |
| GET | `/api/timeseries` | patient time series |
| GET | `/api/model_info` | model metadata and validation status |
| POST | `/api/demo/start` | start one guarded demo stream |
| POST | `/api/demo/stop` | stop demo stream |
| POST | `/api/chat` | AI/fallback screening assistant |

## Development notes

The production deployment should add authentication/authorization, HTTPS, a production database, rate limiting, secret management and patient-level access controls before handling real patient information.
