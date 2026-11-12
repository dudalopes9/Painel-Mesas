# TableVision AI

Sistema de visão computacional em Python que analisa o vídeo da câmera de segurança de um
restaurante e indica, em tempo real, quais mesas estão **ocupadas** e quais estão **disponíveis**,
exibindo tudo em um dashboard web.

Tecnologias: **Python 3.12 · OpenCV · YOLO11 (Ultralytics, pré-treinado no COCO) · NumPy · Pandas · Streamlit**

## Como executar

```powershell
# 1. (uma vez) criar o ambiente e instalar as dependências
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# 2. abrir o dashboard
.\.venv\Scripts\python -m streamlit run app.py
```

O navegador abre em `http://localhost:8501`. Clique em **▶ Iniciar** na barra lateral.
O vídeo de entrada fica em `data/restaurante.mp4` (cópia do vídeo original da câmera, 640x368, 30 fps, 62 min).
O modelo `yolo11n.pt` é baixado automaticamente na primeira execução.

### Controles da barra lateral
| Controle | Função |
|---|---|
| Começar no minuto | Pula para um trecho do vídeo |
| Analisar 1 a cada N frames | 10 = ~3 análises por segundo de vídeo (bom para CPU) |
| Sincronizar com o tempo real | Desligado = processa o mais rápido possível |
| Modelo YOLO | `yolo11n` (rápido) ou `yolo11s` (mais preciso, mais lento) |
| Confirmação temporal | Segundos necessários para confirmar OCUPADA / DISPONÍVEL |

## Como funciona

1. **Leitura do vídeo** – `cv2.VideoCapture` lê os frames; apenas 1 a cada N é analisado.
2. **Detecção de pessoas** – YOLO11 detecta somente a classe `person` (COCO id 0).
   Caixas cortadas na borda superior (clientes em pé no balcão ao fundo) são descartadas.
3. **Regiões das mesas** – cada mesa é um polígono (mesa + cadeiras) definido em
   `config/mesas.json`, desenhado a partir de frames do próprio vídeo (`config/preview_mesas.jpg`).
4. **Atribuição** – cada pessoa vira um ponto de ancoragem (região do quadril, 65% da altura da caixa)
   e é atribuída à mesa cujo polígono contém o ponto (`cv2.pointPolygonTest`, tolerância de 12 px).
5. **Confirmação temporal (histerese)** – cada mesa mantém um histórico de presença:
   * vira **OCUPADA** se houve pessoa em ≥ 60% das análises dos últimos 10 s;
   * volta a **DISPONÍVEL** se houve pessoa em ≤ 15% das análises dos últimos 20 s.

   Assim, pessoas passando pelo corredor ou garçons de passagem não alteram o status, e oclusões
   momentâneas de quem está sentado não liberam a mesa.
6. **Visualização** – polígonos verdes (disponível) / vermelhos (ocupada) e caixas das pessoas sobre o vídeo;
   o dashboard mostra total, ocupadas, disponíveis, taxa de ocupação, um card por mesa com
   temporizador ("Ocupada há" / "Livre há") e o histórico de mudanças de estado.

Os temporizadores e o relógio usam o **tempo do vídeo** (o relógio parte de 17:01:07, horário
mostrado pela câmera no primeiro frame), então os valores são consistentes mesmo se o processamento
for mais lento ou mais rápido que o tempo real.

## Reconfigurar as mesas

Se a câmera ou o vídeo mudarem, redesenhe os polígonos clicando sobre o frame:

```powershell
.\.venv\Scripts\python configurar_mesas.py --minuto 60
```

Clique nos vértices de uma mesa → **ENTER** fecha a mesa → repita → **S** salva (`Z` desfaz, `ESC` sai).
Para apenas gerar a imagem de conferência: `python configurar_mesas.py --preview`.

## Estrutura

```
app.py                 dashboard Streamlit (loop de processamento + interface)
detector.py            YOLO + atribuição pessoa→mesa + máquina de estados temporal
configurar_mesas.py    ferramenta de clique para definir os polígonos
config/mesas.json      polígonos das 14 mesas
config/preview_mesas.jpg  conferência visual dos polígonos
data/restaurante.mp4   vídeo de entrada
```

## Limitações conhecidas
* As 14 mesas são as visíveis nesta câmera; mesas parcialmente fora do quadro (04 e 14) têm menor precisão.
* Pessoas muito pequenas/ocluídas no fundo do salão podem não ser detectadas em todos os frames
  (a confirmação temporal compensa a maior parte disso; o modelo `yolo11s` melhora a detecção).
* Um garçom parado mais de ~10 s ao lado de uma mesa vazia pode marcá-la como ocupada.
