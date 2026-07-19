# Blender Colab Render — Plan

## Necesidades

Renderizar escenas de Blender usando las GPUs T4 gratuitas de Google Colab, en sesiones continuas de ~5 horas, con subida incremental de frames a Drive para no perder progreso si la sesión se interrumpe.

## Áreas críticas / Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Sesión de Colab interrumpida a mitad de animación larga | Pérdida de progreso | Subida incremental de frames + archivo de estado en Drive |
| Blender no encuentra GPU en background mode | Render en CPU (lentísimo) | Script de detección con fallback explícito + advertencia |
| Orden incorrecto de args de línea de comandos | Render no usa la salida/config deseada | Validación exhaustiva en tests del orden exacto |
| Drive montado vs. no montado | Frames no se suben | Validación al inicio + reconciliación al final |
| Enlace de MediaFire sin resolver | .blend no se descarga | Resolución HTML de la página de descarga |
| Python embebido de Blender sin acceso a pip | Scripts de render no pueden usar librerías externas | Separación clara: orquestación en kernel, render con solo stdlib+bpy |

## Factibilidad

- **Técnicamente viable**: la referencia `ynshung/blender-colab` ya demuestra el concepto base.
- **Mejoras respecto a la referencia**: subida paralela por frame (no zip al final), reanudación, scripts personalizados, tests, UI con ipywidgets.
- **Limitación conocida**: una sola GPU T4, sin paralelismo de render. La paralelización es solo en subida vs. render.
- **Riesgo asumible**: las ~5h de sesión Colab son suficientes para animaciones cortas (~50-250 frames a 30s/frame). Para trabajos más largos, la reanudación permite continuar en múltiples sesiones.

## Oportunidades de optimización

1. **Caché de Blender en Drive**: descargar el `.tar.xz` una vez, reusar en sesiones futuras.
2. **Descarga del .blend y aprovisionamiento de Blender en paralelo** al inicio.
3. **Subida de cada frame mientras se renderiza el siguiente** (superposición I/O - cómputo).
4. **Límite de backlog local**: si Drive va más lento que el render, el backlog no crece sin control.

## Flujo de trabajo del proyecto

```
Fase 0 ─→ docs/PLAN.md
Fase 1 ─→ Repositorio git + GitHub (+ .gitignore, LICENSE, README.md inicial)
Fase 2 ─→ Desglose en tickets (to-tickets + task-management)
Fase 3 ─→ Implementación ticket por ticket (implement + tdd + code-review)
Fase 4 ─→ Ensamblado del notebook
Fase 5 ─→ Cierre: tests, docs, checklist, push final
```

Cada fase produce al menos un commit. Un commit por ticket cerrado.

## Flujo de trabajo del render (runtime)

```
1. Usuario pega enlace del .blend + config en el notebook
2. Resolver enlace ─→ obtener URL real de descarga
3. En paralelo: descargar .blend + aprovisionar Blender (desde Drive cache o download)
4. Montar Google Drive (si no está montado)
5. Validar configuración (ruta Drive, rango frames, etc.)
6. Lanzar Blender (proceso no bloqueante)
7. Leer stdout línea por línea, detectando "Saved: '<ruta>'"
8. Por cada frame detectado: copiar a Drive + borrar local (en ThreadPoolExecutor)
9. Actualizar archivo de estado en Drive
10. Actualizar UI de progreso en vivo (ipywidgets)
11. Al terminar/caer: reconciliación (subir frames pendientes)
```

## Características (de §§3-4 de la especificación)

### Obligatorias

1. Subir .blend vía enlace (Directo, Dropbox, Google Drive, MediaFire)
2. Renderizar animación completa (--frame-start / --frame-end / --render-anim)
3. Renderizar 1 solo frame (--render-frame N)
4. Monitor: tiempo/frame, estimado, promedio, % completación, ETA
5. Google Drive: render → subir → borrar (shutil.copy + os.remove)
6. Paralelizar subida+borrado con render del frame siguiente
7. Elegir output: compositor o secuenciador
8. Subir scripts Python personalizados para hooks de render
9. Elegir ruta destino dentro de Drive
10. Nombrar frames por número real de Blender con padding (frame_%06d.png)

### Deseables

11. Archivo de estado para reanudación (en Drive)
12. Activar/desactivar GPU o CPU
13. Activar/desactivar OptiX (frente a CUDA)
