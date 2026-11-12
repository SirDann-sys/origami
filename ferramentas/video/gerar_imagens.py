# Gera as imagens do vídeo (fundos e retratos) no ComfyUI local, com os workflows testados do Estúdio
# (Klein 4B GGUF; 4 passos; VAEDecodeTiled por causa dos 6 GB) e amplia com 4x-AnimeSharp.
# Cada imagem é gerada UMA vez (o autor pediu "sem inventar moda"); N sementes só na triagem.
# Uso (env qwen): python gerar_imagens.py --lista assets.json --saida DIR [--so id1 id2] [--sementes 2]
import argparse, json, shutil, sys, time, uuid
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from caminhos import COMFY              # porta do config.json
LIMITE_S = 900                          # uma imagem que não sai em 15 min não vai sair
COMFY_INPUT = Path(__file__).resolve().parents[2] / "comfyui" / "input"
COMFY_OUTPUT = Path(__file__).resolve().parents[2] / "comfyui" / "output"
FORMATOS = {"largo": (1216, 832), "alto": (832, 1216), "quadrado": (1024, 1024), "panorama": (1344, 768)}

ap = argparse.ArgumentParser()
ap.add_argument("--lista", required=True)
ap.add_argument("--saida", required=True)
ap.add_argument("--so", nargs="*", default=None)
ap.add_argument("--sementes", type=int, default=2)
ap.add_argument("--ampliar", action="store_true", help="passa a escolhida pelo 4x-AnimeSharp")
a = ap.parse_args()


def klein(prompt, seed, formato, prefixo, refs=()):
    w, h = FORMATOS[formato]
    wf = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "flux-2-klein-4b-Q4_K_M.gguf"}},
        "2": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": "Qwen3-4B-Q4_K_M.gguf", "type": "flux2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "9": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["7", 0]}},
        "10": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
    }
    cond = ["7", 0]
    mp = 0.6 if len(refs) > 2 else 1.0
    for i, ref in enumerate(list(refs)[:3]):
        b = 20 + i * 10
        nome = f"vid_{uuid.uuid4().hex[:8]}_{Path(ref).name}"
        shutil.copyfile(ref, COMFY_INPUT / nome)
        wf[str(b)] = {"class_type": "LoadImage", "inputs": {"image": nome}}
        wf[str(b + 1)] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": [str(b), 0], "upscale_method": "lanczos", "megapixels": mp, "resolution_steps": 16}}
        wf[str(b + 2)] = {"class_type": "VAEEncode", "inputs": {"pixels": [str(b + 1), 0], "vae": ["3", 0]}}
        wf[str(b + 3)] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": cond, "latent": [str(b + 2), 0]}}
        cond = [str(b + 3), 0]
    wf["11"] = {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": cond, "negative": ["9", 0], "latent_image": ["10", 0],
                "seed": int(seed), "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}}
    wf["12"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["11", 0], "vae": ["3", 0], "tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}}
    wf["13"] = {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": prefixo}}
    return wf


def ampliar(imagem, prefixo):
    nome = f"vid_{uuid.uuid4().hex[:8]}_{Path(imagem).name}"
    shutil.copyfile(imagem, COMFY_INPUT / nome)
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": nome}},
        "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "4x-AnimeSharp.safetensors"}},
        "3": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
        "4": {"class_type": "ImageScale", "inputs": {"image": ["3", 0], "upscale_method": "lanczos", "width": 2432, "height": 0, "crop": "disabled"}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 0], "filename_prefix": prefixo}},
    }


def rodar(wf, destino):
    pid = requests.post(f"{COMFY}/prompt", json={"prompt": wf, "client_id": "video"}, timeout=60).json()["prompt_id"]
    t0 = time.time()
    while True:
        if time.time() - t0 > LIMITE_S:
            requests.post(f"{COMFY}/interrupt", timeout=10)
            raise RuntimeError(f"o ComfyUI não terminou a imagem em {LIMITE_S // 60} min (interrompida)")
        h = requests.get(f"{COMFY}/history/{pid}", timeout=30).json()
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise RuntimeError(json.dumps(st)[:500])
            for no in h[pid]["outputs"].values():
                for img in no.get("images", []):
                    origem = COMFY_OUTPUT / img.get("subfolder", "") / img["filename"]
                    Path(destino).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(origem, destino)
                    return destino
        time.sleep(1.5)


lista = json.loads(Path(a.lista).read_text(encoding="utf-8"))
saida = Path(a.saida)
estilo = lista["estilo"]
for item in lista["itens"]:
    if a.ampliar or (a.so and item["id"] not in a.so):
        continue
    prompt = f"{item['prompt']}. {estilo}"
    for s in range(a.sementes):
        seed = item.get("seed", 100) + s
        destino = saida / "candidatas" / f"{item['id']}_s{seed}.png"
        t0 = time.time()
        rodar(klein(prompt, seed, item.get("formato", "largo"), f"vid_{item['id']}", item.get("refs", [])), destino)
        print(f"{item['id']} s{seed}: {time.time() - t0:.0f} s", flush=True)
if a.ampliar:
    for item in lista["itens"]:
        if a.so and item["id"] not in a.so or not item.get("escolhida"):
            continue
        rodar(ampliar(saida / "candidatas" / item["escolhida"], f"vid_{item['id']}_4x"), saida / f"{item['id']}.png")
        print("ampliada", item["id"], flush=True)
