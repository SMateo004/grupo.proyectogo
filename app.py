import os
import time
import json
import random
import requests
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# --- Config inicial ---
st.set_page_config(page_title="Simulador de Procesos", layout="wide")

# Inicializar navegación
if "page" not in st.session_state:
    st.session_state.page = "main"
if "timeouts" not in st.session_state:
    st.session_state.timeouts = []

st.title("Simulador de Procesos – Grupo 4, Proyecto 7")

st.markdown("""
Esta app puede funcionar de **dos formas**:
1) **Conectar a una API Go** pública (endpoint `/simulate`) — recomendado para clases.
2) **Modo local (mock)** si no tienes la API: se simula el tiempo de ejecución en Python.
""")

# Config de API
default_api = st.secrets.get("API_URL", "")
api_url = st.text_input("API URL (opcional, deja vacío para modo local/mock)", 
                        value=default_api, 
                        placeholder="https://tu-api-go.onrender.com/simulate")

# ========================
# --- SIDEBAR ---
# ========================
with st.sidebar:
    st.header("Parámetros")
    rondas = st.number_input("Rondas", 1, 100, 5)
    timeout_s = st.number_input("Timeout por ronda (seg)", 0, 60, 2)
    nproc = st.number_input("N° de procesos", 1, 20, 3)

    # Botón para ir a página de configuración de timeouts
    if st.button("Configurar Timeout por Ronda (min)"):
        st.session_state.page = "timeouts"

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

# ========================
# --- FUNCIONES ---
# ========================
def run_local_mock(rondas:int, timeout_s:int, procesos:list, timeout_mins:list):
    """Simula localmente la ejecución (sin API Go)."""
    resultados = []
    rng = random.Random(1234)
    for r in range(1, int(rondas)+1):
        for p in procesos:
            carga = rng.randint(1, 5)
            base_ms = p["cargaBase"] * carga * 100
            jitter_ms = rng.randint(0, p["jitterMaxMs"])
            dur_ms = base_ms + jitter_ms
            ok = True
            err = ""
            # aplicar timeout en minutos si se configuró
            if timeout_mins and r <= len(timeout_mins) and timeout_mins[r-1] > 0:
                if dur_ms > timeout_mins[r-1] * 60 * 1000:
                    ok = False
                    err = "timeout"
                    dur_ms = 0
            # aplicar timeout en segundos
            elif timeout_s > 0 and dur_ms > timeout_s * 1000:
                ok = False
                err = "timeout"
                dur_ms = 0

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

    # --- Métricas ---
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
        finalize(v)

    global_stats = {"count":0,"avgMs":0,"p50Ms":0,"p95Ms":0,"minMs":0,"maxMs":0}
    if all_times:
        arr = sorted(all_times)
        global_stats["count"] = len(arr)
        global_stats["avgMs"] = sum(arr)/len(arr)
        global_stats["minMs"] = arr[0]
        global_stats["maxMs"] = arr[-1]
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

# ========================
# --- PÁGINAS ---
# ========================

if st.session_state.page == "main":
    run = st.button("Ejecutar simulación")

    if run:
        payload = {"rondas": int(rondas), "timeoutRondaS": int(timeout_s), "procesos": procesos}
        if st.session_state.timeouts:
            payload["timeoutPorRondaMins"] = st.session_state.timeouts

        if api_url.strip():
            st.info(f"Llamando API: {api_url}")
            try:
                resp = requests.post(api_url.strip(), json=payload, timeout=120)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                st.error(f"Error con la API ({e}). Usando modo local/mock…")
                data = run_local_mock(rondas, timeout_s, procesos, st.session_state.timeouts)
        else:
            st.warning("API vacía: usando modo local/mock.")
            data = run_local_mock(rondas, timeout_s, procesos, st.session_state.timeouts)

        # --- Mostrar resultados ---
        df = pd.DataFrame(data.get("resultados", []))
        if df.empty:
            st.warning("Sin resultados.")
        else:
            st.subheader("Resultados por ronda")
            st.dataframe(df[["procesoId", "nombre", "ronda", "memoriaMB", "tiempoMs", "ok", "err"]], use_container_width=True)

            st.subheader("Promedio por proceso (ms)")
            ok_df = df[df["ok"]]
            if not ok_df.empty:
                avg_df = ok_df.groupby(["procesoId", "nombre"])["tiempoMs"].mean().reset_index()
                fig1, ax1 = plt.subplots()
                ax1.bar(avg_df["nombre"], avg_df["tiempoMs"])
                ax1.set_xlabel("Proceso")
                ax1.set_ylabel("Tiempo promedio (ms)")
                ax1.set_title("Promedio por Proceso")
                st.pyplot(fig1)

                st.subheader("Tiempos por ronda (ms)")
                fig2, ax2 = plt.subplots()
                for name, sub in ok_df.groupby("nombre"):
                    ax2.plot(sub["ronda"], sub["tiempoMs"], marker="o", label=name)
                ax2.set_xlabel("Ronda")
                ax2.set_ylabel("Tiempo (ms)")
                ax2.set_title("Evolución por Ronda")
                ax2.legend()
                st.pyplot(fig2)

            st.subheader("Métricas")
            por_proc = data.get("porProceso", {})
            rows = []
            for pid, stats in por_proc.items():
                rows.append({"procesoId": int(pid), **stats})
            if rows:
                mdf = pd.DataFrame(rows).sort_values("procesoId")
                st.dataframe(mdf, use_container_width=True)
            g = data.get("global")
            if g and g.get("count", 0) > 0:
                st.success(f"GLOBAL → n={g['count']}  avg={g['avgMs']:.1f}ms  "
                           f"p50={g['p50Ms']:.1f}ms  p95={g['p95Ms']:.1f}ms  "
                           f"min={g['minMs']:.1f}ms  max={g['maxMs']:.1f}ms")

    # Mostrar si hay configuración de timeouts
    if st.session_state.timeouts:
        st.info(f"Timeouts configurados por ronda (min): {st.session_state.timeouts}")

elif st.session_state.page == "timeouts":
    st.title("Configurar Timeout por Ronda (minutos)")
    nuevos_timeouts = []
    for i in range(rondas):
        t = st.number_input(
            f"Timeout Ronda {i+1} (min)",
            min_value=0, max_value=120,
            value=st.session_state.timeouts[i] if i < len(st.session_state.timeouts) else 2,
            step=1, key=f"timeout_{i}"
        )
        nuevos_timeouts.append(t)

    if st.button("Guardar configuración"):
        st.session_state.timeouts = nuevos_timeouts
        st.success("✅ Timeouts guardados.")

    if st.button("Volver a la simulación"):
        st.session_state.page = "main"

    st.info("Aquí configuras el tiempo máximo en minutos permitido por ronda antes de timeout.")
