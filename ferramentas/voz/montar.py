# Escolhe a melhor versão de cada fala pelas métricas da conferência e cola o roteiro inteiro.
# Nota (menor = melhor) = 3·erro_leitura + 2·(1 − timbre) + penalidades (clipping, silêncio longo, ritmo fora do natural).
# Fala reprovada (erro > LIMITE_ERRO ou timbre < LIMITE_TIMBRE em todas as versões) vai para "revisar" no resumo.
# Uso: python montar.py --roteiro R.json --gravacao DIR --saida arquivo.wav
import argparse
from pathlib import Path
from comum import ler_json, gravar_json, ler_wav, gravar_wav, aparar_silencio, normalizar_pico
import numpy as np

LIMITE_ERRO, LIMITE_TIMBRE = 0.15, 0.75

ap = argparse.ArgumentParser()
ap.add_argument("--roteiro", required=True)
ap.add_argument("--gravacao", required=True)
ap.add_argument("--saida", required=True)
ap.add_argument("--pausa", type=float, default=0.45, help="pausa padrão entre falas (s); fala['pausa'] tem prioridade")
a = ap.parse_args()

roteiro = ler_json(a.roteiro)
d = Path(a.gravacao)
grav, conf = ler_json(d / "gravacao.json"), ler_json(d / "conferencia.json")


def nota(c):
    n = 3 * c.get("erro_leitura", 1) + 2 * (1 - c.get("timbre", 0))
    n += 5 * c.get("clipping", 0)
    n += 0.3 * max(0, c.get("maior_silencio_s", 0) - 1.0)
    r = c.get("ritmo", 2.6)
    n += 0.2 * max(0, 1.8 - r, r - 3.6)
    return n


pedacos, sr_final, resumo = [], None, {"escolhas": {}, "revisar": []}
for fala in roteiro["falas"]:
    versoes = grav["falas"][fala["id"]]["versoes"]
    avaliadas = sorted(((nota(conf[Path(v["arquivo"]).name]), v) for v in versoes), key=lambda t: t[0])
    n, melhor = avaliadas[0]
    c = conf[Path(melhor["arquivo"]).name]
    ok = c.get("erro_leitura", 1) <= LIMITE_ERRO and c.get("timbre", 0) >= LIMITE_TIMBRE
    resumo["escolhas"][fala["id"]] = {"arquivo": Path(melhor["arquivo"]).name, "nota": round(n, 3), **c}
    if not ok:
        resumo["revisar"].append(fala["id"])
    x, sr = ler_wav(melhor["arquivo"])
    sr_final = sr_final or sr
    pedacos.append(aparar_silencio(x, sr))
    pedacos.append(np.zeros(int(float(fala.get("pausa", a.pausa)) * sr), dtype="float32"))

audio = normalizar_pico(np.concatenate(pedacos[:-1]), -1.0)
gravar_wav(a.saida, audio, sr_final)
v = list(resumo["escolhas"].values())
resumo["media_erro_leitura"] = round(float(np.mean([e["erro_leitura"] for e in v])), 3)
resumo["media_timbre"] = round(float(np.mean([e["timbre"] for e in v])), 3)
resumo["duracao_s"] = round(len(audio) / sr_final, 1)
resumo["rtf"], resumo["tempo_gpu_s"] = grav.get("rtf"), grav.get("tempo_total_s")
gravar_json(d / "escolhas.json", resumo)
print(f"ok {a.saida} | {resumo['duracao_s']} s | erro {resumo['media_erro_leitura']} | timbre {resumo['media_timbre']} | revisar {resumo['revisar']}")
