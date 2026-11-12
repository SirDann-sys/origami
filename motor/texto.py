# Texto: o texto-mestre do episódio escrito pelo trabalhador (Opus) com contexto mínimo e o alarme de erro
# crítico antes da aprovação. Regras:
#   - nada é escrito com decisão pendente no episódio;
#   - o trabalhador recebe só: o trecho da fonte, o guia deste episódio e dos 2 seguintes, regras, decisões,
#     renomeações, a bíblia e o mestre anterior (nunca a obra inteira, exceto o guia no alarme);
#   - versões antigas do mestre ficam em 02_capitulos/versoes/;
#   - aprovar exige o alarme sem alerta crítico aberto.
import json, re, time
from .obra import Episodio, ler_json, gravar_json, atualizar_json
from . import mesa, trabalhador

RX_LINHAS = re.compile(r"\(L(\d+)[–-](\d+)\)")


def _linhas_fonte(ep):
    for l in mesa._guia(ep.obra):
        m = mesa.RX_EP.match(l)
        if m and int(m.group(1)) == int(ep.ep):
            r = RX_LINHAS.search(l)
            if r:
                return int(r.group(1)), int(r.group(2))
    raise RuntimeError(f"o guia não diz quais linhas da fonte o Ep. {ep.ep} cobre (cabeçalho '## Ep. NN · Título (Lx–y)')")


def _sem_notas(md):
    i = md.lower().find("## notas de adapta")
    return (md[:i] if i >= 0 else md).rstrip().rstrip("-").rstrip()


def _biblia(ep):
    b = ep.raiz / "01_biblia" / "biblia.md"
    return b.read_text(encoding="utf-8") if b.exists() else ""


def _renomeacoes(biblia):
    m = re.search(r"## Renomeações.*?(?=\n## |\Z)", biblia, re.S)
    return m.group(0) if m else ""


def contexto(ep):
    a, b = _linhas_fonte(ep)
    fonte = (ep.raiz / "00_fonte" / "texto_limpo.txt").read_text(encoding="utf-8").splitlines()
    n = int(ep.ep)
    ant = Episodio(ep.obra, n - 1) if n > 1 else None
    dec = ler_json(ep.raiz / "01_biblia" / "decisoes.json", {"itens": [], "regras": []})
    dmd = ep.raiz / "01_biblia" / "decisoes.md"
    biblia = _biblia(ep)
    cfg = ep.cfg
    return {
        "obra": {"titulo": cfg.get("titulo"), "assinatura": cfg.get("assinatura"), "pov": cfg.get("pov"), "nivel_ia": cfg.get("nivel_ia"), "conteudo": cfg.get("conteudo")},
        "episodio": {"numero": n, "titulo": ep.titulo_ep()},
        "fonte": "\n".join(fonte[a - 1:b]),
        "fonte_final_anterior": "\n".join(fonte[max(0, a - 61):a - 1]),
        "guia_episodio": mesa.mapa(ep.obra, ep.ep),
        "guia_seguintes": "\n\n".join(x for x in (mesa.mapa(ep.obra, n + 1), mesa.mapa(ep.obra, n + 2)) if x),
        "regras": dec.get("regras", []),
        "decisoes": {"deste_episodio": [x for x in dec["itens"] if ep.ep in x["eps"] and x["estado"] == "decidido"],
                     "historico": dmd.read_text(encoding="utf-8") if dmd.exists() else ""},
        "renomeacoes": _renomeacoes(biblia),
        "personagens": biblia,
        "mestre_anterior": _sem_notas(ant.mestre.read_text(encoding="utf-8")) if ant and ant.mestre.exists() else "",
        "notas_anterior": (ant.mestre.read_text(encoding="utf-8").split("## Notas de adapta", 1)[-1][:3000]
                           if ant and ant.mestre.exists() else ""),
    }


def _status(ep, **kw):
    atualizar_json(ep.projeto, lambda cfg: cfg.setdefault("episodios", {}).setdefault(ep.ep, {}).update(kw))


def _publicado(ep):
    return ep.cfg.get("episodios", {}).get(ep.ep, {}).get("status") == "publicado"


NIVEIS = ("preservar", "revisar", "expandir", "recriar", "continuar")


def nivel_ia(ep):
    """Quanto a IA mexe no texto : por episódio > por obra > padrão do tipo (rpg = recriar, texto do autor = preservar)."""
    st = ep.cfg.get("episodios", {}).get(ep.ep, {})
    n = st.get("nivel_ia") or ep.cfg.get("nivel_ia") or ("recriar" if ep.cfg.get("tipo", "rpg") == "rpg" else "preservar")
    return n if n in NIVEIS else "recriar"


def _mestre_preservado(ep):
    """Nível "preservar": o texto do autor É o mestre, sem passar pela IA (evita que um conto curto volte inflado e com
    detalhes inventados). Só ganha o cabeçalho padrão; títulos de capítulo da fonte saem; nada é reescrito."""
    import re as _re
    a, b = _linhas_fonte(ep)
    fonte = (ep.raiz / "00_fonte" / "texto_limpo.txt").read_text(encoding="utf-8").splitlines()[a - 1:b]
    corpo = [l for l in fonte if not _re.match(r"^\s*#{1,3}\s", l)]
    while corpo and not corpo[0].strip():
        corpo.pop(0)
    while corpo and not corpo[-1].strip():
        corpo.pop()
    texto = "\n".join(corpo)
    md = (f"# {ep.cfg.get('titulo')}\n\n## Capítulo {int(ep.ep)} — {ep.titulo_ep()}\n\n*por {ep.cfg.get('assinatura') or 'Autor'}*\n\n---\n\n{texto}\n\n"
          f"*[FIM DO CAPÍTULO {int(ep.ep)}]*")
    palavras = len(_re.findall(r"\w+", texto))
    return {"mestre_md": md, "palavras": palavras, "falas_literais": ["todas (texto do autor preservado)"], "inventados": [],
            "decisoes_aplicadas": [], "corte_fonte": f"linhas {a}–{b} da fonte, sem cortes", "duvidas": []}, {"modelo": "texto do autor (sem IA)"}


def escrever(ep, instrucao="", log=None):
    if _publicado(ep):
        raise RuntimeError("episódio publicado: o texto não é reescrito (crie uma versão nova só por decisão explícita)")
    pend = [d["id"] for d in mesa.decisoes(ep.obra, ep.ep) if d["estado"] == "pendente"]
    if pend:
        raise RuntimeError(f"decisões pendentes neste episódio: {', '.join(pend)} (decida ou adie na Mesa)")
    nivel = nivel_ia(ep)
    if nivel == "preservar" and not instrucao:
        r, reg = _mestre_preservado(ep)
    else:
        entrada = contexto(ep)
        entrada["instrucao_autor"] = instrucao or ""
        entrada["obra"]["tipo"] = ep.cfg.get("tipo", "rpg")
        entrada["obra"]["nivel_ia"] = nivel
        entrada["palavras_fonte"] = len(entrada["fonte"].split())
        r, reg = trabalhador.rodar("mestre", entrada, ep.obra, log=log, ep=ep.ep)
    if ep.mestre.exists():                                   # a versão anterior fica guardada
        vdir = ep.mestre.parent / "versoes"; vdir.mkdir(exist_ok=True)
        k = 1
        while (vdir / f"ep{ep.ep}_mestre_v{k}.md").exists():
            k += 1
        ep.mestre.replace(vdir / f"ep{ep.ep}_mestre_v{k}.md")
    lista = lambda t, xs: f"- **{t}:**\n" + "\n".join(f"  {i}. {x}" for i, x in enumerate(xs, 1)) if xs else f"- **{t}:** nenhum"
    notas = "\n".join([
        "## Notas de adaptação (para o autor; não publicar)", "",
        f"- **Escrito pelo Origami** em {time.strftime('%d/%m/%Y %H:%M')} ({reg['modelo']}, {r['palavras']} palavras)."
        + (f" Instrução do autor: \"{instrucao}\"." if instrucao else ""),
        lista("Falas do autor mantidas quase literais", r["falas_literais"]),
        lista("Decisões aplicadas", r["decisoes_aplicadas"]),
        lista("Detalhes INVENTADOS (aprovar ou cortar)", r["inventados"]),
        f"- **Corte de fonte:** {r['corte_fonte']}",
        lista("Dúvidas para o autor", r["duvidas"])])
    ep.mestre.parent.mkdir(parents=True, exist_ok=True)
    ep.mestre.write_text(r["mestre_md"].rstrip() + "\n\n---\n\n" + notas + "\n", encoding="utf-8")
    _status(ep, mestre_aprovado=False, status="mestre em revisão")
    al = alarme(ep, log)
    crit = sum(1 for a in al if a["gravidade"] == "critico")
    return f"mestre escrito ({r['palavras']} palavras, {len(r['inventados'])} inventado(s)) · alarme: {crit} crítico(s), {len(al) - crit} atenção"


def revisar(ep, instrucao, log=None):
    """Ajustar com instrução: parte do texto ATUAL e muda só o que a instrução pede (preserva as correções já feitas).
    É o caminho padrão: reescrever do zero desfaria as correções do autor."""
    if _publicado(ep):
        raise RuntimeError("episódio publicado: o texto não é ajustado aqui")
    if not (instrucao or "").strip():
        raise RuntimeError("escreva a instrução (o que mudar)")
    md = ep.mestre.read_text(encoding="utf-8")
    ctx = contexto(ep)
    resolvidos = [{k: a.get(k) for k in ("problema", "trecho", "nota")} for a in ler_json(_alarme_arq(ep), {"alertas": []})["alertas"]
                  if a["estado"] in ("corrigido", "ignorado")]
    r, reg = trabalhador.rodar("revisar", {"mestre_atual": _sem_notas(md), "instrucao": instrucao, "guia_episodio": ctx["guia_episodio"],
                                           "guia_seguintes": ctx["guia_seguintes"], "fonte": ctx["fonte"], "regras": ctx["regras"],
                                           "decisoes": ctx["decisoes"], "alertas_resolvidos": resolvidos}, ep.obra, log=log, ep=ep.ep)
    vdir = ep.mestre.parent / "versoes"; vdir.mkdir(exist_ok=True)
    k = 1
    while (vdir / f"ep{ep.ep}_mestre_v{k}.md").exists():
        k += 1
    (vdir / f"ep{ep.ep}_mestre_v{k}.md").write_text(md, encoding="utf-8")
    notas = md[md.lower().find("## notas de adapta"):] if "## notas de adapta" in md.lower() else "## Notas de adaptação (para o autor; não publicar)\n"
    notas = notas.rstrip() + "\n" + "\n".join(
        [f"- **Ajuste do autor** em {time.strftime('%d/%m/%Y %H:%M')}: \"{instrucao}\""]
        + [f"  - {m['onde']}: {m['o_que']}" for m in r["mudancas"]] + [f"  - dúvida: {d}" for d in r["duvidas"]]) + "\n"
    ep.mestre.write_text(r["mestre_md"].rstrip() + "\n\n---\n\n" + notas, encoding="utf-8")
    _status(ep, mestre_aprovado=False, status="mestre em revisão")
    al = alarme(ep, log)
    crit = sum(1 for a in al if a["gravidade"] == "critico")
    return f"ajuste aplicado ({len(r['mudancas'])} mudança(s)) · alarme: {crit} crítico(s), {len(al) - crit} atenção"


def _alarme_arq(ep):
    return ep.mestre.parent / f"ep{ep.ep}_alarme.json"


def alarme(ep, log=None):
    if not ep.mestre.exists():
        raise RuntimeError("não há texto-mestre para conferir")
    ctx = contexto(ep)
    guia = "\n".join(mesa._guia(ep.obra))
    entrada = {"mestre": _sem_notas(ep.mestre.read_text(encoding="utf-8")), "episodio": int(ep.ep), "guia_episodio": ctx["guia_episodio"],
               "guia_obra": guia, "regras": ctx["regras"], "decisoes": ctx["decisoes"], "renomeacoes": ctx["renomeacoes"],
               "personagens": ctx["personagens"]}
    r, _ = trabalhador.rodar("alarme", entrada, ep.obra, log=log, ep=ep.ep)
    al = [dict(a, id=i + 1, estado="aberto") for i, a in enumerate(r["alertas"])]
    gravar_json(_alarme_arq(ep), {"data": time.strftime("%Y-%m-%d %H:%M"), "alertas": al})
    return al


def painel(obra, ep_):
    ep = Episodio(obra, ep_)
    md = ep.mestre.read_text(encoding="utf-8") if ep.mestre.exists() else ""
    st = ep.cfg.get("episodios", {}).get(ep.ep, {})
    vdir = ep.mestre.parent / "versoes"
    return {"obra": obra, "ep": ep.ep, "existe": bool(md), "texto": _sem_notas(md),
            "notas": md.split("## Notas de adapta", 1)[1] if "## Notas de adapta" in md else "",
            "palavras": len(re.findall(r"\w+", _sem_notas(md))), "aprovado": bool(st.get("mestre_aprovado")),
            "alarme": ler_json(_alarme_arq(ep), {"alertas": []}),
            "versoes": sorted(p.name for p in vdir.glob(f"ep{ep.ep}_mestre_v*.md")) if vdir.exists() else [],
            "pendentes": [d["id"] for d in mesa.decisoes(obra, ep.ep) if d["estado"] == "pendente"], "publicado": _publicado(ep),
            "roteiro": ep.roteiro_arq.exists(), "relatorio": ler_json(ep.roteiro_arq.with_name(f"ep{ep.ep}_relatorio.json"))}


def marcar_alerta(obra, ep_, id_, estado):
    ep = Episodio(obra, ep_)
    d = ler_json(_alarme_arq(ep))
    next(a for a in d["alertas"] if a["id"] == int(id_))["estado"] = estado     # aberto | corrigido | ignorado
    gravar_json(_alarme_arq(ep), d)
    return {"ok": True}


def aprovar(obra, ep_):
    ep = Episodio(obra, ep_)
    abertos = [a for a in ler_json(_alarme_arq(ep), {"alertas": []})["alertas"] if a["gravidade"] == "critico" and a["estado"] == "aberto"]
    if abertos:
        raise RuntimeError(f"{len(abertos)} alerta(s) crítico(s) aberto(s): corrija ou marque como ignorado antes de aprovar")
    _status(ep, mestre_aprovado=True, status="mestre aprovado", mestre_aprovado_em=time.strftime("%Y-%m-%d %H:%M"))
    return {"ok": True}


def salvar(obra, ep_, novo):
    """Edição à mão do autor: troca o texto (as notas ficam), guarda a versão anterior e pede aprovação de novo."""
    ep = Episodio(obra, ep_)
    if _publicado(ep):
        raise RuntimeError("episódio publicado: o texto não é editado aqui")
    md = ep.mestre.read_text(encoding="utf-8")
    notas = md[md.lower().find("## notas de adapta"):] if "## notas de adapta" in md.lower() else ""
    vdir = ep.mestre.parent / "versoes"; vdir.mkdir(exist_ok=True)
    k = 1
    while (vdir / f"ep{ep.ep}_mestre_v{k}.md").exists():
        k += 1
    (vdir / f"ep{ep.ep}_mestre_v{k}.md").write_text(md, encoding="utf-8")
    ep.mestre.write_text(novo.rstrip() + ("\n\n---\n\n" + notas if notas else "\n"), encoding="utf-8")
    _status(ep, mestre_aprovado=False, status="mestre em revisão")
    return {"ok": True, "versao_guardada": k}


def corrigir_alertas(ep, ids=None, log=None):
    """Corrige SÓ os trechos apontados pelos alertas (todos os críticos abertos, se ids=None): o trabalhador devolve trocas
    antes→depois copiadas do texto; o motor aplica só as que acham o trecho exato (uma vez), guarda a versão anterior
    e marca o alerta como corrigido, registrando a troca. Mais barato e mais seguro que reescrever o capítulo."""
    if _publicado(ep):
        raise RuntimeError("episódio publicado: o texto não é corrigido aqui")
    arq = _alarme_arq(ep)
    d = ler_json(arq, {"alertas": []})
    alvo = [a for a in d["alertas"] if a["estado"] == "aberto" and (a["id"] in ids if ids else a["gravidade"] == "critico")]
    if not alvo:
        return "nenhum alerta aberto para corrigir"
    md = ep.mestre.read_text(encoding="utf-8")
    corpo = _sem_notas(md)
    ctx = contexto(ep)
    r, _ = trabalhador.rodar("corrigir", {"mestre": corpo, "alertas": [{k: a[k] for k in ("id", "trecho", "problema", "sugestao")} for a in alvo],
                                          "guia_episodio": ctx["guia_episodio"], "regras": ctx["regras"]}, ep.obra, log=log, ep=ep.ep)
    feitas, falhas = {}, []
    for t in r["trocas"]:
        if corpo.count(t["antes"]) == 1 and t["antes"] != t["depois"]:
            corpo = corpo.replace(t["antes"], t["depois"])
            feitas.setdefault(t["alerta"], []).append(f"\"{t['antes']}\" → \"{t['depois']}\"")
        else:
            falhas.append(t["alerta"])
    if feitas:
        vdir = ep.mestre.parent / "versoes"; vdir.mkdir(exist_ok=True)
        k = 1
        while (vdir / f"ep{ep.ep}_mestre_v{k}.md").exists():
            k += 1
        (vdir / f"ep{ep.ep}_mestre_v{k}.md").write_text(md, encoding="utf-8")
        notas = md[md.lower().find("## notas de adapta"):] if "## notas de adapta" in md.lower() else ""
        ep.mestre.write_text(corpo.rstrip() + ("\n\n---\n\n" + notas if notas else "\n"), encoding="utf-8")
        _status(ep, mestre_aprovado=False, status="mestre em revisão")
    sem = {s["alerta"]: s["motivo"] for s in r["sem_troca"]}
    for a in d["alertas"]:
        if a["id"] in feitas:
            a.update(estado="corrigido", nota="Opus: " + " · ".join(feitas[a["id"]]))
        elif a["id"] in sem:
            a["nota"] = "Opus não trocou: " + sem[a["id"]]
    gravar_json(arq, d)
    return (f"{len(feitas)} alerta(s) corrigido(s) com {sum(len(v) for v in feitas.values())} troca(s)"
            + (f" · {len(set(falhas))} sem trecho exato (corrigir à mão)" if falhas else "")
            + (f" · {len(sem)} sem troca (ver nota)" if sem else ""))


def anotar_alerta(obra, ep_, id_, estado, nota=""):
    ep = Episodio(obra, ep_)
    d = ler_json(_alarme_arq(ep))
    a = next(x for x in d["alertas"] if x["id"] == int(id_))
    a["estado"] = estado
    if nota:
        a["nota"] = nota
    gravar_json(_alarme_arq(ep), d)
    return {"ok": True}
