# Tempos de cada fala e de cada palavra dentro das partes de um episódio, para as legendas e a troca de retratos.
# As falas são coladas pelo gravar_roteiro (fase montar) como [fala, pausa, fala, pausa…]; aqui refazemos a mesma
# conta a partir dos arquivos, então o resultado bate com o áudio da parte ao milissegundo.
# Palavras: Whisper (timestamps por palavra) na fala, alinhado ao TEXTO DO ROTEIRO (a legenda mostra a grafia do
# autor, não a do Whisper); palavras sem par recebem tempo interpolado.
# Uso (env qwen): python tempos.py --roteiro ep01.json --falas DIR --saida tempos_ep01.json [--partes 3 5]
#   --partes: refaz só essas partes e mantém as outras do arquivo de saída (propagação incremental do Origami)
import argparse, difflib, json, re
from pathlib import Path
import numpy as np, torch, librosa, soundfile as sf
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "voz"))
from comum import MODELOS, ler_json, normalizar_texto

ap = argparse.ArgumentParser()
ap.add_argument("--roteiro", required=True)
ap.add_argument("--falas", required=True)
ap.add_argument("--saida", required=True)
ap.add_argument("--partes", type=int, nargs="*", default=None)
a = ap.parse_args()

from transformers import pipeline
asr = pipeline("automatic-speech-recognition", model=str(MODELOS / "whisper-large-v3-turbo"), dtype=torch.float16, device="cuda:0")
roteiro = ler_json(a.roteiro)


def limpar(t):
    return re.sub(r"\[[^\]]*\]", "", t).strip()      # tira [sigh], [pause] etc.


def palavras_asr(y16, off=0.0):
    if len(y16) < 1600:
        return []
    o = asr({"raw": y16, "sampling_rate": 16000}, return_timestamps="word", generate_kwargs={"language": "portuguese"})
    out = []
    for c in o["chunks"]:
        w, (i, f) = c["text"].strip(), c["timestamp"]
        f = f if f is not None else i + 0.3
        est = 0.6 + 0.09 * len(w)        # palavra "esticada" por segundos: o começo dela é falso, não o fim
        if f - i > est:
            i = f - est
        out.append((w, off + i, off + f))
    return out


def casar(norm_r, idx, wpal, tempos):
    """Alinha as palavras do roteiro (só os índices idx ainda sem tempo) às do Whisper, herdando os tempos."""
    norm_w = [(normalizar_texto(w[0]) or [""])[0] for w in wpal]
    sm = difflib.SequenceMatcher(a=norm_r, b=norm_w, autojunk=False)
    for bl in sm.get_matching_blocks():
        for k in range(bl.size):
            _, ini, fim = wpal[bl.b + k]
            if tempos[idx[bl.a + k]] is None:
                tempos[idx[bl.a + k]] = [ini, fim]


def buracos(tempos, dur):
    """Sequências de palavras sem tempo: (k0, k1, t0, t1) com o intervalo livre entre as vizinhas conhecidas."""
    out, k = [], 0
    while k < len(tempos):
        if tempos[k] is not None:
            k += 1; continue
        k0 = k
        while k < len(tempos) and tempos[k] is None:
            k += 1
        t0 = tempos[k0 - 1][1] if k0 > 0 else 0.0
        t1 = tempos[k][0] if k < len(tempos) else dur
        out.append((k0, k, t0, max(t0, t1)))
    return out


def interpolar(palavras, tempos, dur):
    """O que ainda ficou sem par divide o intervalo livre proporcionalmente ao tamanho das palavras."""
    for k0, k1, t0, t1 in buracos(tempos, dur):
        pesos = [len(palavras[k]) + 1 for k in range(k0, k1)]
        t = t0
        for k, w in zip(range(k0, k1), pesos):
            d = (t1 - t0) * w / sum(pesos)
            tempos[k] = [t, t + d]; t += d


saida = {"partes": {}}
if a.partes and Path(a.saida).exists():
    saida = json.loads(Path(a.saida).read_text(encoding="utf-8"))
for parte in roteiro["partes"]:
    p = parte["parte"]; t = 0.0; falas = []
    if a.partes and p not in a.partes:
        continue
    for i, fala in enumerate(parte["falas"], 1):
        arq = Path(a.falas) / f"{p:02d}_{i:02d}.wav"
        y, sr = sf.read(str(arq), dtype="float32")
        if y.ndim == 2:
            y = y.mean(axis=1)
        dur = len(y) / sr
        y16 = librosa.resample(y, orig_sr=sr, target_sr=16000)
        texto = limpar(fala["texto"])
        palavras = texto.split()
        norm_r = [(normalizar_texto(w) or [""])[0] for w in palavras]
        tempos = [None] * len(palavras)
        casar(norm_r, list(range(len(palavras))), palavras_asr(y16), tempos)
        # o Whisper às vezes "come" o começo de uma fala e a legenda trava. Trecho grande sem par → reconhece de novo só aquele pedaço do áudio.
        for k0, k1, t0, t1 in buracos(tempos, dur):
            if k1 - k0 >= 2 and t1 - t0 > 0.8:
                casar([norm_r[k] for k in range(k0, k1)], list(range(k0, k1)),
                      palavras_asr(y16[int(t0 * 16000):int(t1 * 16000)], t0), tempos)
        interpolar(palavras, tempos, dur)
        falas.append({"fala": i, "voz": fala["voz"], "texto": texto, "inicio": round(t, 3), "fim": round(t + dur, 3),
                      "palavras": [{"p": w, "i": round(t + tt[0], 3), "f": round(t + tt[1], 3)} for w, tt in zip(palavras, tempos)]})
        t += dur + float(fala.get("pausa", 0.45))
    saida["partes"][str(p)] = falas
    print(f"parte {p}: {len(falas)} falas, {t:.1f} s", flush=True)
saida["partes"] = dict(sorted(saida["partes"].items(), key=lambda kv: int(kv[0])))
Path(a.saida).write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
