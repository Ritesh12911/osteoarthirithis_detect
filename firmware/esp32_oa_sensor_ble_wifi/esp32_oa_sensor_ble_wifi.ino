/*
 * ============================================================
 *  AI-Assisted Early Osteoarthritis Detection System
 *  ESP32-S3 N16R8 Firmware — v2.1 (BLE Wi-Fi Provisioning)
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
 *    GPIO 48 (built-in RGB NeoPixel on ESP32-S3-DevKit)
 *    Green  = Normal | Red = OA Risk | Orange = Borderline
 *    Yellow = Connecting | Blue = BLE provisioning mode
 *
 *  DEPENDENCIES (install via Arduino Library Manager):
 *  - Wire (built-in)
 *  - WiFi (built-in ESP32)
 *  - HTTPClient (built-in ESP32)
 *  - Preferences (built-in ESP32)
 *  - ESP32 BLE Arduino (built into ESP32 Arduino core)
 *  - Adafruit MLX90614 Library
 *  - Adafruit MPU6050
 *  - Adafruit Unified Sensor
 *  - ArduinoJson (v6 or v7)
 *
 *  BLE WI-FI PROVISIONING:
 *  ─────────────────────────────────────────────────────────
 *  If Wi-Fi fails on boot, the device advertises as "OA-ESP32-SETUP".
 *  Use nRF Connect (Android/iOS) to:
 *    1. Connect to "OA-ESP32-SETUP"
 *    2. Find service: 12345678-1234-5678-1234-56789abcdef0
 *    3. Write to Wi-Fi char (..def1): YOUR_SSID|YOUR_PASSWORD
 *    4. Watch status char (..def2) for WIFI_CONNECTED:<IP>
 *  Credentials are saved to NVS flash (persist across reboots).
 *
 *  CLOUD INTEGRATION:
 *  ─────────────────────────────────────────────────────────
 *  Update SERVER_URL below to your deployed backend URL.
 *  Example: "https://your-app.railway.app/api/data"
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
#include <Preferences.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <math.h>

// ─── BLE WI-FI PROVISIONING ──────────────────────────────────────────────────
#define BLE_DEVICE_NAME       "OA-ESP32-SETUP"
#define BLE_SERVICE_UUID      "12345678-1234-5678-1234-56789abcdef0"
#define BLE_WIFI_CHAR_UUID    "12345678-1234-5678-1234-56789abcdef1"
#define BLE_STATUS_CHAR_UUID  "12345678-1234-5678-1234-56789abcdef2"

BLEServer          *bleServer              = nullptr;
BLECharacteristic  *bleWifiCharacteristic  = nullptr;
BLECharacteristic  *bleStatusCharacteristic= nullptr;
volatile bool       bleCredentialsPending  = false;
String              blePendingSSID;
String              blePendingPassword;
bool                bleStarted             = false;

class WiFiProvisionCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    String value = characteristic->getValue();
    value.trim();

    int separator = value.indexOf('|');
    if (separator < 0) separator = value.indexOf('\n');

    if (separator <= 0 || separator >= (int)value.length() - 1) {
      Serial.println("[BLE] Invalid format. Send SSID|PASSWORD");
      if (bleStatusCharacteristic) {
        bleStatusCharacteristic->setValue("ERROR: Use SSID|PASSWORD");
        bleStatusCharacteristic->notify();
      }
      return;
    }

    blePendingSSID     = value.substring(0, separator);
    blePendingPassword = value.substring(separator + 1);
    blePendingSSID.trim();
    blePendingPassword.trim();
    bleCredentialsPending = true;

    Serial.printf("[BLE] Wi-Fi credentials received for SSID: %s\n", blePendingSSID.c_str());
    if (bleStatusCharacteristic) {
      bleStatusCharacteristic->setValue("RECEIVED: connecting...");
      bleStatusCharacteristic->notify();
    }
  }
};

void startBLEProvisioning();
void handleBLEProvisioning();

// ─── DATA STRUCTURES ──────────────────────────────────────────────────────────
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
  float tempAsymmetry;  // |jointTemp - 33.0°C|
};

struct FlexFeatures {
  float angleDeg;
  float stiffnessScore;
};

// ─── FORWARD PROTOTYPES ───────────────────────────────────────────────────────
void setup();
void loop();
bool setupI2S();
void setLED(int r, int g, int b);
AudioFeatures readMicrophoneFeatures();
IMUFeatures   readIMUFeatures();
TempFeatures  readTempFeatures();
FlexFeatures  readFlexFeatures();
void sendData(AudioFeatures& audio, TempFeatures& temp, IMUFeatures& imu, FlexFeatures& flex);
bool connectWiFi(uint32_t timeoutMs = 20000);
void loadWiFiCredentials();
void saveWiFiCredentials(const String& ssid, const String& pass);

// ─── USER SETTINGS ────────────────────────────────────────────────────────────
// Default fallback credentials (overridden by NVS or BLE provisioning).
// NOTE: ESP32-S3 supports 2.4 GHz Wi-Fi only.
const char* DEFAULT_WIFI_SSID = "motorola edge 60 fusion";
const char* DEFAULT_WIFI_PASS = "Ritesh1234";

String wifiSSID;
String wifiPASS;

// ─── SERVER URL ───────────────────────────────────────────────────────────────
// *** UPDATE THIS to your deployed backend URL when hosted on Railway/Render ***
// Local development:  "http://192.168.x.x:5000/api/data"
// Railway cloud:      "https://your-app.up.railway.app/api/data"
const char* SERVER_URL      = "http://169.254.236.15:5000/api/data";

// Set to false to test sensors without sending HTTP (useful for diagnostics).
const bool ENABLE_HTTP_POST = true;

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
Preferences       preferences;
bool              mlxOK    = false;
bool              mpuOK    = false;
bool              i2sOK    = false;
int32_t           i2sBuffer[I2S_BUFFER_SIZE];
unsigned long     lastSendTime       = 0;
const int         SEND_INTERVAL_MS   = 500;
int               sessionSampleCount = 0;

// ─── STATUS LED ───────────────────────────────────────────────────────────────
void setLED(int r, int g, int b) {
#ifdef RGB_BUILTIN
  neopixelWrite(RGB_BUILTIN, r, g, b);
#endif
}

// ─── I2S SETUP ────────────────────────────────────────────────────────────────
bool setupI2S() {
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

  esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  if (err != ESP_OK) {
    Serial.printf("[ERR] I2S driver install failed: 0x%08X\n", (unsigned)err);
    return false;
  }

  err = i2s_set_pin(I2S_PORT, &pin_config);
  if (err != ESP_OK) {
    Serial.printf("[ERR] I2S pin setup failed: 0x%08X\n", (unsigned)err);
    i2s_driver_uninstall(I2S_PORT);
    return false;
  }

  i2s_start(I2S_PORT);
  Serial.println("[I2S] Microphone initialized");
  return true;
}

// ─── MICROPHONE FEATURES ──────────────────────────────────────────────────────
AudioFeatures readMicrophoneFeatures() {
  AudioFeatures feat = {0.0f, 0.0f, 0.0f};
  if (!i2sOK) return feat;

  size_t bytesRead = 0;
  i2s_read(I2S_PORT, &i2sBuffer, sizeof(i2sBuffer), &bytesRead, portMAX_DELAY);
  int samplesRead = bytesRead / sizeof(int32_t);

  if (samplesRead == 0) return feat;

  // RMS amplitude
  double sumSq  = 0.0;
  float  maxAmp = 0.0f;
  for (int i = 0; i < samplesRead; i++) {
    float sample = (float)(i2sBuffer[i] >> 14) / 32768.0f;
    sumSq += sample * sample;
    if (fabs(sample) > maxAmp) maxAmp = fabs(sample);
  }
  feat.rms = sqrt(sumSq / samplesRead);

  // Zero-crossing rate → dominant frequency estimate
  int zeroCrossings = 0;
  for (int i = 1; i < samplesRead; i++) {
    float s_prev = (float)(i2sBuffer[i-1] >> 14);
    float s_curr = (float)(i2sBuffer[i]   >> 14);
    if ((s_prev > 0 && s_curr < 0) || (s_prev < 0 && s_curr > 0)) {
      zeroCrossings++;
    }
  }
  float timeWindow    = (float)samplesRead / I2S_SAMPLE_RATE;
  feat.dominantFreqHz = (zeroCrossings / 2.0f) / timeWindow;
  feat.dominantFreqHz = constrain(feat.dominantFreqHz, 20.0f, 8000.0f);

  // Crepitus score: OA joint sounds > 300 Hz with elevated RMS
  if (feat.dominantFreqHz > 300 && feat.rms > 0.02f) {
    float rawScore    = (feat.dominantFreqHz - 300.0f) / 500.0f * feat.rms * 20.0f;
    feat.crepitusScore = (rawScore < 1.0f) ? rawScore : 1.0f;
  } else {
    feat.crepitusScore = 0.0f;
  }

  return feat;
}

// ─── IMU FEATURES ─────────────────────────────────────────────────────────────
IMUFeatures readIMUFeatures() {
  IMUFeatures feat = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f};
  if (!mpuOK) return feat;

  sensors_event_t accel, gyro, temp;
  mpu.getEvent(&accel, &gyro, &temp);

  feat.accelRmsX = fabs(accel.acceleration.x);
  feat.accelRmsY = fabs(accel.acceleration.y);
  feat.accelRmsZ = fabs(accel.acceleration.z);

  // Angular velocity magnitude → ROM estimate over 500ms window
  float gyroMag = sqrt(
    gyro.gyro.x * gyro.gyro.x +
    gyro.gyro.y * gyro.gyro.y +
    gyro.gyro.z * gyro.gyro.z
  );
  feat.gyroRangeDeg = gyroMag * (180.0f / (float)M_PI) * (SEND_INTERVAL_MS / 1000.0f);
  feat.gyroRangeDeg = constrain(feat.gyroRangeDeg, 0.0f, 180.0f);

  // Step symmetry: ratio of lateral to vertical acceleration
  float lateral  = fabs(accel.acceleration.x);
  float vertical = fabs(accel.acceleration.z) + 0.001f;
  feat.stepSymmetry = constrain(1.0f - (lateral / vertical), 0.0f, 1.0f);

  return feat;
}

// ─── TEMPERATURE FEATURES ─────────────────────────────────────────────────────
TempFeatures readTempFeatures() {
  TempFeatures feat = {0.0f, 0.0f, 0.0f};
  if (!mlxOK) return feat;

  feat.ambientTempC  = mlx.readAmbientTempC();
  feat.jointTempC    = mlx.readObjectTempC();
  // Normal knee surface ~32–34°C; OA joints run warmer
  feat.tempAsymmetry = fabs(feat.jointTempC - 33.0f);
  return feat;
}

// ─── FLEX SENSOR ──────────────────────────────────────────────────────────────
FlexFeatures readFlexFeatures() {
  FlexFeatures feat = {0.0f, 0.0f};

  // Average 10 ADC readings for noise reduction
  int adcSum = 0;
  for (int i = 0; i < 10; i++) {
    adcSum += analogRead(FLEX_PIN);
    delayMicroseconds(100);
  }
  int adcVal = adcSum / 10;

  // Map ADC (12-bit 0–4095) → angle
  // Calibration: flat(0°) ≈ 1700 ADC, fully bent(130°) ≈ 3000 ADC
  feat.angleDeg = map(adcVal, 1700, 3000, 0, 130);
  feat.angleDeg = constrain(feat.angleDeg, 0.0f, 180.0f);

  // Stiffness: lower ROM = stiffer joint (OA signature)
  feat.stiffnessScore = constrain(1.0f - (feat.angleDeg / 130.0f), 0.0f, 1.0f);

  return feat;
}

// ─── SEND DATA TO BACKEND ─────────────────────────────────────────────────────
void sendData(AudioFeatures& audio, TempFeatures& temp,
              IMUFeatures& imu, FlexFeatures& flex) {

#if ARDUINOJSON_VERSION_MAJOR >= 7
  JsonDocument doc;
#else
  StaticJsonDocument<1024> doc;
#endif

  doc["patient_id"]      = PATIENT_ID;
  doc["side"]            = PATIENT_SIDE;
  doc["timestamp"]       = millis();
  doc["sample_idx"]      = sessionSampleCount++;

  // Microphone
  doc["audio_rms"]         = audio.rms;
  doc["dominant_freq_hz"]  = audio.dominantFreqHz;
  doc["crepitus_score"]    = audio.crepitusScore;

  // Temperature
  doc["joint_temp_c"]      = temp.jointTempC;
  doc["ambient_temp_c"]    = temp.ambientTempC;
  doc["temp_asymmetry"]    = temp.tempAsymmetry;

  // IMU
  doc["accel_rms_x"]       = imu.accelRmsX;
  doc["accel_rms_y"]       = imu.accelRmsY;
  doc["accel_rms_z"]       = imu.accelRmsZ;
  doc["gyro_range_deg"]    = imu.gyroRangeDeg;
  doc["step_symmetry"]     = imu.stepSymmetry;

  // Flex
  doc["flex_angle_deg"]    = flex.angleDeg;
  doc["flex_stiffness"]    = flex.stiffnessScore;

  String jsonStr;
  serializeJson(doc, jsonStr);

  // ── HTTP POST ────────────────────────────────────────────────────────────────
  if (!ENABLE_HTTP_POST) {
    Serial.println("[HTTP] Disabled (ENABLE_HTTP_POST=false). Printing JSON only.");
  } else if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.setConnectTimeout(3000);
    http.setTimeout(5000);
    Serial.printf("[HTTP] POST --> %s\n", SERVER_URL);

    if (!http.begin(SERVER_URL)) {
      Serial.println("[ERR] HTTP begin() failed. Check SERVER_URL.");
    } else {
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

        // LED feedback
        if      (riskScore > 0.6f) setLED(255,   0, 0);   // Red:    High OA risk
        else if (riskScore > 0.3f) setLED(255, 165, 0);   // Orange: Borderline
        else                       setLED(  0, 255, 0);   // Green:  Normal

      } else {
        Serial.printf("[ERR] HTTP code: %d\n", httpCode);
        setLED(0, 0, 255);  // Blue: server error
      }
      http.end();
    }
  } else {
    Serial.println("[WARN] Wi-Fi disconnected — attempting reconnect...");
    setLED(255, 255, 0);
    connectWiFi(10000);
  }

  // Always print JSON to Serial for debugging
  Serial.println(jsonStr);
}

// ─── NVS CREDENTIAL STORAGE ───────────────────────────────────────────────────
void loadWiFiCredentials() {
  preferences.begin("wifi", true);
  wifiSSID = preferences.getString("ssid", "");
  wifiPASS = preferences.getString("pass", "");
  preferences.end();

  if (wifiSSID.length() == 0) wifiSSID = DEFAULT_WIFI_SSID;
  if (wifiPASS.length() == 0) wifiPASS = DEFAULT_WIFI_PASS;

  Serial.printf("[WiFi] Configured SSID: %s\n", wifiSSID.c_str());
}

void saveWiFiCredentials(const String& ssid, const String& pass) {
  preferences.begin("wifi", false);
  preferences.putString("ssid", ssid);
  preferences.putString("pass", pass);
  preferences.end();
  wifiSSID = ssid;
  wifiPASS = pass;
  Serial.println("[WiFi] Credentials saved to NVS flash.");
}

// ─── BLE PROVISIONING ─────────────────────────────────────────────────────────
void startBLEProvisioning() {
  if (bleStarted) return;

  Serial.println();
  Serial.println("[BLE] Starting Bluetooth Wi-Fi provisioning...");
  Serial.println("[BLE] Device name: OA-ESP32-SETUP");
  Serial.println("[BLE] Use nRF Connect: write SSID|PASSWORD to char ..def1");

  BLEDevice::init(BLE_DEVICE_NAME);
  bleServer = BLEDevice::createServer();

  BLEService *service = bleServer->createService(BLE_SERVICE_UUID);

  bleWifiCharacteristic = service->createCharacteristic(
      BLE_WIFI_CHAR_UUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE);

  bleStatusCharacteristic = service->createCharacteristic(
      BLE_STATUS_CHAR_UUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);

  bleWifiCharacteristic->setValue("Send SSID|PASSWORD");
  bleWifiCharacteristic->setCallbacks(new WiFiProvisionCallbacks());
  bleStatusCharacteristic->setValue("WAITING_FOR_WIFI");

  service->start();

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(BLE_SERVICE_UUID);
  advertising->setScanResponse(true);
  advertising->setMinPreferred(0x06);
  advertising->setMaxPreferred(0x12);
  BLEDevice::startAdvertising();

  bleStarted = true;
  Serial.println("[BLE] *** ADVERTISING as OA-ESP32-SETUP ***");
}

void handleBLEProvisioning() {
  if (!bleCredentialsPending) return;

  String ssid = blePendingSSID;
  String pass = blePendingPassword;
  bleCredentialsPending = false;

  Serial.printf("[BLE] Trying Wi-Fi SSID: %s\n", ssid.c_str());
  setLED(255, 255, 0);

  saveWiFiCredentials(ssid, pass);
  bool ok = connectWiFi(20000);

  if (ok) {
    String msg = "WIFI_CONNECTED:" + WiFi.localIP().toString();
    bleStatusCharacteristic->setValue(msg.c_str());
    bleStatusCharacteristic->notify();
    Serial.println("[BLE] Wi-Fi connected successfully via BLE provisioning.");
    setLED(0, 255, 0);
  } else {
    bleStatusCharacteristic->setValue("WIFI_FAILED:check SSID/password/2.4GHz");
    bleStatusCharacteristic->notify();
    Serial.println("[BLE] Wi-Fi connection failed. BLE remains available.");
    setLED(255, 0, 0);
  }
}

// ─── WI-FI CONNECTION ─────────────────────────────────────────────────────────
bool connectWiFi(uint32_t timeoutMs) {
  if (WiFi.status() == WL_CONNECTED) return true;

  Serial.printf("[WiFi] SSID: %s\n", wifiSSID.c_str());
  Serial.println("[WiFi] Starting 2.4 GHz connection...");

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);        // Disable sleep for more reliable connection
  WiFi.disconnect(true, true);
  delay(300);
  WiFi.begin(wifiSSID.c_str(), wifiPASS.c_str());

  uint32_t   start      = millis();
  wl_status_t lastStatus = WL_NO_SHIELD;

  while (WiFi.status() != WL_CONNECTED && millis() - start < timeoutMs) {
    wl_status_t st = WiFi.status();
    if (st != lastStatus) {
      Serial.printf("\n[WiFi] status=%d", (int)st);
      lastStatus = st;
    }
    Serial.print(".");
    delay(500);
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[WiFi] *** CONNECTED ***");
    Serial.printf("[WiFi] IP      : %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("[WiFi] Gateway : %s\n", WiFi.gatewayIP().toString().c_str());
    Serial.printf("[WiFi] RSSI    : %d dBm\n", WiFi.RSSI());
    return true;
  }

  Serial.printf("[WiFi] FAILED. Final status=%d\n", (int)WiFi.status());
  switch (WiFi.status()) {
    case WL_NO_SSID_AVAIL:  Serial.println("[WiFi] Reason: SSID not found (check 2.4GHz)."); break;
    case WL_CONNECT_FAILED: Serial.println("[WiFi] Reason: Authentication failed (check password)."); break;
    default:                Serial.println("[WiFi] Reason: Timeout — check range & MAC filtering."); break;
  }
  return false;
}

// ─── SETUP ────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  // Wait up to 3s for USB CDC Serial (ESP32-S3 native USB)
  uint32_t serialStart = millis();
  while (!Serial && millis() - serialStart < 3000) delay(10);
  delay(200);

  Serial.println();
  Serial.println("==============================================");
  Serial.println(" OA Detection System -- ESP32-S3 N16R8 v2.1");
  Serial.println(" SIH 2026 | MDoNER | PS-26004");
  Serial.println("==============================================");
  Serial.printf("[BOOT] Chip    : %s\n", ESP.getChipModel());
  Serial.printf("[BOOT] CPU     : %u MHz\n", ESP.getCpuFreqMHz());
  Serial.printf("[BOOT] Flash   : %u MB\n", ESP.getFlashChipSize() / (1024 * 1024));
  Serial.printf("[BOOT] Heap    : %u bytes free\n", ESP.getFreeHeap());
  Serial.printf("[BOOT] Backend : %s\n", SERVER_URL);

  // Load saved Wi-Fi credentials from NVS (falls back to DEFAULT_WIFI_*)
  loadWiFiCredentials();

  // Status LED init
  pinMode(STATUS_LED_PIN, OUTPUT);
  setLED(255, 255, 0);  // Yellow: initializing

  // ── WIFI FIRST (before sensors) so connection diagnostics are visible ────────
  bool wifiOK = connectWiFi(20000);
  if (wifiOK) {
    setLED(0, 255, 0);  // Green: connected
  } else {
    setLED(0, 0, 255);  // Blue: BLE provisioning mode
    startBLEProvisioning();
  }

  // ── I2C ──────────────────────────────────────────────────────────────────────
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  Serial.println("[I2C] Bus started on SDA=8, SCL=9");

  // ── SENSORS (NON-FATAL — board continues even if sensors missing) ─────────────
  mlxOK = mlx.begin();
  if (mlxOK) {
    Serial.println("[MLX90614] OK");
  } else {
    Serial.println("[ERR] MLX90614 not found. Check 3.3V/GND/SDA=8/SCL=9.");
  }

  mpuOK = mpu.begin();
  if (mpuOK) {
    mpu.setAccelerometerRange(MPU6050_RANGE_2_G);
    mpu.setGyroRange(MPU6050_RANGE_250_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    Serial.println("[MPU6050] OK -- +-2G, +-250 deg/s, 21Hz LPF");
  } else {
    Serial.println("[ERR] MPU6050 not found. Check AD0=GND and I2C wiring.");
  }

  // ── ADC FLEX SENSOR ───────────────────────────────────────────────────────────
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);  // 0–3.3V range
  Serial.printf("[ADC] Flex sensor on GPIO %d\n", FLEX_PIN);

  // ── I2S MICROPHONE ────────────────────────────────────────────────────────────
  i2sOK = setupI2S();
  Serial.printf("[I2S] Ready: %s\n", i2sOK ? "YES" : "NO");

  Serial.println("----------------------------------------------");
  Serial.println("[SYS] Startup complete. Streaming sensor data...");
  if (!wifiOK) {
    Serial.println("[SYS] Wi-Fi failed. Connect via BLE: OA-ESP32-SETUP");
    Serial.println("[SYS] nRF Connect -> write SSID|PASSWORD to char ..def1");
  }
  Serial.println("----------------------------------------------");
}

// ─── LOOP ─────────────────────────────────────────────────────────────────────
void loop() {
  // Handle BLE provisioning callbacks (non-blocking)
  handleBLEProvisioning();

  unsigned long now = millis();

  if (now - lastSendTime >= SEND_INTERVAL_MS) {
    lastSendTime = now;

    AudioFeatures audio = readMicrophoneFeatures();
    TempFeatures  temp  = readTempFeatures();
    IMUFeatures   imu   = readIMUFeatures();
    FlexFeatures  flex  = readFlexFeatures();

    // Serial log for monitoring
    Serial.printf("[DATA] temp=%.1fC | flex=%.1fdeg | crepitus=%.3f | stepSym=%.2f\n",
      temp.jointTempC, flex.angleDeg, audio.crepitusScore, imu.stepSymmetry);

    sendData(audio, temp, imu, flex);
  }

  delay(10);  // Yield for Wi-Fi stack
}
