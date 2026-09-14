/*
 * ============================================================
 *  AI-Assisted Early Osteoarthritis Detection System
 *  ESP32-S3 N16R8 Firmware
 *  SIH 2026 — Problem Statement 26004 (MDoNER)
 * ============================================================
 *
 *  SENSOR WIRING:
 *  ─────────────────────────────────────────────────────────
 *  INMP441 (I2S Microphone):
 *    SCK  → GPIO 1
 *    WS   → GPIO 2
 *    SD   → GPIO 3
 *    L/R  → GND  (left channel)
 *    VDD  → 3.3V
 *
 *  MLX90614 (IR Temperature Sensor):
 *    SDA  → GPIO 8
 *    SCL  → GPIO 9
 *    VDD  → 3.3V
 *
 *  MPU6050 (IMU — 6-axis Accel + Gyro):
 *    SDA  → GPIO 8  (shared I2C bus)
 *    SCL  → GPIO 9  (shared I2C bus)
 *    AD0  → GND    (I2C address 0x68)
 *    VDD  → 3.3V
 *
 *  Flex Sensor (Resistive, knee bend):
 *    Signal → GPIO 4 (ADC1_CH3) via voltage divider (10kΩ to GND)
 *    VCC    → 3.3V
 *
 *  STATUS LED:
 *    GPIO 48 (built-in RGB or external LED)
 *    Green  = Normal | Red = OA Risk | Yellow = Connecting
 *
 *  DEPENDENCIES (install via Arduino Library Manager):
 *  - Wire (built-in)
 *  - WiFi (built-in ESP32)
 *  - HTTPClient (built-in ESP32)
 *  - Adafruit MLX90614 Library
 *  - Adafruit MPU6050
 *  - Adafruit Sensor
 *  - ArduinoJson (v6 or v7 supported)
 *  - NimBLE-Arduino (optional, for BLE fallback)
 * ============================================================
 */

#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <driver/i2s.h>
#include <Adafruit_MLX90614.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <math.h>

// ─── BLE FALLBACK (uncomment to enable BLE instead of WiFi) ──────────────────
#define USE_BLE
#ifdef USE_BLE
  #include <NimBLEDevice.h>
  #include <NimBLEServer.h>
  #include <NimBLEUtils.h>
  #define BLE_SERVICE_UUID        "12345678-1234-5678-1234-56789abcdef0"
  #define BLE_CHARACTERISTIC_UUID "12345678-1234-5678-1234-56789abcdef1"
  NimBLECharacteristic *pCharacteristic;
#endif

// ─── DATA STRUCTURES ──────────────────────────────────────────────────────────
// Defined at the top of the file before function prototypes to avoid
// Arduino preprocessor prototype resolution errors.
struct AudioFeatures {
  float rms;
  float dominantFreqHz;
  float crepitusScore;
};

struct IMUFeatures {
  float accelRmsX;
  float accelRmsY;
  float accelRmsZ;
  float gyroRangeDeg;
  float stepSymmetry;
};

struct TempFeatures {
  float jointTempC;
  float ambientTempC;
  float tempAsymmetry; // deviation from normal ~33°C
};

struct FlexFeatures {
  float angleDeg;
  float stiffnessScore;
};

// ─── FORWARD FUNCTION PROTOTYPES ─────────────────────────────────────────────
void setup();
void loop();
void setupI2S();
void setLED(int r, int g, int b);
AudioFeatures readMicrophoneFeatures();
IMUFeatures readIMUFeatures();
TempFeatures readTempFeatures();
FlexFeatures readFlexFeatures();
void sendData(AudioFeatures& audio, TempFeatures& temp, IMUFeatures& imu, FlexFeatures& flex);

// ─── WIFI CONFIG ──────────────────────────────────────────────────────────────
const char* WIFI_SSID     = "Infinix NOTE 50S 5G";      // ← Change this
const char* WIFI_PASS     = "1234554321";   // ← Change this
const char* SERVER_URL    = "http://:5000/api/data"; // ← Change to your PC IP

// ─── PIN CONFIG ───────────────────────────────────────────────────────────────
#define I2S_SCK_PIN     1
#define I2S_WS_PIN      2
#define I2S_DATA_PIN    3
#define SDA_PIN         8
#define SCL_PIN         9
#define FLEX_PIN        4
#define STATUS_LED_PIN  48

// ─── I2S CONFIG ───────────────────────────────────────────────────────────────
#define I2S_PORT        I2S_NUM_0
#define I2S_SAMPLE_RATE 16000
#define I2S_BUFFER_SIZE 512

// ─── PATIENT CONFIG ───────────────────────────────────────────────────────────
String PATIENT_ID   = "PATIENT_001";  // Change per session
String PATIENT_SIDE = "LEFT";         // LEFT or RIGHT knee

// ─── GLOBALS ──────────────────────────────────────────────────────────────────
Adafruit_MLX90614 mlx;
Adafruit_MPU6050  mpu;
int32_t           i2sBuffer[I2S_BUFFER_SIZE];
unsigned long     lastSendTime = 0;
const int         SEND_INTERVAL_MS = 500;
int               sessionSampleCount = 0;

// ─── STATUS LED COLORS ────────────────────────────────────────────────────────
void setLED(int r, int g, int b) {
  // For boards with RGB LED (e.g., GPIO 48 NeoPixel on ESP32-S3-DevKit)
  #ifdef RGB_BUILTIN
    neopixelWrite(RGB_BUILTIN, r, g, b);
  #endif
}

// ─── SETUP I2S ────────────────────────────────────────────────────────────────
void setupI2S() {
  i2s_config_t i2s_config = {
    .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate          = I2S_SAMPLE_RATE,
    .bits_per_sample      = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_I2S,
    .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count        = 8,
    .dma_buf_len          = I2S_BUFFER_SIZE,
    .use_apll             = false,
    .tx_desc_auto_clear   = false,
    .fixed_mclk           = 0
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num   = I2S_SCK_PIN,
    .ws_io_num    = I2S_WS_PIN,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num  = I2S_DATA_PIN
  };

  i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_PORT, &pin_config);
  i2s_start(I2S_PORT);
  Serial.println("[I2S] Microphone initialized");
}

// ─── READ MICROPHONE FEATURES ─────────────────────────────────────────────────
AudioFeatures readMicrophoneFeatures() {
  AudioFeatures feat = {0.0f, 0.0f, 0.0f};

  size_t bytesRead = 0;
  i2s_read(I2S_PORT, &i2sBuffer, sizeof(i2sBuffer), &bytesRead, portMAX_DELAY);
  int samplesRead = bytesRead / sizeof(int32_t);

  if (samplesRead == 0) return feat;

  // Compute RMS amplitude
  double sumSq = 0.0;
  float  maxAmp = 0.0f;
  for (int i = 0; i < samplesRead; i++) {
    float sample = (float)(i2sBuffer[i] >> 14) / 32768.0f; // normalize
    sumSq += sample * sample;
    if (fabs(sample) > maxAmp) maxAmp = fabs(sample);
  }
  feat.rms = sqrt(sumSq / samplesRead);

  // Zero-crossing rate → proxy for dominant frequency
  int zeroCrossings = 0;
  for (int i = 1; i < samplesRead; i++) {
    float s_prev = (float)(i2sBuffer[i-1] >> 14);
    float s_curr = (float)(i2sBuffer[i]   >> 14);
    if ((s_prev > 0 && s_curr < 0) || (s_prev < 0 && s_curr > 0)) {
      zeroCrossings++;
    }
  }
  // ZCR → frequency estimate
  float timeWindow = (float)samplesRead / I2S_SAMPLE_RATE;
  feat.dominantFreqHz = (zeroCrossings / 2.0f) / timeWindow;
  feat.dominantFreqHz = constrain(feat.dominantFreqHz, 20.0f, 8000.0f);

  // Crepitus score: energy in 300–800 Hz band
  // True crepitus has freq > 300 Hz with elevated amplitude
  if (feat.dominantFreqHz > 300 && feat.rms > 0.02f) {
    float rawScore = (feat.dominantFreqHz - 300.0f) / 500.0f * feat.rms * 20.0f;
    feat.crepitusScore = (rawScore < 1.0f) ? rawScore : 1.0f;
  } else {
    feat.crepitusScore = 0.0f;
  }

  return feat;
}

// ─── READ IMU FEATURES ────────────────────────────────────────────────────────
IMUFeatures readIMUFeatures() {
  IMUFeatures feat = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f};
  sensors_event_t accel, gyro, temp;
  mpu.getEvent(&accel, &gyro, &temp);

  feat.accelRmsX = fabs(accel.acceleration.x);
  feat.accelRmsY = fabs(accel.acceleration.y);
  feat.accelRmsZ = fabs(accel.acceleration.z);

  // Integrate gyro for range of motion estimate
  float gyroMag = sqrt(
    gyro.gyro.x * gyro.gyro.x +
    gyro.gyro.y * gyro.gyro.y +
    gyro.gyro.z * gyro.gyro.z
  );
  // Convert rad/s to deg/s, estimate peak ROM from 500ms window
  feat.gyroRangeDeg = gyroMag * (180.0f / (float)M_PI) * (SEND_INTERVAL_MS / 1000.0f);
  feat.gyroRangeDeg = constrain(feat.gyroRangeDeg, 0.0f, 180.0f);

  // Step symmetry: ratio of lateral to vertical acceleration
  float lateral   = fabs(accel.acceleration.x);
  float vertical  = fabs(accel.acceleration.z) + 0.001f;
  feat.stepSymmetry = constrain(1.0f - (lateral / vertical), 0.0f, 1.0f);

  return feat;
}

// ─── READ TEMPERATURE FEATURES ───────────────────────────────────────────────
TempFeatures readTempFeatures() {
  TempFeatures feat = {0.0f, 0.0f, 0.0f};
  feat.ambientTempC  = mlx.readAmbientTempC();
  feat.jointTempC    = mlx.readObjectTempC();
  // Normal knee surface temp ~32–34°C; OA joints run warmer
  feat.tempAsymmetry = fabs(feat.jointTempC - 33.0f);
  return feat;
}

// ─── READ FLEX SENSOR ─────────────────────────────────────────────────────────
FlexFeatures readFlexFeatures() {
  FlexFeatures feat = {0.0f, 0.0f};
  // Average 10 ADC readings to reduce noise
  int adcSum = 0;
  for (int i = 0; i < 10; i++) {
    adcSum += analogRead(FLEX_PIN);
    delayMicroseconds(100);
  }
  int adcVal = adcSum / 10;

  // Map ADC (12-bit, 0-4095) to angle
  // Calibration: flat (0°) = ~1700 ADC, fully bent (130°) = ~3000 ADC
  feat.angleDeg = map(adcVal, 1700, 3000, 0, 130);
  feat.angleDeg = constrain(feat.angleDeg, 0.0f, 180.0f);

  // Stiffness: how restricted the bend is (lower angle = stiffer)
  // Normal ROM ~90–130°; OA restricted to ~30–80°
  feat.stiffnessScore = constrain(1.0f - (feat.angleDeg / 130.0f), 0.0f, 1.0f);

  return feat;
}

// ─── BUILD AND SEND JSON PAYLOAD ──────────────────────────────────────────────
void sendData(AudioFeatures& audio, TempFeatures& temp,
              IMUFeatures& imu, FlexFeatures& flex) {

#if ARDUINOJSON_VERSION_MAJOR >= 7
  JsonDocument doc;
#else
  StaticJsonDocument<1024> doc;
#endif

  doc["patient_id"]       = PATIENT_ID;
  doc["side"]             = PATIENT_SIDE;
  doc["timestamp"]        = millis();
  doc["sample_idx"]       = sessionSampleCount++;

  // Microphone features
  doc["audio_rms"]         = audio.rms;
  doc["dominant_freq_hz"]  = audio.dominantFreqHz;
  doc["crepitus_score"]    = audio.crepitusScore;

  // Temperature features
  doc["joint_temp_c"]      = temp.jointTempC;
  doc["ambient_temp_c"]    = temp.ambientTempC;
  doc["temp_asymmetry"]    = temp.tempAsymmetry;

  // IMU features
  doc["accel_rms_x"]       = imu.accelRmsX;
  doc["accel_rms_y"]       = imu.accelRmsY;
  doc["accel_rms_z"]       = imu.accelRmsZ;
  doc["gyro_range_deg"]    = imu.gyroRangeDeg;
  doc["step_symmetry"]     = imu.stepSymmetry;

  // Flex sensor features
  doc["flex_angle_deg"]    = flex.angleDeg;
  doc["flex_stiffness"]    = flex.stiffnessScore;

  String jsonStr;
  serializeJson(doc, jsonStr);

#ifndef USE_BLE
  // ── WiFi HTTP POST ────────────────────────────────────────────────────────
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");
    int httpCode = http.POST(jsonStr);

    if (httpCode == 200) {
      String response = http.getString();

#if ARDUINOJSON_VERSION_MAJOR >= 7
      JsonDocument respDoc;
#else
      StaticJsonDocument<256> respDoc;
#endif
      deserializeJson(respDoc, response);
      float  riskScore = respDoc["risk_score"] | 0.0f;
      String label     = respDoc["label"]      | "UNKNOWN";

      Serial.printf("[OK] Risk: %.1f%% | Label: %s\n", riskScore * 100, label.c_str());

      // Update LED based on risk
      if (riskScore > 0.6f) {
        setLED(255, 0, 0);   // Red: OA risk
      } else if (riskScore > 0.3f) {
        setLED(255, 165, 0); // Orange: borderline
      } else {
        setLED(0, 255, 0);   // Green: normal
      }
    } else {
      Serial.printf("[ERR] HTTP %d\n", httpCode);
      setLED(0, 0, 255); // Blue: connection error
    }
    http.end();
  } else {
    Serial.println("[WARN] WiFi disconnected, reconnecting...");
    setLED(255, 255, 0); // Yellow: connecting
    WiFi.reconnect();
  }

#else
  // ── BLE UART Notify ───────────────────────────────────────────────────────
  pCharacteristic->setValue(jsonStr.c_str());
  pCharacteristic->notify();
  Serial.println("[BLE] Data sent: " + jsonStr.substring(0, 80) + "...");
#endif

  // Always print to Serial for debugging
  Serial.println(jsonStr);
}

// ─── SETUP ────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("==============================================");
  Serial.println(" OA Detection System — ESP32-S3 N16R8");
  Serial.println(" SIH 2026 | MDoNER | PS-26004");
  Serial.println("==============================================");

  // Status LED
  pinMode(STATUS_LED_PIN, OUTPUT);
  setLED(255, 255, 0); // Yellow: initializing

  // I2C for MLX90614 + MPU6050
  Wire.begin(SDA_PIN, SCL_PIN);
  Serial.println("[I2C] Bus started on SDA=8, SCL=9");

  // MLX90614 IR Temperature
  if (!mlx.begin()) {
    Serial.println("[ERR] MLX90614 not found! Check wiring.");
    setLED(255, 0, 0);
    while(1) delay(1000);
  }
  Serial.println("[MLX90614] Temperature sensor OK");

  // MPU6050 IMU
  if (!mpu.begin()) {
    Serial.println("[ERR] MPU6050 not found! Check wiring.");
    setLED(255, 0, 0);
    while(1) delay(1000);
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_2_G);
  mpu.setGyroRange(MPU6050_RANGE_250_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  Serial.println("[MPU6050] IMU OK — ±2G, ±250°/s, 21Hz LPF");

  // Flex sensor ADC
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db); // 0–3.3V range
  Serial.printf("[ADC] Flex sensor on GPIO %d\n", FLEX_PIN);

  // I2S Microphone
  setupI2S();

#ifndef USE_BLE
  // WiFi connection
  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("[WiFi] Signal: %d dBm\n", WiFi.RSSI());
    setLED(0, 255, 0); // Green: ready
  } else {
    Serial.println("\n[WiFi] Failed to connect!");
    setLED(255, 0, 0);
  }

#else
  // BLE setup
  NimBLEDevice::init("OA_Detector_SIH2026");
  NimBLEServer *pServer = NimBLEDevice::createServer();
  NimBLEService *pService = pServer->createService(BLE_SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(
    BLE_CHARACTERISTIC_UUID,
    NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
  );
  pService->start();
  NimBLEAdvertising *pAdvertising = NimBLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(BLE_SERVICE_UUID);
  pAdvertising->start();
  Serial.println("[BLE] Advertising as 'OA_Detector_SIH2026'");
  setLED(0, 0, 255); // Blue: BLE mode
#endif

  Serial.println("[SYS] All sensors initialized. Starting data collection...");
  Serial.println("----------------------------------------------");
}

// ─── LOOP ─────────────────────────────────────────────────────────────────────
void loop() {
  unsigned long now = millis();

  if (now - lastSendTime >= SEND_INTERVAL_MS) {
    lastSendTime = now;

    // Read all sensors
    AudioFeatures audio = readMicrophoneFeatures();
    TempFeatures  temp  = readTempFeatures();
    IMUFeatures   imu   = readIMUFeatures();
    FlexFeatures  flex  = readFlexFeatures();

    // Log to serial
    Serial.printf("[DATA] t=%.1f°C | flex=%.1f° | crepitus=%.3f | stepSym=%.2f\n",
      temp.jointTempC, flex.angleDeg, audio.crepitusScore, imu.stepSymmetry);

    // Send to server
    sendData(audio, temp, imu, flex);
  }

  // Small yield for WiFi stack
  delay(10);
}
