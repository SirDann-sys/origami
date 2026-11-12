# Triagem automática das imagens geradas:
#   1) conferência sem IA (ferramentas/video/conferir_imagem.py): faixa preta, imagem lisa/estourada, topo claro na capa;
#   2) o Opus OLHA as que passaram (tarefa trabalhador/triagem.md): contagem, fidelidade ao trecho, ficha das personagens,
#      rosto em branco, pseudo-escrita, composição do padrão, beleza;
#   3) as 3 melhores ficam marcadas; a 1ª vira a "pré-escolhida" e é usada sozinha depois do prazo (12 h) se o autor não
#      trocar; nenhuma passou → o pedido é corrigido com os motivos e sai outra rodada de sementes (até 3 rodadas).
# Vale para as cenas da arte (capas, miniatura, Wattpad) e para as imagens do vídeo (fundos e retratos).
import re, sys, time
from pathlib import Path
from .config import FERRAMENTAS
from .obra import Episodio, ler_json, gravar_json, atualizar_json

PRAZO_H = 12             # depois disso a pré-escolhida vale como escolhida (o autor pode trocar a qualquer hora)
RODADAS = 3              # rodadas de sementes por cena antes de chamar o autor
SEMENTES = 4             # candidatas por rodada


def _conferir():
    sys.path.insert(0, str(FERRAMENTAS / "video"))
    from conferir_imagem import conferir
    return conferir


def _alvo(ep, alvo):
    """(arquivo de itens, pasta das candidatas)."""
    if alvo == "arte":
        from .arte import _cands_dir
        return ep.arte_assets, _cands_dir(ep)
    return ep.assets, ep.imagens / "candidatas"


def candidatas(pasta, id_):
    rx = re.compile(rf"^{re.escape(id_)}_s(\d+)$")
    return sorted((p for p in pasta.glob(f"{id_}_s*.png") if rx.match(p.stem)), key=lambda p: int(rx.match(p.stem).group(1)))


def _prazo_h(ep):
    return float(ep.cfg.get("piloto", {}).get("prazo_h", PRAZO_H))


def _e_capa(it):
    u = (it.get("uso") or "").lower()
    return "capa" in u and it.get("formato", "alto") == "alto"


def _prompt_montado(ep, alvo, it):
    if alvo == "arte":
        from .etapas import montar_prompts
        try:
            m, _ = montar_prompts(ep)
            return next((x["prompt"] for x in m["itens"] if x["id"] == it["id"]), it["prompt"])
        except RuntimeError:
            return it["prompt"]
    return it["prompt"]


def _fichas(ep, prompt):
    g = ler_json(ep.raiz / "01_biblia" / "guia_arte.json", {})
    quem = set(re.findall(r"\{([a-z_]+)(?:@[a-z_]+)?\}", prompt))
    return {p: d for p, d in g.get("personagens", {}).items() if p in quem or p in prompt}, g


def precisa_triagem(ep, alvo):
    """Ids com candidatas novas (ainda não vistas) e sem escolha do autor."""
    arq, pasta = _alvo(ep, alvo)
    out = []
    for it in ler_json(arq, {"itens": []})["itens"]:
        if it.get("escolhida") and not it.get("escolha_auto"):
            continue
        if re.search(r"descartad", it.get("uso", "")):
            continue
        vistas = set((it.get("triagem") or {}).get("vistas", []))
        if any(p.name not in vistas for p in candidatas(pasta, it["id"])):
            out.append(it["id"])
    return out


def triar(ep, alvo, ids=None, log=None):
    """Roda a triagem nas candidatas novas. Devolve um resumo; grava o resultado no item (campo "triagem")."""
    from . import trabalhador
    conferir = _conferir()
    arq, pasta = _alvo(ep, alvo)
    ids = ids or precisa_triagem(ep, alvo)
    resumo = []
    for id_ in ids:
        d = ler_json(arq, {"itens": []})
        it = next((x for x in d["itens"] if x["id"] == id_), None)
        if not it:
            continue
        tri = it.get("triagem") or {"vistas": [], "resultado": {}, "rodadas": 0}
        novas = [p for p in candidatas(pasta, id_) if p.name not in set(tri["vistas"])]
        if not novas:
            continue
        capa = alvo == "arte" and _e_capa(it)
        filtro = {p.name: conferir(p, capa=capa) for p in novas}
        for nome, f in filtro.items():
            if not f["ok"]:
                tri["resultado"][nome] = {"aprovada": False, "nota": 0, "problemas": f["problemas"], "assunto_y": [0, 1], "rostos": [],
                                          "rosto_grande_de_frente": False, "filtro": True}
        passaram = [p for p in novas if filtro[p.name]["ok"]]
        if passaram:
            prompt = _prompt_montado(ep, alvo, it)
            fichas, guia = _fichas(ep, prompt)
            refs = [str(ep.raiz / r) for p, r in guia.get("referencias", {}).items() if p in fichas and (ep.raiz / r).exists()]
            entrada = {"cena": {"id": id_, "uso": it.get("uso") or it.get("tipo", ""), "formato": it.get("formato"), "pedido": prompt,
                                "trecho_mestre": _trecho(ep, it.get("trecho")) if alvo == "arte" else ""},
                       "personagens": fichas, "regras": guia.get("regras", []) + guia.get("regras_capas", []) if alvo == "arte" else guia.get("regras", []),
                       "candidatas": [{"arquivo": str(p), "conferencia_automatica": filtro[p.name]["medidas"]} for p in passaram],
                       "referencias_rosto": refs[:3]}
            r, _ = trabalhador.rodar("triagem", entrada, ep.obra, log=log, ep=ep.ep, limite_min=15)
            por_nome = {Path(c["arquivo"]).name: c for c in r["candidatas"]}
            for p in passaram:
                c = por_nome.get(p.name) or {"aprovada": False, "nota": 0, "problemas": ["o revisor não avaliou esta imagem"],
                                             "assunto_y": [0, 1], "rostos": [], "rosto_grande_de_frente": False}
                tri["resultado"][p.name] = {k: c.get(k) for k in ("aprovada", "nota", "problemas", "assunto_y", "rostos", "rosto_grande_de_frente")}
            tri["comentario"] = r.get("comentario", "")
            ordem = [Path(x).name for x in r.get("melhores", [])]
        else:
            ordem, r = [], {"prompt_corrigido": ""}
        tri["vistas"] = sorted(set(tri["vistas"]) | {p.name for p in novas})
        tri["rodadas"] = tri.get("rodadas", 0) + 1
        aprovadas = [n for n, x in tri["resultado"].items() if x["aprovada"] and (pasta / n).exists()]
        # as melhores de todas as rodadas: a ordem do Opus nesta rodada desempata a nota
        aprovadas.sort(key=lambda n: (-tri["resultado"][n]["nota"], ordem.index(n) if n in ordem else 99))
        tri["melhores"] = aprovadas[:3]
        tri["em"] = time.strftime("%Y-%m-%d %H:%M")

        def gravar(dd):
            alvo_it = next(x for x in dd["itens"] if x["id"] == id_)
            alvo_it["triagem"] = tri
            if tri["melhores"]:
                alvo_it["pre_escolhida"] = tri["melhores"][0]
                alvo_it.setdefault("prazo_escolha", time.time() + _prazo_h(ep) * 3600)
                alvo_it.pop("sem_candidata_boa", None)
            elif tri["rodadas"] < RODADAS and r.get("prompt_corrigido"):
                alvo_it.setdefault("prompt_original", alvo_it.get("prompt"))
                alvo_it["prompt"] = _volta_tokens(r["prompt_corrigido"], alvo_it.get("prompt_original", ""))
                alvo_it["mais_sementes"] = True          # o piloto pede outra rodada
            else:
                alvo_it["sem_candidata_boa"] = True       # chama o autor (aba Arte / Imagens)
        atualizar_json(arq, gravar, {"itens": []})
        ap = len(tri["melhores"])
        resumo.append(f"{id_}: {ap} aprovada(s) de {len(tri['resultado'])}" if ap else f"{id_}: nenhuma passou (rodada {tri['rodadas']})")
    return " · ".join(resumo) or "nada novo para triar"


def _volta_tokens(novo, original):
    """O Opus devolve o pedido corrigido. Sem {id@contexto} no novo há dois casos:
      - ele TIROU a personagem (a correção mais comum quando ela sai duplicada/grande): o novo vale;
      - ele DESCREVEU a personagem por extenso (a ficha se perderia): volta o token no lugar da descrição não dá para
        fazer com segurança, então mantém o original."""
    tok = re.findall(r"\{[a-z_]+(?:@[a-z_]+)?\}", original or "")
    if tok and not re.findall(r"\{[a-z_]+(?:@[a-z_]+)?\}", novo) and \
            re.search(r"\b(?:a|the)\s+(?:young|old|middle-aged|tired|elderly)?\s*(?:woman|man|girl|boy|person)\b.*\b(?:hair|wearing|dressed)\b", novo, re.I):
        return original
    return novo


def _trecho(ep, frase):
    from .arte import _trecho as t
    return t(ep, frase)


def aplicar_prazos(ep, alvo):
    """Pré-escolhida cujo prazo venceu vira a escolhida (escolha_auto: o autor ainda pode trocar). Devolve os ids."""
    arq, _ = _alvo(ep, alvo)
    agora, feitos = time.time(), []

    def f(d):
        for it in d["itens"]:
            if it.get("pre_escolhida") and not it.get("escolhida") and it.get("prazo_escolha", 9e18) <= agora:
                it["escolhida"] = it["pre_escolhida"]; it["escolha_auto"] = True
                feitos.append(it["id"])
    atualizar_json(arq, f, {"itens": []})
    if feitos and alvo == "arte" and ep.capas_spec.exists():
        from .arte import resolver_imagens
        for id_ in feitos:
            atualizar_json(ep.capas_spec, lambda s, i=id_: s.update(resolver_imagens(ep, s, cena_escolhida=i)))
    return feitos


def confirmar(obra, ep_, alvo, id_, arquivo=None):
    """O autor confirma (1 clique) a pré-escolhida, ou escolhe outra."""
    ep = Episodio(obra, ep_)
    arq, _ = _alvo(ep, alvo)
    it = next(x for x in ler_json(arq)["itens"] if x["id"] == id_)
    nome = Path(arquivo).name if arquivo else it.get("pre_escolhida")
    if not nome:
        raise RuntimeError("não há imagem pré-escolhida para esta cena")
    if alvo == "arte":
        from .arte import escolher
        escolher(obra, ep_, id_, nome)
    else:
        from .imagens_video import escolher
        escolher(obra, ep_, id_, nome)
    atualizar_json(arq, lambda d: next(x for x in d["itens"] if x["id"] == id_).pop("escolha_auto", None))
    return {"ok": True, "escolhida": nome}


def desce_sugerido(info, altura_capa=1920, linha_titulo=720, margem=40):
    """Quanto descer a cena para o assunto ficar abaixo do título (nada importante acima de y≈720)."""
    try:
        topo = float(info.get("assunto_y", [0, 1])[0])
    except (TypeError, ValueError, IndexError):
        return 0
    falta = linha_titulo + margem - topo * altura_capa
    return int(min(600, max(0, round(falta / 20) * 20)))
