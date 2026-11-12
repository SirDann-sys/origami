# Acabamento de rosto (camada 2 das capas): FaceDetailer + WAI Illustrious SDXL sobre a
# imagem do Klein, com as TAGS da ficha de cada personagem. Sem IP-Adapter: nesta placa ele quebra o rosto (fica rosa,
# com manchas). Não mexe em mãos (o acabamento de mão piorou: mãos ossudas).
# Genérico por obra: as tags vêm do guia de arte da obra → "tags_rosto": {personagem: "1girl, ..."}.
# Uso (env qwen): python acabamento_rosto.py --entrada IMG --saida IMG --guia guia_arte.json --personagens ana,bruno [--semente 7]
#   os rostos detectados são casados da esquerda para a direita com a lista de personagens
import argparse, json, shutil, sys, time, uuid
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from caminhos import COMFY, COMFY_DIR

INPUT, OUTPUT = COMFY_DIR / "input", COMFY_DIR / "output"
QUALIDADE = "masterpiece, best quality, amazing quality, very aesthetic, korean webtoon manhwa style, clean lineart, soft shading, beautiful detailed eyes"
NEGATIVO = "lowres, worst quality, low quality, bad anatomy, deformed face, asymmetrical eyes, extra eyes, blurry, sketch, text, watermark, 3d, realistic"
LIMITE_S = 900


def subir(p):
    nome = f"acab_{uuid.uuid4().hex[:8]}_{Path(p).name}"
    shutil.copyfile(p, INPUT / nome)
    return nome


def fluxo(img_nome, tags, semente, denoise=0.45):
    wf = {
        "1": {"class_type": "LoadImage", "inputs": {"image": img_nome}},
        "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "waiIllustriousSDXL_v170.safetensors"}},
        "3": {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": "bbox/face_yolov8m.pt"}},
        "4": {"class_type": "BboxDetectorSEGS", "inputs": {"bbox_detector": ["3", 0], "image": ["1", 0], "threshold": 0.45,
                                                          "dilation": 10, "crop_factor": 3.0, "drop_size": 24, "labels": "all"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": NEGATIVO}},
    }
    img = ["1", 0]
    for i, t in enumerate(tags):
        b = 100 + i * 10
        wf[str(b + 2)] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1], "text": f"{QUALIDADE}, {t}"}}
        wf[str(b + 3)] = {"class_type": "ImpactSEGSOrderedFilter", "inputs": {"segs": ["4", 0], "target": "x1", "order": False,
                          "take_start": i, "take_count": 1}}
        wf[str(b + 4)] = {"class_type": "DetailerForEach", "inputs": {"image": img, "segs": [str(b + 3), 0], "model": ["2", 0],
                          "clip": ["2", 1], "vae": ["2", 2], "guide_size": 768, "guide_size_for": True, "max_size": 1024, "seed": semente + i,
                          "steps": 28, "cfg": 6.0, "sampler_name": "euler_ancestral", "scheduler": "simple", "positive": [str(b + 2), 0],
                          "negative": ["6", 0], "denoise": denoise, "feather": 10, "noise_mask": True, "force_inpaint": True,
                          "wildcard": "", "cycle": 1}}
        img = [str(b + 4), 0]
    wf["900"] = {"class_type": "SaveImage", "inputs": {"images": img, "filename_prefix": "acabamento"}}
    return wf


def rodar(wf, destino):
    r = requests.post(COMFY + "/prompt", json={"prompt": wf}, timeout=60).json()
    if "prompt_id" not in r:
        raise SystemExit(f"ComfyUI recusou: {json.dumps(r)[:800]}")
    pid, t0 = r["prompt_id"], time.time()
    while time.time() - t0 < LIMITE_S:
        h = requests.get(f"{COMFY}/history/{pid}", timeout=30).json()
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise SystemExit(f"erro no ComfyUI: {json.dumps(st)[:1200]}")
            for no in h[pid]["outputs"].values():
                for im in no.get("images", []):
                    shutil.copyfile(OUTPUT / im.get("subfolder", "") / im["filename"], destino)
                    return
        time.sleep(1)
    requests.post(COMFY + "/interrupt", timeout=10)
    raise SystemExit("o acabamento de rosto não terminou em 15 min")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", required=True)
    ap.add_argument("--saida", required=True)
    ap.add_argument("--guia", required=True)
    ap.add_argument("--personagens", required=True, help="ids da esquerda para a direita, separados por vírgula")
    ap.add_argument("--semente", type=int, default=7)
    a = ap.parse_args()
    guia = json.loads(Path(a.guia).read_text(encoding="utf-8"))
    ids = [p for p in a.personagens.split(",") if p]
    sem = [p for p in ids if not guia.get("tags_rosto", {}).get(p)]
    if not ids or sem:
        raise SystemExit(f"sem tags de rosto no guia de arte para: {', '.join(sem) or '(ninguém)'} (guia_arte.json → tags_rosto)")
    t0 = time.time()
    rodar(fluxo(subir(a.entrada), [guia["tags_rosto"][p] for p in ids], a.semente), a.saida)
    print(f"ok {Path(a.saida).name} ({time.time() - t0:.0f} s)")
