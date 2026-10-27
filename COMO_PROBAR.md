# Cómo probar la Rockola en tu PC

Tú arrancas el servidor (terminal o VS Code/Cursor). No hace falta que el agente lo lance.

## 1. Instalar mpv (obligatorio para ver/oír el vídeo)

Sin `mpv` la canción **no suena**.

En PowerShell:

```powershell
winget install shinchiro.mpv
```

El instalador de winget lo deja en `C:\Program Files\MPV Player\`. Si `mpv --version` falla, **cierra y abre** la terminal (o Cursor/VS Code) para refrescar el PATH.

Comprueba:

```powershell
mpv --version
# o directamente:
& "C:\Program Files\MPV Player\mpv.exe" --version
```

La Rockola también busca ese directorio aunque no esté en el PATH.

## 2. Arrancar el backend

```powershell
cd C:\Users\sjvel\Documents\Rockola-Raspberry
.\venv\Scripts\Activate.ps1
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

O en **VS Code / Cursor**: panel Run and Debug → configuración **Rockola (uvicorn)** → F5.

## 3. Abrir la UI

Navegador: http://127.0.0.1:8000/

## 4. Añadir fichas de prueba (no hay monedero en el PC)

Otra terminal:

```powershell
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/api/credits/add?amount=5"
```

## 5. Probar

1. Busca una canción o usa **Las Más Sonadas**
2. Toca un tema ≤ 10 min
3. Debe abrirse una **ventana de mpv** con vídeo y audio (en Windows no usa fullscreen a propósito)

En la Raspberry Pi irá a pantalla completa automáticamente.

## Si algo falla

| Síntoma | Qué mirar |
|--------|-----------|
| “Instala mpv…” al tocar canción | `winget install shinchiro.mpv` y reinicia uvicorn |
| “No se pudo reproducir el vídeo” | Reinicia uvicorn tras actualizar el código; mpv debe abrir ventana con imagen |
| mpv abre y cierra al instante | Revisa el log del servidor; asegúrate de usar el `venv` del proyecto (trae yt-dlp) |
| Sin fichas | `POST /api/credits/add?amount=5` |

Prueba manual de vídeo (debe verse ~6 s):

```powershell
$env:Path = "C:\Users\sjvel\Documents\Rockola-Raspberry\venv\Scripts;$env:Path"
& "C:\Program Files\MPV Player\mpv.exe" --length=6 --force-window=yes --geometry=640x360 "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

Pantalla completa forzada en PC (opcional):

```powershell
$env:ROCKOLA_FULLSCREEN="1"
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
