# Estúdio de arte: a consistência visual da obra, episódio por episódio.
#   cenas      → assets_epNN.json: cada cena com o modelo de prompt ({personagem@contexto}), o trecho do mestre de onde
#                saiu e a candidata escolhida. O prompt final é montado pelo guia de arte (ninguém reescreve personagem).
#   capas      → capas_epNN.json: miniatura + capa de cada parte (cena escolhida, gancho, enquadramento)
#   comparação → as peças aprovadas do episódio anterior e a grade do perfil (capas de todos os episódios)
import re, time
from pathlib import Path
from .obra import Episodio, ler_json, gravar_json


def _cands_dir(ep):
    novo, legado = ep.arte / "candidatas", ep.arte / "candidatas" / "candidatas"   # obras antigas usam a pasta dupla
    return legado if legado.exists() and any(legado.glob("*.png")) else novo


def _trecho(ep, frase):
    """Parágrafo do mestre que contém a frase (para mostrar ao lado da cena)."""
    if not frase or not ep.mestre.exists():
        return ""
    for par in ep.mestre.read_text(encoding="utf-8").split("\n\n"):
        if frase.lower() in par.lower():
            return par.strip()
    return f"(trecho não encontrado no mestre: \"{frase}\")"


def _finais(ep):
    s = ler_json(ep.capas_spec)
    if not s:
        return []
    d = Path(s["saida"]) if Path(s["saida"]).is_absolute() else ep.arte / s["saida"]
    out = []
    if "miniatura" in s and (d / s["miniatura"]["arquivo"]).exists():
        out.append({"peca": "miniatura", "caminho": str(d / s["miniatura"]["arquivo"])})
    for p in s.get("partes", []):
        f = d / f"capa_parte_{p['n']:02d}.jpg"
        if f.exists():
            out.append({"peca": f"parte {p['n']}", "caminho": str(f)})
    return out


def estudio(obra, ep_):
    from .etapas import montar_prompts
    ep = Episodio(obra, ep_)
    guia = ler_json(ep.raiz / "01_biblia" / "guia_arte.json", {})
    cenas_arq = ler_json(ep.arte_assets, {"itens": []})
    try:
        montado, alertas = montar_prompts(ep)
        finais_prompt = {it["id"]: it["prompt"] for it in montado["itens"]}
        refs_cena = {it["id"]: it.get("refs_quem") or (["(escolhidas à mão)"] if it.get("refs") else []) for it in montado["itens"]}
    except RuntimeError as ex:
        finais_prompt, alertas, refs_cena = {}, [str(ex)], {}
    cd = _cands_dir(ep)
    cenas = []
    for it in cenas_arq["itens"]:
        cands = sorted((p for p in cd.glob(f"{it['id']}_s*.png") if re.search(r"_s(\d+)$", p.stem)), key=lambda p: int(re.search(r"_s(\d+)$", p.stem).group(1)))
        cenas.append({**it, "prompt_final": finais_prompt.get(it["id"], ""), "refs_quem": refs_cena.get(it["id"], []), "trecho_texto": _trecho(ep, it.get("trecho")),
                      "alertas": [a for a in alertas if a.startswith(it["id"] + ":")],
                      "candidatas": [str(p) for p in cands]})
    # episódio anterior e grade do perfil
    eps = sorted(p.name[2:] for p in (ep.raiz / "07_publicacao").glob("ep[0-9][0-9]") if p.is_dir())
    anteriores = [e for e in eps if e < ep.ep]
    anterior = None
    if anteriores:
        a = Episodio(obra, anteriores[-1])
        anterior = {"ep": a.ep, "finais": _finais(a)}
    grade = []
    for e in eps:
        x = Episodio(obra, e)
        grade.append({"ep": e, "capas": [f["caminho"] for f in _finais(x) if f["peca"].startswith("parte")]})
    return {"obra": obra, "ep": ep.ep, "cenas": cenas, "alertas_gerais": [a for a in alertas if ":" not in a.split(" ")[0]],
            "capas": ler_json(ep.capas_spec), "finais": _finais(ep), "anterior": anterior, "grade": grade,
            "personagens": {k: list(v) for k, v in guia.get("personagens", {}).items()}, "estilo": guia.get("estilo", ""),
            "regras": guia.get("regras", []), "n_partes": len(ep.partes()) if ep.roteiro_arq.exists() else 0,
            "referencias": [{"quem": p, "contexto": ctx, "vista": v, "caminho": str(ep.raiz / arq)}
                            for p, por_ctx in guia.get("referencias_capa", {}).items() if not p.startswith("_")
                            for ctx, vistas in por_ctx.items() for v, arq in vistas.items() if (ep.raiz / arq).exists()]}


def salvar_cena(obra, ep_, cena):
    """Cria ou atualiza uma cena (id, formato, prompt com {personagem@contexto}, trecho do mestre, seed)."""
    ep = Episodio(obra, ep_)
    d = ler_json(ep.arte_assets, {"itens": []})
    if not re.fullmatch(r"[a-z0-9_]+", cena.get("id", "")):
        raise RuntimeError("id da cena: só letras minúsculas, números e _")
    campos = {k: cena[k] for k in ("id", "formato", "prompt", "trecho", "seed", "uso") if k in cena}
    atual = next((x for x in d["itens"] if x["id"] == campos["id"]), None)
    if atual:
        atual.update(campos)
    else:
        d["itens"].append({"formato": "alto", "seed": 100 + 10 * len(d["itens"]), **campos})
    gravar_json(ep.arte_assets, d)
    return {"ok": True}


def escolher(obra, ep_, id_, arquivo):
    ep = Episodio(obra, ep_)
    d = ler_json(ep.arte_assets)
    it = next(x for x in d["itens"] if x["id"] == id_)
    it["escolhida"] = Path(arquivo).name
    gravar_json(ep.arte_assets, d)
    if ep.capas_spec.exists():
        gravar_json(ep.capas_spec, resolver_imagens(ep, ler_json(ep.capas_spec), cena_escolhida=id_))
    return {"ok": True}


def novas_sementes(c, obra, ep_, id_, n=2):
    """Mais candidatas para a cena: sementes novas (as antigas continuam guardadas)."""
    from . import db
    ep = Episodio(obra, ep_)
    d = ler_json(ep.arte_assets)
    it = next(x for x in d["itens"] if x["id"] == id_)
    usadas = [int(re.search(r"_s(\d+)$", p.stem).group(1)) for p in _cands_dir(ep).glob(f"{id_}_s*.png")]
    it["seed"] = (max(usadas) + 1) if usadas else it.get("seed", 100)
    gravar_json(ep.arte_assets, d)
    jid = db.enfileirar(c, "arte", obra, ep.ep, params={"so": [id_], "sementes": n})
    return {"ok": True, "job": jid, "seed": it["seed"]}


def salvar_capas(obra, ep_, spec):
    ep = Episodio(obra, ep_)
    spec.setdefault("saida", "final")
    gravar_json(ep.capas_spec, spec)
    return {"ok": True}


# ------------------------------------------------------------------ B1: sugestão de cenas/ganchos e edição das capas
def _rel_escolhida(ep, cena):
    """Caminho da candidata escolhida relativo à pasta arte (como o capas_ep.py lê)."""
    if not cena or not cena.get("escolhida"):
        return ""
    ampliada = ep.arte / f"{cena['id']}.png"
    if cena.get("ampliada_de") == cena["escolhida"] and ampliada.exists():     # 4x (e rosto acabado): a capa usa esta
        return ampliada.name
    return str((_cands_dir(ep) / cena["escolhida"]).relative_to(ep.arte)).replace("\\", "/")


def resolver_imagens(ep, spec, cena_escolhida=None):
    """Liga cada capa à candidata escolhida da cena dela.
    Imagem escolhida ou retocada à mão nunca é perdida:
      - imagem vazia → recebe a escolhida da cena;
      - imagem diferente da escolhida da cena → é "manual" (imagem_manual) e nunca é trocada sozinha;
      - o autor escolheu agora uma candidata desta cena (cena_escolhida) → a capa dessa cena passa a usar a nova."""
    cenas = {c["id"]: c for c in ler_json(ep.arte_assets, {"itens": []})["itens"]}
    for alvo in [spec.get("miniatura")] + spec.get("partes", []):
        if not alvo or not alvo.get("cena"):
            continue
        cena = cenas.get(alvo["cena"])
        da_cena = _rel_escolhida(ep, cena)
        atual = alvo.get("imagem", "")
        trocou = False
        if cena_escolhida and alvo["cena"] == cena_escolhida and da_cena:
            trocou = atual != da_cena
            alvo["imagem"] = da_cena; alvo.pop("imagem_manual", None)
        elif not atual:
            if da_cena:
                alvo["imagem"] = da_cena; trocou = True
            alvo.pop("imagem_manual", None)
        elif da_cena and atual != da_cena:
            if cena and Path(atual).name == cena.get("escolhida"):
                alvo["imagem"] = da_cena           # a mesma escolha, agora ampliada: troca pela versão 4x
            else:
                alvo["imagem_manual"] = True
        if trocou and alvo is not spec.get("miniatura") and not alvo.get("desce_manual"):
            # o assunto precisa ficar abaixo do título (y≈720); a triagem diz onde ele está na imagem
            from .triagem import desce_sugerido
            info = ((cena or {}).get("triagem") or {}).get("resultado", {}).get((cena or {}).get("escolhida", ""), {})
            d = desce_sugerido(info) if info else 0
            if d:
                alvo["desce"] = d
            else:
                alvo.pop("desce", None)
    return spec


def capas_prontas(ep):
    """(prontas, o_que_falta). Capas sem arte não é erro: só espera a escolha na aba Arte."""
    s = ler_json(ep.capas_spec)
    if not s:
        return False, "ainda não há cenas das capas (aba Arte → Sugerir cenas)"
    falta = []
    for nome, alvo in [("miniatura", s.get("miniatura"))] + [(f"parte {p.get('n')}", p) for p in s.get("partes", [])]:
        if alvo is None:
            continue
        im = alvo.get("imagem")
        if not im or not (ep.arte / im).is_file():
            falta.append(nome)
    return (not falta), ("escolher a arte das capas: " + ", ".join(falta)) if falta else ""


def exemplos_aprovados(ep, n=8):
    """Pedidos de imagem que viraram peça publicada (escolhidos pelo autor nos episódios anteriores): o padrão a imitar."""
    out = []
    for e in sorted((p.name[2:] for p in (ep.raiz / "07_publicacao").glob("ep[0-9][0-9]") if p.is_dir()), reverse=True):
        if e >= ep.ep:
            continue
        for it in ler_json(Episodio(ep.obra, e).arte_assets, {"itens": []})["itens"]:
            if it.get("escolhida") and not it.get("escolha_auto") and not re.search(r"descartad|alternativa", it.get("uso", "")):
                out.append({"uso": it.get("uso"), "formato": it.get("formato"), "prompt": it.get("prompt_original") or it["prompt"]})
        if len(out) >= n:
            break
    return out[:n]


def sugerir(ep, log=None):
    from . import trabalhador, texto, mesa
    if not ep.mestre.exists() or not ep.roteiro_arq.exists():
        raise RuntimeError("precisa do texto-mestre e do roteiro de áudio do episódio")
    n = int(ep.ep)
    ant = Episodio(ep.obra, n - 1) if n > 1 else None
    guia = ler_json(ep.raiz / "01_biblia" / "guia_arte.json", {})
    entrada = {"episodio": {"numero": n, "titulo": ep.titulo_ep(), "partes": len(ep.partes())},
               "mestre": texto._sem_notas(ep.mestre.read_text(encoding="utf-8")),
               "roteiro": [{"parte": p["parte"], "falas": [f["texto"] for f in p["falas"]]} for p in ep.roteiro["partes"]],
               "guia_episodio": mesa.mapa(ep.obra, ep.ep),
               "personagens": {k: list(v) for k, v in guia.get("personagens", {}).items()}, "regras": guia.get("regras", []),
               "regras_capas": guia.get("regras_capas", []), "estilo_capas": guia.get("estilo_capas", ""),
               "exemplos_aprovados": exemplos_aprovados(ep),
               "cenas_anterior": ler_json(ant.arte_assets) if ant else None, "capas_anterior": ler_json(ant.capas_spec) if ant else None}
    r, _ = trabalhador.rodar("cenas", entrada, ep.obra, log=log, ep=ep.ep)
    # o topo do capítulo do Wattpad é obrigatório
    topo = r.get("topo_wattpad")
    if not any("topo" in (c.get("uso") or "") for c in r["cenas"]):
        alvo = next((c for c in r["cenas"] if c["id"] == topo), None) or next((c for c in r["cenas"] if "wattpad" in c["uso"]), None)
        if alvo:
            alvo["uso"] = "topo wattpad"
    mestre = entrada["mestre"]
    d = ler_json(ep.arte_assets, {"itens": []})
    existentes = {x["id"]: x for x in d["itens"]}
    base = 100 * n + 1
    for i, c in enumerate(r["cenas"]):
        if c["id"] in existentes and existentes[c["id"]].get("escolhida"):
            continue                       # cena já escolhida pelo autor: não mexe
        novo = {"id": c["id"], "uso": c["uso"], "formato": c["formato"], "prompt": c["prompt"], "trecho": c["trecho"],
                "seed": base + 10 * i}
        if c["trecho"] not in mestre:
            novo["aviso"] = "trecho não encontrado literalmente no mestre"
        if c["id"] in existentes:
            existentes[c["id"]].update(novo)
        else:
            d["itens"].append(novo)
    gravar_json(ep.arte_assets, d)
    titulo = (ep.cfg.get("titulo") or ep.obra).upper()
    serie = f"{titulo} · EP. {n}"
    spec = {"saida": "final", "serie": serie, "total": len(ep.partes()),
            "miniatura": {"arquivo": f"miniatura_ep{ep.ep}.jpg", "cena": r["miniatura"]["cena"], "foco": [0.62, 0.5], "serie": serie,
                          "titulo": r["miniatura"]["titulo"], "sub": r["miniatura"]["sub"]},
            "partes": [{"n": p["n"], "cena": p["cena"], "foco": [0.5, 0.5], "gancho": p["gancho"]} for p in r["partes"]]}
    antigo = ler_json(ep.capas_spec)
    if antigo:
        # sugerir de novo não apaga o acabamento manual de uma capa cuja cena continua a mesma (desce, foco, faixa, imagem)
        velhas = {p.get("n"): p for p in antigo.get("partes", [])}
        for p in spec["partes"]:
            v = velhas.get(p["n"])
            if v and v.get("cena") == p["cena"]:
                for k in ("foco", "desce", "faixa_y", "imagem", "imagem_manual"):
                    if k in v:
                        p[k] = v[k]
        vm = antigo.get("miniatura") or {}
        if vm.get("cena") == spec["miniatura"]["cena"]:
            for k in ("foco", "espelhar", "imagem", "imagem_manual"):
                if k in vm:
                    spec["miniatura"][k] = vm[k]
        ep.capas_spec.replace(ep.capas_spec.with_name(f"capas_ep{ep.ep}_{time.strftime('%Y%m%d_%H%M%S')}.json"))
    gravar_json(ep.capas_spec, resolver_imagens(ep, spec))
    return f"{len(r['cenas'])} cena(s) e os ganchos de {len(r['partes'])} capa(s) sugeridos (gere as candidatas na aba Arte)"


def salvar_capas_editadas(obra, ep_, spec):
    ep = Episodio(obra, ep_)
    spec.setdefault("saida", "final")
    gravar_json(ep.capas_spec, resolver_imagens(ep, spec))
    return {"ok": True}
