# Assistente de obra nova: do arquivo bruto ao guia, à bíblia e ao elenco.
#   1 criar      pasta padrão + projeto.json (modelo do estúdio)
#   2 importar   txt/md/pdf/docx → 00_fonte/texto_limpo.txt (as linhas numeradas são o "L" de todo o guia)
#   3 ler        blocos de ~1.100 linhas → notas de leitura com L (retomável: bloco pronto não é relido)
#   4 estrutura  cortes dos episódios (início/fim em L, título)
#   5 guia       uma seção por episódio lendo o trecho inteiro (retomável)
#   6 bíblia     visão geral, inconsistências → decisões da Mesa, bíblia, guia de arte, pronúncia, pedidos de voz
# Cada passo é um job do motor (o Opus trabalha; o autor revisa na Mesa, no Texto e no Elenco).
import json, re, time
from pathlib import Path
from .config import PROJETOS, RECURSOS
from .obra import ler_json, gravar_json, atualizar_json
from . import trabalhador

BLOCO = 1100
PASTAS = ["00_fonte", "01_biblia", "02_capitulos", "03_personagens", "04_roteiro_audio", "05_audio", "06_video/imagens", "07_publicacao"]


def _raiz(obra):
    return PROJETOS / obra


def criar(pasta, titulo, sigla, tipo="rpg", protagonista="", conteudo="sugestivo"):
    if not re.fullmatch(r"[A-Za-z0-9_]+", pasta or ""):
        raise RuntimeError("nome da pasta: só letras sem acento, números e _ (ex.: Corvo_e_Raposa)")
    raiz = _raiz(pasta)
    if (raiz / "projeto.json").exists():
        raise RuntimeError(f"já existe uma obra em {raiz}")
    for p in PASTAS:
        (raiz / p).mkdir(parents=True, exist_ok=True)
    cfg = {k: v for k, v in ler_json(RECURSOS / "modelos" / "projeto_modelo.json").items() if not k.startswith("_")}
    prot = (protagonista or "protagonista").lower()
    tag = "#" + re.sub(r"\W", "", titulo.lower())
    cfg.update(titulo=titulo, sigla=sigla or pasta, tipo=tipo, conteudo=conteudo, pov=f"1a:{prot}", elenco={}, nomes={}, episodios={},
               video={"destaque": "marca", "titulo_tela": titulo.upper(), "narrador": prot},
               divulgacao={"hashtag": tag,
                           "rodape_legenda": f"📖 {titulo} · por {cfg.get('assinatura') or 'Autor'}\n"
                                             f"{tag} #folhetim #historianarrada"},
               criada_em=time.strftime("%Y-%m-%d"), entrada={"etapa": "criada"})
    gravar_json(raiz / "projeto.json", cfg)
    gravar_json(raiz / "01_biblia" / "decisoes.json", {"regras": [], "itens": []})
    return {"ok": True, "obra": pasta}


def _texto_de(arq):
    ext = arq.suffix.lower()
    if ext in (".txt", ".md"):
        b = arq.read_bytes()
        for cod in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                return b.decode(cod)
            except UnicodeDecodeError:
                continue
        return b.decode("utf-8", errors="replace")
    if ext == ".pdf":
        import pypdf
        return "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(str(arq)).pages)
    if ext == ".docx":
        import docx
        return "\n".join(p.text for p in docx.Document(str(arq)).paragraphs)
    raise RuntimeError(f"formato não suportado: {ext} (use .txt, .md, .pdf ou .docx)")


def importar(obra, nome, dados):
    """Guarda o arquivo original e gera o texto limpo. Vários arquivos (ex.: um por sessão) entram em sequência."""
    raiz = _raiz(obra)
    fonte = raiz / "00_fonte"
    destino = fonte / re.sub(r"[^\w.\-]+", "_", nome)
    destino.write_bytes(dados)
    txt = _texto_de(destino).replace("\r\n", "\n").replace("\r", "\n")
    txt = re.sub(r"[ \t]+\n", "\n", txt)
    txt = re.sub(r"\n{4,}", "\n\n\n", txt).strip("\n") + "\n"
    limpo = fonte / "texto_limpo.txt"
    atual = limpo.read_text(encoding="utf-8") if limpo.exists() else ""
    limpo.write_text(atual + txt, encoding="utf-8")
    n = len((atual + txt).splitlines())
    _marcar(obra, etapa="fonte importada", linhas=n, arquivos=[*_cfg(obra).get("entrada", {}).get("arquivos", []), destino.name])
    return {"ok": True, "linhas": n, "arquivo": destino.name}


def _cfg(obra):
    return ler_json(_raiz(obra) / "projeto.json", {})


def _marcar(obra, **kw):
    atualizar_json(_raiz(obra) / "projeto.json",
                   lambda cfg: cfg.setdefault("entrada", {}).update(kw, atualizado=time.strftime("%Y-%m-%d %H:%M")))


def _linhas(obra):
    arq = _raiz(obra) / "00_fonte" / "texto_limpo.txt"
    if not arq.exists():
        raise RuntimeError("importe a fonte primeiro")
    return arq.read_text(encoding="utf-8").splitlines()


def _numerado(linhas, a, b):
    return "\n".join(f"L{i}: {linhas[i - 1]}" for i in range(a, min(b, len(linhas)) + 1))


def ler(obra, log=None):
    linhas = _linhas(obra)
    d = _raiz(obra) / "01_biblia" / "leitura"
    d.mkdir(parents=True, exist_ok=True)
    resumo, feitos = "", 0
    cfg = _cfg(obra)
    for k, a in enumerate(range(1, len(linhas) + 1, BLOCO), 1):
        b = min(a + BLOCO - 1, len(linhas))
        arq = d / f"bloco_{k:02d}.json"
        if arq.exists():                                     # retomável
            resumo = ler_json(arq)["resumo_ate_aqui"]
            continue
        r, _ = trabalhador.rodar("ler_bloco", {"obra": {"titulo": cfg.get("titulo"), "tipo": cfg.get("tipo")}, "bloco": {"inicio": a, "fim": b},
                                               "texto": _numerado(linhas, a, b), "resumo_ate_aqui": resumo}, obra, log=log, ep="00")
        gravar_json(arq, {"inicio": a, "fim": b, **r})
        resumo = r["resumo_ate_aqui"]; feitos += 1
        _marcar(obra, etapa=f"lendo: bloco {k} de {-(-len(linhas) // BLOCO)}")
    notas = ["# Notas de leitura (Origami, bloco a bloco) — fonte: 00_fonte/texto_limpo.txt", ""]
    for arq in sorted(d.glob("bloco_*.json")):
        x = ler_json(arq)
        notas += [f"## {arq.stem.replace('_', ' ').capitalize()} — linhas {x['inicio']}–{x['fim']}", x["notas_md"], ""]
    (_raiz(obra) / "01_biblia" / "notas_leitura.md").write_text("\n".join(notas), encoding="utf-8")
    _marcar(obra, etapa="leitura pronta")
    return f"leitura: {feitos} bloco(s) novo(s), {len(list(d.glob('bloco_*.json')))} no total"


def _notas(obra):
    return (_raiz(obra) / "01_biblia" / "notas_leitura.md").read_text(encoding="utf-8")


def estruturar(obra, log=None):
    linhas = _linhas(obra)
    cfg = _cfg(obra)
    r, _ = trabalhador.rodar("estrutura", {"obra": {"titulo": cfg.get("titulo"), "tipo": cfg.get("tipo")}, "total_linhas": len(linhas),
                                           "notas": _notas(obra)}, obra, log=log, ep="00")
    gravar_json(_raiz(obra) / "01_biblia" / "estrutura.json", r)
    def _titulos(cfg):
        for e in r["episodios"]:
            cfg.setdefault("episodios", {}).setdefault(f"{e['n']:02d}", {})["titulo"] = e["titulo"]
    atualizar_json(_raiz(obra) / "projeto.json", _titulos)
    _marcar(obra, etapa="estrutura pronta", episodios=len(r["episodios"]))
    return f"estrutura: {len(r['episodios'])} episódio(s)"


def guiar(obra, log=None):
    linhas = _linhas(obra)
    est = ler_json(_raiz(obra) / "01_biblia" / "estrutura.json")
    if not est:
        raise RuntimeError("faça a estrutura primeiro")
    d = _raiz(obra) / "01_biblia" / "guia_eps"
    d.mkdir(parents=True, exist_ok=True)
    blocos = [ler_json(p) for p in sorted((_raiz(obra) / "01_biblia" / "leitura").glob("bloco_*.json"))]
    resumo_serie = [{k: e[k] for k in ("n", "titulo", "resumo")} for e in est["episodios"]]
    feitos = 0
    for e in est["episodios"]:
        arq = d / f"ep{e['n']:02d}.md"
        if arq.exists():                                     # retomável
            continue
        notas = "\n\n".join(b["notas_md"] for b in blocos if b["fim"] >= e["inicio"] and b["inicio"] <= e["fim"])
        r, _ = trabalhador.rodar("guia_ep", {"obra": _cfg(obra).get("titulo"), "episodio": e, "texto": _numerado(linhas, e["inicio"], e["fim"]),
                                             "notas": notas, "estrutura": resumo_serie}, obra, log=log, ep=f"{e['n']:02d}")
        arq.write_text(r["secao_md"].strip() + "\n", encoding="utf-8")
        feitos += 1
        _marcar(obra, etapa=f"guia: episódio {e['n']} de {len(est['episodios'])}")
    _marcar(obra, etapa="guia dos episódios pronto")
    return f"guia: {feitos} episódio(s) novo(s)"


def consolidar(obra, log=None):
    """Bíblia, visão geral e inconsistências; monta o guia_completo.md no formato que a Mesa lê."""
    raiz = _raiz(obra)
    est = ler_json(raiz / "01_biblia" / "estrutura.json")
    secoes = [(raiz / "01_biblia" / "guia_eps" / f"ep{e['n']:02d}.md").read_text(encoding="utf-8") for e in est["episodios"]]
    cfg = _cfg(obra)
    r, _ = trabalhador.rodar("obra_biblia", {"obra": {"titulo": cfg.get("titulo"), "tipo": cfg.get("tipo"), "pov": cfg.get("pov")},
                                             "estrutura": est, "guia": "\n\n".join(secoes), "notas": _notas(obra)}, obra, log=log, ep="00")
    # guia completo (a Mesa lê "## Ep. NN · Título (Lx–y)")
    cab = [f"# Guia completo de *{cfg.get('titulo')}* (leitura integral da fonte)",
           f"Leitura feita pelo Origami em {time.strftime('%d/%m/%Y')}, de `00_fonte/texto_limpo.txt` ({len(_linhas(obra))} linhas). \"L\" = linha da fonte.",
           "", "**Como usar:** episódio por episódio, item por item. As inconsistências são decididas na Mesa quando o episódio em que caem for produzido.", "", "---", ""]
    inc = ["", "# INCONSISTÊNCIAS E AJUSTES (viram decisões na Mesa)"] + [f"{i}. **{x['titulo']}** (Eps. {', '.join(x['eps'])}): {x['contexto']}"
                                                                     for i, x in enumerate(r["inconsistencias"], 1)]
    (raiz / "01_biblia" / "guia_completo.md").write_text("\n".join(cab) + "\n\n".join(secoes) + "\n\n---\n\n" + r["visao_geral_md"] + "\n" + "\n".join(inc) + "\n",
                                                        encoding="utf-8")
    (raiz / "01_biblia" / "biblia.md").write_text(r["biblia_md"], encoding="utf-8")
    dec = {"regras": r["regras"], "itens": [{"id": f"I-{i:02d}", "tipo": "inconsistencia", "eps": [f"{int(e):02d}" for e in x["eps"]], "titulo": x["titulo"],
                                             "contexto": x["contexto"], "opcoes": x["opcoes"], "recomendada": x["recomendada"],
                                             "recomendacao": x["recomendacao"], "estado": "pendente"} for i, x in enumerate(r["inconsistencias"], 1)]}
    gravar_json(raiz / "01_biblia" / "decisoes.json", dec)
    # a base vem de recursos/modelos/guia_arte_base.json
    base = {k: v for k, v in ler_json(RECURSOS / "modelos" / "guia_arte_base.json", {}).items() if k != "_nota"}
    padrao = next((k for d in r["guia_arte"].values() for k in d if k != "retrato"), "trabalho")
    ctxs = sorted({k for d in r["guia_arte"].values() for k in d if k != "retrato"})
    arq_guia = raiz / "01_biblia" / "guia_arte.json"
    antigo = ler_json(arq_guia, {})              # refazer a bíblia não apaga o que o autor já ajustou no guia
    gravar_json(arq_guia, {**base, **antigo, "_nota": "Rascunho do Origami: revise as descrições (são fixas para a série inteira).",
                           "contexto_padrao": antigo.get("contexto_padrao", padrao), "contextos": antigo.get("contextos") or ctxs,
                           "personagens": {**r["guia_arte"], **antigo.get("personagens", {})}})
    # pronúncia é substituição de texto na hora de falar: só grafias curtas, nunca explicações
    pron = {k: v for k, v in r["pronuncia"].items() if v and len(v) <= len(k) + 12 and not re.search(r"[()]|tônic|fechad|abert", v, re.I)}
    if pron:
        gravar_json(raiz / "01_biblia" / "pronuncia.json", {"_nota": "Sugestão do Origami: confira ouvindo.", **pron})
    cfg = _cfg(obra)
    for v in r["elenco"]:
        cfg.setdefault("nomes", {})[v["id"]] = v["nome"]
        cfg.setdefault("vozes_pedidas", {})[v["id"]] = {"origem": "elenco da obra", "eps": ["01"], "descricao": v["descricao"], "frase": "",
                                                       "sugestao": {"genero": v["genero"], "idade": v["idade"], "tom": v["tom"]},
                                                       "pedido_em": time.strftime("%Y-%m-%d")}
        if v.get("narradora"):
            cfg["pov"] = f"1a:{v['id']}"; cfg.setdefault("video", {})["narrador"] = v["id"]
    cfg.setdefault("entrada", {}).update(etapa="pronta para o Ep. 01", atualizado=time.strftime("%Y-%m-%d %H:%M"))
    gravar_json(raiz / "projeto.json", cfg)
    return (f"bíblia: {len(r['inconsistencias'])} inconsistência(s) para decidir, {len(r['elenco'])} voz(es) pedidas, "
            f"{len(r['guia_arte'])} personagem(ns) no guia de arte")


def painel(obra):
    raiz = _raiz(obra)
    cfg = _cfg(obra)
    blocos = len(list((raiz / "01_biblia" / "leitura").glob("bloco_*.json"))) if (raiz / "01_biblia" / "leitura").exists() else 0
    linhas = len(_linhas(obra)) if (raiz / "00_fonte" / "texto_limpo.txt").exists() else 0
    total_blocos = -(-linhas // BLOCO) if linhas else 0
    est = ler_json(raiz / "01_biblia" / "estrutura.json")
    guias = len(list((raiz / "01_biblia" / "guia_eps").glob("ep*.md"))) if (raiz / "01_biblia" / "guia_eps").exists() else 0
    passos = [
        {"id": "fonte", "nome": "Importar a fonte", "feito": linhas > 0, "info": f"{linhas} linhas" if linhas else ""},
        {"id": "ler", "nome": "Ler a obra inteira (bloco a bloco)", "feito": linhas and blocos >= total_blocos, "info": f"{blocos}/{total_blocos} blocos"},
        {"id": "estrutura", "nome": "Dividir em episódios", "feito": bool(est), "info": f"{len(est['episodios'])} episódios" if est else ""},
        {"id": "guia", "nome": "Guia de cada episódio", "feito": bool(est) and guias >= len(est["episodios"]), "info": f"{guias}/{len(est['episodios']) if est else 0}"},
        {"id": "biblia", "nome": "Bíblia, inconsistências, guia de arte e elenco", "feito": (raiz / "01_biblia" / "guia_completo.md").exists(), "info": ""},
    ]
    return {"obra": obra, "titulo": cfg.get("titulo"), "etapa": cfg.get("entrada", {}).get("etapa"), "passos": passos,
            "auto": bool(cfg.get("entrada", {}).get("auto")),
            "estrutura": est, "custo_estimado": f"~US$ {0.35 * total_blocos + 0.4 * (len(est['episodios']) if est else max(1, linhas // 450)) + 1:.0f}" if linhas else ""}
