
# Buscador Biótico Web

Aplicación web para visualizar, filtrar y exportar datos biológicos conectados a una base de datos MySQL. Construida con **Flask** y desplegada usando **Railway** / otros proveedores (Render, etc.). Incluye mapa interactivo (Leaflet), clustering accesible y exportaciones avanzadas CSV/Excel.

## 🚀 Tecnologías utilizadas

- Python 3.10+
- Flask
- MySQL (Railway)
- HTML/CSS (Jinja2 templates)
- OpenPyXL (exportación Excel avanzada)
- Leaflet + MarkerCluster (visualización geoespacial)
- python-dotenv (gestión de variables locales)

## ⚙️ Instalación local

1. Clona el repositorio:

   ```bash
   git clone https://github.com/equalprogramacion-netizen/buscador-ui.git
   cd buscador-ui
   ```

2. Crea un entorno virtual (opcional pero recomendado):

   ```bash
   python -m venv venv
   source venv/bin/activate     # En Linux/macOS
   venv\Scripts\activate        # En Windows
   ```

3. Instala las dependencias:

   ```bash
   pip install -r requirements.txt
   ```

4. Crea un archivo `.env` (puedes copiar de `.env.example`) o configura las variables de entorno para conexión MySQL:

   ```env
   DB_HOST=nozomi.proxy.rlwy.net
   DB_PORT=29793
   DB_USER=root
   DB_PASSWORD=tu_contraseña
   DB_NAME=nombre_de_tu_base
   ```

5. Ejecuta la aplicación:

   ```bash
   python app.py
   ```

   Abre [http://127.0.0.1:5000](http://127.0.0.1:5000) en tu navegador.

---

## 🌐 Despliegue

### En Railway (recomendado)

1. Sube tu base de datos a Railway y copia las credenciales.
2. Crea un nuevo proyecto desde GitHub → selecciona este repositorio.
3. En la pestaña "Variables", agrega:

   ```
   DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
   ```

4. Railway detectará automáticamente tu `Procfile` y ejecutará `gunicorn`.

---

## 📁 Estructura del proyecto

```
biotico_app_web/
├── app.py               # App principal Flask
├── requirements.txt     # Dependencias
├── Procfile             # Para despliegue en producción
├── templates/           # HTML Jinja2
├── static/              # Archivos estáticos (JS/CSS)
├── temp_exports/        # Exportaciones CSV/Excel
└── README.md            # Este archivo
```

---

## 🧪 Funcionalidades principales

- Filtros dinámicos por múltiples campos (municipio, proyecto, nombres científico/común, grupo biológico, tipo hidrobiota, palabra clave global).
- Búsqueda global opcional sobre todas las columnas (LIKE dinámico).
- Exportación avanzada: CSV y Excel con columnas alineadas, BOM opcional, fecha normalizada, coordenadas transformadas opcionales.
- Transformación de coordenadas (EPSG original → WGS84) sin sobrescribir datos crudos.
- Mapa Leaflet con clusters dinámicos, accesibles y contadores con separador de miles.
- Tema oscuro accesible (alto contraste, placeholders legibles, focus-visible consistente).
- Limpieza automática de archivos de exportación (>1 hora).
- Nombres de archivos de exportación con timestamp y hoja Resumen en Excel.

---

## 📦 Variables de entorno clave

```
FLASK_SECRET_KEY=...
EXPORT_FOLDER=temp_exports
DB_HOST=...
DB_PORT=...
DB_USER=...
DB_PASSWORD=...
DB_NAME=railway
DB_TABLE=biotic_database
CSV_ADD_BOM=1
CSV_DELIMITER=,
EXPORT_INCLUDE_MAP_COORDS=1
EXCEL_HEADER_FILL=18263f
EXCEL_HEADER_FONT=e6ebff
EXCEL_MAX_COL_WIDTH=60
```

## ✍️ Autores / Mantenimiento

- Equipo Equal Programación / Netizen
- Contribuciones iniciales: Carlos Guinea

## 🗺️ Roadmap breve

- Paginación server-side para grandes volúmenes
- Índices / FULLTEXT para búsqueda global eficiente
- Filtro por rangos de fecha
- Mejora de logging y métricas (transformaciones fallidas)
- Modo tabla compacta y vista resumen estadística

## 📝 Historial

Consulta `changelog.txt` para detalles de versiones (v3.0.0 última actualización de accesibilidad y exportaciones).

## Local
1) Crear .env (ver ejemplo abajo)
2) `pip install -r requirements.txt`
3) `python app.py`

## Variables de entorno
DB_HOST=...
DB_PORT=...
DB_USER=...
DB_PASSWORD=...
DB_NAME=railway
DB_TABLE=biotic_database