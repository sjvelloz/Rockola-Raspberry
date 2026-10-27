# Configuración Raspberry Pi OS — Rockola en modo Kiosk

> **Guía completa de montaje (pines, botones, protoboard, checklist):** ver [`INSTALACION_PI.md`](INSTALACION_PI.md).

Guía para dejar el jukebox arrancando solo: backend FastAPI (`jukebox.service`), actualización de `yt-dlp` (`maintenance.py`) y Chromium a pantalla completa (1280×800).

> Sustituye `/home/pi/Rockola-Raspberry` y el usuario `pi` si tu ruta o usuario son distintos.

---

## 1. Dependencias del sistema

```bash
sudo apt update
sudo apt install -y \
  python3-venv python3-dev \
  mpv \
  chromium-browser \
  curl \
  unclutter \
  xdotool
```

En Raspberry Pi OS Bookworm el paquete del navegador puede llamarse `chromium` (sin `-browser`). Comprueba con:

```bash
command -v chromium-browser || command -v chromium
```

Si solo existe `chromium`, edita `scripts/start-kiosk.sh` y cambia el binario.

Clona / copia el proyecto y crea el venv:

```bash
cd /home/pi/Rockola-Raspberry
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/pip install RPi.GPIO
./venv/bin/python init_db.py
mkdir -p media/ambient logs
chmod +x scripts/start-kiosk.sh
```

Coloca MP3 de ambiente en `media/ambient/`.

---

## 2. Servicio systemd (`jukebox.service`)

El unit ejecuta `maintenance.py` (equivale a `yt-dlp -U`) **antes** de arrancar Uvicorn.

```bash
# Ajusta User/paths en el fichero si hace falta
sudo cp /home/pi/Rockola-Raspberry/jukebox.service /etc/systemd/system/jukebox.service
sudo systemctl daemon-reload
sudo systemctl enable --now jukebox.service
```

Comprobar:

```bash
systemctl status jukebox.service
journalctl -u jukebox.service -f
curl -s http://127.0.0.1:8000/api/credits
```

### Actualización diaria a las 06:00 (opcional)

Además del arranque, puedes programar cron:

```bash
crontab -e
```

Añade:

```cron
0 6 * * * /home/pi/Rockola-Raspberry/venv/bin/python /home/pi/Rockola-Raspberry/maintenance.py --strict >> /home/pi/Rockola-Raspberry/logs/cron-ytdlp.log 2>&1
```

---

## 3. Modo Kiosk con Chromium (pantalla completa)

### 3.1 Arranque automático al escritorio

1. En **Raspberry Pi Configuration** → **System** → **Boot**: *Desktop*.
2. Autologin del usuario gráfico (`pi`).

### 3.2 Autostart de Chromium

**Labwc / Wayfire (Bookworm por defecto):**

```bash
mkdir -p ~/.config/autostart
cp /home/pi/Rockola-Raspberry/scripts/rockola-kiosk.desktop ~/.config/autostart/
# Ajusta Exec= si tu ruta no es /home/pi/Rockola-Raspberry
```

**LXDE (versiones antiguas):**

```bash
mkdir -p ~/.config/lxsession/LXDE-pi
echo '@/home/pi/Rockola-Raspberry/scripts/start-kiosk.sh' >> ~/.config/lxsession/LXDE-pi/autostart
```

El script `scripts/start-kiosk.sh` espera a que responda `http://127.0.0.1:8000/` y lanza Chromium con:

- `--kiosk`
- `--noerrdialogs`
- `--disable-infobars`
- perfil propio (sin diálogos de “restaurar sesión”)

### 3.3 Ocultar cursor (opcional)

Añade al autostart:

```bash
unclutter -idle 0.3 -root &
```

### 3.4 Desactivar screensaver / blanking

```bash
mkdir -p ~/.config/labwc
# O en openbox/lxsession, según el compositor:
```

En sesión X11 clásica, en `~/.config/lxsession/LXDE-pi/autostart`:

```bash
@xset s off
@xset -dpms
@xset s noblank
```

En Wayland (labwc), desactiva el idle en la configuración del compositor o instala `wl-clipboard` / ajusta `~/.config/labwc/autostart` según tu imagen.

### 3.5 Resolución 1280×800 (pantalla DSI 10,1")

```bash
# Comprobar salidas
kmsprint || xrandr || wlr-randr
```

Si hace falta forzar modo, en `/boot/firmware/config.txt` (Bookworm) o `/boot/config.txt`:

```ini
# Ejemplo — ajusta al panel DSI concreto
display_auto_detect=1
```

Reinicia tras cambios de display.

### 3.6 Dos pantallas: táctil (UI) + tele (vídeo)

La **Raspberry Pi 4 ya trae 2 puertos micro-HDMI** (no uno). Además tienes el conector **DSI** de la pantalla táctil 10,1".

```
┌─────────────────────────────────────────────────────────┐
│  Raspberry Pi 4                                         │
│                                                         │
│  DSI  ──────────────►  Pantalla táctil 10,1" (Rockola)  │
│  micro-HDMI 0 ──────►  (libre / opcional)               │
│  micro-HDMI 1 ──────►  Tele del local (vídeo mpv)       │
└─────────────────────────────────────────────────────────┘
```

- **No hace falta “sacar dos HDMI de un solo puerto”**: usa **DSI + un micro-HDMI** (cable micro-HDMI → HDMI a la tele).
- Chromium kiosk se queda en la **táctil** (buscar / fichas / cola).
- mpv va a **fullscreen en la tele** (`ROCKOLA_MPV_FS_SCREEN=1` en `jukebox.service`).

Comprobar índices de pantalla:

```bash
xrandr --listmonitors   # o: wlr-randr
```

Si el vídeo sale en la táctil en vez de la tele, cambia en `/etc/systemd/system/jukebox.service`:

```ini
Environment=ROCKOLA_MPV_FS_SCREEN=0
```

(o `1`, el que corresponda a la tele) y luego:

```bash
sudo systemctl daemon-reload
sudo systemctl restart jukebox.service
```

---

## 4. GPIO (monedero y botón)

El usuario del servicio debe estar en el grupo `gpio` (ya previsto en `SupplementaryGroups` del unit):

```bash
sudo usermod -aG gpio,video,audio pi
```

Cierra sesión o reinicia para aplicar grupos.

| Señal                         | GPIO (BCM) | Notas                                      |
|-------------------------------|------------|--------------------------------------------|
| Monedero CH-926               | 17         | Pulso vía PC817                            |
| +1 crédito (personal)         | 27         | Compensar ficha / prueba                   |
| Saltar canción                | 22         | Corta la pista actual                      |
| Reiniciar Raspberry           | 23         | **Mantener 2,5 s** (evita toques accidentales) |

Todos los botones: un lado a **GND**, el otro al GPIO (pull-up interno).

Para que el reboot funcione sin contraseña:

```bash
echo 'pi ALL=(ALL) NOPASSWD: /sbin/reboot' | sudo tee /etc/sudoers.d/rockola-reboot
sudo chmod 440 /etc/sudoers.d/rockola-reboot
```

### Playlist de ambiente

Cuando la cola de clientes está vacía (y al acabar lo que pusieron), suena la playlist al azar:

1. Edita `media/ambient/playlist.url` y pon la URL de YouTube (una línea), **o**
2. `export ROCKOLA_AMBIENT_PLAYLIST='https://www.youtube.com/playlist?list=...'`

Si no hay playlist, usa los MP3 de `media/ambient/`.

---

## 5. Arranque completo (orden esperado)

1. Sistema → red.
2. `jukebox.service` → `maintenance.py` (`yt-dlp -U`) → `uvicorn` en `:8000`.
3. Sesión gráfica en la **DSI** → `start-kiosk.sh` → Chromium kiosk (UI).
4. Al reproducir: mpv **fullscreen en la tele (HDMI)**; la táctil sigue usable para encolar.

---

## 6. Comandos útiles

```bash
# Reiniciar backend
sudo systemctl restart jukebox.service

# Solo actualizar yt-dlp a mano
 /home/pi/Rockola-Raspberry/venv/bin/python maintenance.py -v

# Ver log de mantenimiento
tail -f /home/pi/Rockola-Raspberry/logs/maintenance.log

# Simular fichas sin monedero
curl -X POST 'http://127.0.0.1:8000/api/credits/add?amount=5'
```

---

## 7. Checklist rápido

- [ ] `venv` + `requirements.txt` + `RPi.GPIO`
- [ ] `jukebox.service` enabled
- [ ] `curl http://127.0.0.1:8000/` responde
- [ ] Autostart de `start-kiosk.sh` / `.desktop`
- [ ] Chromium en `--kiosk` a 1280×800 (DSI)
- [ ] Tele por micro-HDMI; `ROCKOLA_MPV_FS_SCREEN` apunta a esa pantalla
- [ ] MP3 en `media/ambient/`
- [ ] Grupos `gpio video audio` para `pi`
- [ ] (Opcional) cron 06:00 para `maintenance.py`
