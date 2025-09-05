import os
import time
import json
import random
import requests
import streamlit as st
#import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="Simulador de Procesos", layout="wide")
st.title("Simulador de Procesos – Grupo 4, Proyecto 7")

st.markdown("""
Esta app puede funcionar de **dos formas**:
1) **Conectar a una API Go** pública (endpoint `/simulate`) — recomendado para clases.
2) **Modo local (mock)** si no tienes la API: se simula el tiempo de ejecución en Python.
""")

# Config de API
default_api = st.secrets.get("API_URL", "")
api_url = st.text_input("Se debe mostrar la API", value=default_api, placeholder="https://tu-api-go.onrender.com/simulate")

with st.sidebar:
    st.header("Parámetros")
    rondas = st.number_input("Rondas", 1, 100, 5)
    timeout_s = st.number_input("Timeout por ronda (seg)", 0, 60, 2)
    nproc = st.number_input("N° de procesos", 1, 20, 3)
    timeout_m = st.number_input("Timeout por ronda (min)", 0, 24, 2)

    st.caption("Parámetros por proceso")
    procesos = []
    for i in range(1, int(nproc)+1):
        st.subheader(f"Proceso {i}")
        nombre = st.text_input(f"Nombre {i}", f"Proceso_{i}", key=f"nombre_{i}")
        carga_base = st.slider(f"Carga base {i}", 1, 5, 2, key=f"cb_{i}")
        mem = st.slider(f"Memoria estimada (MB) {i}", 50, 500, 100, key=f"mem_{i}")
        jitter = st.slider(f"Jitter máx (ms) {i}", 0, 1500, 300, key=f"jit_{i}")
        procesos.append({
            "id": i, "nombre": nombre, "cargaBase": int(carga_base),
            "memoriaEstimadamb": int(mem), "jitterMaxMs": int(jitter)
        })

run = st.button("Ejecutar simulación")

def run_local_mock(rondas:int, timeout_s:int, procesos:list, timeout_m:int):
    """Simula localmente la ejecución (sin API Go). Devuelve estructura parecida a la API."""
    resultados = []
    rng = random.Random(1234)
    for r in range(1, int(rondas)+1):
        for p in procesos:
            carga = rng.randint(1, 5)
            base_ms = p["cargaBase"] * carga * 100
            jitter_ms = rng.randint(0, p["jitterMaxMs"])
            dur_ms = base_ms + jitter_ms
            # "Aplicar" timeout si corresponde
            ok = True
            err = ""
            if timeout_s > 0 and dur_ms > timeout_s * 1000:
                ok = False
                err = "timeout"
                dur_ms = 0
            # Simular (opcional): dormir una cantidad mínima para no demorar demasiado
            time.sleep(min(dur_ms, 50) / 1000.0)
            resultados.append({
                "procesoId": p["id"],
                "nombre": p["nombre"],
                "ronda": r,
                "memoriaMB": p["memoriaEstimadamb"],
                "tiempoMs": dur_ms,
                "ok": ok,
                "err": err,
            })
    # Agregar métricas
    porProceso = {}
    all_times = []
    for row in resultados:
        if row["ok"]:
            porProceso.setdefault(row["procesoId"], {"count":0,"avgMs":0,"p50Ms":0,"p95Ms":0,"minMs":0,"maxMs":0,"_all":[]})
            porProceso[row["procesoId"]]["_all"].append(row["tiempoMs"])
            all_times.append(row["tiempoMs"])
    import math
    def finalize(stats):
        if not stats["_all"]:
            return
        arr = sorted(stats["_all"])
        stats["count"] = len(arr)
        stats["avgMs"] = sum(arr)/len(arr)
        stats["minMs"] = arr[0]
        stats["maxMs"] = arr[-1]
        def perc(a, p):
            if not a: return 0
            if p<=0: return a[0]
            if p>=100: return a[-1]
            pos = (p/100.0) * (len(a)-1)
            i = int(math.floor(pos))
            f = pos - i
            if i+1 < len(a):
                return a[i]*(1-f) + a[i+1]*f
            return a[i]
        stats["p50Ms"] = perc(arr, 50)
        stats["p95Ms"] = perc(arr, 95)
        del stats["_all"]
    for k,v in porProceso.items():
        v.setdefault("_all", [])
        finalize(v)
    global_stats = {"count":0,"avgMs":0,"p50Ms":0,"p95Ms":0,"minMs":0,"maxMs":0}
    if all_times:
        arr = sorted(all_times)
        global_stats["count"] = len(arr)
        global_stats["avgMs"] = sum(arr)/len(arr)
        global_stats["minMs"] = arr[0]
        global_stats["maxMs"] = arr[-1]
        import math
        def perc(a,p):
            if not a: return 0
            if p<=0: return a[0]
            if p>=100: return a[-1]
            pos = (p/100.0) * (len(a)-1)
            i = int(math.floor(pos))
            f = pos - i
            if i+1 < len(a):
                return a[i]*(1-f) + a[i+1]*f
            return a[i]
        global_stats["p50Ms"] = perc(arr, 50)
        global_stats["p95Ms"] = perc(arr, 95)
    return {"resultados": resultados, "porProceso": porProceso, "global": global_stats}
import matplotlib.dates as mdates
def plot_times(df):
    """Dibuja gráfico de tiempos por ronda."""
    fig, ax = plt.subplots(figsize=(10, 4))
    for key, grp in df.groupby('nombre'):
        ax = grp.plot(ax=ax, kind='line', x='ronda', y='tiempoMs', label=key, marker='o')
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    plt.xlabel("Ronda")
    plt.ylabel("Tiempo (ms)")
    plt.title("Tiempos por Ronda y Proceso")
    plt.legend(title="Proceso")
    plt.grid(True)
    st.pyplot(fig)
def plot_histogram(df):
    """Dibuja histograma de tiempos."""
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.hist(df['tiempoMs'], bins=20, color='skyblue', edgecolor='black')
    plt.xlabel("Tiempo (ms)")
    plt.ylabel("Frecuencia")
    plt.title("Histograma en barra Tiempos")
    plt.grid(True)
    st.pyplot(fig)
def plot_regresion(df):
    """Dibuja gráfico de regresión (tiempo vs memoria)."""
    import numpy as np
    from sklearn.linear_model import LinearRegression
    fig, ax = plt.subplots(figsize=(10, 4))
    X = df['memoriaMB'].values.reshape(-1, 1)
    y = df['tiempoMs'].values
    model = LinearRegression()
    model.fit(X, y)
    y_pred = model.predict(X)
    ax.scatter(df['memoriaMB'], df['tiempoMs'], color='blue', label='Datos')
    ax.plot(df['memoriaMB'], y_pred, color='red', linewidth=2, label='Regresión')
    plt.xlabel("Memoria Estimada (MB)")
    plt.ylabel("Tiempo (ms)")
    plt.title("Regresión Lineal: Tiempo vs Memoria")
    plt.legend()
    plt.grid(True)
    st.pyplot(fig)


