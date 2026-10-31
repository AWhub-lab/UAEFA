# UAEFA Scraping

Base de trabajo para explorar y extraer datos publicos de `uaefa.ae` de forma prudente.

## Estructura

- `notebooks/`: exploracion y pruebas iterativas en VS Code
- `src/uaefa_scraper/`: cliente y utilidades reutilizables
- `data/raw/`: respuestas crudas guardadas en disco
- `data/processed/`: tablas o JSON ya limpios
- `logs/`: notas y trazas si luego hacen falta

## Flujo recomendado

1. Empezar en `notebooks/01_discovery.ipynb`
2. Validar sitemaps, URLs y respuestas utiles
3. Confirmar el ritmo de peticiones y la cache
4. Pasar la logica estable a `src/uaefa_scraper/`

## Principios

- Sin crawling agresivo
- Con pausas y jitter aleatorio
- Con cache en disco
- Priorizando sitemap y llamadas concretas
- Parando si aparecen errores de rate limit o bloqueos

## Piloto First Division - Jornada 1

El piloto de la temporada 2026/2027 usa exclusivamente los siete partidos de
la jornada 1 de `First Division league` (competición `2572`). Guarda el JSON
original de cada respuesta, crea tablas Parquet y descarga una vez los escudos
y retratos públicos vinculados a las actas.

```bash
python3 scripts/download_first_division_week1.py
```

El proceso no utiliza peticiones paralelas. Espera aleatoriamente entre 2,5 y
4,5 segundos entre cada petición y se detiene si UAEFA responde `403` o `429`.
Para comprobar únicamente los datos sin imágenes:

```bash
python3 scripts/download_first_division_week1.py --skip-media
```

## App local

La app Streamlit lee las tablas Parquet creadas por el piloto y no descarga
nada de UAEFA. Incluye clasificación provisional, fichas de partido,
equipos con cuerpo técnico y fichas de jugador.

```bash
python3 -m streamlit run app.py
```

## Sincronización incremental

Para incorporar todas las jornadas ya finalizadas y, en futuras ejecuciones,
solo los partidos que todavía no estén en la caché local:

```bash
python3 scripts/sync_first_division.py
```

El sincronizador actualiza el calendario una vez, filtra exclusivamente la
competición `2572` y las actas finalizadas, reutiliza JSON e imágenes ya
guardados y deja el resultado consolidado en `data/processed/.../current/`.

## Versión HTML para compartir

`index.html` es una copia autocontenida y responsive de la app (móvil, tablet y escritorio):
mismas cuatro secciones, selector de jornada de corte, inglés/español, impacto en el campo,
comparador y fichas con datos validados de BeSoccer. Lleva dentro los datos, los escudos y las
fotos, y se abre en Safari o Chrome sin servidor ni Python. No se ve en la vista previa
rápida de iOS (WhatsApp, Archivos): hay que abrirlo en el navegador o publicarlo con un enlace.

```bash
python3 scripts/build_index_html.py
```

Reutiliza `app.load_data()` y el CSS de `app.py`, así que se actualiza con los mismos datos que la
app. La lógica está en `scripts/index_app/` (`core.js`, `charts.js`, `impact.js`, `pages_*.js`,
`main.js`, `extra.css` y `template.html`). Si cambias una sección en `app.py`, hay que reflejarla
también ahí.

### Edición estática (para el iPhone y cualquier visor sin JavaScript)

La vista previa de iOS (WhatsApp, Archivos) no ejecuta JavaScript, así que `index.html` solo
enseña la clasificación allí. Para esos casos:

```bash
python3 scripts/build_index_html.py --static            # al_wasl_uae_snapshot_en.html y _es.html
python3 scripts/build_index_html.py --static --min-full 360   # más ligera: ficha completa desde 360'
```

Es el mismo contenido ya dibujado en HTML, con desplegables nativos (`<details>`), jornada 7 fija y
sin filtros. La ficha completa (impacto, temporada, acciones) se incluye para los jugadores con
270' o más; el resto lleva identidad y datos básicos. Hay una variante `_lite_` sin fichas completas.
Requiere Node.js para dibujarla.

