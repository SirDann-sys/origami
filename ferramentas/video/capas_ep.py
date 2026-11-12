# Compõe as artes de divulgação de um episódio no padrão da capa da obra:
# ilustração cinematográfica cheia + degradê escuro + Montserrat + barra na cor de destaque + símbolo da marca.
#   miniatura  1280x720  (YouTube)     texto à esquerda, cena à direita
#   partes     1080x1920 (TikTok/Reels/Shorts) texto dentro do recorte 3:4 central que a grade do perfil mostra
# Uso (env qwen): python capas_ep.py --spec capas.json --marca marca.json
import argparse, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONTES = Path(__file__).resolve().parent / "fontes"
fo = lambda peso, t: ImageFont.truetype(str(FONTES / f"Montserrat-{peso}.ttf"), t)

ap = argparse.ArgumentParser()
ap.add_argument("--spec", required=True)
ap.add_argument("--marca", default=str(Path(__file__).resolve().parents[2] / "recursos" / "marca" / "padrao" / "marca.json"))
a = ap.parse_args()
spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from caminhos import resolver
marca = json.loads(resolver(a.marca).read_text(encoding="utf-8"))
for _k in ("simbolo_branco", "simbolo_cor"):          # caminhos da marca valem mesmo com a pasta do app movida
    if marca.get(_k):
        marca[_k] = str(resolver(marca[_k]))
VIO = tuple(marca["cor_destaque"]); CREME = tuple(marca["cor_texto"])
SIMB = Image.open(marca["simbolo_cor"]).convert("RGBA")


def cobrir(img, W, H, foco=(0.5, 0.5)):
    """Escala para cobrir WxH e recorta em torno do ponto de foco (frações da imagem)."""
    s = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x = min(max(int(img.width * foco[0] - W / 2), 0), img.width - W)
    y = min(max(int(img.height * foco[1] - H / 2), 0), img.height - H)
    return img.crop((x, y, x + W, y + H))


def veu(W, H, alfa):
    ov = np.zeros((H, W, 4), np.uint8); ov[..., :3] = (8, 10, 22); ov[..., 3] = np.clip(alfa, 0, 255).astype(np.uint8)
    return Image.fromarray(ov, "RGBA")


def texto(d, xy, s, fonte, cor, anchor, sombra=4):
    d.text((xy[0] + sombra * 0.6, xy[1] + sombra), s, font=fonte, fill=(0, 0, 0, 170), anchor=anchor)
    d.text(xy, s, font=fonte, fill=cor, anchor=anchor)


def caber(s, peso, tam, larg):
    while fo(peso, tam).getlength(s) > larg and tam > 20: tam -= 2
    return fo(peso, tam)


def simbolo(alt):
    return SIMB.resize((int(SIMB.width * alt / SIMB.height), alt), Image.LANCZOS)


def miniatura(m, saida):
    W, H = 1280, 720
    fonte_img = Image.open(m["imagem"]).convert("RGB")
    if m.get("espelhar"):        # espelhar a imagem tira um rosto de baixo do título
        from PIL import ImageOps
        fonte_img = ImageOps.mirror(fonte_img)
    c = cobrir(fonte_img, W, H, tuple(m.get("foco", (0.62, 0.5)))).convert("RGBA")
    xx = np.arange(W, dtype=np.float32)
    lado = np.clip(1 - xx / (W * 0.62), 0, 1) ** 1.3 * 235
    yy = np.arange(H, dtype=np.float32)[:, None]
    c.alpha_composite(veu(W, H, np.maximum(lado[None, :], np.clip((yy - H * 0.82) / (H * 0.18), 0, 1) * 120)))
    d = ImageDraw.Draw(c)
    x0 = 64
    texto(d, (x0, 74), m["serie"], fo("ExtraBold", 30), VIO, "lm", 2)
    y = 128
    for linha in m["titulo"]:
        f = caber(linha, "ExtraBold", 112, 690)
        texto(d, (x0, y), linha, f, (255, 255, 255), "lt", 6); y += int(f.size * 1.05)
    d.rectangle((x0, y + 14, x0 + 120, y + 21), fill=VIO); y += 50
    for linha in m.get("sub", []):
        texto(d, (x0, y), linha, fo("SemiBold", 44), CREME, "lt", 3); y += 56
    s = simbolo(64); c.alpha_composite(s, (x0, H - 64 - 40))
    texto(d, (x0 + s.width + 18, H - 72), marca["nome"].upper(), fo("ExtraBold", 30), (255, 255, 255), "lm", 2)
    c.convert("RGB").save(saida, quality=93)


def parte(p, comum, saida):
    W, H = 1080, 1920
    c = cobrir(Image.open(p["imagem"]).convert("RGB"), W, H, tuple(p.get("foco", (0.5, 0.5))))
    desce = p.get("desce", 0)  # empurra a cena para baixo do bloco de texto; o topo vira um prolongamento desfocado
    if desce:
        topo = c.crop((0, 0, W, 240)).resize((W, desce + 120), Image.LANCZOS).filter(ImageFilter.GaussianBlur(24))
        novo = Image.new("RGB", (W, H)); novo.paste(topo, (0, 0)); novo.paste(c, (0, desce))
        m = Image.new("L", (W, 120)); dm = ImageDraw.Draw(m)
        for y in range(120): dm.line((0, y, W, y), fill=int(255 * y / 120))
        novo.paste(c.crop((0, 0, W, 120)), (0, desce), m)
        c = novo
    if "faixa_y" in p:  # cena horizontal: inteira na largura, sobre ela mesma desfocada
        img = Image.open(p["imagem"]).convert("RGB")
        fg = img.resize((W, round(img.height * W / img.width)), Image.LANCZOS)
        c = c.filter(ImageFilter.GaussianBlur(30))
        m = Image.new("L", fg.size, 255); dm = ImageDraw.Draw(m); borda = 90
        for y in range(borda):
            v = int(255 * y / borda); dm.line((0, y, W, y), fill=v); dm.line((0, fg.height - 1 - y, W, fg.height - 1 - y), fill=v)
        c.paste(fg, (0, p["faixa_y"]), m)
    c = c.convert("RGBA")
    yy = np.arange(H, dtype=np.float32)[:, None]
    alfa = np.clip(1 - (yy - 720) / 420, 0, 1) ** 1.4 * 228 + np.clip((yy - H * 0.80) / (H * 0.20), 0, 1) * 170
    c.alpha_composite(veu(W, H, np.repeat(alfa, W, 1)))
    d = ImageDraw.Draw(c)
    # recorte 3:4 da grade: y 240..1680. Tudo o que importa fica dentro dele.
    texto(d, (W // 2, 300), comum["serie"], fo("ExtraBold", 38), VIO, "mm", 2)
    texto(d, (W // 2, 400), f"PARTE {p['n']}/{comum['total']}", fo("ExtraBold", 92), (255, 255, 255), "mm", 6)
    d.rectangle((W // 2 - 80, 462, W // 2 + 80, 469), fill=VIO)
    y = 530
    for linha in p["gancho"]:
        f = caber(linha, "ExtraBold", 78, 960)
        texto(d, (W // 2, y), linha, f, CREME, "mt", 4); y += int(f.size * 1.18)
    s = simbolo(70); c.alpha_composite(s, (W // 2 - s.width // 2, 1700))
    texto(d, (W // 2, 1810), marca["handle"], fo("SemiBold", 34), (255, 255, 255), "mm", 2)
    c.convert("RGB").save(saida, quality=93)


saida = Path(spec["saida"]); saida.mkdir(parents=True, exist_ok=True)
if "miniatura" in spec:
    miniatura(spec["miniatura"], saida / spec["miniatura"]["arquivo"]); print("ok miniatura")
for p in spec.get("partes", []):
    parte(p, spec, saida / f"capa_parte_{p['n']:02d}.jpg"); print("ok parte", p["n"])
