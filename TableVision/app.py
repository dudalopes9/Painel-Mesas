"""TableVision AI - Dashboard de ocupacao de mesas (Streamlit).

Execute:  streamlit run app.py
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import pandas as pd
import streamlit as st

from detector import TableMonitor, fmt_tempo

BASE = Path(__file__).parent
VIDEO_PADRAO = BASE / "data" / "restaurante.mp4"
CONFIG_MESAS = BASE / "config" / "mesas.json"
# Horario exibido no OSD da camera no primeiro frame do video (usado so para o relogio)
INICIO_GRAVACAO = "2026-10-22 17:01:07"
DIAS = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

st.set_page_config(page_title="TableVision AI", page_icon="🍽️", layout="wide")

CSS = """
<style>
.stApp { background: radial-gradient(1200px 600px at 50% -10%, #1b2a26 0%, #0f1513 55%, #0b0f0e 100%); }
.block-container { padding-top: 3.2rem; max-width: 1400px; }
.tv-header { display:flex; justify-content:space-between; align-items:flex-end; margin-bottom: 18px; }
.tv-brand { display:flex; gap:12px; align-items:center; }
.tv-logo { width:42px; height:42px; border-radius:10px; background:#1f2a28; display:flex;
           align-items:center; justify-content:center; font-size:20px; border:1px solid #2c3a37; }
.tv-title { font-family: Georgia, serif; font-size: 26px; font-weight: 700; color:#f3f4f2; line-height:1.1; }
.tv-sub { font-size: 12px; color:#8a9692; }
.tv-clock { text-align:right; }
.tv-clock .h { font-size: 34px; font-weight: 800; color:#f3f4f2; line-height:1; }
.tv-clock .d { font-size: 12px; color:#8a9692; }
.kpis { display:grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px; }
.kpi { background:#1d2523; border:1px solid #2a3532; border-left: 4px solid var(--c); border-radius:8px; padding:12px 16px; }
.kpi .l { font-size:10px; letter-spacing:.08em; color:#95a19d; font-weight:700; text-transform:uppercase; }
.kpi .v { font-size:34px; font-weight:800; color:#f3f4f2; line-height:1.15; }
.sec { display:flex; justify-content:space-between; align-items:center; margin: 6px 0 10px; }
.sec .t { color:#f3f4f2; font-weight:700; font-size:15px; }
.leg { font-size:11px; color:#a6b1ad; }
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin: 0 4px 0 12px; }
.grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 14px; }
.card { border-radius:8px; padding:14px 16px 12px; color:#1d2422; position:relative; }
.card.livre { background:#bfe5c8; } .card.ocup { background:#f2b3ae; }
.card .top { display:flex; justify-content:space-between; align-items:flex-start; }
.card .ic { width:30px; height:30px; border-radius:8px; background:rgba(255,255,255,.65);
            display:inline-flex; align-items:center; justify-content:center; font-size:15px; margin-right:8px; }
.card .nm { font-weight:800; font-size:15px; }
.card .lg { font-size:10px; color:#4b5753; }
.badge { font-size:10px; font-weight:800; letter-spacing:.04em; color:#fff; padding:4px 9px; border-radius:20px; }
.livre .badge { background:#2f8a46; } .ocup .badge { background:#b3312b; }
.card .lbl { font-size:9px; letter-spacing:.08em; font-weight:700; color:#4b5753; margin-top:12px; text-transform:uppercase; }
.card .bot { display:flex; justify-content:space-between; align-items:flex-end; }
.card .tm { font-size:32px; font-weight:800; font-variant-numeric: tabular-nums; line-height:1.05; }
.card .st { font-size:10px; color:#4b5753; margin-bottom:5px; white-space:nowrap; }
.vid-cap { color:#8a9692; font-size:12px; margin-top:4px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource(show_spinner="Carregando modelo YOLO...")
def carregar_modelo(nome: str):
    from ultralytics import YOLO
    return YOLO(nome)


def html_header(relogio: datetime | None) -> str:
    if relogio:
        h = relogio.strftime("%H:%M:%S")
        d = f"{DIAS[relogio.weekday()]}, {relogio.day} de {MESES[relogio.month - 1]} de {relogio.year}"
    else:
        h, d = "--:--:--", "Aguardando início"
    return f"""
<div class="tv-header">
  <div class="tv-brand"><div class="tv-logo">🍽️</div>
    <div><div class="tv-title">TableVision AI</div>
    <div class="tv-sub">Painel de Mesas · Salão Principal · Visão computacional com YOLO + OpenCV</div></div></div>
  <div class="tv-clock"><div class="h">{h}</div><div class="d">{d}</div></div>
</div>"""


def html_kpis(r: dict) -> str:
    def k(lbl, val, cor):
        return f'<div class="kpi" style="--c:{cor}"><div class="l">{lbl}</div><div class="v">{val}</div></div>'
    return ('<div class="kpis">'
            + k("Total de mesas", f"{r['total']:02d}", "#9aa6a2")
            + k("Disponíveis", f"{r['disponiveis']:02d}", "#7fd39a")
            + k("Ocupadas", f"{r['ocupadas']:02d}", "#f08a84")
            + k("Taxa de ocupação", f"{r['percentual']:.0f}%", "#f3c969")
            + "</div>")


def html_cards(r: dict) -> str:
    cards = []
    for m in r["mesas"]:
        oc = m["ocupada"]
        cls, badge = ("ocup", "OCUPADA") if oc else ("livre", "DISPONÍVEL")
        lbl = "Ocupada há" if oc else "Livre há"
        p = m["pessoas"]
        st_txt = ("Em uso" if p == 0 else f"{p} pessoa{'s' if p > 1 else ''}") if oc else "Pronta para uso"
        cards.append(f"""
<div class="card {cls}">
  <div class="top"><div style="display:flex;align-items:center"><span class="ic">🍽️</span>
    <div><div class="nm">{m['nome']}</div><div class="lg">{m['lugares']} lugares</div></div></div>
    <span class="badge">{badge}</span></div>
  <div class="lbl">{lbl}</div>
  <div class="bot"><div class="tm">{fmt_tempo(m['tempo'])}</div><div class="st">{st_txt}</div></div>
</div>""")
    legenda = ('<span class="leg"><span class="dot" style="background:#7fd39a"></span>Disponível'
               '<span class="dot" style="background:#f08a84"></span>Ocupada</span>')
    return f'<div class="sec"><span class="t">Mesas</span>{legenda}</div><div class="grid">{"".join(cards)}</div>'


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("⚙️ Configurações")
    video = st.text_input("Vídeo de entrada", str(VIDEO_PADRAO))
    cap_info = cv2.VideoCapture(video)
    fps_video = cap_info.get(cv2.CAP_PROP_FPS) or 30.0
    duracao = cap_info.get(cv2.CAP_PROP_FRAME_COUNT) / fps_video if cap_info.isOpened() else 0
    cap_info.release()
    if duracao <= 0:
        st.error("Não foi possível abrir o vídeo.")
    inicio_min = st.slider("Começar no minuto", 0, max(int(duracao // 60), 0), 0)
    pular = st.slider("Analisar 1 a cada N frames", 1, 30, 10,
                      help="10 = ~3 análises por segundo de vídeo (vídeo a 30 fps).")
    tempo_real = st.toggle("Sincronizar com o tempo real do vídeo", value=True,
                           help="Desligado: processa o mais rápido possível (acelera a simulação).")
    modelo_nome = st.selectbox("Modelo YOLO", ["yolo11n.pt", "yolo11s.pt"],
                               help="n = mais rápido, s = mais preciso (mais lento em CPU).")
    conf = st.slider("Confiança mínima", 0.10, 0.90, 0.35, 0.05)
    st.subheader("Confirmação temporal")
    t_on = st.slider("Segundos para confirmar OCUPADA", 2, 30, 10)
    t_off = st.slider("Segundos para confirmar DISPONÍVEL", 5, 90, 20)
    st.caption("Evita que pessoas passando ou garçons alterem o status das mesas.")
    c1, c2 = st.columns(2)
    iniciar = c1.button("▶ Iniciar", type="primary", width="stretch")
    parar = c2.button("■ Parar", width="stretch")

if iniciar:
    st.session_state.rodando = True
if parar:
    st.session_state.rodando = False

# ----------------------------------------------------------------- layout
ph_header = st.empty()
ph_kpis = st.empty()
col_vid, col_info = st.columns([3, 2], gap="large")
with col_vid:
    ph_video = st.empty()
    ph_vcap = st.empty()
with col_info:
    st.markdown('<div class="sec"><span class="t">Últimas mudanças de estado</span></div>', unsafe_allow_html=True)
    ph_eventos = st.empty()
ph_cards = st.empty()

inicio_rel = datetime.strptime(INICIO_GRAVACAO, "%Y-%m-%d %H:%M:%S")

if not st.session_state.get("rodando"):
    ph_header.markdown(html_header(None), unsafe_allow_html=True)
    ultimo = st.session_state.get("ultimo")
    if ultimo:
        ph_kpis.markdown(html_kpis(ultimo["resumo"]), unsafe_allow_html=True)
        ph_video.image(ultimo["frame"], channels="RGB", width="stretch")
        ph_cards.markdown(html_cards(ultimo["resumo"]), unsafe_allow_html=True)
        if ultimo["eventos"]:
            ph_eventos.dataframe(pd.DataFrame(ultimo["eventos"]), hide_index=True, width="stretch")
        ph_vcap.markdown('<div class="vid-cap">Análise pausada. Clique em ▶ Iniciar para recomeçar.</div>',
                         unsafe_allow_html=True)
    else:
        st.info("Clique em **▶ Iniciar** na barra lateral para processar o vídeo do restaurante.")
    st.stop()

# -------------------------------------------------------------- processamento
monitor = TableMonitor(CONFIG_MESAS, modelo=carregar_modelo(modelo_nome), conf=conf,
                       t_confirma_ocupada=t_on, t_confirma_livre=t_off)
cap = cv2.VideoCapture(video)
t_ini = inicio_min * 60.0
cap.set(cv2.CAP_PROP_POS_MSEC, t_ini * 1000)
monitor.reiniciar(t_ini)

idx = int(round(t_ini * fps_video))
wall0, ultimo_t = time.time(), t_ini
while cap.isOpened() and st.session_state.get("rodando"):
    ok = cap.grab()
    if not ok:
        break
    idx += 1
    if idx % pular:
        continue
    ok, frame = cap.retrieve()
    if not ok:
        break
    t = idx / fps_video

    if tempo_real:  # espera para acompanhar o relogio do video
        atraso = (t - t_ini) - (time.time() - wall0)
        if atraso > 0:
            time.sleep(atraso)

    t_proc = time.time()
    anotado, caixas = monitor.processar(frame, t)
    ms = (time.time() - t_proc) * 1000
    r = monitor.resumo(t)
    rgb = cv2.cvtColor(anotado, cv2.COLOR_BGR2RGB)

    eventos = [{"Horário": (inicio_rel + timedelta(seconds=e["t"])).strftime("%H:%M:%S"),
                "Mesa": e["mesa"], "Novo estado": e["evento"],
                "Duração anterior": fmt_tempo(e["duracao_anterior"])}
               for e in reversed(monitor.eventos[-12:])]

    ph_header.markdown(html_header(inicio_rel + timedelta(seconds=t)), unsafe_allow_html=True)
    ph_kpis.markdown(html_kpis(r), unsafe_allow_html=True)
    ph_video.image(rgb, channels="RGB", width="stretch")
    ph_vcap.markdown(
        f'<div class="vid-cap">Vídeo {fmt_tempo(t)} / {fmt_tempo(duracao)} · '
        f'{len(caixas)} pessoa(s) detectada(s) · inferência {ms:.0f} ms</div>', unsafe_allow_html=True)
    if eventos:
        ph_eventos.dataframe(pd.DataFrame(eventos), hide_index=True, width="stretch")
    else:
        ph_eventos.caption("Nenhuma mudança confirmada ainda.")
    ph_cards.markdown(html_cards(r), unsafe_allow_html=True)
    st.session_state.ultimo = {"resumo": r, "frame": rgb, "eventos": eventos}

cap.release()
st.session_state.rodando = False
