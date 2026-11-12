"""TableVision AI - deteccao de pessoas (YOLO) e classificacao de ocupacao das mesas.

Pipeline por frame:
  1. YOLO detecta pessoas (classe 0 do COCO).
  2. Cada pessoa gera um "ponto de ancoragem" (regiao do quadril/colo, onde o
     corpo encontra a cadeira) e e atribuida a no maximo uma mesa (poligono).
  3. Cada mesa guarda um historico temporal de presenca e so muda de estado
     depois de uma confirmacao temporal (histerese), evitando que pessoas
     passando ou garcons de passagem mudem o status.
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

VERDE = (80, 200, 120)     # BGR
VERMELHO = (60, 60, 230)
AZUL = (255, 170, 60)


@dataclass
class Mesa:
    id: int
    nome: str
    lugares: int
    poligono: np.ndarray
    ocupada: bool = False
    desde: float = 0.0                       # instante (s do video) da ultima mudanca
    historico: deque = field(default_factory=deque)  # (t, presenca 0/1)
    pessoas: int = 0                         # pessoas no frame atual

    def tempo_no_estado(self, t: float) -> float:
        return max(0.0, t - self.desde)


def carregar_mesas(caminho: str | Path) -> tuple[list[Mesa], tuple[int, int]]:
    cfg = json.loads(Path(caminho).read_text(encoding="utf-8"))
    mesas = [
        Mesa(m["id"], m["nome"], m.get("lugares", 4), np.array(m["poligono"], dtype=np.int32))
        for m in cfg["mesas"]
    ]
    return mesas, tuple(cfg.get("frame_size", (0, 0)))


class TableMonitor:
    """Processa frames e mantem o estado de cada mesa."""

    def __init__(
        self,
        config_path: str | Path = "config/mesas.json",
        modelo: str = "yolo11n.pt",
        conf: float = 0.35,
        imgsz: int = 960,
        t_confirma_ocupada: float = 10.0,
        t_confirma_livre: float = 20.0,
        limiar_ocupada: float = 0.6,
        limiar_livre: float = 0.15,
    ):
        self.mesas, self.frame_size = carregar_mesas(config_path)
        if isinstance(modelo, str):
            from ultralytics import YOLO  # import tardio: acelera o carregamento do Streamlit
            modelo = YOLO(modelo)
        self.modelo = modelo
        self.eventos: list[dict] = []   # historico de mudancas de estado
        self.conf = conf
        self.imgsz = imgsz
        self.t_on = t_confirma_ocupada
        self.t_off = t_confirma_livre
        self.lim_on = limiar_ocupada
        self.lim_off = limiar_livre
        self._escala = None

    # ------------------------------------------------------------------ util
    def _ajustar_escala(self, frame: np.ndarray):
        """Reescala os poligonos se o video tiver resolucao diferente da config."""
        h, w = frame.shape[:2]
        fw, fh = self.frame_size
        if self._escala is None:
            self._escala = (w / fw, h / fh) if fw and fh else (1.0, 1.0)
            if self._escala != (1.0, 1.0):
                sx, sy = self._escala
                for m in self.mesas:
                    m.poligono = (m.poligono * [sx, sy]).astype(np.int32)

    def detectar_pessoas(self, frame: np.ndarray) -> list[tuple[int, int, int, int, float]]:
        r = self.modelo.predict(frame, classes=[0], conf=self.conf, imgsz=self.imgsz, verbose=False)[0]
        caixas = []
        for (x1, y1, x2, y2), c in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()):
            # Caixas cortadas na borda superior = pessoas em pe no balcao do fundo
            # (nesta camera nenhuma mesa fica la). Nao contam para as mesas.
            if y1 <= 3:
                continue
            caixas.append((int(x1), int(y1), int(x2), int(y2), float(c)))
        return caixas

    @staticmethod
    def ancora(caixa) -> tuple[int, int]:
        """Ponto que representa onde a pessoa esta 'apoiada' (quadril/colo)."""
        x1, y1, x2, y2 = caixa[:4]
        return int((x1 + x2) / 2), int(y1 + 0.65 * (y2 - y1))

    def _mesa_da_pessoa(self, ponto, tolerancia: float = 12.0) -> Mesa | None:
        """Mesa cujo poligono contem o ponto (ou esta a ate `tolerancia` px dele)."""
        melhor, dist_melhor = None, -tolerancia
        for m in self.mesas:
            d = cv2.pointPolygonTest(m.poligono, ponto, True)  # >0 dentro, <0 fora
            if d >= dist_melhor:
                melhor, dist_melhor = m, d
        return melhor

    # -------------------------------------------------------------- processo
    def processar(self, frame: np.ndarray, t: float):
        """Processa um frame no instante t (segundos do video).

        Retorna (frame_anotado, caixas).
        """
        self._ajustar_escala(frame)
        caixas = self.detectar_pessoas(frame)

        for m in self.mesas:
            m.pessoas = 0
        atribuicoes = []
        for cx in caixas:
            p = self.ancora(cx)
            m = self._mesa_da_pessoa(p)
            if m is not None:
                m.pessoas += 1
            atribuicoes.append((cx, p, m))

        for m in self.mesas:
            self._atualizar_estado(m, t)

        return self.desenhar(frame, atribuicoes), caixas

    def _atualizar_estado(self, m: Mesa, t: float):
        m.historico.append((t, 1 if m.pessoas > 0 else 0))
        janela = max(self.t_on, self.t_off)
        while m.historico and t - m.historico[0][0] > janela:
            m.historico.popleft()

        def razao(seg):
            v = [p for (ti, p) in m.historico if t - ti <= seg]
            return sum(v) / len(v) if v else 0.0

        # Exige que a janela ja tenha dados suficientes antes de decidir
        cobertura = t - m.historico[0][0] if m.historico else 0.0
        novo = m.ocupada
        if not m.ocupada:
            if cobertura >= self.t_on * 0.9 and razao(self.t_on) >= self.lim_on:
                novo = True
        else:
            if cobertura >= self.t_off * 0.9 and razao(self.t_off) <= self.lim_off:
                novo = False
        if novo != m.ocupada:
            self.eventos.append({"t": t, "mesa": m.nome,
                                 "evento": "OCUPADA" if novo else "DISPONÍVEL",
                                 "duracao_anterior": t - m.desde})
            m.ocupada, m.desde = novo, t

    def reiniciar(self, t: float = 0.0):
        for m in self.mesas:
            m.ocupada, m.desde, m.pessoas = False, t, 0
            m.historico.clear()
        self.eventos.clear()

    # --------------------------------------------------------------- desenho
    def desenhar(self, frame: np.ndarray, atribuicoes) -> np.ndarray:
        out = frame.copy()
        overlay = frame.copy()
        for m in self.mesas:
            cor = VERMELHO if m.ocupada else VERDE
            cv2.fillPoly(overlay, [m.poligono], cor)
        out = cv2.addWeighted(overlay, 0.22, out, 0.78, 0)
        for m in self.mesas:
            cor = VERMELHO if m.ocupada else VERDE
            cv2.polylines(out, [m.poligono], True, cor, 2)
            x, y = m.poligono.min(axis=0)
            rot = f"{m.id:02d}"
            (tw, th), _ = cv2.getTextSize(rot, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(out, (x, y), (x + tw + 6, y + th + 6), cor, -1)
            cv2.putText(out, rot, (x + 3, y + th + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

        for (x1, y1, x2, y2, c), p, m in atribuicoes:
            cor = AZUL if m is None else (VERMELHO if m.ocupada else (0, 200, 255))
            cv2.rectangle(out, (x1, y1), (x2, y2), cor, 2)
            cv2.circle(out, p, 3, cor, -1)
            cv2.putText(out, f"pessoa {c:.2f}", (x1, max(10, y1 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, cor, 1, cv2.LINE_AA)
        return out

    # ---------------------------------------------------------------- resumo
    def resumo(self, t: float) -> dict:
        total = len(self.mesas)
        ocup = sum(m.ocupada for m in self.mesas)
        return {
            "total": total,
            "ocupadas": ocup,
            "disponiveis": total - ocup,
            "percentual": (100.0 * ocup / total) if total else 0.0,
            "mesas": [
                {
                    "id": m.id, "nome": m.nome, "lugares": m.lugares,
                    "ocupada": m.ocupada, "pessoas": m.pessoas,
                    "tempo": m.tempo_no_estado(t),
                }
                for m in self.mesas
            ],
        }


def fmt_tempo(seg: float) -> str:
    seg = int(seg)
    return f"{seg // 3600:02d}:{(seg % 3600) // 60:02d}:{seg % 60:02d}"
