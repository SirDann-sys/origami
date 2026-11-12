# Ajustes feitos pela interface, sem editar JSON à mão.
#   trilha     → humor e final musical de cada parte (plano_cues.json); mudar recompõe só aquela parte
#   titulo     → título do episódio (etiqueta do 16:9, Wattpad, metadados)
#   publicado  → marca/desmarca o episódio como publicado (trava as telas de revisão)
#   segmentos  → cenário e figurino de cada trecho do vídeo (plano_video_epNN.json)
#   guia       → guia de arte da obra (estilo, receita das capas, regras, tags de rosto, acabamento)
import re
from pathlib import Path
from .config import FERRAMENTAS
from .obra import Episodio, ler_json, gravar_json, atualizar_json

HUMORES = {"A": "sério, piano e cordas (ré menor)", "A_escuro": "sombrio", "B": "esperança contida", "C": "tensão (pulsação grave)",
           "D": "caloroso, vitória (maior)", "E": "cotidiano, claro (fá maior)"}
FINAIS = {"suspensao": "suspense (gancho)", "suspensao_grave": "suspense grave", "tonica_escura": "fecha sombrio",
          "sexto_suspenso": "pergunta no ar", "dominante_aberta": "aberto e tenso", "brilho": "fecha com brilho",
          "cadencia_maior": "fecha resolvido"}


def _vocab():
    """Confere a lista com o compositor (se alguém acrescentar um humor lá, ele aparece aqui sem descrição)."""
    txt = (FERRAMENTAS / "musica" / "compor_cues.py").read_text(encoding="utf-8")
    hum = re.findall(r'^\s+"([A-Za-z_]+)": \[\[', txt, re.M)
    fin = re.findall(r'"([a-z_]+)": \["', txt[txt.find("FINAIS"):txt.find("FINAIS") + 800])
    return ({h: HUMORES.get(h, h) for h in hum} or HUMORES), ({f: FINAIS.get(f, f) for f in fin} or FINAIS)


# ------------------------------------------------------------------ trilha
def trilha(obra, ep_):
    ep = Episodio(obra, ep_)
    h, f = _vocab()
    plano = ler_json(ep.plano_cues, {"partes": []})
    return {"partes": [{"parte": p["parte"], "humor": p.get("humor"), "final": p.get("final")} for p in plano["partes"]],
            "humores": h, "finais": f}


def salvar_trilha(obra, ep_, parte, humor, final):
    ep = Episodio(obra, ep_)
    h, f = _vocab()
    if humor not in h or final not in f:
        raise RuntimeError("humor ou final desconhecido")

    def mudar(plano):
        p = next((x for x in plano["partes"] if x["parte"] == int(parte)), None)
        if not p:
            raise RuntimeError(f"a parte {parte} não está no plano da trilha")
        p.update(humor=humor, final=final)
    atualizar_json(ep.plano_cues, mudar)
    return {"ok": True, "aviso": "a trilha da parte é recomposta no próximo Produzir (o áudio volta a 'a aprovar' só nessa parte)"}


# ------------------------------------------------------------------ episódio
def salvar_titulo(obra, ep_, titulo):
    ep = Episodio(obra, ep_)
    titulo = (titulo or "").strip()
    if not titulo:
        raise RuntimeError("o título não pode ficar vazio")
    atualizar_json(ep.projeto, lambda c: c.setdefault("episodios", {}).setdefault(ep.ep, {}).update(titulo=titulo))
    return {"ok": True}


def marcar_publicado(obra, ep_, publicado=True):
    ep = Episodio(obra, ep_)

    def f(c):
        st = c.setdefault("episodios", {}).setdefault(ep.ep, {})
        if publicado:
            st.update(status="publicado", feito_a_mao=False, piloto=False)
        else:
            st["status"] = "entregue"
    atualizar_json(ep.projeto, f)
    return {"ok": True}


# ------------------------------------------------------------------ vídeo: cenário e figurino por trecho
def segmentos(obra, ep_, parte):
    ep = Episodio(obra, ep_)
    pv = ler_json(ep.plano_video)
    if not pv:
        raise RuntimeError("o plano de vídeo sai junto com o roteiro")
    falas = ep.parte(int(parte))["falas"]
    guia = ler_json(ep.raiz / "01_biblia" / "guia_arte.json", {})
    contextos = sorted(set(guia.get("contextos") or {k for d in guia.get("personagens", {}).values() for k in d if k != "retrato"})
                       | {k for r in pv.get("retratos", {}).values() if isinstance(r, dict) for k in r})     # figurinos dos retratos
    fundos = sorted({p.stem for p in ep.imagens.glob("fundo_*.png")} | {i["id"] for i in ler_json(ep.assets, {"itens": []})["itens"]
                                                                        if i.get("tipo") == "fundo"})
    return {"segmentos": [{"fala": s[0], "fundo": s[1], "figurino": s[2] if len(s) > 2 else ep.contexto_padrao(),
                           "texto": falas[s[0] - 1]["texto"][:90] if 0 < s[0] <= len(falas) else ""} for s in pv["partes"][str(int(parte))]],
            "falas": [{"n": i, "voz": f["voz"], "texto": f["texto"][:90]} for i, f in enumerate(falas, 1)],
            "fundos": fundos, "contextos": contextos}


def salvar_segmentos(obra, ep_, parte, segs):
    ep = Episodio(obra, ep_)
    n_falas = len(ep.parte(int(parte))["falas"])
    novos = []
    for s in sorted(segs, key=lambda x: int(x["fala"])):
        f = int(s["fala"])
        if not 1 <= f <= n_falas:
            raise RuntimeError(f"fala {f} fora da parte (1–{n_falas})")
        if not re.fullmatch(r"[a-z0-9_]+", s.get("fundo", "")):
            raise RuntimeError("cenário inválido")
        novos.append([f, s["fundo"], s.get("figurino") or ep.contexto_padrao()])
    if not novos or novos[0][0] != 1:
        raise RuntimeError("o primeiro trecho precisa começar na fala 1")
    atualizar_json(ep.plano_video, lambda pv: pv["partes"].__setitem__(str(int(parte)), novos))
    return {"ok": True, "aviso": "o vídeo desta parte é refeito no próximo Produzir"}


# ------------------------------------------------------------------ guia de arte
CAMPOS_GUIA = ("estilo", "estilo_capas", "regras", "regras_capas", "tags_rosto", "acabamento_rosto", "capas_com_referencia",
               "contexto_padrao")


def guia(obra):
    from .config import PROJETOS
    g = ler_json(PROJETOS / obra / "01_biblia" / "guia_arte.json", {})
    return {k: g.get(k) for k in CAMPOS_GUIA} | {"personagens": g.get("personagens", {}),
                                                 "contextos": g.get("contextos") or sorted({k for d in g.get("personagens", {}).values() for k in d if k != "retrato"})}


def salvar_guia(obra, campos):
    from .config import PROJETOS
    arq = PROJETOS / obra / "01_biblia" / "guia_arte.json"
    if not arq.exists():
        raise RuntimeError("a obra ainda não tem guia de arte (sai da bíblia, no assistente de obra nova)")

    def f(g):
        for k, v in campos.items():
            if k in CAMPOS_GUIA:
                g[k] = v
            elif k == "personagens" and isinstance(v, dict):
                for p, ctxs in v.items():
                    g.setdefault("personagens", {}).setdefault(p, {}).update({c: d for c, d in ctxs.items() if isinstance(d, str)})
    atualizar_json(arq, f)
    return {"ok": True}


# ------------------------------------------------------------------ nível de IA (quanto a IA mexe no texto)
def salvar_nivel(obra, ep_, nivel, escopo="ep"):
    from .texto import NIVEIS
    if nivel not in NIVEIS:
        raise RuntimeError(f"nível desconhecido: {nivel}")
    ep = Episodio(obra, ep_)
    if escopo == "obra":
        atualizar_json(ep.projeto, lambda c: c.update(nivel_ia=nivel))
    else:
        atualizar_json(ep.projeto, lambda c: c.setdefault("episodios", {}).setdefault(ep.ep, {}).update(nivel_ia=nivel))
    return {"ok": True, "aviso": "vale para o próximo texto-mestre deste episódio (o atual não muda sozinho)"}
