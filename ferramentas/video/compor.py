# Compõe o vídeo de uma parte (9:16 para TikTok/Reels/Shorts ou 16:9 para o episódio completo):
#  - fundo da locação com movimento lento de câmera (subpixel, OpenCV), crossfade entre locações, vinheta, grão leve
#    e escurecimento na faixa da legenda;
#  - cartão 3x4 da narradora SEMPRE na tela, em destaque (acende quando ela fala); o cartão de quem fala com ela entra
#    e sai com fade; nome embaixo de cada cartão;
#  - legenda grande sincronizada palavra a palavra (ASS renderizado pelo libass do ffmpeg), palavra falada destacada;
#  - áudio = a parte mixada (−14 LUFS). Codifica em NVENC.
#  - MARCA (--marca marca.json): assinatura fixa sob o título, marca d'água móvel (símbolo + @perfil, muda de lugar a cada
#    ~10 s, sempre fora das zonas que o TikTok cobre) e cartão final na cauda musical (--cartao parte|fim|nenhum).
#    Assim, mesmo repostado, o vídeo leva de volta ao perfil original.
# Uso (env qwen): python compor.py --formato vertical|horizontal --parte 3 --plano P.json --tempos T.json
#                   --imagens DIR --audio parte.wav --saida out.mp4 [--rotulo "PARTE 3/8"]
import argparse, json, math, subprocess, shutil, tempfile
from pathlib import Path
import numpy as np, cv2, soundfile as sf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FFMPEG = str(Path(__file__).resolve().parents[2] / "ffmpeg" / "ffmpeg.exe")   # ffmpeg do próprio app
FONTES = Path(__file__).resolve().parent / "fontes"
FPS = 30
BRANCO = (255, 255, 255)

ap = argparse.ArgumentParser()
ap.add_argument("--formato", choices=["vertical", "horizontal"], default="vertical")
ap.add_argument("--parte", type=int, required=True)
ap.add_argument("--plano", required=True)
ap.add_argument("--tempos", required=True)
ap.add_argument("--imagens", required=True)
ap.add_argument("--audio", required=True)
ap.add_argument("--saida", required=True)
ap.add_argument("--rotulo", default="")
ap.add_argument("--marca", default=None, help="marca.json (perfil, símbolo, textos do cartão final)")
ap.add_argument("--cartao", choices=["parte", "fim", "nenhum"], default="nenhum")
ap.add_argument("--proxima", default="", help="texto da próxima parte no cartão, ex.: 'PARTE 3/8'")
ap.add_argument("--ep", type=int, default=1)
ap.add_argument("--titulo_meta", default="")
ap.add_argument("--destaque", default="255,196,92", help="cor de destaque R,G,B (cards ativos, rótulo, palavra da legenda); vem do projeto.json")
ap.add_argument("--quadros", default="", help="prévia: só renderiza estes segundos (ex.: '2,40,-2') em PNG, sem legenda")
a = ap.parse_args()
AMBAR = tuple(int(x) for x in a.destaque.split(","))   # cor de destaque da obra

plano = json.loads(Path(a.plano).read_text(encoding="utf-8"))
falas = json.loads(Path(a.tempos).read_text(encoding="utf-8"))["partes"][str(a.parte)]
dur = sf.info(a.audio).duration
img_dir = Path(a.imagens)
V = a.formato == "vertical"
W, H = (1080, 1920) if V else (1920, 1080)

# ---------- layout (zonas seguras do TikTok: topo ~150 px e base ~420 px ficam livres) ----------
if V:
    L = dict(titulo_y=140, narr=(70, 272, 400, 533), outro=(690, 340, 320, 427), nome_h=64,
             leg_y=1270, leg_larg=940, leg_fs=66, faixa=(1080, 1560))
else:
    L = dict(titulo_y=50, narr=(60, 560, 270, 360), outro=(360, 620, 225, 300), nome_h=52,
             leg_y=960, leg_larg=1500, leg_fs=58, faixa=(820, 1080))


def fonte(peso, tam):
    return ImageFont.truetype(str(FONTES / f"Montserrat-{peso}.ttf"), tam)


def cartao(img_path, nome, larg, alt, nome_h, ativo):
    """Retrato 3x4 com cantos arredondados, borda, sombra e plaquinha de nome. RGBA."""
    pad = 28
    tela = Image.new("RGBA", (larg + 2 * pad, alt + nome_h + 2 * pad + 10), (0, 0, 0, 0))
    foto = Image.open(img_path).convert("RGB")
    fw, fh = foto.size
    # recorte 3x4 centrado no rosto: terço superior da imagem (os retratos são bustos)
    alvo = larg / alt
    if fw / fh > alvo:
        nw = int(fh * alvo); foto = foto.crop(((fw - nw) // 2, 0, (fw - nw) // 2 + nw, fh))
    else:
        nh = int(fw / alvo); topo = int((fh - nh) * 0.12); foto = foto.crop((0, topo, fw, topo + nh))
    foto = foto.resize((larg, alt), Image.LANCZOS)
    if not ativo:
        foto = Image.blend(foto, foto.convert("L").convert("RGB"), 0.55).point(lambda v: int(v * 0.72))
    raio = 26
    masc = Image.new("L", (larg, alt), 0); ImageDraw.Draw(masc).rounded_rectangle((0, 0, larg, alt), raio, fill=255)
    sombra = Image.new("RGBA", tela.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((pad, pad + 8, pad + larg, pad + alt + 8), raio, fill=(0, 0, 0, 150))
    tela = Image.alpha_composite(tela, sombra.filter(ImageFilter.GaussianBlur(14)))
    tela.paste(foto, (pad, pad), masc)
    cor_borda = AMBAR + (255,) if ativo else (255, 255, 255, 110)
    ImageDraw.Draw(tela).rounded_rectangle((pad, pad, pad + larg, pad + alt), raio, outline=cor_borda, width=5 if ativo else 3)
    # plaquinha do nome
    d = ImageDraw.Draw(tela)
    fs = int(nome_h * 0.5)
    f = fonte("ExtraBold", fs)
    tw = d.textlength(nome.upper(), font=f)
    py = pad + alt + 10
    d.rounded_rectangle((pad, py, pad + larg, py + nome_h), 14, fill=(12, 14, 20, 215 if ativo else 150))
    d.text((pad + (larg - tw) / 2, py + (nome_h - fs) / 2 - 4), nome.upper(), font=f,
           fill=(AMBAR + (255,)) if ativo else (230, 230, 230, 200))
    return np.array(tela).astype(np.float32) / 255.0, pad


def retrato_id(voz, figurino):
    # o figurino pedido, o padrão da obra ou o 1º retrato
    r = plano["retratos"][voz]
    return r.get(figurino) or r.get(plano.get("contexto_padrao", "")) or next(iter(r.values()))


# ---------- segmentos de fundo ----------
segs = plano["partes"][str(a.parte)]
inicios = []
for k, seg in enumerate(segs):
    fala_ini, fundo = seg[0], seg[1]
    figurino = seg[2] if len(seg) > 2 else plano.get("contexto_padrao", "")    # trecho sem figurino: o padrão
    t0 = 0.0 if k == 0 else falas[fala_ini - 1]["inicio"] - 0.35
    inicios.append((t0, fundo, figurino))
segmentos = [(t0, (inicios[k + 1][0] if k + 1 < len(inicios) else dur), fundo, fig) for k, (t0, fundo, fig) in enumerate(inicios)]

rng = np.random.default_rng(a.parte * 7)
cache_fundo = {}


def fundo_base(nome):
    if nome not in cache_fundo:
        im = cv2.cvtColor(cv2.imread(str(img_dir / f"{nome}.png")), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        h, w = im.shape[:2]
        esc = max(W / w, H / h) * 1.12          # margem para o movimento
        im = cv2.resize(im, (int(w * esc), int(h * esc)), interpolation=cv2.INTER_AREA)
        cache_fundo[nome] = im
    return cache_fundo[nome]


movs = []
for (t0, t1, nome, fig) in segmentos:
    im = fundo_base(nome); h, w = im.shape[:2]
    folga_x, folga_y = w - W, h - H
    # pan lento: até 22 px/s, no máximo 70% da folga; direção alternada; zoom 1,00 → 1,035
    dist = min(folga_x * 0.7, 22 * (t1 - t0)) if folga_x > 0 else 0
    x_ini = (folga_x - dist) * rng.uniform(0.15, 0.85)
    if rng.random() < 0.5:
        x_ini, dist = x_ini + dist, -dist
    movs.append(dict(t0=t0, t1=t1, im=im, x0=x_ini, dx=dist, y0=folga_y * 0.5, fig=fig))


def quadro_fundo(m, t):
    p = min(max((t - m["t0"]) / max(m["t1"] - m["t0"], 1e-3), 0), 1)
    p = p * p * (3 - 2 * p)                       # suaviza começo e fim do movimento
    z = 1.0 + 0.035 * p
    cx = m["x0"] + m["dx"] * p + W / 2
    cy = m["y0"] + H / 2
    M = np.float32([[z, 0, W / 2 - z * cx], [0, z, H / 2 - z * cy]])
    return cv2.warpAffine(m["im"], M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


# vinheta + faixa escura da legenda + leve escurecimento geral (legibilidade dos cartões)
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
vinheta = np.clip(1.0 - 0.38 * np.clip(r - 0.55, 0, None) ** 1.4, 0.5, 1.0)
f0, f1 = L["faixa"]
faixa = 1.0 - 0.45 * np.clip(1 - np.abs(yy - (f0 + f1) / 2) / ((f1 - f0) / 2), 0, 1) ** 0.8
escurecer = (vinheta * faixa * 0.86)[..., None]
graos = [rng.normal(0, 0.018, (H // 2, W // 2, 1)).astype(np.float32) for _ in range(6)]

# ---------- cartões ----------
narr = plano["narrador"]
x, y, cw, ch = L["narr"]
cards = {}


def card(voz, fig, ativo, caixa):
    k = (voz, fig, ativo, caixa)
    if k not in cards:
        rid = retrato_id(voz, fig)
        cards[k] = cartao(img_dir / f"{rid}.png", plano["nomes"][voz], caixa[2], caixa[3], L["nome_h"], ativo)
    return cards[k]


def colar(fr, rgba_pad, pos, alfa=1.0):
    rgba, pad = rgba_pad
    x0, y0 = pos[0] - pad, pos[1] - pad
    h, w = rgba.shape[:2]
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    sub = rgba[ya - y0:yb - y0, xa - x0:xb - x0]
    al = sub[..., 3:4] * alfa
    fr[ya:yb, xa:xb] = fr[ya:yb, xa:xb] * (1 - al) + sub[..., :3] * al


def atividade(voz, t, troca=0.25):
    """0..1: o quanto o card de `voz` está aceso. Quem falou por último continua aceso durante o silêncio,
    até a próxima fala começar; na troca de falante, a luz passa de um para o outro em `troca` segundos."""
    c = None
    for k, f in enumerate(falas):
        if f["inicio"] - 0.1 <= t:
            c = k
    if c is None:
        return 1.0 if voz == narr else 0.0
    atual = falas[c]["voz"]
    ant = falas[c - 1]["voz"] if c > 0 else narr
    a = min(1.0, (t - (falas[c]["inicio"] - 0.1)) / troca)
    if ant == atual:
        return 1.0 if voz == atual else 0.0
    return a if voz == atual else (1 - a) if voz == ant else 0.0


# janelas de exibição do "outro" falante (junta falas vizinhas do mesmo personagem; fade de 0,3 s)
janelas = []
for f in falas:
    if f["voz"] == narr:
        continue
    if janelas and janelas[-1]["voz"] == f["voz"] and f["inicio"] - janelas[-1]["t1"] < 4.0:
        janelas[-1]["t1"] = f["fim"]
    else:
        janelas.append({"voz": f["voz"], "t0": f["inicio"] - 0.4, "t1": f["fim"]})
for j in janelas:
    j["t1"] += 1.2


def figurino_em(t):
    for m in movs:
        if m["t0"] <= t < m["t1"]:
            return m["fig"]
    return movs[-1]["fig"]


# ---------- legendas ASS ----------
def ass_tempo(s):
    s = max(s, 0); h = int(s // 3600); m = int(s % 3600 // 60); sec = s % 60
    return f"{h}:{m:02d}:{sec:05.2f}"


def blocos(palavras, max_chars=22 if V else 34, max_linhas=2):
    out, atual, linhas, larg = [], [], 1, 0
    for w in palavras:
        n = len(w["p"])
        # última palavra da frase pode passar um pouco do limite, para não ficar sozinha num bloco
        folga = 8 if w["p"][-1] in ".?!," else 0
        if atual and larg + 1 + n > max_chars + folga:
            if linhas >= max_linhas:
                out.append(atual); atual, linhas, larg = [], 1, 0
            else:
                atual.append({"quebra": True}); linhas += 1; larg = 0
        atual.append(w); larg += n + 1
        if w["p"][-1] in ".?!" and linhas == max_linhas and larg > max_chars * 0.5:
            out.append(atual); atual, linhas, larg = [], 1, 0
    if atual:
        out.append(atual)
    # palavra sozinha que é só o fim da frase anterior (ex.: "cozinha."): a última palavra do bloco anterior desce
    # junto. Palavra sozinha que é uma frase inteira ("Papelada.") fica: é intencional.
    for k in range(1, len(out)):
        ws = [x for x in out[k] if "p" in x]
        pw = [x for x in out[k - 1] if "p" in x]
        if len(ws) == 1 and len(pw) >= 3 and pw[-1]["p"][-1] not in ".?!":
            ultima = out[k - 1].pop()
            while out[k - 1] and "quebra" in out[k - 1][-1]:
                out[k - 1].pop()
            out[k].insert(0, ultima)
    return out


cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Leg,Montserrat ExtraBold,{L['leg_fs']},&H00FFFFFF,&H00FFFFFF,&H00101010,&H96000000,0,0,0,0,100,100,0,0,1,{5 if V else 4},{2},8,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
ev = []
COR_ATIVA = "&H00%02X%02X%02X&" % (AMBAR[2], AMBAR[1], AMBAR[0])     # destaque em BGR (ASS)
for f in falas:
    for bl in blocos(f["palavras"]):
        ws = [w for w in bl if "p" in w]
        b0, b1 = ws[0]["i"], ws[-1]["f"]
        for k, w in enumerate(ws):
            t_ini = b0 if k == 0 else w["i"]
            t_fim = ws[k + 1]["i"] if k + 1 < len(ws) else b1 + 0.25
            partes = []
            for item in bl:
                if item.get("quebra"):
                    partes.append("\\N"); continue
                cor = f"{{\\c{COR_ATIVA}}}" if item is w else "{\\c&H00FFFFFF&}"
                partes.append(cor + item["p"] + " ")
            pos = f"{{\\an8\\pos({W // 2},{L['leg_y']})\\q2}}"
            ev.append([t_ini, t_fim, pos + "".join(partes).strip()])
# nunca duas legendas ao mesmo tempo: cada evento termina, no máximo, quando o seguinte começa
ev.sort(key=lambda e: e[0])
for k in range(len(ev) - 1):
    ev[k][1] = min(ev[k][1], ev[k + 1][0])
ev = [f"Dialogue: 0,{ass_tempo(a)},{ass_tempo(b)},Leg,,0,0,0,,{txt}" for a, b, txt in ev if b > a]

tmp = Path(tempfile.mkdtemp(prefix="compor_"))
shutil.copytree(FONTES, tmp / "fontes")
(tmp / "leg.ass").write_text(cab + "\n".join(ev) + "\n", encoding="utf-8")

# ---------- título fixo (renderizado uma vez) ----------
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from caminhos import resolver
marca = json.loads(resolver(a.marca).read_text(encoding="utf-8")) if a.marca else None
if marca:                                            # caminhos da marca valem mesmo com a pasta do app movida
    for _k in ("simbolo_branco", "simbolo_cor"):
        if marca.get(_k):
            marca[_k] = str(resolver(marca[_k]))
tit = Image.new("RGBA", (W, 160), (0, 0, 0, 0)); d = ImageDraw.Draw(tit)
f1 = fonte("ExtraBold", 40 if V else 34); f2 = fonte("SemiBold", 28 if V else 24)
t1_ = plano["titulo_tela"]; t2_ = a.rotulo
x_t = 70 if V else 60
d.text((x_t, 10), t1_, font=f1, fill=(255, 255, 255, 235), stroke_width=2, stroke_fill=(0, 0, 0, 160))
d.text((x_t, 62 if V else 54), t2_, font=f2, fill=AMBAR + (235,), stroke_width=2, stroke_fill=(0, 0, 0, 160))
if marca:   # assinatura fixa: quem reposta leva junto
    f3 = fonte("SemiBold", 24 if V else 20)
    d.text((x_t, 100 if V else 88), f"{marca['nome']} · {marca['assinatura']} · {marca['handle']}", font=f3,
           fill=tuple(marca["cor_texto"]) + (200,), stroke_width=2, stroke_fill=(0, 0, 0, 150))
titulo = (np.array(tit).astype(np.float32) / 255.0, 0)


def rgba_np(im):
    return (np.array(im).astype(np.float32) / 255.0, 0)


# ---------- marca d'água móvel ----------
selo, posicoes = None, []
if marca:
    sb = Image.open(marca["simbolo_branco"]).convert("RGBA")
    hs = 64 if V else 52
    sb = sb.resize((int(sb.width * hs / sb.height), hs), Image.LANCZOS)
    fh = fonte("SemiBold", 30 if V else 26)
    lw = int(ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(marca["handle"], font=fh))
    im = Image.new("RGBA", (sb.width + 12 + lw + 8, hs + 8), (0, 0, 0, 0))
    im.alpha_composite(sb, (2, 4))
    ImageDraw.Draw(im).text((sb.width + 12, hs // 2 + 4), marca["handle"], font=fh, fill=(255, 255, 255, 255), anchor="lm",
                            stroke_width=2, stroke_fill=(0, 0, 0, 120))
    op = marca["marca_dagua"]["opacidade"]
    im.putalpha(im.getchannel("A").point(lambda v: int(v * op)))
    selo = rgba_np(im)
    # faixas livres: entre os cartões e a legenda (vertical); lado direito, acima da legenda (horizontal)
    posicoes = ([(90, 900), (560, 1010), (240, 1150), (600, 880), (90, 1060)] if V else
                [(1500, 140), (1180, 420), (1560, 640), (980, 200), (1420, 300)])

t_voz = falas[-1]["fim"] if falas else dur


def selo_em(t):
    """(posição, alfa) da marca d'água: troca de lugar a cada `troca_s`, com fade de saída e de entrada."""
    md = marca["marca_dagua"]; T, tr = md["troca_s"], md["transicao_s"]
    k = int(t // T); fase = t - k * T
    al = min(1.0, fase / tr, (T - fase) / tr)
    return posicoes[k % len(posicoes)], max(al, 0.0)


# ---------- cartão final (na cauda musical, depois da última fala) ----------
cartao_fim = None
if marca and a.cartao != "nenhum":
    cf = marca["cartao_final"]; dest = tuple(marca["cor_destaque"]); creme = tuple(marca["cor_texto"])
    c = Image.new("RGBA", (W, H), (10, 14, 26, 228))
    dc = ImageDraw.Draw(c)
    sc = Image.open(marca["simbolo_cor"]).convert("RGBA")
    hs = 190 if V else 150
    sc = sc.resize((int(sc.width * hs / sc.height), hs), Image.LANCZOS)
    y = int(H * (0.30 if V else 0.20))
    c.alpha_composite(sc, ((W - sc.width) // 2, y)); y += hs + (50 if V else 30)
    if a.cartao == "parte":
        dc.text((W // 2, y), cf["continua"], font=fonte("SemiBold", 40 if V else 34), fill=creme + (230,), anchor="mt"); y += 60 if V else 48
        dc.text((W // 2, y), a.proxima, font=fonte("ExtraBold", 92 if V else 76), fill=(255, 255, 255, 255), anchor="mt"); y += 130 if V else 100
    else:
        dc.text((W // 2, y), cf["fim"].format(ep=a.ep).upper(), font=fonte("ExtraBold", 66 if V else 60), fill=(255, 255, 255, 255), anchor="mt"); y += 90 if V else 78
        dc.text((W // 2, y), cf["fim_sub"].format(prox=a.ep + 1), font=fonte("SemiBold", 40 if V else 34), fill=creme + (230,), anchor="mt"); y += 90 if V else 70
    dc.rectangle((W // 2 - 90, y, W // 2 + 90, y + 5), fill=dest + (255,)); y += 40 if V else 32
    for ln in (cf["linhas"] if V else cf.get("linhas_horizontal", cf["linhas"])):
        dc.text((W // 2, y), ln, font=fonte("SemiBold", 42 if V else 34), fill=creme + (240,), anchor="mt"); y += 60 if V else 48
    y += 20
    dc.text((W // 2, y), marca["handle"], font=fonte("ExtraBold", 58 if V else 48), fill=dest + (255,), anchor="mt")
    cartao_fim = rgba_np(c)
t_cartao = t_voz + 0.35

# ---------- render ----------
cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
       "-i", str(Path(a.audio).resolve()), "-vf", "ass=leg.ass:fontsdir=fontes",
       "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart"]
if marca:   # metadados do arquivo original (somem num re-upload, mas identificam o arquivo-fonte)
    cmd += ["-metadata", f"title={a.titulo_meta or plano['titulo_tela']}", "-metadata", f"artist={marca['nome']} · {marca['assinatura']}",
            "-metadata", f"comment={marca['handle']}", "-metadata", f"copyright={marca['direitos']}"]
cmd += [str(Path(a.saida).resolve())]
PREVIA = [float(x) for x in a.quadros.split(",")] if a.quadros else None
if PREVIA:
    PREVIA = [x if x >= 0 else dur + x for x in PREVIA]
    quadros_previa = {int(x * FPS): x for x in PREVIA}
else:
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=tmp)
n = int(math.ceil(dur * FPS))
XF = 0.8   # crossfade entre locações (s)
for i in (sorted(quadros_previa) if PREVIA else range(n)):
    t = i / FPS
    k = max(j for j, m in enumerate(movs) if m["t0"] <= t or j == 0)
    fr = quadro_fundo(movs[k], t)
    if k > 0 and t - movs[k]["t0"] < XF:
        al = (t - movs[k]["t0"]) / XF
        fr = quadro_fundo(movs[k - 1], t) * (1 - al) + fr * al
    fr = fr * escurecer
    g = cv2.resize(graos[i % len(graos)], (W, H), interpolation=cv2.INTER_NEAREST)[..., None]
    fr = np.clip(fr + g, 0, 1)
    fig = figurino_em(t)
    an = atividade(narr, t)
    colar(fr, card(narr, fig, False, L["narr"]), L["narr"][:2])
    if an > 0:
        colar(fr, card(narr, fig, True, L["narr"]), L["narr"][:2], alfa=an)
    for j in janelas:
        if j["t0"] <= t <= j["t1"]:
            al = max(min(1.0, (t - j["t0"]) / 0.3, (j["t1"] - t) / 0.3), 0)
            ao = atividade(j["voz"], t)
            colar(fr, card(j["voz"], fig, False, L["outro"]), L["outro"][:2], alfa=al)
            if ao > 0:
                colar(fr, card(j["voz"], fig, True, L["outro"]), L["outro"][:2], alfa=al * ao)
    colar(fr, titulo, (0, L["titulo_y"] - 10))
    ac = min(1.0, max(0.0, (t - t_cartao) / 0.5)) if cartao_fim is not None else 0.0
    if selo is not None and ac < 1:
        pos, al = selo_em(t)
        if al > 0:
            colar(fr, selo, pos, alfa=al * (1 - ac))
    if ac > 0:
        colar(fr, cartao_fim, (0, 0), alfa=ac)
    if PREVIA:
        Image.fromarray((fr * 255).astype(np.uint8)).save(Path(a.saida).with_suffix("") .as_posix() + f"_t{t:06.2f}.png")
        continue
    proc.stdin.write((fr * 255).astype(np.uint8).tobytes())
if not PREVIA:   # as legendas ficam ao lado do vídeo: o Origami confere sobreposição e palavra sozinha
    shutil.copyfile(tmp / "leg.ass", Path(a.saida).with_suffix(".ass"))
shutil.rmtree(tmp, ignore_errors=True)
if PREVIA:
    print("prévia ok", len(PREVIA), "quadros"); raise SystemExit
proc.stdin.close()
proc.wait()
print("ok", a.saida, f"{dur:.1f} s", "rc", proc.returncode)
