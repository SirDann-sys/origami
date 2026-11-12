# Imagens do vídeo: os cenários (fundos) e os retratos dos cards de quem fala. São as mesmas da série inteira:
# um cenário/retrato criado num episódio é reaproveitado nos seguintes (consistência). Aqui só entram as NOVAS de
# cada episódio (assets_epNN.json, escritas pelo roteiro); as antigas aparecem como biblioteca para comparar.
#   retrato novo: a descrição do personagem vem do guia de arte da obra; personagem sem descrição no guia é cadastrado
#   ali primeiro (vale para os episódios seguintes e para as capas).
import re
from .obra import Episodio, ler_json, gravar_json


def desc_retrato(guia, quem, padrao=None):
    """Descrição do ROSTO para o card (de frente). "retrato" no guia; senão a do contexto padrão, se não for de costas/silhueta."""
    d = guia.get("personagens", {}).get(quem, {})
    if d.get("retrato"):
        return d["retrato"]
    h = d.get(padrao or guia.get("contexto_padrao") or "", "") or next((v for k, v in d.items() if k != "retrato"), "")
    return "" if not h or re.search(r"silhouette|from behind|back view", h, re.I) else h


def quem_do_retrato(ep, id_):
    """retrato_ana_casual → ana. O sufixo só sai se for um contexto/figurino do guia DA OBRA."""
    resto = id_[len("retrato_"):] if id_.startswith("retrato_") else id_
    g = ler_json(ep.raiz / "01_biblia" / "guia_arte.json", {})
    pers = g.get("personagens", {})
    if resto in pers:
        return resto
    ctxs = {k for d in pers.values() for k in d if k != "retrato"} | set(g.get("contextos", [])) | {"casual", "fora"}
    base, _, suf = resto.rpartition("_")
    return base if base and suf in ctxs else resto


def referencia(ep, quem):
    """Rosto oficial do personagem (guia_arte.json → referencias), caminho absoluto, se existir."""
    g = ler_json(ep.raiz / "01_biblia" / "guia_arte.json", {})
    r = g.get("referencias", {}).get(quem)
    return str(ep.raiz / r) if r and (ep.raiz / r).exists() else None


HORARIOS = {"manha": "in soft early-morning daylight, pale golden sunrise light through the windows",
            "dia": "in bright natural daylight, clear midday light",
            "tarde": "in warm late-afternoon golden hour light, long shadows",
            "noite": "at night, dark outside the windows, lit only by warm interior lamps and city lights"}


def id_variante(base, horario):
    return f"{base}__{horario}"


def item_variante(ep, base, horario, estilo_prompt=""):
    """Mesmo lugar, outro horário: a imagem original entra como REFERÊNCIA (Klein) e o prompt só muda a luz.
    (O lugar não muda por ser dia ou noite.)"""
    if horario not in HORARIOS:
        raise RuntimeError(f"horário desconhecido: {horario} (use {', '.join(HORARIOS)})")
    original = ep.imagens / f"{base}.png"
    if not original.exists():
        raise RuntimeError(f"{base} não está na biblioteca da série")
    return {"id": id_variante(base, horario), "tipo": "fundo", "formato": "largo", "seed": 700, "refs": [str(original)],
            "variante_de": base, "horario": horario,
            "prompt": f"Exactly the same place as in the reference image: same room, same layout, same furniture, same window and "
                      f"camera angle, no people. Only the time of day changes: {HORARIOS[horario]}."}


def _cands(ep):
    return ep.imagens / "candidatas"


def painel(obra, ep_):
    ep = Episodio(obra, ep_)
    guia = ler_json(ep.raiz / "01_biblia" / "guia_arte.json", {})
    assets = ler_json(ep.assets, {"itens": []})
    usadas = set()
    if ep.roteiro_arq.exists() and ep.plano_video.exists():
        for n in ep.partes():
            try:
                usadas |= set(ep.imagens_da_parte(n))
            except Exception:
                pass
    itens = []
    for it in assets["itens"]:
        cs = sorted(_cands(ep).glob(f"{it['id']}_s*.png"), key=lambda p: int(re.search(r"_s(\d+)$", p.stem).group(1)))
        quem = quem_do_retrato(ep, it["id"]) if it.get("tipo") == "retrato" else None
        itens.append({**it, "candidatas": [str(p) for p in cs], "final": str(ep.imagens / f"{it['id']}.png") if (ep.imagens / f"{it['id']}.png").exists() else None,
                      "personagem": quem, "sem_guia": bool(quem) and not (ep.imagens / f"{it['id']}.png").exists()
                      and not desc_retrato(guia, quem),
                      "referencia": referencia(ep, quem) if quem else None})
    biblioteca = sorted(p.stem for p in ep.imagens.glob("*.png"))
    faltam = sorted(i for i in usadas if not (ep.imagens / f"{i}.png").exists())
    return {"obra": obra, "ep": ep.ep, "itens": itens, "biblioteca": [{"id": b, "caminho": str(ep.imagens / f"{b}.png")} for b in biblioteca],
            "faltam": faltam, "estilo": assets.get("estilo", ""), "personagens_guia": list(guia.get("personagens", {}))}


def salvar_item(obra, ep_, item):
    ep = Episodio(obra, ep_)
    d = ler_json(ep.assets, {"itens": []})
    it = next(x for x in d["itens"] if x["id"] == item["id"])
    for k in ("prompt", "formato"):
        if k in item:
            it[k] = item[k]
    it.pop("revisar", None)
    gravar_json(ep.assets, d)
    return {"ok": True}


def cadastrar_personagem(obra, ep_, personagem, retrato, trabalho="", fora=""):
    """Põe o personagem no guia de arte (descrições fixas em inglês) e refaz o prompt do retrato a partir do rosto.
    Não apaga o que já existia (ex.: o Diretor de costas, usado nas capas)."""
    ep = Episodio(obra, ep_)
    arq = ep.raiz / "01_biblia" / "guia_arte.json"
    g = ler_json(arq, {"personagens": {}})
    d0 = g.setdefault("personagens", {}).setdefault(personagem, {})
    d0["retrato"] = retrato.strip()
    if trabalho.strip():
        d0[ep.contexto_padrao()] = trabalho.strip()
    if fora.strip():
        d0["fora"] = fora.strip()
    gravar_json(arq, g)
    d = ler_json(ep.assets, {"itens": []})
    for it in d["itens"]:
        if it["id"] == f"retrato_{personagem}":
            it["prompt"] = f"Portrait card of {retrato.strip()}, chest up, facing the viewer, neutral background"
            it.pop("revisar", None)
    gravar_json(ep.assets, d)
    return {"ok": True}


def escolher(obra, ep_, id_, arquivo):
    ep = Episodio(obra, ep_)
    d = ler_json(ep.assets)
    next(x for x in d["itens"] if x["id"] == id_)["escolhida"] = re.split(r"[\\/]", arquivo)[-1]
    gravar_json(ep.assets, d)
    return {"ok": True}


def mais_sementes(c, obra, ep_, id_, n=2):
    from . import db
    ep = Episodio(obra, ep_)
    d = ler_json(ep.assets)
    it = next(x for x in d["itens"] if x["id"] == id_)
    if it.get("tipo") == "retrato" and not it.get("refs"):          # mesmo rosto: gera a partir da referência oficial
        quem = quem_do_retrato(ep, id_)
        ref = referencia(ep, quem)
        if ref:
            it["refs"] = [ref]
    usadas = [int(re.search(r"_s(\d+)$", p.stem).group(1)) for p in _cands(ep).glob(f"{id_}_s*.png")]
    if usadas:
        it["seed"] = max(usadas) + 1
    gravar_json(ep.assets, d)
    return {"ok": True, "job": db.enfileirar(c, "imagens", obra, ep.ep, params={"so": [id_], "sementes": n})}


def ampliar(c, obra, ep_, ids):
    from . import db
    ep = Episodio(obra, ep_)
    sem = [i for i in ids if not next((x for x in ler_json(ep.assets)["itens"] if x["id"] == i), {}).get("escolhida")]
    if sem:
        raise RuntimeError(f"escolha a candidata antes de finalizar: {', '.join(sem)}")
    return {"ok": True, "job": db.enfileirar(c, "imagens", obra, ep.ep, params={"so": ids, "ampliar": True})}


def registrar_referencias(ep, ids, log=None):
    """Depois de finalizar: retrato de personagem SEM referência vira o rosto oficial dele (03_personagens/<id>/ref.png)."""
    import shutil
    arq = ep.raiz / "01_biblia" / "guia_arte.json"
    g = ler_json(arq, {})
    novos = []
    for i in ids:
        if not i.startswith("retrato_") or not (ep.imagens / f"{i}.png").exists():
            continue
        quem = quem_do_retrato(ep, i)
        if referencia(ep, quem):
            continue
        dest = ep.raiz / "03_personagens" / quem / "ref.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ep.imagens / f"{i}.png", dest)
        g.setdefault("referencias", {})[quem] = f"03_personagens/{quem}/ref.png"
        novos.append(quem)
    if novos:
        gravar_json(arq, g)
        if log:
            log.write(f"referência oficial registrada: {', '.join(novos)}\n")
    return novos


def reusar(obra, ep_, id_novo, id_existente, horario=""):
    """Usa um cenário/retrato que já existe na série no lugar de um novo (consistência: o mesmo lugar aparece igual).
    Ex.: o roteiro pede "fundo_sala_nova" quando a série já tem "fundo_sala_janela"."""
    ep = Episodio(obra, ep_)
    if not (ep.imagens / f"{id_existente}.png").exists():
        raise RuntimeError(f"{id_existente} não está na biblioteca da série")
    alvo = id_existente
    if horario:                                   # mesmo lugar, outro horário: vira uma variante gerada a partir do original
        it = item_variante(ep, id_existente, horario)
        alvo = it["id"]
        d0 = ler_json(ep.assets, {"itens": []})
        if not (ep.imagens / f"{alvo}.png").exists() and not any(x["id"] == alvo for x in d0["itens"]):
            d0["itens"].append(it)
            gravar_json(ep.assets, d0)
    id_existente = alvo
    pv = ler_json(ep.plano_video)
    trocas = 0
    for segs in pv["partes"].values():
        for seg in segs:
            if seg[1] == id_novo:
                seg[1] = id_existente; trocas += 1
    for v, r in pv.get("retratos", {}).items():
        if isinstance(r, dict):
            for fig, rid in r.items():
                if rid == id_novo:
                    r[fig] = id_existente; trocas += 1
    gravar_json(ep.plano_video, pv)
    d = ler_json(ep.assets, {"itens": []})
    d["itens"] = [x for x in d["itens"] if x["id"] != id_novo]
    gravar_json(ep.assets, d)
    return {"ok": True, "trocas": trocas, "usa": id_existente, "gerar": not (ep.imagens / f"{id_existente}.png").exists()}
