# Conferência objetiva de uma gravação: o Whisper retranscreve cada versão e mede o erro de leitura.
# Também mede clipping, silêncio interno longo e duração fora do esperado (sinal de loop ou palavra engolida).
# Uso (env qwen): python conferir.py --gravacao DIR [DIR ...]
import argparse
from pathlib import Path
from comum import MODELOS, ler_json, gravar_json, ler_wav, wer, carregar_pronuncia, aplicar_pronuncia
import numpy as np
import torch, librosa

ap = argparse.ArgumentParser()
ap.add_argument("--gravacao", nargs="+", required=True)
ap.add_argument("--roteiro", required=True, help="para saber os nomes próprios (pronúncia) que o Whisper pode grafar diferente")
a = ap.parse_args()

from transformers import pipeline
asr = pipeline("automatic-speech-recognition", model=str(MODELOS / "whisper-large-v3-turbo"),
               dtype=torch.float16, device="cuda:0")
roteiro = ler_json(a.roteiro)
pron = carregar_pronuncia(roteiro)
nomes = list(pron.keys()) + list(pron.values())
original = {f["id"]: f["texto"] for f in roteiro["falas"]}


def maior_silencio(x, sr, limiar_db=-40):
    quadro = int(0.02 * sr)
    n = len(x) // quadro
    if n == 0:
        return 0.0
    rms = np.sqrt((x[: n * quadro].reshape(n, quadro) ** 2).mean(axis=1))
    mudo = rms < (10 ** (limiar_db / 20)) * (rms.max() or 1)
    nz = np.where(~mudo)[0]
    if len(nz) < 2:
        return 0.0
    mudo = mudo[nz[0]: nz[-1]]          # só silêncios internos
    melhor = atual = 0
    for m in mudo:
        atual = atual + 1 if m else 0
        melhor = max(melhor, atual)
    return melhor * 0.02


for d in a.gravacao:
    d = Path(d)
    grav = ler_json(d / "gravacao.json")
    conf = ler_json(d / "conferencia.json") if (d / "conferencia.json").exists() else {}
    for fid, f in grav["falas"].items():
        palavras = len(original[fid].split())
        for v in f["versoes"]:
            x, sr = ler_wav(v["arquivo"])
            x16 = librosa.resample(x, orig_sr=sr, target_sr=16000)
            txt = asr({"raw": x16, "sampling_rate": 16000},
                      generate_kwargs={"language": "portuguese", "task": "transcribe"})["text"].strip()
            c = conf.setdefault(Path(v["arquivo"]).name, {})
            c.update(
                fala=fid,
                transcricao=txt,
                # o mesmo dicionário nos dois lados: "Dra." escrito pelo Whisper conta igual a "Doutora" falado
                erro_leitura=round(wer(aplicar_pronuncia(original[fid], pron), aplicar_pronuncia(txt, pron), ignorar=nomes), 3),
                clipping=round(float((np.abs(x) > 0.999).mean()), 5),
                maior_silencio_s=round(maior_silencio(x, sr), 2),
                ritmo=round(palavras / max(v["duracao"], 0.1), 2),   # palavras/s; fala natural ≈ 2–3,3
            )
            print(f"{d.name} {Path(v['arquivo']).name}: erro {c['erro_leitura']:.2f} | {txt[:70]}", flush=True)
    gravar_json(d / "conferencia.json", conf)
print("ok")
