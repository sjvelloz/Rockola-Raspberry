/*
 * Rockola — mando de botones por WiFi (ESP32 DevKit ~30/32 pines)
 *
 * 1) Instala Arduino IDE + soporte ESP32 (espressif)
 * 2) Placa: "ESP32 Dev Module"
 * 3) Edita WIFI_SSID, WIFI_PASS y ROCKOLA_HOST
 * 4) Sube el sketch (cable USB)
 *
 * Botones módulo VCC/GND/OUT (activo en alto al pulsar):
 *   VCC → 3V3 de la ESP32
 *   GND → GND
 *   OUT → GPIO de la tabla
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include "wifi_secrets.h"  // SSID/clave/IP (local; no va a GitHub)

// Hold para reinicio (como en la Pi)
const unsigned long REBOOT_HOLD_MS = 2500;

struct Button {
  const char* name;
  uint8_t pin;
  const char* path;       // POST path, o nullptr si es reboot por hold
  bool holdForReboot;
  bool lastHigh;
  unsigned long pressedSince;
  unsigned long lastFireMs;
};

Button buttons[] = {
  // name,        pin, path,                     hold,  last, since, lastFire
  {"credit",      32,  "/api/credits/add",       false, false, 0, 0},
  {"skip",        33,  "/api/player/skip",       false, false, 0, 0},
  {"pause",       25,  "/api/player/pause",      false, false, 0, 0},
  {"birthday",    26,  "/api/birthday/open",     false, false, 0, 0},
  {"reboot",      27,  "/api/system/reboot",     true,  false, 0, 0},
};

const size_t N_BUTTONS = sizeof(buttons) / sizeof(buttons[0]);
const unsigned long DEBOUNCE_MS = 40;
const unsigned long COOLDOWN_MS = 350;

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi");
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("OK IP=");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi FAIL — revisa SSID/clave");
  }
}

bool postPath(const char* path) {
  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
    if (WiFi.status() != WL_CONNECTED) return false;
  }

  String url = String("http://") + ROCKOLA_HOST + ":" + ROCKOLA_PORT + path;
  HTTPClient http;
  http.setConnectTimeout(2500);
  http.setTimeout(2500);
  if (!http.begin(url)) {
    Serial.println("http.begin fail");
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  int code = http.POST("{}");
  Serial.printf("POST %s → %d\n", path, code);
  http.end();
  return code > 0 && code < 400;
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\nRockola ESP32 buttons");

  for (size_t i = 0; i < N_BUTTONS; i++) {
    pinMode(buttons[i].pin, INPUT_PULLDOWN);
    buttons[i].lastHigh = digitalRead(buttons[i].pin) == HIGH;
  }

  connectWifi();
}

void loop() {
  unsigned long now = millis();

  for (size_t i = 0; i < N_BUTTONS; i++) {
    Button& b = buttons[i];
    bool high = digitalRead(b.pin) == HIGH;

    if (b.holdForReboot) {
      if (high) {
        if (b.pressedSince == 0) b.pressedSince = now;
        if (now - b.pressedSince >= REBOOT_HOLD_MS && now - b.lastFireMs > 5000) {
          Serial.println("REBOOT hold");
          postPath(b.path);
          b.lastFireMs = now;
          b.pressedSince = 0;  // evita spam
          delay(800);
        }
      } else {
        b.pressedSince = 0;
      }
    } else {
      // flanco de subida (activo en alto)
      if (high && !b.lastHigh) {
        delay(DEBOUNCE_MS);
        if (digitalRead(b.pin) == HIGH && now - b.lastFireMs > COOLDOWN_MS) {
          Serial.printf("BTN %s\n", b.name);
          postPath(b.path);
          b.lastFireMs = millis();
        }
      }
    }

    b.lastHigh = high;
  }

  delay(12);
}
