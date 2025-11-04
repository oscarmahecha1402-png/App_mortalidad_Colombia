# Actividad 4.Aplicación web interactiva para el análisis de mortalidad en Colombia
# Curso de aplicaciones 1.
# Estudiante: Oscar Raúl Mahecha Sánchez.
# Grupo 2.
# Maestría en Inteligencia Artificial
# Universidad de la Salle
# 2025-2

## Estructura
- `app.py` — App Dash (lee un único Excel en `data/datos.xlsx` con 4 hojas: `Fallecimientos`, `Descripcion_cod_fall`, `Dep_mun`, `Ubi_Dep_mun`).
- `data/` — `datos.xlsx`.
- `requirements.txt`, `Procfile`, `render.yaml` 

## Ejecución local
```bash
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Abrir http://127.0.0.1:8050

## Despliegue en Azure App Services
- Variables: `PATH_EXCEL=data/datos.xlsx` 
- Inicio: `web: gunicorn app:server --workers 4 --threads 2 --timeout 600 --access-logfile - --error-logfile - --log-level info
