
# Aplicación Web Biotico

Aplicación web para visualizar, filtrar y exportar datos biológicos conectados a una base de datos MySQL. Construida con **Flask** y desplegada usando **Railway**.

## 🚀 Tecnologías utilizadas

- Python 3.10+
- Flask
- MySQL (Railway)
- HTML/CSS (Jinja2 templates)
- Pandas (para exportaciones CSV/Excel)

## ⚙️ Instalación local

1. Clona el repositorio:

   ```bash
   git clone https://github.com/CarlosGuinea666/biotico_app_web.git
   cd biotico_app_web
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

4. Crea un archivo `.env` (opcional) o configura las variables de entorno para conexión MySQL:

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

- Filtros dinámicos por año, tipo, municipio, etc.
- Exportación de resultados a CSV y Excel
- Transformación de coordenadas (UTM a geográficas)
- Conexión directa a base de datos MySQL en la nube

---

## ✍️ Autor

- **Carlos Guinea** - [GitHub](https://github.com/CarlosGuinea666)

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