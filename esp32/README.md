# Mando ESP32 → Rockola (WiFi)

Los botones van a la ESP32; ella llama por HTTP a la Raspberry (mismas funciones que el GPIO).

## 1. Software en el PC

1. Instala [Arduino IDE](https://www.arduino.cc/en/software)
2. `Archivo → Preferencias → URLs adicionales`:
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
3. `Herramientas → Placa → Gestor de placas` → busca **esp32** (Espressif) → Instalar
4. Copia secretos si hace falta: `wifi_secrets.h.example` → `wifi_secrets.h`
   (en este PC ya está rellenado con la WiFi actual; **no se sube a GitHub**)
5. Abre `esp32/rockola_buttons/rockola_buttons.ino`
6. Placa: **ESP32 Dev Module**
7. Puerto: el COM que salga al enchufar el USB
8. Subir

Abre el **Monitor serie** a **115200** baudios: debe decir `WiFi OK IP=...`

Para apuntar a rockola-1, en `wifi_secrets.h` pon `ROCKOLA_HOST = "192.168.1.244"`.

## 2. Cableado (módulos VCC / GND / OUT)

| Módulo | ESP32 |
|--------|-------|
| **VCC** (todos) | **3V3** (no 5V) |
| **GND** (todos) | **GND** |
| OUT crédito | **GPIO 32** |
| OUT skip | **GPIO 33** |
| OUT pausa | **GPIO 25** |
| OUT cumpleaños | **GPIO 26** |
| OUT reinicio | **GPIO 27** (mantener ~2,5 s) |

La ESP32 se alimenta por **USB** (cargador o powerbank).

## 3. En la Raspberry

Actualiza el código (incluye `POST /api/system/reboot`) y reinicia jukebox.
La Pi y la ESP32 deben estar en la **misma WiFi**.

Prueba rápida desde el PC:

```bash
curl -X POST http://192.168.1.245:8000/api/player/pause
```
