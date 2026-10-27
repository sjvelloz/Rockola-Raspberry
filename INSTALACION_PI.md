# Guía completa — Rockola en Raspberry Pi 4

Paso a paso para dejarla **niquelada**: hardware, pines, software, kiosk y tele.

> Usuario/ruta por defecto: `pi` y `/home/pi/Rockola-Raspberry`. Cámbialos si usas otros.

---

## 0. Qué vas a montar

| Pieza | Función |
|-------|---------|
| Raspberry Pi 4 (4 GB+) | Cerebro |
| Pantalla DSI táctil 10,1" (1280×800) | UI Rockola (buscar / fichas / cola) |
| Tele por **micro-HDMI → HDMI** | Vídeo de las canciones de pago |
| Monedero CH-926 + optoacoplador PC817 | Fichas → GPIO 17 |
| 3 botones pulsadores | Crédito / Skip / Reinicio |
| Altavoces o audio de la tele | Sonido |
| (Opcional) protoboard + cables Dupont | Probar botones antes de caja definitiva |

Playlist de ambiente ya configurada:

`https://www.youtube.com/playlist?list=PL09D787B7F7593B9D`

---

## 1. Mapa de pines (BCM)

Vista típica de la Pi con los pines **que usamos** (numeración **BCM**, la que usa el código):

```
                         3V3  (1)  (2)  5V
                       GPIO2  (3)  (4)  5V
                       GPIO3  (5)  (6)  GND   ◄── GND común botones / opto
                       GPIO4  (7)  (8)  GPIO14
                         GND  (9) (10)  GPIO15
                      GPIO17 (11) (12)  GPIO18   ◄── 17 = MONEDERO (CH-926 / PC817)
                      GPIO27 (13) (14)  GND      ◄── 27 = +1 CRÉDITO
                      GPIO22 (15) (16)  GPIO23   ◄── 22 = SKIP | 23 = REINICIO (hold 2,5s)
                         3V3 (17) (18)  GPIO24
                      GPIO10 (19) (20)  GND
                       GPIO9 (21) (22)  GPIO25
                      GPIO11 (23) (24)  GPIO8
                         GND (25) (26)  GPIO7
                       … resto no usado por la Rockola …
```

| Señal | Pin físico | BCM | Qué hace |
|-------|------------|-----|----------|
| Monedero (vía PC817) | 11 | **17** | +1 ficha por pulso |
| Botón crédito | 13 | **27** | +1 crédito (personal / compensar) |
| Botón skip | 15 | **22** | Salta la canción actual |
| Botón reinicio | 16 | **23** | Reinicia la Pi si **mantienes 2,5 s** |
| Masa | 6, 9, 14, 20, 25… | **GND** | Común de botones y opto |

**Importante:** en el código y en esta guía hablamos siempre de **BCM** (17, 27, 22, 23), no del número “físico” de la placa.

---

## 2. ¿Hace falta protoboard?

**No es obligatorio.**

### Para probar rápido (recomendado al principio)
- Protoboard pequeña + cables Dupont hembra-macho (o hembra-hembra + botones con patillas).
- Cada botón: **un lado a GND**, **el otro al GPIO**.
- La Pi tiene **pull-up interno**: no hace falta resistencia extra para los botones.

```
   GPIO 27/22/23 ─────┬──── pin del botón
                      │
                     [BOTÓN]
                      │
   GND ───────────────┴──── otro pin del botón
```

### Para la máquina definitiva
- Los mismos 3 botones en el frontal de la caja.
- Cables soldados o conectores JST/Dupont bien sujetos.
- Monedero **siempre** con el **PC817** (optoacoplador) entre el CH-926 y el GPIO 17: **no conectes el monedero a 12 V directo al GPIO**.

Esquema conceptual monedero (según tu REQUISITOS):

```
  CH-926 (pulso) ──► PC817 ──► GPIO 17
                       │
                      GND
```

(Alimentación del monedero según su manual, típicamente 12 V aparte; la lógica al GPIO solo pasa por el opto.)

---

## 3. Pantallas

La Pi 4 tiene **2 micro-HDMI** + **DSI**:

```
  DSI          →  táctil 10,1"   →  Chromium (Rockola)
  micro-HDMI   →  tele           →  vídeo mpv a pantalla completa
```

1. Conecta la DSI (táctil).
2. Conecta **un** micro-HDMI a la tele (cable micro-HDMI → HDMI).
3. En software, `ROCKOLA_MPV_FS_SCREEN=1` (en `jukebox.service`) manda el vídeo a la tele. Si sale en la táctil, prueba `0` o `1` tras mirar:

```bash
xrandr --listmonitors
# o
wlr-randr
```

---

## 4. Software — instalación limpia

### 4.1 Sistema
- Raspberry Pi OS (Bookworm) con escritorio.
- Autologin del usuario gráfico.
- Red (Wi‑Fi o cable) estable.

```bash
sudo apt update
sudo apt install -y \
  python3-venv python3-dev \
  mpv \
  chromium-browser \
  curl unclutter \
  git
```

Si el navegador se llama solo `chromium`, edita `scripts/start-kiosk.sh`.

### 4.2 Proyecto

```bash
# Copia el proyecto a la Pi, por ejemplo:
cd /home/pi
# (scp, pendrive, git clone…)
cd /home/pi/Rockola-Raspberry

python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/pip install RPi.GPIO
./venv/bin/python init_db.py

mkdir -p media/ambient logs
chmod +x scripts/start-kiosk.sh

# Comprueba que la playlist está (ya viene en el repo):
cat media/ambient/playlist.url
```

### 4.3 Permisos GPIO + reboot sin contraseña

```bash
sudo usermod -aG gpio,video,audio,render pi

echo 'pi ALL=(ALL) NOPASSWD: /sbin/reboot' | sudo tee /etc/sudoers.d/rockola-reboot
sudo chmod 440 /etc/sudoers.d/rockola-reboot
```

Cierra sesión o reinicia para aplicar grupos.

### 4.4 Servicio backend

```bash
sudo cp /home/pi/Rockola-Raspberry/jukebox.service /etc/systemd/system/
# Revisa User= y rutas si no eres "pi"
sudo systemctl daemon-reload
sudo systemctl enable --now jukebox.service
systemctl status jukebox.service
curl -s http://127.0.0.1:8000/api/credits
```

### 4.5 Kiosk Chromium (táctil)

```bash
mkdir -p ~/.config/autostart
cp /home/pi/Rockola-Raspberry/scripts/rockola-kiosk.desktop ~/.config/autostart/
```

Opcional — ocultar cursor y no apagar pantalla (X11):

```bash
# En autostart o sesión:
unclutter -idle 0.3 -root &
xset s off
xset -dpms
xset s noblank
```

Reinicia y deberías ver la UI a pantalla completa en la DSI.

### 4.6 (Opcional) Actualizar yt-dlp cada día a las 06:00

```bash
crontab -e
```

```cron
0 6 * * * /home/pi/Rockola-Raspberry/venv/bin/python /home/pi/Rockola-Raspberry/maintenance.py --strict >> /home/pi/Rockola-Raspberry/logs/cron-ytdlp.log 2>&1
```

---

## 5. Pruebas en orden

1. **UI** en la táctil: http://127.0.0.1:8000/ (o sola al arrancar).
2. **Fichas por API** (si aún no hay monedero):
   ```bash
   curl -X POST 'http://127.0.0.1:8000/api/credits/add?amount=3'
   ```
3. Busca / “Las Más Sonadas” → encola → el vídeo debe salir en la **tele**.
4. Botón **crédito (27)**: sube fichas en el header.
5. Botón **skip (22)**: corta la canción.
6. Botón **reboot (23)**: mantener 2,5 s → reinicia (un toque corto no hace nada).
7. Vacía la cola: debe sonar ambiente **aleatorio** de tu playlist (solo audio).
8. Monedero: una ficha = +1 crédito.

Logs útiles:

```bash
journalctl -u jukebox.service -f
tail -f /home/pi/Rockola-Raspberry/logs/mpv-user.log
tail -f /home/pi/Rockola-Raspberry/logs/maintenance.log
```

---

## 6. Checklist final “niquelado”

- [ ] DSI táctil + Chromium kiosk
- [ ] Tele por micro-HDMI; vídeo en tele, UI en táctil
- [ ] `jukebox.service` enabled y estable
- [ ] `RPi.GPIO` instalado; grupos `gpio video audio`
- [ ] Pines: 17 monedero, 27 crédito, 22 skip, 23 reboot
- [ ] Opto PC817 en el monedero
- [ ] `playlist.url` con tu lista (ya puesta)
- [ ] Sudoers para `reboot`
- [ ] (Opcional) cron 06:00 `maintenance.py`
- [ ] Caja cerrada: sin acceso a teclado/ratón del sistema

---

## 7. Resumen de botones en la caja

| Botón en el frontal | Cable a | Uso diario |
|---------------------|---------|------------|
| “+ crédito” / servicio | GPIO **27** + GND | Equipo: regalar/compensar ficha |
| “Saltar” | GPIO **22** + GND | Tema malo / atasco |
| “Reinicio” (escondido o con protectión) | GPIO **23** + GND | Mantener 2,5 s si se cuelga |

Más detalle de kiosk/systemd también en `KIOSK.md`. Cuando cambies la interfaz, el backend y estos pines no hace falta tocarlos.
