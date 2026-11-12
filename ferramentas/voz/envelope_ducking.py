# Calcula a automação de "ducking": a música abaixa enquanto há fala e sobe nas pausas e no fim.
# Detecta fala por RMS em janelas de 50 ms (limiar relativo ao pico), junta lacunas curtas (< min_pausa)
# e gera pontos (segundos, dB) com rampas de descida/subida.
# Uso (env qwen): python envelope_ducking.py --voz parte.wav [--sob -9 --pausa -2 --min_pausa 0.7] → JSON na saída padrão
import argparse, json
import numpy as np
from comum import ler_wav

ap = argparse.ArgumentParser()
ap.add_argument("--voz", required=True)
ap.add_argument("--sob", type=float, default=-9.0, help="dB da música durante a fala")
ap.add_argument("--pausa", type=float, default=-2.0, help="dB da música nas pausas longas")
ap.add_argument("--min_pausa", type=float, default=0.7, help="pausas menores que isso não sobem a música (s)")
ap.add_argument("--rampa_desce", type=float, default=0.25)
ap.add_argument("--rampa_sobe", type=float, default=0.6)
a = ap.parse_args()

x, sr = ler_wav(a.voz)
q = int(0.05 * sr)
n = len(x) // q
rms = np.sqrt((x[: n * q].reshape(n, q) ** 2).mean(axis=1)) + 1e-9
fala = 20 * np.log10(rms / rms.max()) > -38

# segmentos de fala, juntando lacunas menores que min_pausa
segs, ini = [], None
for i, f in enumerate(fala):
    if f and ini is None:
        ini = i
    if not f and ini is not None:
        segs.append([ini * 0.05, i * 0.05]); ini = None
if ini is not None:
    segs.append([ini * 0.05, n * 0.05])
juntos = []
for s in segs:
    if juntos and s[0] - juntos[-1][1] < a.min_pausa:
        juntos[-1][1] = s[1]
    else:
        juntos.append(s)

pts = [(0.0, a.sob)]          # a voz entra logo no começo
for s, e in juntos:
    pts += [(max(0.0, s - a.rampa_desce), None), (s, a.sob), (e, a.sob)]
    pts.append((e + a.rampa_sobe, a.pausa))
# preenche os "None" (início da rampa de descida) com o valor anterior, para a rampa sair do patamar
saida, ult = [], a.pausa
for t, v in sorted(pts, key=lambda p: p[0]):
    v = ult if v is None else v
    if saida and abs(saida[-1][0] - t) < 1e-3:
        saida[-1] = (t, v)
    else:
        saida.append((round(t, 3), v))
    ult = v
print(json.dumps({"duracao_s": round(n * 0.05, 3), "segmentos_fala": len(juntos), "pontos": saida}))
