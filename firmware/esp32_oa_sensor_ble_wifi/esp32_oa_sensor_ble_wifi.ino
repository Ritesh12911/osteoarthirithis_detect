/*
 * ============================================================================
 *  OsteoBelt - AI-assisted early osteoarthritis (OA) screening knee brace
 *  Seeed XIAO ESP32-S3 firmware v3.0        MDoNER
 * ============================================================================
 *  Rewritten from OA_Detector_XIAO_ESP32S3.ino v2.1. Main fixes:
 *   - Audio: correct 24-bit scaling, DC removal, continuous capture task,
 *            windowed Goertzel spectrum, motion-gated crepitus-event detector
 *   - IMU:   no Adafruit libs; dual MPU6050 (0x68 thigh / 0x69 shank),
 *            complementary filter, real knee angle, ROM, stride regularity
 *   - Flex:  multi-point calibration stored in NVS (+ auto-calibration against
 *            the IMU knee angle), works for either divider orientation
 *   - Net:   HTTP POST runs in its own task (never stalls sensing), no
 *            blocking Wi-Fi reconnect, server URL settable at run time
 *   - BLE:   MTU 517 (v2.1 notifications were truncated to 20 bytes)
 *   - Safety: no Wi-Fi password in source, invalid sensor values are not
 *            reported as 0 degC / 33 degC asymmetry
 *
 *  BOARD SETTINGS (Arduino IDE, esp32 core 3.x)
 *    Board: XIAO_ESP32S3 | USB CDC On Boot: Enabled | PSRAM: OPI PSRAM
 *  LIBRARIES: ArduinoJson (v6 or v7), OneWire, DallasTemperature
 *             (Wire, WiFi, HTTPClient, Preferences, BLE come with the core)
 *
 *  PIN MAP (matches the OsteoBelt Hub PCB)
 *    D0  GPIO1  I2S BCLK  (INMP441 SCK)      D5  GPIO6  J_AUX data (opt. WS2812)
 *    D1  GPIO2  I2S WS                       D6  GPIO43 spare (J_AUX)
 *    D2  GPIO3  I2S SD                       D7  GPIO44 push button (to GND)
 *    D3  GPIO4  flex divider (ADC1)          D8  GPIO7  battery sense (1:2)
 *    D4  GPIO5  DS18B20 1-Wire (4.7k pull-up) D9/D10 GPIO8/9 I2C SDA/SCL
 *    GPIO21 on-board user LED (active LOW)
 *
 *  SERIAL COMMANDS (115200): type  help
 * ============================================================================
 */

#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <driver/i2s.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Preferences.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <math.h>

#define FW_VERSION "3.0"

// ---- Types are declared first: Arduino auto-generates function prototypes
// ---- above all code, so any type used in a function signature must precede them.
struct Imu {
  uint8_t addr = 0;
  bool ok = false, init = false;
  uint8_t fails = 0;
  float ax = 0, ay = 0, az = 0;                    // g
  float gx = 0, gy = 0, gz = 0;                    // deg/s (bias removed)
  float gbx = 0, gby = 0, gbz = 0;
  float theta = 0;                                 // sagittal angle, deg
  float pitch = 0, roll = 0, yaw = 0;
  uint32_t lastTry = 0;
};
struct AudioOut { float rms, dbfs, domHz, bandE; uint16_t events5s; uint8_t bins[16]; };

// ------------------------------- PINS ---------------------------------------
#define PIN_I2S_BCLK 1
#define PIN_I2S_WS   2
#define PIN_I2S_SD   3
#define PIN_FLEX     4
#define PIN_ONEWIRE  5
#define PIN_EXT_RGB  6
#define PIN_BUTTON   44
#define PIN_VBAT     7
#define PIN_SDA      8
#define PIN_SCL      9
#define PIN_LED      21

#define EXT_RGB_ENABLED 0     // 1 = WS2812 connected to J_AUX (D5)

// ------------------------------ TUNING --------------------------------------
#define IMU_THIGH_ADDR   0x68
#define IMU_SHANK_ADDR   0x69          // pod with AD0 tied to 3V3
#define I2C_HZ           200000
#define IMU_PERIOD_US    10000         // 100 Hz fusion loop
#define COMP_ALPHA       0.98f
#define SEND_INTERVAL_MS 500
#define FLEX_R_FIXED     10000.0f      // ohms, fixed divider resistor to GND
#define FLEX_VCC_MV      3300.0f       // measure the 3V3 rail for best accuracy
#define VBAT_DIV         2.0f          // 100k/100k divider on the hub PCB
#define ROM_REF_DEG      60.0f         // normal level-walking knee excursion
#define ROM_WINDOW_S     10
#define I2S_RATE         16000
#define AUDIO_FRAME      512           // 32 ms, 31.25 Hz resolution
#define NET_JSON_MAX     768
#define WIFI_RETRY_MS    20000
#define MAX_CAL          16
#define AC_BINS          13            // auto-cal: 10 deg bins, 0..130
#define AC_DURATION_MS   20000
#define DEFAULT_SERVER_URL "https://jointsense-jmkt.onrender.com/api/data"          // e.g. "http://192.168.1.50:5000/api/data"

// ------------------------------- BLE ----------------------------------------
#define BLE_DEVICE_NAME       "JointSense_OsteoBelt"
#define BLE_SERVICE_UUID      "12345678-1234-5678-1234-56789abcdef0"
#define BLE_SENSOR_CHAR_UUID  "12345678-1234-5678-1234-56789abcdef1"  // NOTIFY JSON telemetry
#define BLE_WIFI_CHAR_UUID    "12345678-1234-5678-1234-56789abcdef2"  // WRITE  SSID|PASSWORD
#define BLE_FFT_CHAR_UUID     "12345678-1234-5678-1234-56789abcdef3"  // NOTIFY 16-bin spectrum

static BLECharacteristic *bleSensor = nullptr, *bleWifi = nullptr, *bleFFT = nullptr;
static volatile bool bleConnected = false;
static volatile bool bleCredsPending = false;
static String blePendingSSID, blePendingPass;

class BleServerCb : public BLEServerCallbacks {
  void onConnect(BLEServer *) override { bleConnected = true; Serial.println("[BLE] client connected"); }
  void onDisconnect(BLEServer *s) override {
    bleConnected = false;
    Serial.println("[BLE] client disconnected, advertising again");
    s->startAdvertising();
  }
};

class WifiWriteCb : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    String v = String(c->getValue().c_str());
    v.trim();
    int sep = v.indexOf('|');
    if (sep <= 0 || sep >= (int)v.length() - 1) {
      Serial.println("[BLE] bad format, expected SSID|PASSWORD");
      if (bleWifi) { bleWifi->setValue("ERROR: use SSID|PASSWORD"); bleWifi->notify(); }
      return;
    }
    blePendingSSID = v.substring(0, sep);
    blePendingPass = v.substring(sep + 1);
    blePendingSSID.trim();
    blePendingPass.trim();
    bleCredsPending = true;                    // set last
    if (bleWifi) { bleWifi->setValue("RECEIVED: connecting..."); bleWifi->notify(); }
  }
};

// ------------------------------ GLOBALS -------------------------------------
static Preferences prefs;
static String wifiSSID, wifiPASS, serverURL, patientId, patientSide;
static OneWire oneWire(PIN_ONEWIRE);
static DallasTemperature ds18b20(&oneWire);
static DeviceAddress dsAddr[2];
static int dsCount = 0;
static bool i2sOK = false;
static bool verboseJson = false;
static uint32_t sampleIdx = 0;

static const float RAD2DEG = 57.2957795f;
static inline float r2(float v) { return isfinite(v) ? roundf(v * 100.0f) / 100.0f : 0.0f; }
static inline float wrap180(float a) { while (a > 180.0f) a -= 360.0f; while (a < -180.0f) a += 360.0f; return a; }

static volatile float g_motionDps = 0;        // knee motion speed -> audio gate
static volatile float g_risk = -1.0f;         // last backend risk score (0..1)
static char g_label[20] = "";

// ------------------------------- NVS ----------------------------------------
static void nvsPutStr(const char *k, const String &v) { prefs.begin("oa", false); prefs.putString(k, v); prefs.end(); }
static void nvsPutFloat(const char *k, float v)       { prefs.begin("oa", false); prefs.putFloat(k, v);  prefs.end(); }
static void nvsPutInt(const char *k, int v)           { prefs.begin("oa", false); prefs.putInt(k, v);    prefs.end(); }

// ============================== STATUS LED ===================================
enum LedMode { M_BOOT, M_BLE_ONLY, M_ONLINE, M_AUTOCAL, M_ERROR };
static LedMode ledMode = M_BOOT;

static void extRgb(uint8_t r, uint8_t g, uint8_t b) {
#if EXT_RGB_ENABLED
 #if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  rgbLedWrite(PIN_EXT_RGB, r, g, b);
 #else
  neopixelWrite(PIN_EXT_RGB, r, g, b);
 #endif
#else
  (void)r; (void)g; (void)b;
#endif
}

static void statusService() {
  uint32_t t = millis();
  bool on = false;
  switch (ledMode) {
    case M_BOOT:     on = true; break;
    case M_BLE_ONLY: on = (t % 1000) < 100; break;
    case M_ONLINE:   on = (t % 2000) < 60; break;
    case M_AUTOCAL:  on = (t % 200) < 100; break;
    case M_ERROR:    { uint32_t p = t % 1200; on = (p < 120) || (p > 240 && p < 360); } break;
  }
  digitalWrite(PIN_LED, on ? LOW : HIGH);

  static int lastCol = -1;                         // external RGB = OA risk colour
  int col = 0;
  if (ledMode == M_AUTOCAL) col = ((t % 400) < 200) ? 4 : 0;
  else if (g_risk > 0.6f) col = 1;
  else if (g_risk > 0.3f) col = 2;
  else if (g_risk >= 0.0f) col = 3;
  if (col != lastCol) {
    lastCol = col;
    switch (col) {
      case 1: extRgb(40, 0, 0); break;
      case 2: extRgb(40, 18, 0); break;
      case 3: extRgb(0, 30, 0); break;
      case 4: extRgb(0, 0, 40); break;
      default: extRgb(0, 0, 4); break;
    }
  }
}

// ================================ BATTERY ====================================
static float vbat = 0;
static void batteryService() {
  float mv = 0;
  for (int i = 0; i < 8; i++) mv += analogReadMilliVolts(PIN_VBAT);
  float v = (mv / 8.0f) * VBAT_DIV / 1000.0f;
  vbat = (vbat <= 0.01f) ? v : vbat + 0.2f * (v - vbat);
}
static int batteryPct(float v) {
  static const float V[7] = {3.30f, 3.60f, 3.70f, 3.80f, 3.90f, 4.00f, 4.20f};
  static const float P[7] = {0, 5, 15, 40, 60, 80, 100};
  if (v < 2.5f) return 0;                          // no battery (USB powered)
  if (v <= V[0]) return 0;
  if (v >= V[6]) return 100;
  for (int i = 0; i < 6; i++)
    if (v < V[i + 1]) return (int)(P[i] + (v - V[i]) * (P[i + 1] - P[i]) / (V[i + 1] - V[i]));
  return 100;
}

// ============================= MPU6050 DRIVER ================================

static Imu imuT, imuS;                             // thigh (0x68), shank (0x69)

static bool i2cWriteReg(uint8_t a, uint8_t r, uint8_t v) {
  Wire.beginTransmission(a); Wire.write(r); Wire.write(v);
  return Wire.endTransmission() == 0;
}
static bool i2cReadRegs(uint8_t a, uint8_t r, uint8_t *buf, uint8_t n) {
  Wire.beginTransmission(a); Wire.write(r);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((uint8_t)a, (uint8_t)n) != n) return false;
  for (uint8_t i = 0; i < n; i++) buf[i] = Wire.read();
  return true;
}

static bool imuBegin(Imu &m) {
  uint8_t who = 0;
  if (!i2cReadRegs(m.addr, 0x75, &who, 1)) return false;
  if (who != 0x68 && who != 0x70 && who != 0x72) return false;   // genuine / common clones
  if (!i2cWriteReg(m.addr, 0x6B, 0x01)) return false;             // wake, PLL(gyro X) clock
  delay(50);
  i2cWriteReg(m.addr, 0x1A, 0x03);                                // DLPF ~44 Hz
  i2cWriteReg(m.addr, 0x19, 0x04);                                // 200 Hz internal rate
  i2cWriteReg(m.addr, 0x1B, 0x08);                                // gyro  +-500 dps
  i2cWriteReg(m.addr, 0x1C, 0x08);                                // accel +-4 g
  m.ok = true; m.init = false; m.fails = 0;
  return true;
}

static bool imuReadRaw(Imu &m) {
  uint8_t b[14];
  if (!i2cReadRegs(m.addr, 0x3B, b, 14)) return false;
  auto s = [&](int i) { return (int16_t)((b[i] << 8) | b[i + 1]); };
  m.ax = s(0) / 8192.0f;  m.ay = s(2) / 8192.0f;  m.az = s(4) / 8192.0f;
  m.gx = s(8) / 65.5f - m.gbx;  m.gy = s(10) / 65.5f - m.gby;  m.gz = s(12) / 65.5f - m.gbz;
  return true;
}

static void imuCalibGyro(Imu &m) {                 // sensor must be still ~0.8 s
  const int N = 150;
  float sx = 0, sy = 0, sz = 0, zmin = 1e9f, zmax = -1e9f;
  int got = 0;
  m.gbx = m.gby = m.gbz = 0;
  for (int i = 0; i < N; i++) {
    if (imuReadRaw(m)) { sx += m.gx; sy += m.gy; sz += m.gz; zmin = fminf(zmin, m.gz); zmax = fmaxf(zmax, m.gz); got++; }
    delay(5);
  }
  if (got > N / 2 && (zmax - zmin) < 4.0f) {
    m.gbx = sx / got; m.gby = sy / got; m.gbz = sz / got;
    Serial.printf("[IMU 0x%02X] gyro bias %.2f %.2f %.2f dps\n", m.addr, m.gbx, m.gby, m.gbz);
  } else {
    Serial.printf("[IMU 0x%02X] gyro bias skipped (moving). Reboot while still.\n", m.addr);
  }
}

// Complementary filter on the sagittal-plane angle. Sensor Z must be the knee
// flexion axis (module flat on the lateral side of the limb, Z pointing out).
static void imuUpdate(Imu &m, float dt) {
  float mag = sqrtf(m.ax * m.ax + m.ay * m.ay + m.az * m.az);
  float acc = atan2f(m.ay, m.ax) * RAD2DEG;
  if (!m.init) { m.theta = acc; m.init = true; }
  else {
    float pred = wrap180(m.theta - m.gz * dt);
    float k = (fabsf(mag - 1.0f) < 0.20f) ? (1.0f - COMP_ALPHA) : 0.0f;   // ignore accel when accelerating hard
    m.theta = wrap180(pred + k * wrap180(acc - pred));
  }
  float p = atan2f(-m.ax, sqrtf(m.ay * m.ay + m.az * m.az)) * RAD2DEG;
  float r = atan2f(m.ay, m.az) * RAD2DEG;
  m.pitch += 0.2f * (p - m.pitch);
  m.roll = wrap180(m.roll + 0.2f * wrap180(r - m.roll));
  m.yaw = wrap180(m.yaw + m.gz * dt);              // drifts: MPU6050 has no magnetometer
}

// ============================ KNEE ANGLE / GAIT ==============================
static float kneeRawZero = 0;
static int   kneeSignDir = 0;                      // 0 = not yet learned
static float g_kneeImu = 0;
static bool  g_kneeImuValid = false;

static void zeroKnee() {
  if (!(imuT.ok && imuS.ok)) { Serial.println("[CAL] Zero needs both IMUs."); return; }
  kneeRawZero = wrap180(imuT.theta - imuS.theta);
  imuT.yaw = imuS.yaw = 0;
  nvsPutFloat("kz", kneeRawZero);
  Serial.printf("[CAL] Knee zero stored (raw %.1f). Leg should be straight.\n", kneeRawZero);
}

static float strideMs[8]; static uint8_t strideN = 0;
static uint32_t lastSwingMs = 0;
static float accMean[3] = {0, 0, 0}; static double accSq[3] = {0, 0, 0}; static uint32_t accN = 0;

static void gaitUpdate(float wAbs, float hi, float lo, uint32_t now) {
  static bool inSwing = false;
  if (!inSwing && wAbs > hi) {
    inSwing = true;
    if (now - lastSwingMs > 300) {
      uint32_t iv = now - lastSwingMs;
      if (lastSwingMs != 0 && iv < 2500) {
        if (strideN == 8) { memmove(strideMs, strideMs + 1, 7 * sizeof(float)); strideN = 7; }
        strideMs[strideN++] = (float)iv;
      }
      lastSwingMs = now;
    }
  } else if (inSwing && wAbs < lo) inSwing = false;
}
static bool isMoving() { return lastSwingMs != 0 && (millis() - lastSwingMs) < 3000; }

// ================================ FLEX SENSOR ================================
struct FlexCal { uint8_t n; float deg[MAX_CAL]; float ohm[MAX_CAL]; };
static FlexCal flexCal = {0, {0}, {0}};
static float flexOhmEma = 0;

static float flexReadMv() {
  uint32_t s = 0;
  for (int i = 0; i < 16; i++) s += analogReadMilliVolts(PIN_FLEX);
  return s / 16.0f;
}
static float flexMvToOhm(float mv) {
  if (mv < 5.0f) return 1e7f;
  if (mv >= FLEX_VCC_MV - 5.0f) return 0.0f;
  return FLEX_R_FIXED * (FLEX_VCC_MV - mv) / mv;   // flex on top (3V3 side), fixed R to GND
}
static void flexCalSort() {
  for (int i = 1; i < flexCal.n; i++) {
    float o = flexCal.ohm[i], d = flexCal.deg[i];
    int j = i - 1;
    while (j >= 0 && flexCal.ohm[j] > o) { flexCal.ohm[j + 1] = flexCal.ohm[j]; flexCal.deg[j + 1] = flexCal.deg[j]; j--; }
    flexCal.ohm[j + 1] = o; flexCal.deg[j + 1] = d;
  }
}
static void flexCalAdd(float deg, float ohm) {
  for (int i = 0; i < flexCal.n; i++)
    if (fabsf(flexCal.deg[i] - deg) < 2.0f) { flexCal.ohm[i] = ohm; flexCal.deg[i] = deg; flexCalSort(); return; }
  if (flexCal.n >= MAX_CAL) { Serial.println("[CAL] flex table full (cal clear)"); return; }
  flexCal.deg[flexCal.n] = deg; flexCal.ohm[flexCal.n] = ohm; flexCal.n++;
  flexCalSort();
}
static void flexCalSave() { prefs.begin("oa", false); prefs.putBytes("flexcal", &flexCal, sizeof(flexCal)); prefs.end(); }

static bool flexCalibrated() { return flexCal.n >= 2; }
static float flexAngleFromOhm(float ohm) {         // piecewise-linear in resistance
  if (flexCal.n < 2) return 0;
  uint8_t n = flexCal.n, i = 0;
  while (i < n - 2 && ohm > flexCal.ohm[i + 1]) i++;
  float span = flexCal.ohm[i + 1] - flexCal.ohm[i];
  float a = (fabsf(span) < 1.0f) ? flexCal.deg[i]
          : flexCal.deg[i] + (ohm - flexCal.ohm[i]) * (flexCal.deg[i + 1] - flexCal.deg[i]) / span;
  return constrain(a, -10.0f, 160.0f);
}

// ---- auto-calibration: slowly flex the knee 0->120->0 while the IMU pair
//      provides the reference angle; flex resistance is binned against it.
static bool acActive = false;
static uint32_t acStart = 0;
static float acSumO[AC_BINS], acSumD[AC_BINS];
static uint16_t acCnt[AC_BINS];

static void acBegin() {
  if (!(imuT.ok && imuS.ok)) { Serial.println("[AUTOCAL] needs both IMU pods."); return; }
  memset(acSumO, 0, sizeof(acSumO)); memset(acSumD, 0, sizeof(acSumD)); memset(acCnt, 0, sizeof(acCnt));
  acActive = true; acStart = millis();
  Serial.println("[AUTOCAL] started: slowly bend the knee 0 -> ~120 -> 0 deg, twice (20 s).");
}
static void acFinish(bool ok) {
  acActive = false;
  if (!ok) { Serial.println("[AUTOCAL] cancelled."); return; }
  FlexCal backup = flexCal;
  flexCal.n = 0;
  int pts = 0; float lo = 999, hi = -999;
  for (int b = 0; b < AC_BINS; b++) {
    if (acCnt[b] >= 15) {
      float d = acSumD[b] / acCnt[b], o = acSumO[b] / acCnt[b];
      flexCalAdd(d, o); pts++; lo = fminf(lo, d); hi = fmaxf(hi, d);
    }
  }
  if (pts >= 4 && (hi - lo) >= 40.0f) {
    flexCalSave();
    Serial.printf("[AUTOCAL] OK: %d points, %.0f..%.0f deg stored.\n", pts, lo, hi);
  } else {
    flexCal = backup;
    Serial.printf("[AUTOCAL] FAILED (%d usable bins, span %.0f deg). Bend slower / wider and retry.\n", pts, hi - lo);
  }
}
static void acSample() {
  float deg = constrain(g_kneeImu, 0.0f, 129.9f);
  int b = (int)(deg / 10.0f);
  float o = flexMvToOhm(flexReadMv());
  acSumO[b] += o; acSumD[b] += deg; acCnt[b]++;
}

// ============================== TEMPERATURE ==================================
static float jointC = NAN, ambC = NAN;
static void dsInit() {
  ds18b20.begin();
  dsCount = ds18b20.getDeviceCount();
  for (int i = 0; i < dsCount && i < 2; i++) ds18b20.getAddress(dsAddr[i], i);
  if (dsCount > 0) {
    ds18b20.setResolution(11);                      // 0.125 C, ~375 ms
    ds18b20.setWaitForConversion(false);
    ds18b20.requestTemperatures();
  }
}
static void tempService() {
  static uint32_t lastTry = 0;
  if (dsCount == 0) { if (millis() - lastTry > 10000) { lastTry = millis(); dsInit(); } return; }
  float j = ds18b20.getTempC(dsAddr[0]);
  jointC = (j > 5.0f && j < 45.0f) ? j : NAN;
  if (dsCount > 1) { float a = ds18b20.getTempC(dsAddr[1]); ambC = (a > -20.0f && a < 60.0f) ? a : NAN; }
  ds18b20.requestTemperatures();
}

// ================================ AUDIO ======================================
static const float FFT_FREQS[16] = {60, 120, 200, 300, 400, 500, 600, 700, 800, 1000, 1200, 1600, 2000, 3000, 5000, 7000};
static AudioOut g_audio = {0, -120, 0, 0, 0, {0}};
static portMUX_TYPE audioMux = portMUX_INITIALIZER_UNLOCKED;

static bool setupI2S() {
  i2s_config_t cfg; memset(&cfg, 0, sizeof(cfg));
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = I2S_RATE;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;            // INMP441 L/R pin -> GND
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 6;
  cfg.dma_buf_len = 256;
  cfg.use_apll = false;
  i2s_pin_config_t pins; memset(&pins, 0, sizeof(pins));
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = PIN_I2S_BCLK;
  pins.ws_io_num = PIN_I2S_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = PIN_I2S_SD;
  if (i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL) != ESP_OK) { Serial.println("[I2S] install failed"); return false; }
  if (i2s_set_pin(I2S_NUM_0, &pins) != ESP_OK) { Serial.println("[I2S] set_pin failed"); i2s_driver_uninstall(I2S_NUM_0); return false; }
  i2s_zero_dma_buffer(I2S_NUM_0);
  return true;
}

// Continuous capture + analysis (own task, so nothing else can starve the DMA).
static void audioTask(void *) {
  static int32_t raw[AUDIO_FRAME];
  static float frame[AUDIO_FRAME], hann[AUDIO_FRAME];
  float coeff[16], hannSum = 0;
  for (int i = 0; i < AUDIO_FRAME; i++) { hann[i] = 0.5f * (1.0f - cosf(2.0f * (float)M_PI * i / (AUDIO_FRAME - 1))); hannSum += hann[i]; }
  for (int b = 0; b < 16; b++) coeff[b] = 2.0f * cosf(2.0f * (float)M_PI * FFT_FREQS[b] / I2S_RATE);

  float dcX = 0, dcY = 0, rmsEma = 0, floorE = 1e-4f, spec[16] = {0};
  uint32_t lastEvt = 0, evt[32] = {0}; uint8_t evtIdx = 0;

  for (;;) {
    size_t br = 0;
    esp_err_t e = i2s_read(I2S_NUM_0, raw, sizeof(raw), &br, pdMS_TO_TICKS(100));
    if (e != ESP_OK || br < sizeof(raw)) { vTaskDelay(1); continue; }

    double sumSq = 0;
    for (int i = 0; i < AUDIO_FRAME; i++) {
      float x = (float)(raw[i] >> 8) / 8388608.0f;           // 24-bit signed -> +-1.0
      float y = x - dcX + 0.995f * dcY;                      // DC blocker (INMP441 has offset)
      dcX = x; dcY = y; frame[i] = y; sumSq += (double)y * y;
    }
    float rms = sqrtf((float)(sumSq / AUDIO_FRAME));
    rmsEma += 0.1f * (rms - rmsEma);

    float amp[16], bandSq = 0;
    for (int b = 0; b < 16; b++) {
      float s1 = 0, s2 = 0;
      for (int i = 0; i < AUDIO_FRAME; i++) { float s0 = frame[i] * hann[i] + coeff[b] * s1 - s2; s2 = s1; s1 = s0; }
      float mag = sqrtf(fmaxf(s1 * s1 + s2 * s2 - coeff[b] * s1 * s2, 0.0f));
      amp[b] = 2.0f * mag / hannSum;                         // ~ sine amplitude, full scale = 1.0
      spec[b] += 0.2f * (amp[b] - spec[b]);
      if (b >= 3 && b <= 12) bandSq += amp[b] * amp[b];      // 300 Hz .. 2 kHz
    }
    float bandE = sqrtf(bandSq);

    // crepitus = short broadband bursts in 0.3-2 kHz, only counted while the knee moves
    uint32_t now = millis();
    bool burst = bandE > floorE * 4.0f && bandE > 0.0015f;
    if (burst && g_motionDps > 15.0f && (now - lastEvt) > 80) { lastEvt = now; evt[evtIdx++ & 31] = now; }
    floorE += ((bandE < floorE * 2.0f) ? 0.02f : 0.001f) * (bandE - floorE);
    floorE = fmaxf(floorE, 1e-5f);

    uint16_t ev5 = 0;
    for (int i = 0; i < 32; i++) if (evt[i] && (now - evt[i]) < 5000) ev5++;

    int best = 2;
    for (int b = 3; b < 16; b++) if (spec[b] > spec[best]) best = b;

    AudioOut o;
    o.rms = rmsEma; o.dbfs = 20.0f * log10f(rmsEma + 1e-7f); o.domHz = FFT_FREQS[best];
    o.bandE = bandE; o.events5s = ev5;
    for (int b = 0; b < 16; b++) {
      float db = 20.0f * log10f(spec[b] + 1e-7f);            // -90 dBFS .. -30 dBFS -> 0..255
      o.bins[b] = (uint8_t)constrain((int)((db + 90.0f) * 255.0f / 60.0f), 0, 255);
    }
    portENTER_CRITICAL(&audioMux); g_audio = o; portEXIT_CRITICAL(&audioMux);
  }
}
static AudioOut audioSnapshot() { AudioOut o; portENTER_CRITICAL(&audioMux); o = g_audio; portEXIT_CRITICAL(&audioMux); return o; }

// ================================ NETWORK ====================================
struct NetMsg { char json[NET_JSON_MAX]; };
static QueueHandle_t netQ = nullptr;
static uint32_t wifiLastAttempt = 0;
static bool provWait = false; static uint32_t provStart = 0;

static void wifiBegin() {
  if (wifiSSID.length() == 0) return;
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(wifiSSID.c_str(), wifiPASS.c_str());
  wifiLastAttempt = millis();
  Serial.printf("[WiFi] connecting to '%s' (2.4 GHz only)...\n", wifiSSID.c_str());
}
static void wifiService() {
  static bool wasUp = false;
  bool up = (WiFi.status() == WL_CONNECTED);
  if (up && !wasUp) Serial.printf("[WiFi] connected, IP %s, RSSI %d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  if (!up && wasUp) Serial.println("[WiFi] lost connection");
  wasUp = up;
  if (!up && wifiSSID.length() && millis() - wifiLastAttempt > WIFI_RETRY_MS) {
    WiFi.disconnect(); WiFi.begin(wifiSSID.c_str(), wifiPASS.c_str()); wifiLastAttempt = millis();
  }
}
static void bleWifiNotify(const String &s) { if (bleWifi) { bleWifi->setValue(s.c_str()); bleWifi->notify(); } }
static void provisioningService() {
  if (bleCredsPending) {
    bleCredsPending = false;
    wifiSSID = blePendingSSID; wifiPASS = blePendingPass;
    nvsPutStr("ssid", wifiSSID); nvsPutStr("pass", wifiPASS);
    WiFi.disconnect(); wifiBegin();
    provWait = true; provStart = millis();
  }
  if (provWait) {
    if (WiFi.status() == WL_CONNECTED) { bleWifiNotify("WIFI_CONNECTED:" + WiFi.localIP().toString()); provWait = false; }
    else if (millis() - provStart > 25000) { bleWifiNotify("WIFI_FAILED:check SSID/password/2.4GHz"); provWait = false; }
  }
}

static void netEnqueue(const char *json) {
  NetMsg m; strlcpy(m.json, json, sizeof(m.json));
  if (xQueueSend(netQ, &m, 0) != pdTRUE) { NetMsg d; xQueueReceive(netQ, &d, 0); xQueueSend(netQ, &m, 0); }  // drop oldest
}

static void netTask(void *) {
  HTTPClient http;
  http.setReuse(true);
  NetMsg m; uint8_t fails = 0;
  for (;;) {
    if (xQueueReceive(netQ, &m, portMAX_DELAY) != pdTRUE) continue;
    if (WiFi.status() != WL_CONNECTED || serverURL.length() == 0) continue;   // BLE-only: drop
    http.setConnectTimeout(2000); http.setTimeout(3000);
    if (!http.begin(serverURL)) continue;
    http.addHeader("Content-Type", "application/json");
    int code = http.POST((uint8_t *)m.json, strlen(m.json));
    if (code == 200) {
      fails = 0;
      String resp = http.getString();
#if ARDUINOJSON_VERSION_MAJOR >= 7
      JsonDocument rd;
#else
      StaticJsonDocument<256> rd;
#endif
      if (!deserializeJson(rd, resp)) {
        g_risk = rd["risk_score"] | 0.0f;
        const char *lb = rd["label"] | "UNKNOWN";
        strlcpy(g_label, lb, sizeof(g_label));
        Serial.printf("[NET] risk %.1f%% label %s\n", g_risk * 100.0f, g_label);
      }
    } else {
      Serial.printf("[NET] POST failed (%d) -> %s\n", code, serverURL.c_str());
      if (++fails >= 3) { fails = 0; xQueueReset(netQ); vTaskDelay(pdMS_TO_TICKS(4000)); }
    }
    http.end();
  }
}

static void startBLE() {
  BLEDevice::init(BLE_DEVICE_NAME);
  BLEDevice::setMTU(517);                                    // without this notifications are cut to 20 bytes
  BLEServer *srv = BLEDevice::createServer();
  srv->setCallbacks(new BleServerCb());
  BLEService *svc = srv->createService(BLEUUID(BLE_SERVICE_UUID), 20, 0);

  bleSensor = svc->createCharacteristic(BLE_SENSOR_CHAR_UUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  bleSensor->addDescriptor(new BLE2902());
  bleSensor->setValue("{\"status\":\"waiting\"}");

  bleWifi = svc->createCharacteristic(BLE_WIFI_CHAR_UUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_NOTIFY);
  bleWifi->addDescriptor(new BLE2902());
  bleWifi->setValue("Send SSID|PASSWORD");
  bleWifi->setCallbacks(new WifiWriteCb());

  bleFFT = svc->createCharacteristic(BLE_FFT_CHAR_UUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  bleFFT->addDescriptor(new BLE2902());
  static uint8_t z[16] = {0};
  bleFFT->setValue(z, 16);

  svc->start();
  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(BLE_SERVICE_UUID);
  adv->setScanResponse(true);
  adv->setMinPreferred(0x06);
  adv->setMaxPreferred(0x12);
  BLEDevice::startAdvertising();
  Serial.println("[BLE] advertising as " BLE_DEVICE_NAME);
}

// ============================== SERIAL CONSOLE ===============================
static void printStatus() {
  float mv = flexReadMv(), ohm = flexMvToOhm(mv);
  Serial.println("---------------- STATUS ----------------");
  Serial.printf("IMU thigh 0x68 : %s | IMU shank 0x69 : %s\n", imuT.ok ? "OK" : "missing", imuS.ok ? "OK" : "missing");
  if (g_kneeImuValid) Serial.printf("Knee (IMU)     : %.1f deg  (zero %.1f, sign %d)\n", g_kneeImu, kneeRawZero, kneeSignDir);
  Serial.printf("Flex           : %.0f mV  %.0f ohm  -> %.1f deg  (%s, %d pts)\n", mv, ohm,
                flexAngleFromOhm(ohm), flexCalibrated() ? "calibrated" : "NOT calibrated", flexCal.n);
  Serial.printf("DS18B20        : %d sensor(s)  joint %.2f C  ambient %.2f C\n", dsCount, jointC, ambC);
  AudioOut a = audioSnapshot();
  Serial.printf("Mic            : %s  level %.1f dBFS  dom %.0f Hz  events(5s) %u\n", i2sOK ? "OK" : "FAIL", a.dbfs, a.domHz, a.events5s);
  Serial.printf("Battery        : %.2f V (%d%%)\n", vbat, batteryPct(vbat));
  Serial.printf("Wi-Fi          : %s  SSID '%s'  URL '%s'\n", WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString().c_str() : "down", wifiSSID.c_str(), serverURL.c_str());
  Serial.printf("Patient        : %s / %s   BLE %s\n", patientId.c_str(), patientSide.c_str(), bleConnected ? "connected" : "idle");
  Serial.println("----------------------------------------");
}
static void printHelp() {
  Serial.println(F("Commands:\n"
    "  status                 show all sensors\n"
    "  zero                   knee angle = 0 now (leg straight)   [button: short press]\n"
    "  autocal                flex auto-calibration vs IMU angle  [button: hold 1.5 s]\n"
    "  cal <deg>              add manual flex calibration point at <deg>\n"
    "  cal show | cal clear   list / erase flex calibration\n"
    "  sign                   flip knee angle sign\n"
    "  id <text> | side <L|R> patient id / knee side\n"
    "  url <http://ip:port/api/data>   backend URL (saved)\n"
    "  wifi <ssid>|<password> | wifi clear\n"
    "  json on|off            print telemetry JSON\n"
    "  reboot"));
}
static void handleCommand(String line) {
  line.trim();
  String lc = line; lc.toLowerCase();
  if (lc == "help" || lc == "?") printHelp();
  else if (lc == "status") printStatus();
  else if (lc == "zero") zeroKnee();
  else if (lc == "autocal") { if (acActive) acFinish(false); else acBegin(); }
  else if (lc == "sign") { kneeSignDir = (kneeSignDir == -1) ? 1 : -1; nvsPutInt("ksign", kneeSignDir); Serial.printf("[CAL] sign = %d\n", kneeSignDir); }
  else if (lc == "cal show") {
    for (int i = 0; i < flexCal.n; i++) Serial.printf("  %6.1f deg  %8.0f ohm\n", flexCal.deg[i], flexCal.ohm[i]);
    if (!flexCal.n) Serial.println("  (empty)");
  }
  else if (lc == "cal clear") { flexCal.n = 0; flexCalSave(); Serial.println("[CAL] flex calibration cleared"); }
  else if (lc.startsWith("cal ")) {
    float deg = line.substring(4).toFloat();
    float ohm = flexMvToOhm(flexReadMv());
    delay(300); ohm = 0.5f * (ohm + flexMvToOhm(flexReadMv()));
    flexCalAdd(deg, ohm); flexCalSave();
    Serial.printf("[CAL] flex point: %.1f deg = %.0f ohm  (%d points)\n", deg, ohm, flexCal.n);
  }
  else if (lc.startsWith("id "))   { patientId = line.substring(3); patientId.trim(); nvsPutStr("pid", patientId); Serial.println("[CFG] id saved"); }
  else if (lc.startsWith("side ")) { patientSide = (lc.charAt(5) == 'r') ? "RIGHT" : "LEFT"; nvsPutStr("side", patientSide); Serial.println("[CFG] side " + patientSide); }
  else if (lc.startsWith("url "))  { serverURL = line.substring(4); serverURL.trim(); nvsPutStr("url", serverURL); Serial.println("[CFG] url saved: " + serverURL); }
  else if (lc == "wifi clear")     { wifiSSID = ""; wifiPASS = ""; nvsPutStr("ssid", ""); nvsPutStr("pass", ""); WiFi.disconnect(); Serial.println("[CFG] wifi cleared"); }
  else if (lc.startsWith("wifi ")) {
    String v = line.substring(5); int sep = v.indexOf('|');
    if (sep <= 0) Serial.println("usage: wifi SSID|PASSWORD");
    else { blePendingSSID = v.substring(0, sep); blePendingPass = v.substring(sep + 1); bleCredsPending = true; }
  }
  else if (lc == "json on") verboseJson = true;
  else if (lc == "json off") verboseJson = false;
  else if (lc == "reboot") ESP.restart();
  else if (line.length()) Serial.println("unknown command, type: help");
}
static void serialService() {
  static String buf;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') { if (buf.length()) handleCommand(buf); buf = ""; }
    else if (buf.length() < 200) buf += c;
  }
}

// =============================== BUTTON ======================================
static void buttonService() {
  static bool prev = true; static uint32_t tDown = 0;
  bool s = digitalRead(PIN_BUTTON);
  if (prev && !s) tDown = millis();
  if (!prev && s) {
    uint32_t d = millis() - tDown;
    if (d >= 1500) { if (acActive) acFinish(false); else acBegin(); }
    else if (d > 40) zeroKnee();
  }
  prev = s;
}

// ============================= SENSOR SERVICES ===============================
static void imuService() {
  static uint32_t lastUs = 0; static uint8_t tick = 0;
  uint32_t nowUs = micros();
  if (nowUs - lastUs < IMU_PERIOD_US) return;
  float dt = (nowUs - lastUs) / 1e6f;
  if (dt > 0.05f) dt = 0.01f;
  lastUs = nowUs;
  uint32_t nowMs = millis();

  Imu *arr[2] = {&imuT, &imuS};
  for (int i = 0; i < 2; i++) {
    Imu &m = *arr[i];
    if (m.ok) {
      if (imuReadRaw(m)) { m.fails = 0; imuUpdate(m, dt); }
      else if (++m.fails >= 20) { m.ok = false; Serial.printf("[IMU 0x%02X] lost\n", m.addr); }
    } else if (nowMs - m.lastTry > 3000) {            // hot-plug: try to bring the pod back
      m.lastTry = nowMs;
      if (imuBegin(m)) Serial.printf("[IMU 0x%02X] connected\n", m.addr);
    }
  }

  // knee angle from the two segment angles
  if (imuT.ok && imuS.ok && imuT.init && imuS.init) {
    float kr = wrap180((imuT.theta - imuS.theta) - kneeRawZero);
    if (kneeSignDir == 0 && fabsf(kr) > 25.0f) { kneeSignDir = (kr > 0) ? 1 : -1; nvsPutInt("ksign", kneeSignDir); }
    g_kneeImu = (kneeSignDir == 0 ? 1 : kneeSignDir) * kr;
    g_kneeImuValid = true;
  } else g_kneeImuValid = false;

  // motion gate for audio + gait
  Imu *prim = imuT.ok ? &imuT : (imuS.ok ? &imuS : nullptr);
  float sp = (imuT.ok && imuS.ok) ? fabsf(imuT.gz - imuS.gz) : (prim ? fabsf(prim->gz) : 0.0f);
  g_motionDps = g_motionDps + 0.1f * (sp - g_motionDps);
  if (imuS.ok) gaitUpdate(fabsf(imuS.gz), 150.0f, 50.0f, nowMs);
  else if (imuT.ok) gaitUpdate(fabsf(imuT.gz), 70.0f, 25.0f, nowMs);

  // dynamic acceleration RMS (gravity removed by running mean)
  if (prim) {
    float v[3] = {prim->ax, prim->ay, prim->az};
    for (int k = 0; k < 3; k++) { float d = v[k] - accMean[k]; accMean[k] += 0.02f * d; accSq[k] += (double)d * d; }
    accN++;
  }

  if (acActive && (++tick & 1) == 0) {                // 50 Hz auto-cal sampling
    if (g_kneeImuValid) acSample();
    if (nowMs - acStart > AC_DURATION_MS) acFinish(true);
  }
}

static float romBuf[ROM_WINDOW_S * 10]; static uint16_t romIdx = 0, romCount = 0;
static float stiffness = 0;

static void slowService() {                           // 10 Hz
  static uint32_t last = 0, lastBat = 0;
  uint32_t now = millis();
  if (now - last < 100) return;
  last = now;
  float ohm = flexMvToOhm(flexReadMv());
  flexOhmEma = (flexOhmEma <= 0) ? ohm : flexOhmEma + 0.3f * (ohm - flexOhmEma);
  float ang = g_kneeImuValid ? g_kneeImu : (flexCalibrated() ? flexAngleFromOhm(flexOhmEma) : 0.0f);
  romBuf[romIdx] = ang; romIdx = (romIdx + 1) % (ROM_WINDOW_S * 10);
  if (romCount < ROM_WINDOW_S * 10) romCount++;
  if (now - lastBat > 1000) { lastBat = now; batteryService(); }
}

static void telemetryService() {
  static uint32_t last = 0;
  uint32_t now = millis();
  if (now - last < SEND_INTERVAL_MS) return;
  last = now;

  tempService();
  AudioOut au = audioSnapshot();

  // range of motion over the last ROM_WINDOW_S seconds
  float rom = 0;
  if (romCount >= 30) {
    float lo = 1e9f, hi = -1e9f;
    for (uint16_t i = 0; i < romCount; i++) { lo = fminf(lo, romBuf[i]); hi = fmaxf(hi, romBuf[i]); }
    rom = hi - lo;
  }
  bool moving = isMoving();
  if (moving && romCount >= 30) stiffness = constrain(1.0f - rom / ROM_REF_DEG, 0.0f, 1.0f);

  // stride statistics
  float cadence = 0, regularity = 0;
  if (moving && strideN >= 3) {
    float mean = 0; for (int i = 0; i < strideN; i++) mean += strideMs[i]; mean /= strideN;
    float dsum = 0; for (int i = 1; i < strideN; i++) dsum += fabsf(strideMs[i] - strideMs[i - 1]);
    cadence = 120000.0f / mean;                        // steps/min (2 steps per stride)
    regularity = constrain(1.0f - (dsum / (strideN - 1)) / mean, 0.0f, 1.0f);
  }

  Imu *prim = imuT.ok ? &imuT : (imuS.ok ? &imuS : nullptr);
  float arms[3] = {0, 0, 0};
  if (accN > 0) for (int k = 0; k < 3; k++) arms[k] = sqrtf((float)(accSq[k] / accN)) * 9.80665f;
  accSq[0] = accSq[1] = accSq[2] = 0; accN = 0;

  float flexAng = flexCalibrated() ? flexAngleFromOhm(flexOhmEma) : 0.0f;
  float disagree = (g_kneeImuValid && flexCalibrated()) ? fabsf(g_kneeImu - flexAng) : 0.0f;
  float kneeBest = g_kneeImuValid ? g_kneeImu : flexAng;
  float tAsym = isnan(jointC) ? 0.0f : fabsf(jointC - 33.0f);
  float crep = constrain(au.events5s / 8.0f, 0.0f, 1.0f);

#if ARDUINOJSON_VERSION_MAJOR >= 7
  JsonDocument doc;
#else
  StaticJsonDocument<1024> doc;
#endif
  doc["patient_id"] = patientId;            doc["side"] = patientSide;
  doc["timestamp"] = now;                   doc["sample_idx"] = sampleIdx++;
  doc["audio_rms"] = r2(au.rms * 100.0f) / 100.0f;
  doc["audio_dbfs"] = r2(au.dbfs);
  doc["dominant_freq_hz"] = (int)au.domHz;
  doc["crepitus_score"] = r2(crep);         doc["crepitus_events"] = au.events5s;
  doc["joint_temp_c"] = r2(isnan(jointC) ? 0.0f : jointC);
  doc["ambient_temp_c"] = r2(isnan(ambC) ? 0.0f : ambC);
  doc["temp_asymmetry"] = r2(tAsym);
  doc["temp_valid"] = isnan(jointC) ? 0 : 1;
  doc["accel_rms_x"] = r2(arms[0]);         doc["accel_rms_y"] = r2(arms[1]);   doc["accel_rms_z"] = r2(arms[2]);
  doc["gyro_range_deg"] = r2(rom);          doc["rom_deg"] = r2(rom);
  doc["step_symmetry"] = r2(regularity);    doc["cadence_spm"] = r2(cadence);
  doc["pitch"] = r2(prim ? prim->pitch : 0); doc["roll"] = r2(prim ? prim->roll : 0); doc["yaw"] = r2(prim ? prim->yaw : 0);
  doc["knee_angle_deg"] = r2(kneeBest);
  doc["flex_angle_deg"] = r2(flexAng);      doc["flex_stiffness"] = r2(stiffness);
  doc["flex_calibrated"] = flexCalibrated() ? 1 : 0;
  doc["imu_pair_ok"] = g_kneeImuValid ? 1 : 0;
  doc["angle_disagree_deg"] = r2(disagree);
  doc["battery_v"] = r2(vbat);              doc["battery_pct"] = batteryPct(vbat);
  doc["fw"] = FW_VERSION;

  char out[NET_JSON_MAX];
  size_t len = serializeJson(doc, out, sizeof(out));

  if (bleConnected && bleSensor && len > 0) { bleSensor->setValue((uint8_t *)out, len); bleSensor->notify(); }
  netEnqueue(out);

  Serial.printf("[DATA] knee %.1f | flex %.1f%s | ROM %.0f | cad %.0f | crep %.2f | T %.1fC | %.2fV | mic %.0fdB\n",
                kneeBest, flexAng, flexCalibrated() ? "" : "(uncal)", rom, cadence, crep, jointC, vbat, au.dbfs);
  if (verboseJson) Serial.println(out);
}

static void fftService() {
  static uint32_t last = 0;
  uint32_t now = millis();
  if (!bleConnected || !bleFFT || !i2sOK || now - last < 100) return;
  last = now;
  AudioOut a = audioSnapshot();
  bleFFT->setValue(a.bins, 16);
  bleFFT->notify();
}

// ================================ SETUP / LOOP ===============================
void setup() {
  Serial.begin(115200);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 2500) delay(10);
  Serial.printf("\n=== OsteoBelt firmware v%s | %s %u MHz ===\n", FW_VERSION, ESP.getChipModel(), ESP.getCpuFreqMHz());

  pinMode(PIN_LED, OUTPUT); digitalWrite(PIN_LED, LOW);
  pinMode(PIN_BUTTON, INPUT_PULLUP);

  prefs.begin("oa", true);
  wifiSSID = prefs.getString("ssid", ""); wifiPASS = prefs.getString("pass", "");
  serverURL = prefs.getString("url", DEFAULT_SERVER_URL);
  patientId = prefs.getString("pid", "PATIENT_001"); patientSide = prefs.getString("side", "LEFT");
  kneeRawZero = prefs.getFloat("kz", 0.0f); kneeSignDir = prefs.getInt("ksign", 0);
  if (prefs.getBytesLength("flexcal") == sizeof(FlexCal)) prefs.getBytes("flexcal", &flexCal, sizeof(FlexCal));
  prefs.end();
  if (flexCal.n > MAX_CAL) flexCal.n = 0;

  analogReadResolution(12);
  analogSetPinAttenuation(PIN_FLEX, ADC_11db);
  analogSetPinAttenuation(PIN_VBAT, ADC_11db);

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(I2C_HZ);
  Wire.setTimeOut(20);
  imuT.addr = IMU_THIGH_ADDR; imuS.addr = IMU_SHANK_ADDR;
  Serial.println("[IMU] keep the brace still for 2 s (gyro bias)...");
  if (imuBegin(imuT)) imuCalibGyro(imuT); else Serial.println("[IMU] thigh pod (0x68) not found");
  if (imuBegin(imuS)) imuCalibGyro(imuS); else Serial.println("[IMU] shank pod (0x69) not found");

  dsInit();
  Serial.printf("[DS18B20] %d sensor(s)\n", dsCount);

  i2sOK = setupI2S();
  if (i2sOK) xTaskCreatePinnedToCore(audioTask, "audio", 8192, NULL, 3, NULL, 1);
  Serial.printf("[I2S] mic %s\n", i2sOK ? "OK" : "FAILED");

  netQ = xQueueCreate(6, sizeof(NetMsg));
  xTaskCreatePinnedToCore(netTask, "net", 10240, NULL, 1, NULL, 0);
  WiFi.persistent(false);
  startBLE();
  wifiBegin();

  batteryService();
  if (flexCal.n < 2) Serial.println("[FLEX] not calibrated: use 'autocal' (hold button 1.5 s) or 'cal <deg>'");
  if (kneeRawZero == 0.0f) Serial.println("[KNEE] press the button with the leg straight to zero the knee angle");
  Serial.println("Type 'help' for commands.");
  ledMode = M_BLE_ONLY;
}

void loop() {
  serialService();
  buttonService();
  imuService();
  slowService();
  fftService();
  telemetryService();
  provisioningService();
  wifiService();

  if (acActive) ledMode = M_AUTOCAL;
  else if (!imuT.ok && !imuS.ok) ledMode = M_ERROR;
  else if (WiFi.status() == WL_CONNECTED && serverURL.length()) ledMode = M_ONLINE;
  else ledMode = M_BLE_ONLY;
  statusService();
  delay(1);
}
