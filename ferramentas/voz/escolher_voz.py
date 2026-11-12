# Fixa a candidata escolhida pelo autor como a referência oficial da voz.
# Uso: python escolher_voz.py --id ana_alto_frio --candidata 2
import argparse, shutil
from comum import BANCO, ler_json, gravar_json

ap = argparse.ArgumentParser()
ap.add_argument("--id", required=True)
ap.add_argument("--candidata", type=int, required=True)
a = ap.parse_args()

pasta = BANCO / a.id
shutil.copyfile(pasta / "candidatas" / f"c{a.candidata}.wav", pasta / "ref.wav")
info = ler_json(pasta / "voz.json")
info.update(escolhida=a.candidata, status="pronta")
gravar_json(pasta / "voz.json", info)
print("ok", pasta / "ref.wav")
