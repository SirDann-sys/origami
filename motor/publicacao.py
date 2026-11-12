# Publicação: o kit do episódio pronto para copiar, a entrega peça por peça e o registro do que foi
# postado. O app NUNCA posta sozinho: o autor posta, o app guarda o que foi feito (plataforma, peça, data, link).
import time
from .obra import Episodio, ler_json, gravar_json, atualizar_json

PLATAFORMAS = ["TikTok", "Instagram", "YouTube Shorts", "YouTube", "Wattpad"]


def painel(obra, ep_):
    from .etapas import entregaveis
    ep = Episodio(obra, ep_)
    if not ep.roteiro_arq.exists():
        raise RuntimeError(f"o Ep. {ep.ep} ainda não tem roteiro de áudio: comece pela Mesa e pelo Texto")
    itens = []
    for orig, nome, grupo in entregaveis(ep):
        dest = ep.entrega / nome
        itens.append({"nome": nome, "grupo": grupo, "pronto": orig.exists(), "entregue": dest.exists(),
                      "caminho": str(dest if dest.exists() else orig)})
    return {"obra": obra, "ep": ep.ep, "kit": ler_json(ep.publicacao / "kit.json"), "entregaveis": itens,
            "wattpad_imagens": imagens_wattpad(ep),
            "pasta_entrega": str(ep.entrega), "postagens": ler_json(ep.publicacao / "postagens.json", {"postagens": []})["postagens"],
            "plataformas": PLATAFORMAS}


# A Entrega e a Postagem compartilham o mesmo registro de "postado": marcar num marca no outro.
REDE_DE = {"TikTok": "tiktok", "Instagram": "instagram", "YouTube Shorts": "shorts", "YouTube": "youtube", "Wattpad": "wattpad"}
PLATAFORMA_DE = {v: k for k, v in REDE_DE.items()}


def peca_cal(peca):
    """'parte 3' → 'parte:3' · 'episódio completo' → 'completo' · 'capítulo' → 'capitulo' (e o caminho de volta)."""
    if peca.startswith("parte "):
        return "parte:" + peca.split()[1]
    return {"episódio completo": "completo", "capítulo": "capitulo"}.get(peca, peca)


def peca_entrega(peca):
    if peca.startswith("parte:"):
        return "parte " + peca.split(":")[1]
    return {"completo": "episódio completo", "capitulo": "capítulo"}.get(peca, peca)


def _anotar(ep, plataforma, peca, link, feito):
    arq = ep.publicacao / "postagens.json"

    def f(d):
        d["postagens"] = [p for p in d.setdefault("postagens", []) if not (p["plataforma"] == plataforma and p["peca"] == peca)]
        if feito:
            d["postagens"].append({"plataforma": plataforma, "peca": peca, "link": (link or "").strip(), "data": time.strftime("%Y-%m-%d %H:%M")})
    atualizar_json(arq, f, {"postagens": []})


def registrar(obra, ep_, plataforma, peca, link="", _do_calendario=False):
    ep = Episodio(obra, ep_)
    _anotar(ep, plataforma, peca, link, True)
    if not _do_calendario:
        _calendario(obra, ep.ep, plataforma, peca, "feito_manual", link)
    return {"ok": True}


def desfazer(obra, ep_, plataforma, peca, _do_calendario=False):
    ep = Episodio(obra, ep_)
    _anotar(ep, plataforma, peca, "", False)
    if not _do_calendario:
        _calendario(obra, ep.ep, plataforma, peca, "planejado", "")
    return {"ok": True}


def _calendario(obra, ep, plataforma, peca, estado, link):
    from . import postagem
    rede, pc = REDE_DE.get(plataforma), peca_cal(peca)
    if not rede:
        return
    d = postagem.ler(obra)
    mudou = False
    for x in d["itens"]:
        if x["ep"] == ep and x["peca"] == pc and x["rede"] == rede and x["estado"] in ("planejado", "feito_manual"):
            x["estado"] = estado; x["link"] = link; x["marcado_em"] = time.strftime("%Y-%m-%d %H:%M"); mudou = True
    if mudou:
        postagem.gravar(obra, d)


def imagens_wattpad(ep):
    """Cenas com uso "wattpad" (ou "topo") e candidata escolhida → onde entram no capítulo.
    Regra da série: a imagem entra DEPOIS da frase que revela o que ela mostra (a frase do trecho da cena),
    nunca antes (spoiler dentro do capítulo). "topo" = mídia do topo do capítulo."""
    from .arte import _cands_dir
    import re
    cenas = ler_json(ep.arte_assets, {"itens": []})["itens"]
    corpo = ep.mestre.read_text(encoding="utf-8") if ep.mestre.exists() else ""
    out = []
    for c in cenas:
        uso = (c.get("uso") or "").lower()
        if "wattpad" not in uso and "topo" not in uso or "descart" in uso or "não usad" in uso or not c.get("escolhida"):
            continue
        frase = (c.get("trecho") or "").strip()
        par = next((x for x in corpo.split("\n\n") if frase and frase in x), "")
        # a imagem vai depois do PARÁGRAFO que contém a frase (é onde o editor do Wattpad aceita a linha vazia)
        fim_par = re.split(r"(?<=[.!?…])\s+", par.strip())[-1] if par else ""
        out.append({"id": c["id"], "imagem": str(_cands_dir(ep) / c["escolhida"]), "topo": "topo" in uso,
                    "depois_de": fim_par or frase, "achou": bool(par), "uso": c.get("uso")})
    return sorted(out, key=lambda x: (not x["topo"], corpo.find(x["depois_de"]) if x["depois_de"] in corpo else 10 ** 9))
