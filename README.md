# Simulador de Procesos – Streamlit (con API Go opcional)

Este proyecto despliega una UI en **Streamlit** para visualizar rondas de ejecución de procesos.
Puede trabajar de dos modos:
1. **Conexión a API Go** (`/simulate`) pública.
2. **Modo local (mock)** sin API: simula los tiempos en Python.

## Estructura mínima del repo
- `app.py`: aplicación Streamlit.
- `requirements.txt`: dependencias.

## Despliegue en Streamlit Cloud
1. Sube estos archivos a un repositorio en GitHub (por ejemplo `simulador-procesos-streamlit`).
2. Ve a https://share.streamlit.io, inicia sesión con GitHub y elige **New app**.
3. Selecciona tu repo, branch y archivo principal `app.py`.
4. (Opcional) Configura `API_URL` en **Secrets** si usarás backend Go:
   - En Streamlit Cloud → *App* → *Settings* → *Secrets*:
     ```toml
     API_URL = "https://tu-api-go.onrender.com/simulate"
     ```
5. Deploy.

## API Go (opcional)
La app asume un endpoint `POST /simulate` que recibe:
```json
{
  "rondas": 5,
  "timeoutRondaS": 2,
  "procesos": [
    {"id":1,"nombre":"Proceso_A","cargaBase":2,"memoriaEstimadamb":120,"jitterMaxMs":300}
  ]
}
```
y responde con:
```json
{
  "resultados": [
    {"procesoId":1,"nombre":"Proceso_A","ronda":1,"memoriaMB":120,"tiempoMs":350,"ok":true}
  ],
  "porProceso": {"1":{"count":5,"avgMs":300.0,"p50Ms":295.0,"p95Ms":480.0,"minMs":200.0,"maxMs":520.0}},
  "global": {"count":15,"avgMs":310.2,"p50Ms":305.0,"p95Ms":510.0,"minMs":190.0,"maxMs":540.0}
}
```

## Desarrollo local
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Notas
- En Cloud, si no defines `API_URL`, la app corre en modo **local/mock**.
- Si defines `API_URL` (secrets o input), se intenta llamar a la API Go; si falla, se cae a modo mock.