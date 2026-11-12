# Revisão de vídeo: assistir a parte, marcar o ponto com uma nota e ver as checagens automáticas.
#   marcas     → 06_video/epNN/marcas.json: {id, parte, t, nota, tipo (imagem | legenda | regra visual | tempo), estado}
#   checagens  → duração vídeo × áudio; legendas sobrepostas; bloco de legenda com uma palavra só
import re, time
import soundfile as sf
from .obra import Episodio, ler_json, gravar_json

RX_DIAL = re.compile(r"^Dialogue:\s*\d+,(\d+):(\d+):(\d+\.\d+),(\d+):(\d+):(\d+\.\d+),[^,]*,[^,]*,\d+,\d+,\d+,[^,]*,(.*)$")


def _seg(h, m, s):
    return int(h) * 3600 + int(m) * 60 + float(s)


def legendas(ass):
    out = []
    for l in ass.read_text(encoding="utf-8").splitlines():
        m = RX_DIAL.match(l)
        if m:
            txt = re.sub(r"\{[^}]*\}", "", m.group(7)).replace("\\N", " ").strip()
            out.append((_seg(*m.group(1, 2, 3)), _seg(*m.group(4, 5, 6)), txt))
    return out


def _dur_video(mp4):
    import cv2
    cap = cv2.VideoCapture(str(mp4))
    n, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS) or 30
    cap.release()
    return n / fps if n else None


def checagens(ep, n):
    res = []
    mp4, wav = ep.video_parte(n), ep.mix_wav(n)
    if not mp4.exists():
        return [{"ok": False, "nome": "vídeo", "msg": "a parte ainda não foi renderizada"}]
    dv, da = _dur_video(mp4), sf.info(str(wav)).duration if wav.exists() else None
    if dv and da:
        dif = dv - da
        res.append({"ok": abs(dif) < 0.15, "nome": "duração", "msg": f"vídeo {dv:.2f} s × áudio {da:.2f} s (diferença {dif:+.2f} s)"})
    ass = mp4.with_suffix(".ass")
    if not ass.exists():
        res.append({"ok": None, "nome": "legendas", "msg": "sem o arquivo de legendas (vídeo renderizado antes do app)"})
        return res
    leg = sorted(legendas(ass))
    # sobreposição: só conta entre blocos de texto diferentes (o karaokê repete o bloco a cada palavra)
    blocos = []
    for i, f, t in leg:
        if blocos and blocos[-1][2] == t and abs(blocos[-1][1] - i) < 0.02:
            blocos[-1] = (blocos[-1][0], f, t)
        else:
            blocos.append((i, f, t))
    tv = travadas(ep, n)
    res.append({"ok": not tv, "nome": "legenda travada", "msg": "nenhuma" if not tv else
                "falas " + ", ".join(k for _, k in tv) + ": refaça a legenda (marca tipo legenda)", "tempos": [t for t, _ in tv]})
    sobre = [(a, b) for a, b in zip(blocos, blocos[1:]) if b[0] < a[1] - 0.02 and b[2] != a[2]]
    res.append({"ok": not sobre, "nome": "legendas sobrepostas",
                "msg": "nenhuma" if not sobre else "; ".join(f"{a[0]:.1f}s \"{a[2][:30]}\" × \"{b[2][:30]}\"" for a, b in sobre[:4]),
                "tempos": [a[0] for a, _ in sobre]})
    # palavra sozinha só é problema quando é sobra da frase anterior; frase de uma palavra ("Papelada.") é intencional
    sozinhas = [(b[0], b[2]) for a, b in zip([(0, 0, ".")] + blocos, blocos)
                if len(b[2].split()) == 1 and a[2].rstrip()[-1:] not in ".?!"]
    res.append({"ok": not sozinhas, "nome": "palavra sozinha num bloco",
                "msg": "nenhuma" if not sozinhas else "; ".join(f"{i:.1f}s \"{t}\"" for i, t in sozinhas[:6]),
                "tempos": [i for i, _ in sozinhas]})
    return res


def _marcas_arq(ep):
    return ep.video_ep / "marcas.json"


RESPIRO_16x9 = 0.4      # episodio_16x9.sh segura o último quadro de cada parte por 0,4 s (o respiro do áudio)


def inicios_16x9(ep):
    """Onde cada parte começa dentro do 16:9 (s): duração da mix de cada parte + o respiro entre elas."""
    out, t = {}, 0.0
    for n in ep.partes():
        out[n] = t
        if ep.mix_wav(n).exists():
            t += sf.info(str(ep.mix_wav(n))).duration + RESPIRO_16x9
    return out


def local_16x9(ep, t):
    """Segundo do 16:9 → (parte, segundo dentro da parte)."""
    ini = inicios_16x9(ep)
    n = max((k for k, v in ini.items() if v <= t), default=1)
    return n, round(t - ini[n], 2)


def episodio_16x9(obra, ep_):
    """Aba 16:9 da revisão de vídeo. Marcas aqui ficam com parte 0 e o segundo do 16:9."""
    ep = Episodio(obra, ep_)
    mp4, wav = ep.video_16x9(), ep.episodio_wav()
    ch = []
    if not mp4.exists():
        ch.append({"ok": False, "nome": "vídeo", "msg": "o 16:9 ainda não foi renderizado"})
    else:
        dv, da = _dur_video(mp4), sf.info(str(wav)).duration if wav.exists() else None
        if dv and da:
            ch.append({"ok": abs(dv - da) < 0.5, "nome": "duração", "msg": f"vídeo {dv:.1f} s × áudio {da:.1f} s (diferença {dv - da:+.2f} s)"})
    ini = inicios_16x9(ep)
    tv = [(ini[n] + t, k) for n in ep.partes() for t, k in travadas(ep, n)]
    ch.append({"ok": not tv, "nome": "legenda travada", "msg": "nenhuma" if not tv else "falas " + ", ".join(k for _, k in tv),
               "tempos": [t for t, _ in tv]})
    ch.append({"ok": None, "nome": "partes", "msg": " · ".join(f"P{n} em {int(v // 60)}:{v % 60:04.1f}" for n, v in ini.items())})
    st = ep.cfg.get("episodios", {}).get(ep.ep, {})
    return {"obra": obra, "ep": ep.ep, "parte": 0, "partes": ep.partes(), "video": str(mp4), "existe": mp4.exists(),
            "checagens": ch, "marcas": [m for m in ler_json(_marcas_arq(ep), {"marcas": []})["marcas"] if m["parte"] == 0],
            "previa": [], "publicado": st.get("status") == "publicado", "horizontal": True}


def parte(obra, ep_, n):
    ep = Episodio(obra, ep_)
    if not ep.roteiro_arq.exists():
        raise RuntimeError(f"o Ep. {ep.ep} ainda não tem roteiro de áudio: comece pela Mesa e pelo Texto")
    n = int(n)
    if n == 0:
        return episodio_16x9(obra, ep_)
    marcas = [m for m in ler_json(_marcas_arq(ep), {"marcas": []})["marcas"] if m["parte"] == n]
    st = ep.cfg.get("episodios", {}).get(ep.ep, {})
    return {"obra": obra, "ep": ep.ep, "parte": n, "partes": ep.partes(), "video": str(ep.video_parte(n)),
            "existe": ep.video_parte(n).exists(), "checagens": checagens(ep, n), "marcas": marcas,
            "previa": quadros_previa(ep, n),
            "publicado": st.get("status") == "publicado"}


def marcar(obra, ep_, n, t, nota, tipo):
    ep = Episodio(obra, ep_)
    d = ler_json(_marcas_arq(ep), {"marcas": []})
    m = {"id": max([x["id"] for x in d["marcas"]], default=0) + 1, "parte": int(n), "t": round(float(t), 2), "nota": nota.strip(),
         "tipo": tipo, "estado": "aberta", "criada": time.strftime("%Y-%m-%d %H:%M")}
    d["marcas"].append(m)
    gravar_json(_marcas_arq(ep), d)
    return m


def apagar(obra, ep_, id_):
    """Apaga uma marca criada sem querer (ex.: a mesma nota salva duas vezes)."""
    ep = Episodio(obra, ep_)
    d = ler_json(_marcas_arq(ep))
    d["marcas"] = [x for x in d["marcas"] if x["id"] != int(id_)]
    gravar_json(_marcas_arq(ep), d)
    return {"ok": True}


def travadas(ep, n):
    """Falas em que a legenda trava: várias palavras no mesmo instante, ou uma palavra "esticada" por segundos
    (acontece quando o Whisper perde o começo de uma fala e empilha as palavras no mesmo instante)."""
    out = []
    for f in (ler_json(ep.tempos, {"partes": {}})["partes"].get(str(n)) or []):
        pal = f.get("palavras") or []
        zeradas = sum(1 for w in pal if w["f"] - w["i"] < 0.02)
        longa = max((w["f"] - w["i"] for w in pal), default=0)
        if zeradas >= 3 or longa > 2.5:
            out.append((f["inicio"], f"{n:02d}_{f['fala']:02d}"))
    return out


def resolver(obra, ep_, id_, estado="resolvida"):
    ep = Episodio(obra, ep_)
    d = ler_json(_marcas_arq(ep))
    m = next(x for x in d["marcas"] if x["id"] == int(id_))
    m.update(estado=estado, resolvida=time.strftime("%Y-%m-%d %H:%M"))
    gravar_json(_marcas_arq(ep), d)
    return m


# ------------------------------------------------------------------ prévia em quadros e marca → ação
def momentos_criticos(ep, n, maximo=10):
    """Onde o vídeo costuma errar: troca de falante (luz dos cards), troca de cenário, começo e cartão final."""
    pv = ler_json(ep.plano_video)
    falas = (ler_json(ep.tempos, {"partes": {}})["partes"].get(str(n)) or [])
    segs = {s[0]: s[1] for s in pv["partes"][str(n)]}
    ts, ant = [1.0], None
    for f in falas:
        if f.get("inicio") is None:
            continue
        if f["voz"] != ant and ant is not None:
            ts.append(f["inicio"] + 0.4)                 # logo depois da troca de quem fala
        if f["fala"] in segs and f["fala"] != 1:
            ts.append(f["inicio"] + 0.2)                 # logo depois da troca de cenário
        ant = f["voz"]
    ts.append(-1.5)                                      # cartão final
    ts = sorted(set(round(t, 1) for t in ts if t < 0 or t > 0.5), key=lambda t: (t < 0, t))
    if len(ts) > maximo:                                 # espalha
        passo = len(ts) / maximo
        ts = [ts[int(i * passo)] for i in range(maximo - 1)] + [ts[-1]]
    return ts


def previa_dir(ep):
    return ep.video_ep / "previa"


def quadros_previa(ep, n):
    d = previa_dir(ep)
    return [str(p) for p in sorted(d.glob(f"parte_{n:02d}_t*.png"))] if d.exists() else []


def acao_da_marca(obra, ep_, id_):
    """Traduz a marca em "onde corrigir": imagem → o cenário/retrato daquele segundo; tempo → a fala daquele segundo."""
    ep = Episodio(obra, ep_)
    m = next(x for x in ler_json(_marcas_arq(ep))["marcas"] if x["id"] == int(id_))
    n, t = m["parte"], m["t"]
    if n == 0:                                   # marca feita no 16:9: acha a parte e o segundo dentro dela
        n, t = local_16x9(ep, t)
    falas = ler_json(ep.tempos, {"partes": {}})["partes"].get(str(n)) or []
    fala = next((f for f in falas if f.get("inicio") is not None and f["inicio"] <= t <= f["fim"] + 1.2), None)
    if fala is None and falas:
        fala = min((f for f in falas if f.get("inicio") is not None), key=lambda f: abs(f["inicio"] - t))
    pv = ler_json(ep.plano_video)
    seg = None
    for s in pv["partes"][str(n)]:
        if fala and s[0] <= fala["fala"]:
            seg = s
    novas = {it["id"] for it in ler_json(ep.assets, {"itens": []})["itens"]}
    fundo = seg[1] if seg else None
    return {"marca": m, "parte": n, "t": t, "fala": f"{n:02d}_{fala['fala']:02d}" if fala else None,
            "voz": fala["voz"] if fala else None, "fundo": fundo, "fundo_deste_ep": fundo in novas,
            "retrato": (pv.get("retratos", {}).get(fala["voz"], {}) or {}).get(seg[2] if seg and len(seg) > 2 else ep.contexto_padrao()) if fala else None}
