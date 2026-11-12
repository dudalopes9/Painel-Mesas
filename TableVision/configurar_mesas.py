"""Ferramenta simples para (re)definir os poligonos das mesas clicando no video.

Uso:
    python configurar_mesas.py                 # frame do minuto 60 (salao quase vazio)
    python configurar_mesas.py --minuto 10
    python configurar_mesas.py --preview       # apenas salva config/preview_mesas.jpg

Controles na janela:
    clique esquerdo  adiciona um vertice ao poligono atual
    ENTER            fecha o poligono atual (vira a proxima mesa)
    Z                desfaz o ultimo vertice
    S                salva em config/mesas.json e sai
    ESC              sai sem salvar
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

BASE = Path(__file__).parent
CFG = BASE / "config" / "mesas.json"
ESCALA = 2  # janela ampliada para facilitar os cliques


def ler_frame(video, minuto):
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, minuto * 60_000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit("Nao foi possivel ler o video.")
    return frame


def desenhar(frame, mesas, atual):
    img = cv2.resize(frame, None, fx=ESCALA, fy=ESCALA)
    for m in mesas:
        pts = (np.array(m["poligono"]) * ESCALA).astype(np.int32)
        cv2.polylines(img, [pts], True, (80, 200, 120), 2)
        x, y = pts.min(axis=0)
        cv2.putText(img, m["nome"], (x + 4, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
    for i, p in enumerate(atual):
        q = (p[0] * ESCALA, p[1] * ESCALA)
        cv2.circle(img, q, 4, (0, 200, 255), -1)
        if i:
            a = (atual[i - 1][0] * ESCALA, atual[i - 1][1] * ESCALA)
            cv2.line(img, a, q, (0, 200, 255), 2)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(BASE / "data" / "restaurante.mp4"))
    ap.add_argument("--minuto", type=float, default=60)
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()

    frame = ler_frame(a.video, a.minuto)
    h, w = frame.shape[:2]

    if a.preview:
        cfg = json.loads(CFG.read_text(encoding="utf-8"))
        out = BASE / "config" / "preview_mesas.jpg"
        cv2.imwrite(str(out), desenhar(frame, cfg["mesas"], []))
        print("Preview salvo em", out)
        return

    mesas, atual = [], []

    def clique(ev, x, y, *_):
        if ev == cv2.EVENT_LBUTTONDOWN:
            atual.append((x // ESCALA, y // ESCALA))

    cv2.namedWindow("Configurar mesas")
    cv2.setMouseCallback("Configurar mesas", clique)
    while True:
        cv2.imshow("Configurar mesas", desenhar(frame, mesas, atual))
        k = cv2.waitKey(30) & 0xFF
        if k == 13 and len(atual) >= 3:          # ENTER
            n = len(mesas) + 1
            mesas.append({"id": n, "nome": f"Mesa {n:02d}", "lugares": 4,
                          "poligono": [list(map(int, p)) for p in atual]})
            atual.clear()
        elif k in (ord("z"), ord("Z")) and atual:
            atual.pop()
        elif k in (ord("s"), ord("S")):
            if mesas:
                CFG.write_text(json.dumps({"frame_size": [w, h], "mesas": mesas},
                                          ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"{len(mesas)} mesas salvas em {CFG}")
            break
        elif k == 27:
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
