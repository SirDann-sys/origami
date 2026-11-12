# Mesa do episódio: os dados das três colunas.
#   Mapa      → o trecho do guia da obra para este episódio (só leitura) + as regras fixas
#   Decisões  → os itens de 01_biblia/decisoes.json que caem neste episódio; decidir grava no json e no decisoes.md
#   Etapas    → a cadeia do episódio com o estado de cada etapa (do motor)
import re, time
from pathlib import Path
from .config import PROJETOS, DEMO
from .obra import Episodio, ler_json, gravar_json

RX_EP = re.compile(r"^## Ep\. (\d+) · (.+?)(?: \(L[^)]*\))?(?: — .*)?$")


def obras():
    out = []
    for p in sorted(PROJETOS.iterdir()):
        cfg = ler_json(p / "projeto.json")
        if cfg and not p.name.startswith("_"):
            out.append({"obra": p.name, "titulo": cfg.get("titulo", p.name), "sigla": cfg.get("sigla"),
                        "episodios": len(episodios(p.name))})
    return out


def _guia(obra):
    g = PROJETOS / obra / "01_biblia" / "guia_completo.md"
    return g.read_text(encoding="utf-8").splitlines() if g.exists() else []


def episodios(obra):
    """Episódios do guia (um item por número; seções de continuação se juntam) + estado do projeto.json."""
    cfg = ler_json(PROJETOS / obra / "projeto.json", {})
    eps = {}
    for l in _guia(obra):
        m = RX_EP.match(l)
        if m:
            n = f"{int(m.group(1)):02d}"
            eps.setdefault(n, {"ep": n, "titulo": re.sub(r"\s*★.*", "", m.group(2)).strip()})
    for n, e in eps.items():
        info = cfg.get("episodios", {}).get(n, {})
        e["titulo"] = info.get("titulo", e["titulo"])
        e["status"] = info.get("status", "a fazer")
        e["pendentes"] = sum(1 for d in decisoes(obra, n) if d["estado"] == "pendente")
    return list(eps.values())


def mapa(obra, ep):
    """Texto do guia para este episódio (todas as seções com o número dele)."""
    linhas, dentro, out = _guia(obra), False, []
    for l in linhas:
        m = RX_EP.match(l)
        if m or l.startswith("# ") or (l.startswith("## ") and not m):
            dentro = bool(m) and int(m.group(1)) == int(ep)
        if dentro:
            out.append(l)
    return "\n".join(out).strip()


def _dec_arq(obra):
    return PROJETOS / obra / "01_biblia" / "decisoes.json"


def decisoes(obra, ep=None):
    d = ler_json(_dec_arq(obra), {"itens": []})
    return [x for x in d["itens"] if ep is None or f"{int(ep):02d}" in x["eps"]]


def regras(obra):
    return ler_json(_dec_arq(obra), {}).get("regras", [])


def decidir(obra, id_, escolha, nota="", adiar=False):
    arq = _dec_arq(obra)
    d = ler_json(arq)
    it = next(x for x in d["itens"] if x["id"] == id_)
    hoje = time.strftime("%Y-%m-%d")
    it.update(estado="adiado" if adiar else "decidido", decisao=escolha, nota=nota, data=hoje)
    gravar_json(arq, d)
    md = PROJETOS / obra / "01_biblia" / "decisoes.md"
    with open(md, "a", encoding="utf-8") as f:
        f.write(f"\n- {hoje} · **{id_} · {'ADIADO' if adiar else 'DECIDIDO'} (Mesa, Ep. {', '.join(it['eps'])})**: "
                f"{it['titulo']} → {escolha}" + (f" — {nota}" if nota else "") + "\n")
    if not adiar:
        pedir_voz(obra, it)
    return it


def pedir_voz(obra, it):
    """Decidir "criar voz" abre um PEDIDO de voz na aba Elenco, que fica aberto até a voz ser aprovada."""
    pers = it.get("personagem")
    if it.get("tipo") != "producao" or not pers or not re.match(r"(criar|voz própria)", (it.get("decisao") or "").lower()):
        return
    cfg_arq = PROJETOS / obra / "projeto.json"
    cfg = ler_json(cfg_arq)
    if pers in cfg.get("elenco", {}):
        return
    novo = {"origem": it["id"], "eps": it["eps"], "descricao": it.get("recomendacao") or it.get("contexto", ""),
            "frase": it.get("frase", ""), "sugestao": it.get("voz_sugerida", {}), "pedido_em": time.strftime("%Y-%m-%d")}
    antigo = cfg.setdefault("vozes_pedidas", {}).get(pers)
    # decisão repetida não apaga o que já existe (ex.: a sugestão de timbre)
    cfg["vozes_pedidas"][pers] = {**novo, **{k: v for k, v in (antigo or {}).items() if v}} if antigo else novo
    gravar_json(cfg_arq, cfg)


# ------------------------------------------------------------------ etapas do episódio
TEXTO = [("mestre", "Texto-mestre", "autor aprova"), ("roteiro", "Roteiro (quem fala o quê)", "automático")]
NOMES = {"sincronizar": "Sincronizar roteiro", "voz": "Vozes (gravar e conferir)", "montar": "Montar partes",
         "cue": "Trilha: deixas", "stems": "Trilha: instrumentos", "mix": "Mixagem", "episodio": "Episódio completo (áudio)",
         "tempos": "Tempos das palavras", "video": "Vídeos 9:16", "video16x9": "Episódio 16:9",
         "capas": "Capas e miniatura", "wattpad": "Capítulo do Wattpad", "entregar": "Entrega"}


def etapas(obra, ep, c):
    from .etapas import ETAPAS, CADEIA, situacao, voz_pendentes
    e = Episodio(obra, ep)
    out = []
    st = e.cfg.get("episodios", {}).get(e.ep, {})
    out.append({"id": "mestre", "nome": "Texto-mestre", "quem": "autor aprova",
                "estado": ("aprovado" if st.get("mestre_aprovado") else "rascunho") if e.mestre.exists() else "a fazer"})
    out.append({"id": "roteiro", "nome": "Roteiro (quem fala o quê)", "quem": "automático",
                "estado": "pronto" if e.roteiro_arq.exists() else "a fazer"})
    if st.get("status") == "publicado" and st.get("feito_a_mao", True):
        # episódio publicado por fora do app: não há assinaturas do motor; não é "refazer"
        for t in CADEIA[1:]:
            out.append({"id": t, "nome": NOMES.get(t, t), "quem": "motor", "estado": "publicado (piloto)"})
        return out
    if not e.roteiro_arq.exists():
        for t in CADEIA:
            out.append({"id": t, "nome": NOMES.get(t, t), "quem": "motor", "estado": "aguardando"})
        return out
    # sem as partes gravadas não é erro, é só ordem: tudo o que vem depois das vozes espera por elas
    sem_partes = not all(e.parte_wav(n).exists() for n in e.partes())
    depois_da_voz = [t for t in CADEIA[CADEIA.index("montar") + 1:] if t != "wattpad"]   # o capítulo só precisa do texto
    from .aprovacao import DEPOIS_DO_AUDIO, estado as estado_audio
    ea = estado_audio(obra, ep, c)
    for t in CADEIA:
        if t == "sincronizar":
            continue
        if sem_partes and t in depois_da_voz and not ETAPAS[t].get("sempre"):
            out.append({"id": t, "nome": NOMES.get(t, t), "quem": "motor", "estado": "aguardando as vozes"})
            continue
        if t in DEPOIS_DO_AUDIO and not ea["aprovado"]:
            out.append({"id": t, "nome": NOMES.get(t, t), "quem": "motor", "estado": "aguardando você aprovar o áudio"})
            continue
        if t == "capas":
            from .arte import capas_prontas
            ok_capas, falta_capas = capas_prontas(e)
            if not ok_capas:
                out.append({"id": t, "nome": NOMES.get(t, t), "quem": "motor", "estado": "aguardando a arte das capas",
                            "detalhe": falta_capas})
                continue
        novo = []
        try:
            if t == "voz":
                n = len(voz_pendentes(e)); est = f"{n} fala(s) a gravar" if n else "em dia"
            elif ETAPAS[t].get("sempre"):
                est = "sob pedido"
            elif ETAPAS[t]["escopo"] == "parte":
                sit = {n: situacao(e, t, n, c)[0] for n in e.partes()}
                d = [n for n, s in sit.items() if s == "refazer"]
                novo = [n for n, s in sit.items() if s == "codigo novo"]
                est = f"refazer partes {d}" if d else ("em dia" if not novo else "código novo disponível")
                if d and novo:
                    est += f" · código novo nas partes {novo}"
                elif novo and len(novo) < len(sit):
                    est += f" (partes {novo})"
            else:
                s = situacao(e, t, None, c)[0]
                novo = [None] if s == "codigo novo" else []
                est = {"refazer": "refazer", "em dia": "em dia", "codigo novo": "código novo disponível"}[s]
        except Exception as ex:
            est = f"falta: {str(ex)[:90]}" if isinstance(ex, RuntimeError) else "sem dados ainda"
            novo = []        # (a exceção pode vir no meio do cálculo)
        if DEMO and est.startswith("refazer"):
            est = "fora da demonstração (arquivos pesados)"     # stems, episódio completo e 16:9 não vão no repositório
        item = {"id": t, "nome": NOMES.get(t, t), "quem": "motor", "estado": est}
        if novo and not ETAPAS[t].get("sempre") and t != "voz":
            item["codigo_novo"] = True       # a Mesa mostra "aplicar o código novo" (refaz esta etapa e o que depender)
        out.append(item)
        if t == "episodio":                       # o portão: o autor ouve e aprova antes de legenda e vídeos
            if sem_partes or ea["sem_mix"]:
                ap = "aguardando o áudio"
            elif ea["aprovado"]:
                ap = f"aprovado ({ea['em']})" if ea.get("em") and ea["em"] != "publicado" else "aprovado"
            else:
                ap = f"a aprovar: partes {ea['partes_a_aprovar']}"
            out.append({"id": "aprovacao", "nome": "Aprovação do áudio", "quem": "você ouve e aprova", "estado": ap})
    return out


TELA = {"aprovacao": "revisao", "mestre": "texto", "roteiro": "texto", "voz": "revisao", "montar": "revisao", "cue": "revisao", "stems": "revisao",
        "mix": "revisao", "episodio": "revisao", "tempos": "video", "video": "video", "video16x9": "video", "capas": "arte",
        "wattpad": "pub", "entregar": "pub", "kit": "pub", "imagens": "imagens"}


def prontidao(obra, ep):
    """O que impede de produzir o episódio agora (vazio = pode produzir)."""
    e = Episodio(obra, ep)
    falta = [f"decisão pendente: {d['id']}" for d in decisoes(obra, ep) if d["estado"] == "pendente"]
    st = e.cfg.get("episodios", {}).get(e.ep, {})
    if not st.get("mestre_aprovado"):
        falta.append("texto-mestre não aprovado")
    if not e.roteiro_arq.exists():
        return falta + ["roteiro de áudio não gerado"]
    elenco = e.cfg.get("elenco", {})
    sem_voz = sorted({f["voz"] for p in e.roteiro["partes"] for f in p["falas"]} - set(elenco))
    if sem_voz:
        falta.append("vozes sem elenco: " + ", ".join(sem_voz))
    try:
        imgs = sorted({i for n in e.partes() for i in e.imagens_da_parte(n) if not (e.imagens / f"{i}.png").exists()})
        if imgs:
            falta.append("imagens do vídeo a gerar (aba Imagens do vídeo): " + ", ".join(imgs))
    except Exception as ex:
        falta.append(f"plano de vídeo: {ex}")
    if not e.plano_cues.exists():
        falta.append("plano da trilha ausente")
    return falta


def mesa(obra, ep, c):
    from .obra import ler_json as _l
    ets = etapas(obra, ep, c)
    e = Episodio(obra, ep)
    pub = e.cfg.get("episodios", {}).get(e.ep, {}).get("status") == "publicado"
    if e.roteiro_arq.exists() and not pub:
        try:
            fal = sorted({i for n in e.partes() for i in e.imagens_da_parte(n) if not (e.imagens / f"{i}.png").exists()})
            est = f"faltam {len(fal)}" if fal else "em dia"
        except Exception:
            est = "sem plano de vídeo"
        ets.insert(next((k for k, x in enumerate(ets) if x["id"] == "video"), len(ets)),
                   {"id": "imagens", "nome": "Imagens do vídeo (cenários e retratos)", "quem": "autor escolhe", "estado": est})
    ets.append({"id": "kit", "nome": "Kit de postagem", "quem": "Opus + autor revisa",
                "estado": "pronto" if (e.publicacao / "kit.json").exists() else "a fazer"})
    for x in ets:
        x["tela"] = TELA.get(x["id"])
    from .texto import nivel_ia
    return {"obra": obra, "ep": f"{int(ep):02d}", "episodios": episodios(obra), "mapa": mapa(obra, ep), "nivel_ia": nivel_ia(e),
            "regras": regras(obra), "decisoes": decisoes(obra, ep), "etapas": ets,
            "prontidao": [] if pub else prontidao(obra, ep), "publicado": pub}
