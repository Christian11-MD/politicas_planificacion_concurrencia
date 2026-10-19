import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from modelos import Proc
from datos import ALGORITMOS, EJEMPLOS
from algoritmos import planificar, cola_listos, preparar_inicios
from metricas import calcular_metricas
from concurrencia import SimulacionConcurrencia


st.set_page_config(
    page_title="Sistemas Operativos",
    layout="wide",
    initial_sidebar_state="expanded",
)



st.markdown("""
<style>
/* Fondo principal */
.stApp {
    background-color: #0b1120;
    color: #e5edf7;
}

/* Menú lateral */
[data-testid="stSidebar"] {
    background-color: #111c2e;
}

/* Tarjetas de métricas */
[data-testid="stMetric"] {
    background-color: #142238;
    border: 1px solid #23405b;
    padding: 16px;
    border-radius: 12px;
}

/* Valores de las métricas */
[data-testid="stMetricValue"] {
    color: #5eead4;
}

/* Títulos */
h1, h2, h3 {
    color: #e5edf7;
}

/* Botones */
.stButton > button {
    background-color: #0e7490;
    color: white;
    border: none;
    border-radius: 8px;
}

.stButton > button:hover {
    background-color: #0891b2;
    color: white;
}

/* Ocultar barras de herramientas de Streamlit */
[data-testid="stElementToolbar"],
[data-testid="stElementToolbarButton"],
[data-testid="stToolbar"] {
    display: none !important;
}

/* Ocultar menús emergentes de las tablas */
[data-testid="stDataFrame"] [role="menu"],
[data-testid="stDataFrame"] [data-testid="glide-menu"],
[data-testid="stDataFrame"] [data-testid="portal"] {
    display: none !important;
}

/* Ocultar barra de herramientas de Plotly */
.js-plotly-plot .plotly .modebar {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)


if "procesos" not in st.session_state:
    st.session_state.procesos = []

if "resultado" not in st.session_state:
    st.session_state.resultado = None


def cargar_ejemplo(nombre):
    st.session_state.procesos = [
        Proc(n, l, r, p)
        for n, l, r, p in EJEMPLOS[nombre]
    ]
    st.session_state.resultado = None


def importar_txt(archivo):
    try:
        df = pd.read_csv(archivo, sep=None, engine="python")
        df.columns = [
            str(c).strip().lower() for c in df.columns
        ]

        requeridas = {
            "nombre", "llegada", "rafaga", "prioridad"
        }

        if not requeridas.issubset(set(df.columns)):
            st.error(
                "El TXT debe tener las columnas: "
                "nombre, llegada, rafaga, prioridad."
            )
            return

        df = df[[
            "nombre", "llegada", "rafaga", "prioridad"
        ]].copy()

        df["nombre"] = df["nombre"].astype(str).str.strip()

        for columna in ["llegada", "rafaga", "prioridad"]:
            df[columna] = pd.to_numeric(
                df[columna], errors="raise"
            )

            if df[columna].isna().any():
                raise ValueError(
                    f"Hay valores vacíos en {columna}."
                )

            if (df[columna] % 1 != 0).any():
                raise ValueError(
                    f"{columna} debe contener números enteros."
                )

        if df["nombre"].eq("").any():
            raise ValueError("Hay procesos sin nombre.")

        if df["nombre"].duplicated().any():
            raise ValueError("Hay nombres de procesos repetidos.")

        if (df["llegada"] < 0).any():
            raise ValueError("La llegada no puede ser negativa.")

        if (df["rafaga"] <= 0).any():
            raise ValueError("La ráfaga debe ser mayor que cero.")

        if (df["prioridad"] < 0).any():
            raise ValueError("La prioridad no puede ser negativa.")

        st.session_state.procesos = [
            Proc(
                str(f.nombre),
                int(f.llegada),
                int(f.rafaga),
                int(f.prioridad),
            )
            for f in df.itertuples(index=False)
        ]

        st.session_state.resultado = None
        st.success(f"Se importaron {len(df)} procesos.")

    except Exception as e:
        st.error(f"No se pudo importar el archivo: {e}")


def crear_gantt(segmentos):
    """Dibuja el Gantt a partir de los tramos (inicio, fin, proceso_o_None)."""
    fig = go.Figure()
    colores = {}
    paleta = [
        "#0ca891", "#d1ad0f", "#d91782", "#1c7ad2",
        "#4B14AA", "#bbca1f", "#9771a8", "#72d4f4",
        "#336e87", "#f26480"
    ]

    nombres = list(dict.fromkeys(
        "CPU ociosa" if p is None else p
        for _, _, p in segmentos
    ))

    for i, nombre in enumerate(nombres):
        colores[nombre] = (
            "#475569" if nombre == "CPU ociosa"
            else paleta[i % len(paleta)]
        )

    for inicio, fin, proceso in segmentos:
        nombre = "CPU ociosa" if proceso is None else proceso

        fig.add_trace(go.Bar(
            x=[fin - inicio],
            y=[nombre],
            base=[inicio],
            orientation="h",
            name=nombre,
            marker_color=colores[nombre],
            showlegend=False,
            hovertemplate=(
                f"Proceso: {nombre}<br>"
                f"Inicio: {inicio}<br>"
                f"Fin: {fin}<br>"
                f"Duración: {fin - inicio}"
                "<extra></extra>"
            ),
        ))

    tiempo_total = max((fin for _, fin, _ in segmentos), default=0)

    fig.update_layout(
        title="Diagrama de Gantt de la CPU",
        xaxis_title="Tiempo",
        yaxis_title="Proceso",
        template="plotly_dark",
        paper_bgcolor="#0b1120",
        plot_bgcolor="#111c2e",
        font_color="#e5edf7",
        height=max(300, min(650, len(nombres) * 45)),
        barmode="overlay",
        showlegend=False,
        margin=dict(l=30, r=20, t=60, b=40),
    )

    fig.update_xaxes(
        gridcolor="#26364b",
        dtick=max(1, tiempo_total // 20),
    )
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=nombres[::-1],
    )

    return fig


# ---------------- CABECERA ----------------

st.title("Políticas de planificación y concurrencia")

# ---------------- PANEL LATERAL ----------------

with st.sidebar:
    st.header("Configuración")

    politica_nombre = st.selectbox(
        "Algoritmo de planificación",
        list(ALGORITMOS.keys()),
    )
    politica = ALGORITMOS[politica_nombre]

    quantum = 2
    if politica == "RR":
        quantum = st.number_input(
            "Quantum",
            min_value=1,
            value=2,
            step=1,
        )

    st.divider()
    st.subheader("Cargar procesos")

    ejemplo = st.selectbox(
        "Ejercicios de ejemplo",
        ["Ninguno"] + list(EJEMPLOS.keys()),
    )

    if st.button("Cargar ejemplo", use_container_width=True):
        if ejemplo != "Ninguno":
            cargar_ejemplo(ejemplo)
            st.rerun()

    st.divider()

    archivo = st.file_uploader(
        "Importar archivo TXT o CSV",
        type=["txt", "csv"],
    )

    if st.button("Importar archivo", use_container_width=True):
        if archivo is not None:
            importar_txt(archivo)
            st.rerun()
        else:
            st.warning("Primero selecciona un archivo.")

    st.caption(
        "Formato: nombre,llegada,rafaga,prioridad"
    )


    st.divider()

    if st.button("Limpiar procesos", use_container_width=True):
        st.session_state.procesos = []
        st.session_state.resultado = None
        st.rerun()


# ---------------- REGISTRO MANUAL ----------------

st.subheader("Registro de procesos")

with st.form("form_proceso", clear_on_submit=True):
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        nombre = st.text_input("Nombre", placeholder="P1")
    with c2:
        llegada = st.number_input(
            "Tiempo de llegada", min_value=0, value=0, step=1
        )
    with c3:
        rafaga = st.number_input(
            "Ráfaga de CPU", min_value=1, value=5, step=1
        )
    with c4:
        prioridad = st.number_input(
            "Prioridad", min_value=0, value=1, step=1
        )

    agregar = st.form_submit_button(
        "＋ Agregar proceso",
        use_container_width=True,
    )

    if agregar:
        nombre = nombre.strip()

        if not nombre:
            st.error("Ingresa el nombre del proceso.")
        elif any(p.nombre == nombre for p in st.session_state.procesos):
            st.error("Ya existe un proceso con ese nombre.")
        else:
            st.session_state.procesos.append(
                Proc(nombre, int(llegada), int(rafaga), int(prioridad))
            )
            st.session_state.resultado = None
            st.rerun()


# ---------------- TABLA DE PROCESOS ----------------

procesos = st.session_state.procesos

st.subheader(f"Procesos cargados: {len(procesos)}")

if procesos:
    df_procesos = pd.DataFrame([
        {
            "Proceso": p.nombre,
            "Llegada": p.llegada,
            "Ráfaga": p.rafaga,
            "Prioridad": p.prioridad,
        }
        for p in procesos
    ])

    st.dataframe(
        df_procesos,
        use_container_width=True,
        hide_index=True,
        height=250,
    )

else:
    st.info("Agrega procesos, carga un ejemplo o importa un archivo.")

st.divider()

# ---------------- SIMULACIÓN ----------------

if st.button(
    "▶ Ejecutar simulación",
    type="primary",
    use_container_width=True,
    disabled=not procesos,
):
    try:
        with st.spinner("Calculando planificación..."):
            segmentos = planificar(
                procesos,
                politica,
                int(quantum) if politica == "RR" else None,
            )

            filas, globales = calcular_metricas(procesos, segmentos)

            st.session_state.resultado = {
                "politica": politica_nombre,
                "politica_clave": politica,
                "procesos": list(procesos),
                "segmentos": segmentos,
                "filas": filas,
                "g": globales,
            }

    except Exception as e:
        st.error(f"Error durante la simulación: {e}")


# ---------------- RESULTADOS ----------------

resultado = st.session_state.resultado

if resultado:
    st.header("Resultados de la simulación")
    st.caption(f"Algoritmo utilizado: {resultado['politica']}")

    segmentos = resultado["segmentos"]
    filas = resultado["filas"]
    g = resultado["g"]
    procs_res = resultado["procesos"]
    politica_usada = resultado["politica_clave"]

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("Procesos", g["n"])
    m2.metric("Uso de CPU", f"{g['uso_cpu']:.2f}%")
    m3.metric("Espera promedio", f"{g['prom_es']:.2f}")
    m4.metric("Retorno promedio", f"{g['prom_r']:.2f}")

    m5, m6, m7 = st.columns(3)

    m5.metric("Tiempo total", g["tiempo_total"])
    m6.metric("Respuesta promedio", f"{g['prom_resp']:.2f}")
    m7.metric("Varianza de espera", f"{g['var_es']:.2f}")

    m8, m9, m10 = st.columns(3)

    m8.metric("Espera máxima", g["max_es"])
    m9.metric("Cambios de contexto", g["cambios"])
    m10.metric("Rendimiento", f"{g['rendimiento']:.3f} proc/u")

    st.plotly_chart(
        crear_gantt(segmentos),
        use_container_width=True,
    )

    st.subheader("Métricas por proceso")

    df_resultados = pd.DataFrame(
        filas,
        columns=[
            "Proceso",
            "Llegada",
            "Ráfaga",
            "Finalización",
            "Retorno",
            "Espera",
            "Respuesta",
        ],
    )

    st.dataframe(
        df_resultados,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Cola de listos")

    total_tiempo = g["tiempo_total"]
    inicios = preparar_inicios(segmentos)

    if total_tiempo > 1:
        instante = st.slider(
            "Selecciona el instante de la simulación",
            min_value=0,
            max_value=total_tiempo - 1,
            value=0,
        )
    else:
        instante = 0

    en_cpu, listos = cola_listos(
        procs_res, segmentos, politica_usada, instante, inicios
    )

    q1, q2 = st.columns(2)
    q1.metric("En CPU", en_cpu if en_cpu is not None else "CPU ociosa")
    q2.metric("Procesos esperando", len(listos))

    if listos:
        st.write(" → ".join(
            f"{nombre} (resta {resta})"
            for nombre, resta, _, _ in listos
        ))
    else:
        st.info("La cola de listos está vacía en este instante.")

    with st.expander("Ver evolución de la cola"):
        # La cola solo cambia cuando llega un proceso o cambia el tramo de CPU.
        eventos = sorted(
            {ini for ini, _, _ in segmentos}
            | {p.llegada for p in procs_res}
        )
        eventos = [t for t in eventos if t < total_tiempo]
        LIMITE_FILAS = 2000

        filas_cola = []
        for t in eventos[:LIMITE_FILAS]:
            cpu, lst = cola_listos(
                procs_res, segmentos, politica_usada, t, inicios
            )
            filas_cola.append({
                "Tiempo": t,
                "En CPU": cpu if cpu is not None else "—",
                "Cantidad en cola": len(lst),
                "Procesos listos": " → ".join(n for n, _, _, _ in lst),
            })

        if len(eventos) > LIMITE_FILAS:
            st.caption(f"Se muestran los primeros {LIMITE_FILAS} eventos.")

        st.dataframe(
            pd.DataFrame(filas_cola),
            use_container_width=True,
            hide_index=True,
            height=300,
        )


# ==========================================================
# MODULO DE PROBLEMAS CLASICOS DE CONCURRENCIA
# ==========================================================

st.divider()
st.header("Problemas de Concurrencia")

if "sim_concurrencia" not in st.session_state:
    st.session_state.sim_concurrencia = SimulacionConcurrencia()

sim = st.session_state.sim_concurrencia

problemas = {
    "Productor-consumidor": sim.productor_consumidor,
    "Lectores-escritores": sim.lectores_escritores,
    "Filósofos comensales": sim.filosofos_comensales,
    "Barbero dormilón": sim.barbero_dormilon,
    "Problema de los fumadores": sim.fumadores,
}

st.markdown("""
<style>
.lab-panel {
    background: linear-gradient(135deg, #111c2e 0%, #142238 100%);
    border: 1px solid #29445f;
    border-radius: 16px;
    padding: 16px;
    margin: 6px 0 12px 0;
}
.lab-label {
    color: #8ba4be;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
}
.lab-value {
    color: #e5edf7;
    font-size: 22px;
    font-weight: 700;
}
.worker {
    background: #17263a;
    border: 1px solid #35516e;
    border-radius: 14px;
    padding: 14px;
    text-align: center;
    min-height: 118px;
}
.worker-icon { font-size: 32px; }
.worker-name { color: #e5edf7; font-weight: 700; margin-top: 4px; }
.scene-card { background: #142238; border: 1px solid #35516e; border-radius: 14px; padding: 13px; text-align: center; min-height: 112px; margin-bottom: 8px; }
.scene-card .scene-icon { font-size: 29px; }
.scene-card .scene-name { color: #e5edf7; font-weight: 700; margin-top: 5px; }
.scene-card .scene-state { color: #5eead4; font-size: 12px; margin-top: 6px; }
.resource-pill { display: inline-block; background: #1d334b; border: 1px solid #3a5877; color: #c5d7e9; border-radius: 999px; padding: 6px 11px; margin: 3px; font-size: 12px; }
.scene-center { background: #0a1220; border: 1px dashed #3b5874; border-radius: 14px; padding: 20px 10px; text-align: center; color: #c7d7e8; margin: 6px 0 12px; }
.scene-center .big-icon { font-size: 42px; }
.scene-note { color: #9db0c5; font-size: 13px; text-align: center; margin-top: 6px; }
.worker-state { color: #5eead4; font-size: 13px; margin-top: 6px; }
.conveyor {
    background: #0a1220;
    border: 1px solid #2b4057;
    border-radius: 16px;
    padding: 15px;
    overflow: hidden;
}
.conveyor-track {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 72px;
    padding: 10px;
    border-radius: 12px;
    background: repeating-linear-gradient(90deg, #1b2a3c 0px, #1b2a3c 24px, #24374d 24px, #24374d 48px);
    background-size: 96px 100%;
    animation: moveTrack 1.2s linear infinite;
}
.buffer-item {
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 48px;
    height: 48px;
    border-radius: 12px;
    background: linear-gradient(145deg, #0e7490, #155e75);
    border: 2px solid #67e8f9;
    color: white;
    font-size: 19px;
    font-weight: 800;
    box-shadow: 0 0 14px #0891b244;
    animation: appear 0.3s ease-out;
}
.buffer-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 48px;
    height: 48px;
    border: 2px dashed #40536a;
    border-radius: 12px;
    color: #71849b;
    font-size: 11px;
}
@keyframes moveTrack { from { background-position: 0 0; } to { background-position: 96px 0; } }
@keyframes appear { from { transform: translateY(-8px) scale(.8); opacity: .3; } to { transform: translateY(0) scale(1); opacity: 1; } }
@media (prefers-reduced-motion: reduce) {
    .conveyor-track { animation: none; }
    .buffer-item { animation: none; }
}
</style>
""", unsafe_allow_html=True)


@st.fragment(run_every=0.35)
def modulo_concurrencia():
    sim = st.session_state.sim_concurrencia

    selector_col, descripcion_col = st.columns([1, 2])
    with selector_col:
        problema = st.selectbox(
            "Problemas de concurrencia",
            list(problemas.keys()),
            key="problema_concurrencia",
        )
    with descripcion_col:
        descripciones = {
            "Productor-consumidor": "Un productor agrega elementos y un consumidor los retira. Los semáforos controlan los espacios y elementos; un mutex protege el buffer.",
            "Lectores-escritores": "Varios lectores pueden consultar el recurso, mientras que un escritor necesita acceso exclusivo.",
            "Filósofos comensales": "Los filósofos compiten por tenedores compartidos y deben evitar bloqueos.",
            "Barbero dormilón": "El barbero duerme si no hay clientes y atiende cuando alguien espera, limitado por las sillas.",
            "Problema de los fumadores": "El agente pone dos ingredientes sin saber quién fumará; tres intermediarios (pushers) detectan el par y despiertan al fumador que tiene el tercero, evitando el deadlock.",
        }
        st.markdown(
            f'<div class="lab-panel"><div class="lab-label">Objetivo del experimento</div>'
            f'<div style="color:#d9e7f5;margin-top:8px">{descripciones[problema]}</div></div>',
            unsafe_allow_html=True,
        )

    argumentos = {}
    if problema == "Productor-consumidor":
        c1, c2, c3 = st.columns(3)
        with c1:
            argumentos["capacidad"] = int(st.number_input(
                "Capacidad del buffer", min_value=1, max_value=10,
                value=5, step=1, key="capacidad_buffer"
            ))
        with c2:
            argumentos["total_elementos"] = int(st.number_input(
                "Elementos por producir", min_value=1, max_value=100,
                value=20, step=1, key="total_elementos"
            ))
        with c3:
            argumentos["velocidad"] = float(st.slider(
                "Velocidad", min_value=0.25, max_value=3.0,
                value=1.0, step=0.25, key="velocidad_productor_consumidor"
            ))
    elif problema == "Lectores-escritores":
        c1, c2 = st.columns(2)
        with c1:
            argumentos["cantidad_lectores"] = int(st.number_input(
                "Cantidad de lectores", min_value=1, max_value=10,
                value=3, key="cantidad_lectores"
            ))
        with c2:
            argumentos["cantidad_escritores"] = int(st.number_input(
                "Cantidad de escritores", min_value=1, max_value=10,
                value=2, key="cantidad_escritores"
            ))
    elif problema == "Filósofos comensales":
        argumentos["cantidad"] = int(st.number_input(
            "Cantidad de filósofos", min_value=2, max_value=10,
            value=5, key="cantidad_filosofos"
        ))
    elif problema == "Barbero dormilón":
        c1, c2 = st.columns(2)
        with c1:
            argumentos["cantidad_clientes"] = int(st.number_input(
                "Cantidad de clientes", min_value=1, max_value=20,
                value=8, key="cantidad_clientes"
            ))
        with c2:
            argumentos["sillas"] = int(st.number_input(
                "Sillas de espera", min_value=1, max_value=10,
                value=3, key="sillas_barberia"
            ))
    elif problema == "Problema de los fumadores":
        argumentos["rondas"] = int(st.number_input(
            "Cantidad de rondas", min_value=1, max_value=20,
            value=6, key="rondas_fumadores"
        ))

    if problema == "Lectores-escritores":
        argumentos["politica"] = st.selectbox(
            "Política de acceso",
            ["Preferencia a lectores", "Preferencia a escritores", "Equitativa (bloques por turno)"],
            key="politica_lectores_escritores",
        )
    if problema != "Productor-consumidor":      # el productor-consumidor ya tiene su propio control
        argumentos["velocidad"] = float(st.slider(
            "Velocidad", min_value=0.25, max_value=3.0,
            value=1.0, step=0.25, key=f"velocidad_{problema}"
        ))

    c1, c2, c3 = st.columns(3)
    with c1:
        iniciar = st.button(
            "▶ Iniciar experimento", type="primary",
            disabled=sim.activa, use_container_width=True,
            key="iniciar_concurrencia"
        )
    with c2:
        detener = st.button(
            "■ Detener", disabled=not sim.activa,
            use_container_width=True, key="detener_concurrencia"
        )
    with c3:
        reiniciar = st.button(
            "↻ Limpiar monitor", disabled=sim.activa,
            use_container_width=True, key="reiniciar_concurrencia"
        )

    if iniciar:
        with sim.mutex:
            sim.eventos.clear()
            sim.estados.clear()
            sim.datos.clear()
        if not sim.iniciar(problemas[problema], **argumentos):
            st.warning("Ya existe un experimento en ejecución.")
    if detener:
        sim.detener()
    if reiniciar:
        with sim.mutex:
            sim.eventos.clear()
            sim.estados.clear()
            sim.datos.clear()
        st.rerun()

    with sim.mutex:
        datos = dict(sim.datos)
        estados = dict(sim.estados)
        eventos = list(sim.eventos)
        activa = sim.activa

    estado_general = "EN EJECUCIÓN" if activa else (
        "FINALIZADO" if eventos else "LISTO PARA INICIAR"
    )
    color_estado = "#5eead4" if activa else "#fbbf24"
    st.markdown(
        f'<div class="lab-panel" style="display:flex;justify-content:space-between;align-items:center">'
        f'<div><div class="lab-label">Estado del experimento</div>'
        f'<div class="lab-value" style="color:{color_estado}">{estado_general}</div></div>'
        f'<div style="text-align:right"><div class="lab-label">Hilos de la simulación</div>'
        f'<div class="lab-value">{len(sim.hilos)}</div></div></div>',
        unsafe_allow_html=True,
    )

    if problema == "Productor-consumidor":
        capacidad = int(datos.get("capacidad", argumentos.get("capacidad", 5)))
        buffer = datos.get("buffer", [])
        producidos = int(datos.get("producidos", 0))
        consumidos = int(datos.get("consumidos", 0))
        total = int(datos.get("total_elementos", argumentos.get("total_elementos", 20)))
        ocupacion = len(buffer) / max(1, capacidad)
        progreso = consumidos / max(1, total)

        st.subheader("🏭 Escena del laboratorio")
        cprod, cscene, ccons = st.columns([1, 2.3, 1])
        with cprod:
            st.markdown(
                f'<div class="worker"><div class="worker-icon">🏭</div>'
                f'<div class="worker-name">Productor</div>'
                f'<div class="worker-state">{estados.get("Productor", "Preparado")}</div>'
                f'<div style="color:#8ba4be;font-size:12px;margin-top:8px">Crea elementos</div></div>',
                unsafe_allow_html=True,
            )
        with cscene:
            # Una sola pieza HTML mantiene la cinta y las celdas dentro de la escena.
            slots = []
            for i in range(capacidad):
                if i < len(buffer):
                    slots.append(f'<div class="buffer-item">{buffer[i]}</div>')
                else:
                    slots.append('<div class="buffer-empty">VACÍO</div>')
            st.markdown(
                '<div class="conveyor"><div class="lab-label" style="margin-bottom:8px">Buffer compartido · cinta transportadora</div>'
                '<div class="conveyor-track" style="animation-duration:1.2s">'
                + "".join(slots)
                + '</div><div style="display:flex;justify-content:space-between;margin-top:10px;color:#9db0c5;font-size:12px">'
                + f'<span>Ocupación: {len(buffer)}/{capacidad}</span>'
                + f'<span>{int(ocupacion * 100)}%</span></div></div>',
                unsafe_allow_html=True,
            )
        with ccons:
            st.markdown(
                f'<div class="worker"><div class="worker-icon">📦</div>'
                f'<div class="worker-name">Consumidor</div>'
                f'<div class="worker-state">{estados.get("Consumidor", "Preparado")}</div>'
                f'<div style="color:#8ba4be;font-size:12px;margin-top:8px">Retira elementos</div></div>',
                unsafe_allow_html=True,
            )

        st.progress(min(1.0, progreso), text=f"Consumo total: {consumidos}/{total} elementos")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Producidos", producidos)
        m2.metric("Consumidos", consumidos)
        m3.metric("Espacios libres", datos.get("espacios_libres", capacidad))
        m4.metric("Elementos disponibles", datos.get("elementos_disponibles", 0))

        m5, m6, m7 = st.columns(3)
        m5.metric("Último producido", datos.get("ultimo_producido") or "—")
        m6.metric("Último consumido", datos.get("ultimo_consumido") or "—")
        m7.metric("Velocidad configurada", f'{datos.get("velocidad", argumentos.get("velocidad", 1.0))}×')

        st.subheader("🔐 Recursos de sincronización")
        s1, s2 = st.columns(2)
        with s1:
            st.markdown(
                f'<div class="lab-panel"><div class="lab-label">Semáforo · espacios_libres</div>'
                f'<div class="lab-value">{datos.get("espacios_libres", capacidad)} / {capacidad}</div>'
                f'<div style="color:#9db0c5;font-size:12px;margin-top:6px">El productor necesita un permiso para agregar.</div></div>',
                unsafe_allow_html=True,
            )
        with s2:
            st.markdown(
                f'<div class="lab-panel"><div class="lab-label">Semáforo · elementos_disponibles</div>'
                f'<div class="lab-value">{datos.get("elementos_disponibles", 0)}</div>'
                f'<div style="color:#9db0c5;font-size:12px;margin-top:6px">El consumidor necesita un permiso para retirar.</div></div>',
                unsafe_allow_html=True,
            )
        st.caption(f"Actividad reciente: {datos.get('accion', 'Esperando inicio')}")

    elif problema == "Lectores-escritores":
        st.subheader("📚 Escena: sala de lectura y escritura")
        lectores = [(n, e) for n, e in estados.items() if n.startswith("Lector ")]
        escritores = [(n, e) for n, e in estados.items() if n.startswith("Escritor ")]
        recurso_col, detalle_col = st.columns([1, 2])
        with recurso_col:
            lectura_activa = sum(1 for _, e in lectores if e == "Leyendo")
            escritura_activa = sum(1 for _, e in escritores if e == "Escribiendo")
            icono = "✍️" if escritura_activa else "📖" if lectura_activa else "🔒"
            titulo_recurso = "Escritura exclusiva" if escritura_activa else "Lectura compartida" if lectura_activa else "Recurso libre"
            st.markdown(
                f'<div class="scene-center"><div class="big-icon">{icono}</div>'
                f'<b>{titulo_recurso}</b><div class="scene-note">Valor compartido: {datos.get("valor_compartido", 0)}</div></div>',
                unsafe_allow_html=True,
            )
            m1, m2 = st.columns(2)
            m1.metric("Leyendo simultáneamente", lectura_activa)
            m2.metric("Escribiendo", escritura_activa)
            m3, m4 = st.columns(2)
            m3.metric("Lecturas completadas", datos.get("lecturas_realizadas", 0))
            m4.metric("Escrituras completadas", datos.get("escrituras_realizadas", 0))
        with detalle_col:
            st.markdown("**Lectores**")
            cols = st.columns(min(5, max(1, len(lectores))))
            for i, (nombre, estado) in enumerate(lectores):
                with cols[i % len(cols)]:
                    st.markdown(f'<div class="scene-card"><div class="scene-icon">👓</div><div class="scene-name">{nombre}</div><div class="scene-state">{estado}</div></div>', unsafe_allow_html=True)
            st.markdown("**Escritores**")
            cols = st.columns(min(5, max(1, len(escritores))))
            for i, (nombre, estado) in enumerate(escritores):
                with cols[i % len(cols)]:
                    st.markdown(f'<div class="scene-card"><div class="scene-icon">✍️</div><div class="scene-name">{nombre}</div><div class="scene-state">{estado}</div></div>', unsafe_allow_html=True)
        st.caption("Regla: varios lectores pueden acceder simultáneamente, pero un escritor necesita que el recurso quede libre.")

    elif problema == "Filósofos comensales":
        st.subheader("🍽️ Escena: mesa de filósofos")
        filosofos = [(n, e) for n, e in estados.items() if n.startswith("Filósofo ")]
        cantidad_f = int(argumentos.get("cantidad", 5))
        mesa_col, info_col = st.columns([2, 1])
        with mesa_col:
            st.markdown('<div class="scene-center"><div class="big-icon">🍝</div><b>Mesa compartida</b><div class="scene-note">Cada filósofo necesita dos tenedores para comer.</div></div>', unsafe_allow_html=True)
            cols = st.columns(min(5, max(1, len(filosofos))))
            for i, (nombre, estado) in enumerate(filosofos):
                icono = "🍝" if estado == "Comiendo" else "💭" if estado == "Pensando" else "🍴"
                with cols[i % len(cols)]:
                    st.markdown(f'<div class="scene-card"><div class="scene-icon">{icono}</div><div class="scene-name">{nombre}</div><div class="scene-state">{estado}</div></div>', unsafe_allow_html=True)
        with info_col:
            comiendo = sum(1 for _, e in filosofos if e == "Comiendo")
            pensando = sum(1 for _, e in filosofos if e == "Pensando")
            m1, m2, m3 = st.columns(3)
            m1.metric("Filósofos", cantidad_f)
            m2.metric("Comiendo", comiendo)
            m3.metric("Pensando", pensando)
            comidas = int(datos.get("comidas_completadas", 0))
            objetivo = int(datos.get("comidas_objetivo", cantidad_f * 2))
            st.progress(min(1.0, comidas / max(1, objetivo)), text=f"Comidas completadas: {comidas}/{objetivo}")
            tenedores = datos.get("tenedores_ocupados", [False] * cantidad_f)
            tenedores_html = "".join(
                f'<span class="resource-pill">🍴 Tenedor {i + 1}: {"Ocupado" if ocupado else "Libre"}</span>'
                for i, ocupado in enumerate(tenedores)
            )
            st.markdown(f'<div class="lab-panel"><div class="lab-label">Estado de los tenedores</div>{tenedores_html}<div class="scene-note">El semáforo permite competir a lo sumo N−1 filósofos y evita el deadlock circular.</div></div>', unsafe_allow_html=True)

    elif problema == "Barbero dormilón":
        st.subheader("💈 Escena: barbería")
        barbero_estado = estados.get("Barbero", "Esperando inicio")
        clientes = [(n, e) for n, e in estados.items() if n.startswith("Cliente ")]
        sillas = int(datos.get("sillas", argumentos.get("sillas", 3)))
        esperando = sum(1 for _, e in clientes if e == "Esperando")
        atendidos = sum(1 for _, e in clientes if e == "Atendido")
        rechazados = sum(1 for _, e in clientes if "Se fue" in e)
        bcol, sala_col = st.columns([1, 2])
        with bcol:
            icono_barbero = "💤" if "Durmiendo" in barbero_estado else "✂️" if "Cortando" in barbero_estado else "💈"
            st.markdown(f'<div class="scene-center"><div class="big-icon">{icono_barbero}</div><b>Barbero</b><div class="scene-note">{barbero_estado}</div></div>', unsafe_allow_html=True)
            st.metric("Clientes atendidos", datos.get("clientes_atendidos", atendidos))
            st.metric("Clientes rechazados", datos.get("clientes_rechazados", rechazados))
        with sala_col:
            st.markdown("**Sala de espera**")
            esperando_real = int(datos.get("clientes_esperando", esperando))
            silla_html = "".join(f'<span class="resource-pill">🪑 Silla {i+1}: ' + ("Ocupada" if i < esperando_real else "Libre") + '</span>' for i in range(sillas))
            st.markdown(f'<div class="lab-panel">{silla_html}<div class="scene-note">Ocupación de la cola: {min(esperando_real, sillas)}/{sillas}</div></div>', unsafe_allow_html=True)
            st.markdown("**Clientes**")
            if clientes:
                cols = st.columns(min(5, len(clientes)))
                for i, (nombre, estado) in enumerate(clientes):
                    icono = "💇" if estado == "Atendido" else "🪑" if estado == "Esperando" else "🚪" if "Se fue" in estado else "🙂"
                    with cols[i % len(cols)]:
                        st.markdown(f'<div class="scene-card"><div class="scene-icon">{icono}</div><div class="scene-name">{nombre}</div><div class="scene-state">{estado}</div></div>', unsafe_allow_html=True)
            else:
                st.info("Los clientes aparecerán cuando inicies la simulación.")
        st.caption("Los clientes que encuentran todas las sillas ocupadas se retiran; el barbero duerme cuando no hay clientes.")

    elif problema == "Problema de los fumadores":
        st.subheader("🚬 Escena: mesa de ingredientes")
        agente_col, mesa_col = st.columns([1, 1.5])
        with agente_col:
            st.markdown(f'<div class="scene-center"><div class="big-icon">🧑‍🍳</div><b>Agente</b><div class="scene-note">{estados.get("Agente", "Esperando inicio")}</div></div>', unsafe_allow_html=True)
            st.metric("Ronda", f'{datos.get("ronda_actual", 0)}/{datos.get("rondas_configuradas", argumentos.get("rondas", 6))}')
        with mesa_col:
            ingredientes_mesa = datos.get("ingredientes_mesa", [])
            iconos_ingredientes = {"Tabaco": "🍃", "Papel": "📄", "Fósforos": "🔥"}
            visual_ingredientes = "  ".join(iconos_ingredientes.get(nombre, "❔") for nombre in ingredientes_mesa) if ingredientes_mesa else "—"
            texto_mesa = ", ".join(ingredientes_mesa) if ingredientes_mesa else "Mesa libre: esperando al agente"
            st.markdown(f'<div class="scene-center"><div class="big-icon">{visual_ingredientes}</div><b>Ingredientes sobre la mesa</b><div class="scene-note">{texto_mesa}</div></div>', unsafe_allow_html=True)
            fumador_actual = datos.get("fumador_actual")
            if fumador_actual and ingredientes_mesa:
                st.info(f"El fumador {fumador_actual} posee el tercer ingrediente y puede recoger los dos de la mesa.")
            m1, m2 = st.columns(2)
            m1.metric("Rondas completadas", datos.get("rondas_completadas", 0))
            m2.metric("Rondas totales", datos.get("rondas_configuradas", argumentos.get("rondas", 6)))
        fumadores = [(n, e) for n, e in estados.items() if n.startswith("Fumador ")]
        cols = st.columns(3)
        for i in range(3):
            nombre = f"Fumador {i+1}"
            estado = dict(fumadores).get(nombre, "Esperando ingredientes")
            icono = "🚬" if estado == "Fumando" else "⏳"
            with cols[i]:
                st.markdown(f'<div class="scene-card"><div class="scene-icon">{icono}</div><div class="scene-name">{nombre}</div><div class="scene-state">{estado}</div></div>', unsafe_allow_html=True)
        st.caption("El agente sólo pone dos ingredientes. Los pushers registran lo que hay en la mesa y despiertan al fumador correcto; cuando éste termina, avisa al agente.")

    st.subheader("🧵 Monitor de hilos")
    if estados:
        estado_cols = st.columns(min(4, max(1, len(estados))))
        for i, (nombre, estado) in enumerate(estados.items()):
            with estado_cols[i % len(estado_cols)]:
                st.markdown(
                    f'<div class="worker"><div class="worker-icon">⚙️</div>'
                    f'<div class="worker-name">{nombre}</div>'
                    f'<div class="worker-state">{estado}</div></div>',
                    unsafe_allow_html=True,
                )
    else:
        st.info("Los estados de los hilos aparecerán al iniciar el experimento.")


modulo_concurrencia()
