# Texto-mestre (02_capitulos/epNN_mestre.md) → capítulo do Wattpad em HTML (colar com formatação) e TXT (reserva).
# Convenções do texto-mestre:
#   cabeçalho até o primeiro "---" (título da obra, "## Capítulo N — Título", assinatura) → vira só o título do capítulo
#   "---" → separador "* * *" centralizado        **x** → negrito        *x* → itálico
#   "> linha" → texto de quadro/aviso/mensagem: centralizado e em itálico, SEM o ">"
#   "## Notas de adaptação" em diante → não publica
#   a nota do autor sai da marca (marca.json → "nota_wattpad"), nunca escrita à mão
# Uso (env qwen): python wattpad_cap.py --mestre ep02_mestre.md --saida DIR --ep 2 --titulo "Rodada" [--marca marca.json]
import argparse, html, json, re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--mestre", required=True)
ap.add_argument("--saida", required=True)
ap.add_argument("--ep", type=int, required=True)
ap.add_argument("--titulo", required=True, help="título do episódio, ex.: Arquivo")
ap.add_argument("--marca", default=str(Path(__file__).resolve().parents[2] / "recursos" / "marca" / "padrao" / "marca.json"))
a = ap.parse_args()

marca = json.loads(Path(a.marca).read_text(encoding="utf-8"))
NOTA = marca.get("nota_wattpad", [
    "Nota do autor: este capítulo também existe em vídeo, narrado, ilustrado e com trilha original. "
    "Episódio completo no YouTube e partes curtas no TikTok e no Instagram: {handle}.",
    "Escrito por {assinatura_nome}, com assistência de IA, a partir de uma história original."])
assinatura_nome = marca["assinatura"].replace("por ", "")
NOTA = [n.format(handle=marca["handle"], assinatura_nome=assinatura_nome) for n in NOTA]

linhas = Path(a.mestre).read_text(encoding="utf-8").splitlines()
# corpo: depois do primeiro separador, até as notas de adaptação
sep = next((i for i, l in enumerate(linhas) if l.strip() == "---"), None)
if sep is None:   # mestre sem "---": pula só o cabeçalho (# título)
    sep = next((i for i, l in enumerate(linhas) if l.strip() and not l.lstrip().startswith("#")), 0) - 1
ini = sep + 1
fim = next((i for i, l in enumerate(linhas) if l.strip().lower().startswith("## notas de adapta")), len(linhas))
corpo = linhas[ini:fim]
corpo = [l for l in corpo if not re.match(r"^[\s*_]*\[fim d[oe] cap", l, re.I)]   # marca de fim do mestre: não publica
while corpo and corpo[-1].strip() in ("", "---"):
    corpo.pop()

# blocos: parágrafos separados por linha em branco; linhas "> " seguidas formam um bloco de quadro
blocos, atual = [], []
for l in corpo + [""]:
    if not l.strip():
        if atual:
            blocos.append(atual); atual = []
    else:
        atual.append(l.rstrip())


def inline_html(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<i>\1</i>", s)
    return s


def inline_txt(s):
    return re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", s)


H, T = [], []
for b in blocos:
    if len(b) == 1 and b[0].strip() == "---":
        H.append('<p style="text-align:center">* * *</p>'); T.append("* * *")
    elif all(l.lstrip().startswith(">") for l in b):
        for l in b:
            t = l.lstrip()[1:].strip()
            H.append(f'<p style="text-align:center"><i>{inline_html(t)}</i></p>'); T.append("    " + inline_txt(t))
    else:
        t = " ".join(x.strip() for x in b)
        H.append(f"<p>{inline_html(t)}</p>"); T.append(inline_txt(t))
H.append('<p style="text-align:center">* * *</p>'); T.append("* * *")
for n in NOTA:
    H.append(f"<p>{html.escape(n, quote=False)}</p>"); T.append(n)

titulo = f"Capítulo {a.ep} — {a.titulo}"
saida = Path(a.saida); saida.mkdir(parents=True, exist_ok=True)
base = f"wattpad_cap{a.ep:02d}_{re.sub(r'[^0-9A-Za-zÀ-ú]+', '_', a.titulo).strip('_')}"
pagina = ('<!doctype html><meta charset="utf-8"><title>' + html.escape(titulo) + '</title>'
          '<body style="max-width:680px;margin:40px auto;font:18px Georgia,serif;line-height:1.6">'
          f"<h2>{html.escape(titulo)}</h2>" + "\n".join(H) + "</body>")
(saida / f"{base}.html").write_text(pagina, encoding="utf-8")
(saida / f"{base}.txt").write_text(titulo + "\n\n" + "\n\n".join(T) + "\n", encoding="utf-8")
palavras = sum(len(inline_txt(x).split()) for x in T)
assert ">" not in "".join(T).replace("->", ""), "sobrou '>' no texto"
print(f"ok {base}: {len(blocos)} blocos, {palavras} palavras")
