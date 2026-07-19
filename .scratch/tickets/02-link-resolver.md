# 02 — Resolutor de enlaces (link_resolver.py)

**What to build:** Funcion `resolve_download_url(url: str) -> str` que toma un enlace publico de Directo/Dropbox/Google Drive/MediaFire y devuelve la URL real de descarga. Cada proveedor usa su propia logica: Dropbox cambia dl=0 por dl=1, Google Drive usa gdown, MediaFire extrae de HTML.

**Blocked by:** None — can start immediately (independiente)

**Status:** ready-for-agent

- [ ] `resolve_download_url()` con dispatcher por proveedor
- [ ] Resolutor para enlaces directos (requests.get stream)
- [ ] Resolutor para Dropbox (?dl=0 -> ?dl=1)
- [ ] Resolutor para Google Drive (gdown)
- [ ] Resolutor para MediaFire (extraer URL real del HTML)
- [ ] Pruebas con HTTP mockeado (pytest + responses / pytest-mock)
