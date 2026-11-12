"""Exporta a demonstração do Origami como site estático (pasta demo/), para hospedar no Cloudflare Pages.

O motor sobe em modo demonstração dentro deste processo; cada rota GET que a interface usa é gravada como JSON
(com caminhos da máquina trocados por caminhos relativos), e os arquivos citados (imagens, capas, vídeo, áudio) são
copiados. No navegador, um service worker (sw.js) responde no lugar do motor.

Uso (da raiz do repositório, com as dependências de requirements-demo.txt):
    python ferramentas/demo/exportar_site.py [--saida demo]
"""
import argparse, json, os, re, shutil, sys, threading, urllib.error, urllib.parse, urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
AQUI = Path(__file__).resolve().parent
os.environ["ORIGAMI_DEMO"] = "1"
os.environ["ORIGAMI_PORTA"] = "0"
sys.path.insert(0, str(RAIZ))

from http.server import ThreadingHTTPServer          # noqa: E402
from motor import worker                             # noqa: E402
from motor.config import PROJETOS, INTERFACE         # noqa: E402
from motor.obra import Episodio, ler_json            # noqa: E402

IGNORAR = {"t", "desde"}
PERMITIDAS = ("exemplos/", "ui/")                     # só o que pode ir para o site


def chave(url):
    """A mesma chave do sw.js: caminho + parâmetros (decodificados) em ordem, sem os de cache."""
    u = urllib.parse.urlsplit(url)
    p = sorted((k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True) if k not in IGNORAR)
    return u.path + ("?" + "&".join(f"{k}={v}" for k, v in p) if p else "")


def rotas():
    """Todas as leituras que as telas fazem, para cada obra, episódio e parte."""
    q = urllib.parse.quote
    out = ["/api/ambiente", "/api/obras", "/api/arquivos", "/api/postagem/conexao", "/estado"]
    for raiz in sorted(p for p in PROJETOS.iterdir() if (p / "projeto.json").exists()):
        o = q(raiz.name)
        out += [f"/api/obra?obra={o}", f"/api/custo?obra={o}", f"/api/fila?obra={o}", f"/api/elenco?obra={o}",
                f"/api/postagem?obra={o}", f"/api/pronuncia?obra={o}", f"/api/ajustes/guia?obra={o}"]
        for ep in ler_json(raiz / "projeto.json", {}).get("episodios", {}):
            base = f"obra={o}&ep={ep}"
            out += [f"/api/{r}?{base}" for r in ("mesa", "pendencias", "texto", "arte", "imagens", "publicacao", "ajustes/trilha")]
            e = Episodio(raiz.name, ep)
            partes = e.partes() if e.roteiro_arq.exists() else [1]
            for n in partes:
                out += [f"/api/revisao?{base}&parte={n}", f"/api/video?{base}&parte={n}", f"/api/ajustes/segmentos?{base}&parte={n}"]
            out.append(f"/api/video?{base}&parte=0")
    return out


def relativo(x, achados):
    """Troca caminhos absolutos desta máquina por caminhos relativos à raiz do repositório (barras normais)."""
    if isinstance(x, dict):
        return {k: relativo(v, achados) for k, v in x.items()}
    if isinstance(x, list):
        return [relativo(v, achados) for v in x]
    if not isinstance(x, str):
        return x
    s = x
    for pref in {str(RAIZ), str(RAIZ).replace("\\", "/")}:
        if pref in s:
            s = re.sub(re.escape(pref) + r"[\\/]([^\s\"']*)", lambda m: m.group(1).replace("\\", "/"), s)
            s = s.replace(pref, ".")
    cand = s.replace("\\", "/")
    if cand.startswith("exemplos/") and (RAIZ / cand).is_file():
        achados.add(cand)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default=str(RAIZ / "demo"))
    a = ap.parse_args()
    saida = Path(a.saida).resolve()
    if saida.exists():
        shutil.rmtree(saida)
    (saida / "dados").mkdir(parents=True)

    worker.semear_demo()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), worker.Api)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    manifesto, achados, problemas = {"rotas": {}}, set(), []
    for i, url in enumerate(rotas()):
        try:
            with urllib.request.urlopen(base + url, timeout=120) as r:
                status, corpo = r.status, r.read()
        except urllib.error.HTTPError as ex:
            status, corpo = ex.code, ex.read()
        try:
            dado = relativo(json.loads(corpo.decode("utf-8")), achados)
        except ValueError:
            problemas.append(f"{url}: resposta não é JSON"); continue
        if status != 200:
            problemas.append(f"{url}: {status} {str(dado)[:120]}")
        nome = f"{i:03d}.json"
        (saida / "dados" / nome).write_text(json.dumps(dado, ensure_ascii=False), encoding="utf-8")
        manifesto["rotas"][chave(url)] = {"f": nome, "s": status}
    srv.shutdown()
    (saida / "dados" / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=1), encoding="utf-8")

    # a interface, sem mudança, em /ui/
    shutil.copytree(INTERFACE, saida / "ui")
    for p in achados:                                   # imagens, capas, vídeo e áudio citados pelas telas
        alvo = saida / p
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RAIZ / p, alvo)

    # index.html: o mesmo da interface, mas carregado depois que o service worker assume
    html = (INTERFACE / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r'<script src="([^"]+)"></script>\n?', html)
    html = re.sub(r'<script src="[^"]+"></script>\n?', "", html)
    html = html.replace("</body>", '<p id="demo-carregando">Carregando a demonstração…</p>\n'
                                   f'<script src="/iniciar.js" data-scripts="{",".join(scripts)}"></script>\n</body>')
    html = html.replace("<title>Origami</title>", "<title>Origami · demonstração</title>\n"
                        '<meta name="description" content="Origami: do texto ao episódio publicado. Demonstração somente leitura.">')
    (saida / "index.html").write_text(html, encoding="utf-8")
    for f in ("sw.js", "iniciar.js", "_headers"):
        shutil.copy2(AQUI / f, saida / f)
    shutil.copy2(INTERFACE / "origami.svg", saida / "favicon.svg")

    tot = sum(p.stat().st_size for p in saida.rglob("*") if p.is_file())
    print(f"{len(manifesto['rotas'])} rotas · {len(achados)} arquivos de mídia · {tot / 1e6:.1f} MB em {saida}")
    for p in problemas:
        print("  aviso:", p)


if __name__ == "__main__":
    main()
