# Roteiro de áudio: mestre aprovado → roteiro (partes, falas, vozes, pausas) + plano da trilha + plano do vídeo
# + cenários novos. O trabalhador (Opus) corta e atribui; o motor confere o que dá para medir e grava os arquivos que
# a cadeia de produção já usa (os mesmos formatos do piloto).
#   conferências do motor: duração estimada por parte (2,4 palavras/s, medido na narração), repetição viciosa (3+ palavras
#   repetidas na fala ou na vizinha), vozes/fundos/humores válidos; voz nova vira decisão na Mesa (escalar antes de gravar).
import re, time
from pathlib import Path
from .obra import Episodio, ler_json, gravar_json
from . import trabalhador, texto, mesa

PALAVRAS_POR_S = 2.4
HUMORES = {"A": "melancolia leve, piano (rotina, abertura)", "A_escuro": "melancolia pesada (humilhação, perda)",
           "B": "calor e ternura (cena íntima calma)", "C": "tensão (confronto, ameaça; ostinato grave)",
           "D": "esperança, virada (tom maior, fecho de episódio)",
           "E": "cotidiano leve, sininhos de celesta/glockenspiel, estilo slice of life (rotina boa, manhã, humor leve)"}
FINAIS = {"suspensao": "fica no ar", "suspensao_grave": "fica no ar, pesado", "tonica_escura": "fecha triste",
          "sexto_suspenso": "suspenso e delicado", "dominante_aberta": "pergunta tensa", "brilho": "abre luz",
          "cadencia_maior": "fecha com esperança"}


def _fundos_existentes(ep):
    out = {}
    for f in sorted(ep.video.glob("assets_ep*.json")):
        for it in ler_json(f, {"itens": []})["itens"]:
            if it.get("tipo") == "fundo":
                out[it["id"]] = it["prompt"][:220]
    return out


def _anterior(ep):
    n = int(ep.ep)
    return Episodio(ep.obra, n - 1) if n > 1 else None


def repeticoes(partes, n=3):
    """Expressões de n+ palavras repetidas na mesma fala ou na fala seguinte (soa como erro em voz sintética)."""
    norm = lambda t: re.findall(r"[a-zà-úç]+", t.lower())
    achados = []
    for p in partes:
        fs = p["falas"]
        for i, f in enumerate(fs):
            janela = norm(f["texto"]) + (norm(fs[i + 1]["texto"]) if i + 1 < len(fs) else [])
            vistos = {}
            for k in range(len(janela) - n + 1):
                g = " ".join(janela[k:k + n])
                if g in vistos and k - vistos[g] >= n:
                    achados.append(f"P{p['parte']} fala {i + 1}: \"{g}\" repetido")
                    break
                vistos.setdefault(g, k)
    return sorted(set(achados))


def gerar(ep, log=None):
    st = ep.cfg.get("episodios", {}).get(ep.ep, {})
    if not st.get("mestre_aprovado"):
        raise RuntimeError("o texto-mestre ainda não foi aprovado (aba Texto)")
    ant = _anterior(ep)
    rot_ant = ler_json(ant.roteiro_arq) if ant else None
    pv_ant = ler_json(ant.plano_video) if ant else None
    vozes = dict((rot_ant or {}).get("vozes", {}))
    for v in ep.cfg.get("elenco", {}):
        vozes.setdefault(v, v)
    padrao = ep.contexto_padrao()
    ctx_guia = sorted({k for d in ler_json(ep.raiz / "01_biblia" / "guia_arte.json", {}).get("personagens", {}).values() for k in d if k != "retrato"})
    figurinos = sorted({f for r in (pv_ant or {}).get("retratos", {}).values() if isinstance(r, dict) for f in r}) or ctx_guia or [padrao]
    fundos = _fundos_existentes(ep)
    dec = ler_json(ep.raiz / "01_biblia" / "decisoes.json", {"itens": [], "regras": []})
    entrada = {"mestre": texto._sem_notas(ep.mestre.read_text(encoding="utf-8")), "episodio": {"numero": int(ep.ep), "titulo": ep.titulo_ep()},
               "roteiro_anterior": rot_ant or {},
               # 1º episódio de uma obra: sem anterior, o modelo do estúdio mostra o formato (não a história)
               "exemplo_estudio": {} if rot_ant else ler_json(Path(__file__).resolve().parents[1] / "recursos" / "modelos" / "roteiro_exemplo.json", {}), "vozes": vozes, "humores": HUMORES, "finais": FINAIS, "fundos_existentes": fundos,
               "figurinos": figurinos, "regras": dec.get("regras", []),
               "decisoes": [x for x in dec["itens"] if ep.ep in x["eps"] and x["estado"] == "decidido"]}
    # o número de partes segue o tamanho do texto (um capítulo curto não é inflado) e, no texto do autor (preservar/revisar), as falas SÃO o texto dele, só divididas
    nivel = texto.nivel_ia(ep)
    pal = len(entrada["mestre"].split())
    alvo = pal if nivel in ("preservar", "revisar") else min(pal, 1700)
    entrada.update(nivel_ia=nivel, palavras_mestre=pal, partes_alvo=max(1, min(9, round(alvo / 200))), palavras_alvo=alvo)
    r, reg = trabalhador.rodar("roteiro", entrada, ep.obra, log=log, ep=ep.ep)

    # ---- conferências do motor
    obs, erros = list(r["observacoes"]), []
    variantes = set()
    novas = {v["id"]: v for v in r["vozes_novas"]}
    fundos_novos = {f["id"]: f for f in r["fundos_novos"]}
    for p in r["partes"]:
        pal = sum(len(f["texto"].split()) for f in p["falas"])
        seg = pal / PALAVRAS_POR_S
        if not 65 <= seg <= 150:
            msg = f"P{p['parte']}: {pal} palavras ≈ {seg:.0f} s (fora de 65–150 s)"
            # texto do autor (preservar/revisar): o tamanho é o dele; vira aviso, a duração real sai depois de gravar
            (obs if nivel in ("preservar", "revisar") and 50 <= seg <= 180 else erros).append(msg)
        if p["humor"] not in HUMORES or p["final"] not in FINAIS:
            erros.append(f"P{p['parte']}: humor/final inválido ({p['humor']}/{p['final']})")
        for f in p["falas"]:
            if f["voz"] not in vozes and f["voz"] not in novas:
                erros.append(f"P{p['parte']}: voz desconhecida '{f['voz']}'")
        for s in p["segmentos"]:
            base, _, hor = s[1].partition("__")
            if hor and base in fundos:               # variante de horário de um lugar existente: o app gera a partir do original
                variantes.add((base, hor))
            elif s[1] not in fundos and s[1] not in fundos_novos:
                erros.append(f"P{p['parte']}: fundo desconhecido '{s[1]}'")
    reps = repeticoes(r["partes"])

    # ---- arquivos da cadeia (mesmos formatos do piloto)
    cfg = ep.cfg
    rot = {"obra": cfg.get("titulo"), "episodio": int(ep.ep), "titulo": ep.titulo_ep(), "assinatura": cfg.get("assinatura"),
           "vozes": {**vozes, **{k: f"{v['nome']}: {v['descricao']}" for k, v in novas.items() if not v.get("_so_retrato")}},
           "partes": [{"parte": p["parte"], "ambiente": p["ambiente"],
                       "falas": [{k: f[k] for k in ("voz", "texto", "estilo", "pausa") if f.get(k) not in (None, "")} for f in p["falas"]]}
                      for p in r["partes"]]}
    if ep.roteiro_arq.exists():
        vdir = ep.roteiro_arq.parent / "versoes"; vdir.mkdir(exist_ok=True)
        ep.roteiro_arq.replace(vdir / f"ep{ep.ep}_{time.strftime('%Y%m%d_%H%M%S')}.json")
    gravar_json(ep.roteiro_arq, rot)
    gravar_json(ep.plano_cues, {"obra": cfg.get("titulo"), "episodio": ep.ep,
                                "partes": [{"parte": p["parte"], "humor": p["humor"], "final": p["final"]} for p in r["partes"]]})
    pv = {k: v for k, v in (pv_ant or {}).items() if k != "partes"}
    if not pv_ant:     # 1º episódio da obra: a base do vídeo vem da configuração da obra
        vb = cfg.get("video", {})
        narr = vb.get("narrador") or (cfg.get("pov", "").split(":")[-1] if ":" in cfg.get("pov", "") else next(iter(vozes), ""))
        pv.update(obra=cfg.get("titulo"), titulo_tela=vb.get("titulo_tela", (cfg.get("titulo") or ep.obra).upper()), narrador=narr,
                  nomes=dict(cfg.get("nomes", {})), retratos={},
                  comentario="segmentos: [fala_inicial (1-based), fundo, figurino]. O fundo vale da fala indicada até a próxima mudança.")
        falam = sorted({f["voz"] for p in r["partes"] for f in p["falas"]})
        for v in falam:
            pv["nomes"].setdefault(v, v.capitalize())
            pv["retratos"].setdefault(v, {padrao: f"retrato_{v}"})
            if v not in novas:      # quem já tem voz mas ainda não tem retrato também precisa de um
                novas[v] = {"id": v, "nome": pv["nomes"][v], "descricao": vozes.get(v, v), "_so_retrato": True}
    pv.update(episodio=int(ep.ep), partes={str(p["parte"]): p["segmentos"] for p in r["partes"]})
    for k, v in novas.items():
        pv.setdefault("nomes", {})[k] = v["nome"]
        pv.setdefault("retratos", {})[k] = {padrao: f"retrato_{k}"}
    gravar_json(ep.plano_video, pv)
    ass_ant = ler_json(ant.assets) if ant else {}
    itens = [{"id": f["id"], "tipo": "fundo", "formato": "largo", "seed": 100 + i, "prompt": f["prompt"]} for i, f in enumerate(r["fundos_novos"])]
    from .imagens_video import item_variante
    for base, hor in sorted(variantes):
        if not (ep.imagens / f"{base}__{hor}.png").exists():
            try:
                itens.append(item_variante(ep, base, hor))
            except RuntimeError as ex:
                erros.append(str(ex))
    guia = ler_json(ep.raiz / "01_biblia" / "guia_arte.json", {})
    from .imagens_video import desc_retrato, referencia
    for k, v in novas.items():
        desc = desc_retrato(guia, k)
        ref = referencia(ep, k)
        itens.append({"id": f"retrato_{k}", "tipo": "retrato", "formato": "alto", "seed": 300,
                      "prompt": f"Portrait card of {desc or v['descricao']}, chest up, facing the viewer, neutral background",
                      **({"refs": [ref]} if ref else {}),
                      **({} if desc else {"revisar": "o rosto do personagem não está no guia de arte"})})
    gravar_json(ep.assets, {"estilo": ass_ant.get("estilo", guia.get("estilo", "")), "itens": itens})

    # vozes novas viram decisão na Mesa: escalar (criar/ouvir/aprovar) antes de gravar
    d = ler_json(ep.raiz / "01_biblia" / "decisoes.json")
    for k, v in novas.items():
        idd = f"V-{ep.ep}-{k}"
        # já decidido antes (ex.: P-01 "criar voz do Diretor") ou já pedido no Elenco: não pergunta de novo
        ja = k in cfg.get("vozes_pedidas", {}) or any(x.get("personagem") == k and x["estado"] == "decidido" for x in d["itens"])
        if not v.get("_so_retrato") and not ja and not any(x["id"] == idd for x in d["itens"]) and k not in cfg.get("elenco", {}):
            d["itens"].append({"id": idd, "tipo": "producao", "eps": [ep.ep], "titulo": f"Voz nova: {v['nome']}",
                               "contexto": v["descricao"], "opcoes": ["Criar no banco (ouvir 4 candidatas)", "Usar uma voz existente"],
                               "recomendada": 0, "recomendacao": "Criar no banco: personagem novo com fala.", "estado": "pendente",
                               # ao decidir "criar", vira pedido no Elenco já com uma fala real dele para as candidatas lerem
                               "personagem": k, "frase": next((f["texto"] for p in r["partes"] for f in p["falas"] if f["voz"] == k
                                                               and len(f["texto"].split()) >= 6), "")})
    gravar_json(ep.raiz / "01_biblia" / "decisoes.json", d)
    rel = {"data": time.strftime("%Y-%m-%d %H:%M"), "erros": erros, "repeticoes": reps, "observacoes": obs,
           "vozes_novas": [k for k, v in novas.items() if not v.get("_so_retrato")], "fundos_novos": list(fundos_novos),
           "partes": [{"parte": p["parte"], "palavras": sum(len(f["texto"].split()) for f in p["falas"]),
                       "segundos": round(sum(len(f["texto"].split()) for f in p["falas"]) / PALAVRAS_POR_S)} for p in r["partes"]]}
    gravar_json(ep.roteiro_arq.with_name(f"ep{ep.ep}_relatorio.json"), rel)
    texto._status(ep, status="roteiro em revisão" if erros or reps else "roteiro pronto", roteiro_conferido=False)
    return (f"roteiro: {len(r['partes'])} partes, {sum(x['palavras'] for x in rel['partes'])} palavras · "
            f"{len(erros)} erro(s), {len(reps)} repetição(ões), {len(novas)} voz(es) nova(s), {len(fundos_novos)} cenário(s) novo(s)")
