Aquí tienes una especificación técnica completa y estructurada lista para entregar a un agente de IA o desarrollador. Está redactada como una orden de arquitectura de software para que la interprete e implemente sin ambigüedades.

---

# Especificación de Arquitectura de Software: Jukebox Comercial con YouTube y Fichas

## 1. Visión General del Sistema

Desarrollar una aplicación de Jukebox para Raspberry Pi 4 ejecutada en modo Kiosk a pantalla completa sobre una pantalla táctil DSI de 10,1" (1280x800). El sistema debe gestionar créditos mediante impulsos de hardware (monedero de fichas), permitir búsqueda restringida de YouTube con vistas previas, gestionar una cola de reproducción, limitar la duración a 10 minutos por vídeo, reproducir música de ambiente cuando no haya peticiones activa, y mantener una base de datos con un ranking de lo más escuchado.

---

## 2. Requisitos de Hardware e Interfaces

* **Hardware:** Raspberry Pi 4 (4GB RAM) ejecutando Raspberry Pi OS.
* **Entrada de Créditos:** Monedero CH-926 conectado al GPIO 17 mediante un módulo optoacoplador PC817 (lectura por interrupción/pulsos).
* **Botones de Servicio:** Botón físico en GPIO (p. ej., GPIO 27) para añadir créditos de prueba / mantenimiento de forma manual.
* **Reproductor de Salida:** `mpv` a pantalla completa mediante aceleración de hardware, integrado vía Python (usando `python-mpv` o subprocesos IPC).

---

## 3. Arquitectura del Software (Backend Python + Frontend Web)

### 3.1. Gestor de Hardware y Créditos (`credits_manager.py`)

* Escuchar eventos de interrupción en el pin **GPIO 17**.
* Implementar un algoritmo de anti-rebote (*debounce*) de al menos $50\text{ ms}$ para contar correctamente los pulsos enviados por el PC817.
* Incrementar la variable global/estado de `creditos_disponibles` y emitir un evento en tiempo real vía WebSockets o Server-Sent Events (SSE) a la interfaz visual.
* Gestionar el botón de mantenimiento en GPIO 27 para añadir créditos manuales sin ficha.

### 3.2. Módulo de Búsqueda e Integración con YouTube (`youtube_service.py`)

* Utilizar la librería `yt-dlp` en Python para realizar búsquedas mediante cadenas de texto.
* Extraer y formatear de cada resultado los siguientes metadatos:
* `id_youtube`: ID del vídeo.
* `titulo`: Título limpio de la canción.
* `miniatura`: URL de la vista previa en alta calidad (`thumbnail`).
* `duration_seconds`: Duración en segundos.
* `duration_formatted`: Duración en formato `MM:SS`.


* **Filtro de seguridad en backend:** Marcar el parámetro `elegible = True` únicamente si `duration_seconds <= 600` (10 minutos).

### 3.3. Motor de Reproducción y Gestor de Cola (`player_engine.py`)

Manejar 3 estados principales mediante un hilo secundario (*threading* / *asyncio*):

1. **Estado IDLE (Música de Ambiente):**
* Si la cola de peticiones está vacía (`cola_canciones.empty()`), reproducir una lista de reproducción local en MP3 o una selección fija de YouTube a un volumen moderado.


2. **Transición a Pago:**
* Al recibir una canción validada desde el frontend, pausar/atenuar (*fade-out*) la música de ambiente.
* Restar **1 crédito** del contador global.


3. **Estado PLAYING (Cola de Usuario):**
* Extraer el enlace de reproducción (*stream URL*) con `yt-dlp` e invocar `mpv`.
* Argumentos obligatorios para `mpv`: `--fullscreen`, `--no-osd` (sin interfaz sobrepuesta), `--length=600` (corte automático a los 10 min por seguridad).
* Registrar el inicio del tema en la base de datos de estadísticas.
* Al terminar el vídeo, pasar a la siguiente canción de la cola o regresar al **Estado IDLE** si la cola queda vacía.



### 3.4. Base de Datos y Ranking ("Las Más Sonadas") (`database.py`)

* Usar una base de datos local **SQLite** (`jukebox.db`).
* Tabla `canciones`: `id_youtube` (TEXT PRIMARY KEY), `titulo` (TEXT), `miniatura` (TEXT), `reproducciones` (INTEGER DEFAULT 1), `ultima_reproduccion` (TIMESTAMP).
* Lógica al seleccionar un tema: ejecutar un `INSERT INTO ... ON CONFLICT(id_youtube) DO UPDATE SET reproducciones = reproducciones + 1`.
* Endpoint para consultar el **Top 10 de reproducciones** ordenado por `reproducciones DESC`.

### 3.5. Interfaz Gráfica de Usuario (Frontend Kiosk)

* Página web local (HTML/CSS/JS) ejecutada en Chromium en modo Kiosk (`--kiosk --noerrdialogs`).
* **Diseño adaptado a pantalla de 10,1" táctil:**
* Header/Footer fijo mostrando claramente: **Fichas Disponibles: X**.
* Barra de búsqueda con teclado táctil virtual integrado en pantalla.
* Rejilla de tarjetas (*cards*) con las miniaturas de búsqueda, título y duración.
* Deshabilitar visualmente o mostrar *"Supera 10 min"* en tarjetas cuya duración supere los 600 segundos.
* Botón directo de **"🔥 Las Más Sonadas"** que renderiza el Top 10 desde la base de datos para selección rápida a 1 toque.
* Vista lateral o flotante con la **Cola de Próximas Canciones**.


* Bloqueo total del navegador (deshabilitar menú contextual con clic derecho, atajos de teclado y gestos de salida).

---

## 4. Mantenimiento Automático y Resiliencia

1. **Autoactualización de `yt-dlp`:**
* Incluir un script en Python ejecutado en el arranque del sistema (o vía `cron` diario a las 06:00 AM) que ejecute `yt-dlp -U` para garantizar compatibilidad continua con cambios de YouTube.


2. **Caché y Fallback:**
* Almacenar temporalmente las URLs de flujo extraídas en memoria o disco para agilizar reproducciones repetidas dentro del mismo día.
* En caso de fallo de red o error inesperado de `yt-dlp`, reinsertar el crédito consumido al usuario y devolver la interfaz al estado de selección con una alerta limpia en pantalla.



---

## 5. Entregables Esperados del Código

1. Servidor en Python (Flask / FastAPI / WebSockets).
2. Scripts de configuración del sistema (inicio automático en Kiosk de Raspberry Pi OS).
3. Esquema de SQLite y script de inicialización (`init_db.py`).
4. Código Frontend (HTML, CSS responsive para 1280x800, JavaScript sin librerías externas pesadas).