# Conferência automática de uma imagem gerada, SEM IA (rápida e de graça), antes da triagem do Opus.
# Pega os defeitos mais comuns das candidatas:
#   faixa      → faixa ou retângulo preto chapado (defeito do VAE tiled do Klein; ~1 em 8 imagens)
#   vazia      → imagem quase lisa (sem conteúdo)
#   estourada  → branco demais (luz estourada)
#   topo       → só para capas (formato alto): a metade de cima precisa ser escura o bastante para o véu e o título
# Uso (env qwen): python conferir_imagem.py IMG [IMG...] [--capa]  → uma linha JSON por imagem
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image

LIMITE_PRETO = 1            # o defeito do VAE é preto ABSOLUTO (0–1); sombra de verdade tem textura (2–40)
AREA_FAIXA = 0.008          # retângulo preto ≥ 0,8% da imagem já é defeito
RETANGULAR = 0.90           # quanto da caixa o pedaço preto preenche (o defeito é um retângulo reto)
TOPO_MAX = 0.42             # luminância média (0–1) máxima dos 40% de cima numa capa
TOPO_FRACAO = 0.40


def _lum(a):
    return (0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]) / 255.0


def conferir(caminho, capa=False):
    """{"ok": bool, "problemas": [...], "medidas": {...}}. Os problemas são frases para o autor e para o Opus."""
    im = Image.open(caminho).convert("RGB")
    if max(im.size) > 1400:                       # mede numa cópia reduzida (rápido; o defeito é grande)
        im.thumbnail((1400, 1400))
    a = np.asarray(im).astype(np.int16)
    h, w = a.shape[:2]
    lum = _lum(a)
    probs, med = [], {}

    preto = a.max(axis=2) <= LIMITE_PRETO
    from scipy import ndimage
    rot, n = ndimage.label(preto)
    pior = 0.0
    if n:
        areas = ndimage.sum(preto, rot, index=np.arange(1, n + 1))
        for i in np.argsort(areas)[::-1][:5]:
            area = areas[i] / (h * w)
            if area < AREA_FAIXA:
                break
            sl = ndimage.find_objects(rot == i + 1)[0]
            caixa = (sl[0].stop - sl[0].start) * (sl[1].stop - sl[1].start)
            # céu/teto preto de propósito (topo escuro da capa) encosta em 3 ou 4 bordas; o defeito é um ladrilho
            bordas = (sl[0].start == 0) + (sl[0].stop == h) + (sl[1].start == 0) + (sl[1].stop == w)
            if areas[i] / caixa >= RETANGULAR and bordas < 3:
                pior = max(pior, area)
    med["faixa_preta"] = round(pior, 4)
    if pior:
        probs.append(f"faixa/retângulo preto chapado ({pior:.1%} da imagem): defeito de geração")

    med["desvio"] = round(float(lum.std()), 3)
    if lum.std() < 0.035:
        probs.append("imagem quase lisa, sem conteúdo")
    estour = float((lum > 0.97).mean())
    med["estourado"] = round(estour, 3)
    if estour > 0.25:
        probs.append(f"luz estourada ({estour:.0%} quase branco)")
    if capa:
        topo = float(lum[: int(h * TOPO_FRACAO)].mean())
        med["topo"] = round(topo, 3)
        if topo > TOPO_MAX:
            probs.append(f"topo claro demais para o título (luminância {topo:.2f} > {TOPO_MAX})")
    return {"ok": not probs, "problemas": probs, "medidas": med}


if __name__ == "__main__":
    capa = "--capa" in sys.argv
    for p in [x for x in sys.argv[1:] if not x.startswith("--")]:
        print(json.dumps({"imagem": str(Path(p)), **conferir(p, capa)}, ensure_ascii=False), flush=True)
