# Semelhança de timbre de cada versão com a voz oficial (ref.wav do banco), via o VoiceEncoder do Chatterbox.
# 1,0 = mesma voz. Grava em conferencia.json e salva timbre.npy no banco (impressão digital da voz).
# Uso (env chatterbox): python timbre.py --gravacao DIR [DIR ...]
import argparse
from pathlib import Path
from comum import BANCO, MODELOS, ler_json, gravar_json, ler_wav
import numpy as np
import torch
from chatterbox.models.voice_encoder import VoiceEncoder

ap = argparse.ArgumentParser()
ap.add_argument("--gravacao", nargs="+", required=True)
a = ap.parse_args()

ve = VoiceEncoder()
ve.load_state_dict(torch.load(MODELOS / "chatterbox_mtl" / "ve.pt", weights_only=True))
ve.to("cuda").eval()
cache = {}


def impressao(id_voz):
    if id_voz not in cache:
        arq = BANCO / id_voz / "timbre.npy"
        if arq.exists():
            cache[id_voz] = np.load(arq)
        else:
            x, sr = ler_wav(BANCO / id_voz / "ref.wav")
            cache[id_voz] = ve.embeds_from_wavs([x], sample_rate=sr, as_spk=True)
            np.save(arq, cache[id_voz])
    return cache[id_voz]


for d in a.gravacao:
    d = Path(d)
    grav = ler_json(d / "gravacao.json")
    conf = ler_json(d / "conferencia.json") if (d / "conferencia.json").exists() else {}
    for fid, f in grav["falas"].items():
        alvo = impressao(f["voz"])
        for v in f["versoes"]:
            x, sr = ler_wav(v["arquivo"])
            e = ve.embeds_from_wavs([x], sample_rate=sr, as_spk=True)
            sim = float(VoiceEncoder.voice_similarity(e, alvo))
            conf.setdefault(Path(v["arquivo"]).name, {})["timbre"] = round(sim, 3)
            print(f"{d.name} {Path(v['arquivo']).name}: timbre {sim:.3f}", flush=True)
    gravar_json(d / "conferencia.json", conf)
print("ok")
