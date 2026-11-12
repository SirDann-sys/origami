# Elenco: criar, ouvir e aprovar vozes (banco compartilhado entre obras).
# Mesma receita das vozes aprovadas no piloto: VoiceStudio/OmniVoice em modo "design" (instruct: gênero, idade, tom)
# + semente; 4 candidatas lendo uma fala real do personagem; a escolhida vira banco/<id>/ (ref.wav + voz.json)
# e entra no elenco da obra (projeto.json). A decisão da Mesa sobre a voz é fechada junto.
import json, shutil, subprocess, tempfile, time
from pathlib import Path
import requests
from .config import VOZES, VOICESTUDIO, FFMPEG
from .obra import Episodio, ler_json, gravar_json, atualizar_json
from .config import PROJETOS

BANCO = VOZES
CANDS = BANCO / "_candidatas"
GENEROS = {"feminina": "female", "masculina": "male"}
IDADES = {"jovem adulta": "young adult", "meia-idade": "middle-aged", "idosa": "elderly", "adolescente": "teenager"}
TONS = {"muito grave": "very low pitch", "grave": "low pitch", "médio": "moderate pitch", "agudo": "high pitch"}


def _cfg(obra):
    return ler_json(PROJETOS / obra / "projeto.json")


def _falas(obra, voz):
    out = []
    for f in sorted((PROJETOS / obra / "04_roteiro_audio").glob("ep[0-9][0-9].json")):
        for p in ler_json(f, {}).get("partes", []):
            out += [x["texto"] for x in p["falas"] if x["voz"] == voz]
    return out


def _nota_frase(t):
    """Boa frase de teste: inteira e fluente (12–30 palavras), sem reticências nem cortes que escondem o timbre."""
    n = len(t.split())
    quebras = t.count("...") + t.count("…") + t.count("—") + t.count(" - ")
    return (12 <= n <= 30) * 10 - quebras * 6 - abs(n - 20) * 0.2


def _frase_do_personagem(obra, voz):
    """A fala real mais fluente do personagem (fala quebrada ou hesitante esconde o timbre).
    Se nenhuma for boa, devolve vazio: use "Sugerir frases"."""
    falas = sorted(_falas(obra, voz), key=_nota_frase, reverse=True)
    return falas[0] if falas and _nota_frase(falas[0]) > 0 else ""


def sugerir_frases(obra, personagem, descricao=""):
    """Frases de teste escritas para revelar o timbre e o jeito do personagem (Opus, ~10 s)."""
    from . import trabalhador
    biblia = PROJETOS / obra / "01_biblia" / "biblia.md"
    b = biblia.read_text(encoding="utf-8") if biblia.exists() else ""
    cfg = _cfg(obra)
    nome = cfg.get("nomes", {}).get(personagem, personagem)
    pedido = cfg.get("vozes_pedidas", {}).get(personagem, {})
    trecho = "\n".join(l for l in b.splitlines() if personagem.lower() in l.lower() or nome.lower() in l.lower())[:4000]
    r, _ = trabalhador.rodar("frase_voz", {"personagem": {"id": personagem, "nome": nome, "descricao": descricao or pedido.get("descricao", "")},
                                           "falas": _falas(obra, personagem)[:40], "biblia": trecho}, obra)
    r["recomendada"] = min(max(int(r.get("recomendada", 1)) - 1, 0), len(r["frases"]) - 1)   # o Opus numera 1–3; a tela usa 0–2
    return r


def painel(obra):
    cfg = _cfg(obra)
    elenco = []
    for pers, vid in cfg.get("elenco", {}).items():
        v = ler_json(BANCO / vid / "voz.json", {})
        elenco.append({"personagem": pers, "voz": vid, "nome": v.get("nome", vid), "status": v.get("status"),
                       "ref": str(BANCO / vid / "ref.wav"), "receita": v.get("receita", {})})
    # quem precisa de voz: decisões de voz pendentes + vozes dos roteiros sem elenco
    precisa = {}
    for f in sorted((PROJETOS / obra / "04_roteiro_audio").glob("ep[0-9][0-9].json")):
        r = ler_json(f, {})
        for vid, desc in r.get("vozes", {}).items():
            if vid not in cfg.get("elenco", {}):
                precisa.setdefault(vid, {"personagem": vid, "descricao": desc, "ep": f.stem[2:4]})
    # pedidos de voz abertos por decisões da Mesa ("criar voz nova") ficam aqui até a voz ser aprovada
    for pers, p in cfg.get("vozes_pedidas", {}).items():
        if pers not in cfg.get("elenco", {}):
            precisa[pers] = {"personagem": pers, "descricao": p.get("descricao", ""), "ep": ", ".join(p.get("eps", [])),
                             "origem": p.get("origem"), "sugestao": p.get("sugestao", {}), "frase": p.get("frase", "")}
    dec = ler_json(PROJETOS / obra / "01_biblia" / "decisoes.json", {"itens": []})
    decisoes = [d for d in dec["itens"] if d["tipo"] == "producao" and "voz" in d["titulo"].lower() and d["estado"] == "pendente"]
    cands = {}
    for d in CANDS.glob(f"{obra}__*"):
        if d.name.split("__", 1)[1] in cfg.get("elenco", {}):
            continue                                     # já aprovada: as candidatas ficam no arquivo, fora da tela
        cands[d.name.split("__", 1)[1]] = [{"arquivo": str(w), "info": ler_json(w.with_suffix(".json"), {})}
                                         for w in sorted(d.glob("*.wav"), key=lambda p: p.stat().st_mtime)]
    return {"obra": obra, "elenco": elenco, "precisa": list(precisa.values()), "decisoes": decisoes, "candidatas": cands,
            "opcoes": {"generos": list(GENEROS), "idades": list(IDADES), "tons": list(TONS)},
            "frases": {p: ((precisa.get(p, {}).get("frase") if _nota_frase(precisa.get(p, {}).get("frase") or "") > 0 else "")
                           or _frase_do_personagem(obra, p))
                       for p in list(precisa) + [e["personagem"] for e in elenco]}}


def _arquivar_candidatas(obra, personagem):
    """Depois de aprovar, as candidatas saem da tela e vão para _candidatas/_aprovadas (guardadas para comparar depois)."""
    d = CANDS / f"{obra}__{personagem}"
    if d.exists():
        destino = CANDS / "_aprovadas" / f"{obra}__{personagem}__{time.strftime('%Y%m%d_%H%M')}"
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(d), str(destino))


def gerar_candidatas(obra, personagem, genero, idade, tom, frase, velocidade=0.92, n=4, log=None):
    """Roda no worker (recurso gpu:voz): n sementes da mesma descrição lendo a mesma frase."""
    instruct = f"{GENEROS[genero]}, {IDADES[idade]}, {TONS[tom]}"
    d = CANDS / f"{obra}__{personagem}"; d.mkdir(parents=True, exist_ok=True)
    ja = [ler_json(w.with_suffix(".json"), {}).get("seed", 0) for w in d.glob("*.wav")]
    base = (max(ja) + 1) if ja else 1
    feitas = []
    for s in range(base, base + n):
        try:
            requests.post(VOICESTUDIO + "/system/flush-memory", timeout=30)
        except requests.RequestException:
            pass
        dados = {"text": frase, "language": "pt", "instruct": instruct, "seed": s, "engine": "omnivoice",
                 "effect_preset": "warm", "speed": velocidade, "num_step": 64}
        r = requests.post(VOICESTUDIO + "/generate", data=dados, timeout=900)
        r.raise_for_status()
        nome = f"{personagem}_{genero[0]}_{idade.split()[0]}_{tom.replace(' ', '')}_s{s}"
        with tempfile.TemporaryDirectory() as t:
            b = Path(t) / "b.wav"; b.write_bytes(r.content)
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(b), "-af", "deesser=i=0.4:m=0.5:f=0.5",
                            "-c:a", "pcm_s24le", str(d / f"{nome}.wav")], check=True)
        gravar_json(d / f"{nome}.json", {"seed": s, "instruct": instruct, "genero": genero, "idade": idade, "tom": tom,
                                          "velocidade": velocidade, "frase": frase})
        feitas.append(nome)
        if log:
            log.write(f"candidata {nome}\n"); log.flush()
    return f"{len(feitas)} candidata(s) para {personagem}: {', '.join(feitas)}"


def aprovar(obra, personagem, arquivo):
    w = Path(arquivo)
    info = ler_json(w.with_suffix(".json"))
    g = "f" if info["genero"] == "feminina" else "m"
    vid = f"omni_{g}_{info['idade'].split()[0].replace('-', '')}_{info['tom'].replace(' ', '')}_s{info['seed']}"
    pasta = BANCO / vid
    if pasta.exists():
        vid += "_" + personagem; pasta = BANCO / vid
    pasta.mkdir(parents=True)
    shutil.copyfile(w, pasta / "ref.wav")
    (pasta / "ref.txt").write_text(info["frase"], encoding="utf-8")
    cfg = _cfg(obra)
    gravar_json(pasta / "voz.json", {
        "id": vid, "nome": f"{info['genero'].capitalize()}, {info['idade']}, tom {info['tom']} (aprovada como {personagem})",
        "status": "aprovada", "aprovada_em": time.strftime("%Y-%m-%d"), "obras": [f"{cfg.get('titulo')}: {personagem}"],
        "receita": {"app": "VoiceStudio (API http://127.0.0.1:3900/generate)", "engine": "omnivoice", "modelo": "k2-fsa/OmniVoice",
                    "instruct": info["instruct"], "language": "pt", "seed": info["seed"], "speed": info["velocidade"], "num_step": 64,
                    "effect_preset": "warm", "pos_processamento": "ffmpeg deesser=i=0.4:m=0.5:f=0.5"},
        "notas": "Criada e aprovada no Origami (aba Elenco)."})
    def _aplicar(cfg):
        cfg.setdefault("elenco", {})[personagem] = vid
        cfg.get("vozes_pedidas", {}).pop(personagem, None)          # pedido atendido
    _arquivar_candidatas(obra, personagem)
    atualizar_json(PROJETOS / obra / "projeto.json", _aplicar)
    # fecha a decisão de voz deste personagem, se houver
    arq = PROJETOS / obra / "01_biblia" / "decisoes.json"
    dec = ler_json(arq, {"itens": []})
    for d in dec["itens"]:
        if d["estado"] == "pendente" and d["tipo"] == "producao" and (d["id"].endswith("-" + personagem) or f"voz" in d["titulo"].lower()
                                                                       and personagem.lower() in (d["titulo"] + d["contexto"]).lower()):
            d.update(estado="decidido", decisao=f"Voz criada e aprovada: {vid}", data=time.strftime("%Y-%m-%d"))
    gravar_json(arq, dec)
    return {"ok": True, "voz": vid}
