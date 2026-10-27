"""Compatibilidad: delega en maintenance.py (yt-dlp -U)."""

from maintenance import main

if __name__ == "__main__":
    raise SystemExit(main())
