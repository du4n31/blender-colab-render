# 03 — Aprovisionamiento de Blender (blender_provisioning.py)

**What to build:** Descarga el binario portable de Blender (`.tar.xz`) desde download.blender.org, lo extrae y devuelve la ruta al ejecutable. Soporta cache en Drive: si ya existe el `.tar.xz` en Drive, lo copia desde ahi en vez de descargar de nuevo.

**Blocked by:** 01-config (usa constantes de version y URL)

**Status:** ready-for-agent

- [ ] `get_blender_path(cache_dir: str | None) -> str` — devuelve ruta al binario, descargando si es necesario
- [ ] Logica de cache: buscar .tar.xz en cache_dir (Drive), descargar si no existe
- [ ] Extraer .tar.xz a directorio temporal
- [ ] Verificar que el binario existe y es ejecutable
- [ ] Pruebas con mock de requests/subprocess
