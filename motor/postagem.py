# Postagem: o calendário da obra (o que postar, onde e quando) e a integração com o Postiz, que agenda nas redes.
#   07_publicacao/calendario.json da obra:
#     config  → horários, fuso, redes curtas, ajustes de cada rede (settings do Postiz)
#     uploads → arquivo local → URL no Postiz (o vídeo sobe uma vez e serve às 3 redes)
#     itens   → {id, data, hora, ep, peca (parte:N | completo | capitulo), rede, estado, texto, titulo, postiz_id, origem, nota}
#   estados: planejado → agendado (no Postiz) → publicado | erro;  feito_manual (Wattpad ou postado à mão)
#   O Wattpad não tem integração: fica no calendário como lembrete, com o arquivo e o texto à mão.
# O autor aprova: sugerir só PLANEJA; nada vai para as redes sem ele clicar em "Agendar".
import json, re, shutil, subprocess, time, uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from .obra import Episodio, ler_json, gravar_json
from .config import PROJETOS

REDES = {"tiktok": "TikTok", "instagram": "Instagram Reels", "shorts": "YouTube Shorts", "youtube": "YouTube", "wattpad": "Wattpad"}
CURTAS = ["tiktok", "instagram", "shorts"]
# identificador do canal no Postiz para cada rede do calendário
CANAL = {"tiktok": ("tiktok",), "instagram": ("instagram", "instagram-standalone"), "shorts": ("youtube",), "youtube": ("youtube",)}
CONFIG_PADRAO = {
    "fuso": "-03:00", "hora_curtos": "19:00", "hora_youtube": "17:00", "hora_wattpad": "20:00", "redes_curtas": CURTAS,
    # ajustes conferidos com `postiz integrations:settings` quando os canais forem conectados (regras de cada rede)
    "ajustes": {
        "tiktok": {"privacy_level": "PUBLIC_TO_EVERYONE", "duet": False, "stitch": False, "comment": True,
                   "content_posting_method": "DIRECT_POST"},
        "instagram": {"post_type": "post"},
        "shorts": {"type": "public"},
        "youtube": {"type": "public"},
    },
}


# ------------------------------------------------------------------ Postiz (CLI)
def _cli():
    exe = shutil.which("postiz") or shutil.which("postiz.cmd")
    if not exe:
        raise RuntimeError("o Postiz não está instalado neste PC (npm install -g postiz)")
    return exe


def postiz(*args, timeout=600):
    """Roda o CLI do Postiz e devolve o JSON da resposta (o CLI imprime um cabeçalho antes do JSON)."""
    r = subprocess.run([_cli(), *map(str, args)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    saida = (r.stdout or "") + (r.stderr or "")
    if "Not authenticated" in saida or "expired or invalid" in saida:
        raise RuntimeError("o Postiz não está conectado: faça o login (aba Postagem → Conectar)")
    m = re.search(r"[\[{]", r.stdout or "")
    if r.returncode != 0 or not m:
        raise RuntimeError(f"Postiz: {saida.strip()[-400:] or 'sem resposta'}")
    try:
        return json.loads(r.stdout[m.start():])
    except json.JSONDecodeError:
        raise RuntimeError(f"Postiz: resposta inesperada: {r.stdout.strip()[-300:]}")


def conexao():
    """Login e canais conectados."""
    try:
        _cli()
    except RuntimeError as e:
        return {"instalado": False, "logado": False, "erro": str(e), "canais": []}
    r = subprocess.run([_cli(), "auth:status"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if "valid" not in (r.stdout or "") or "invalid" in (r.stdout or "") or "Not authenticated" in (r.stdout or ""):
        return {"instalado": True, "logado": False, "erro": (r.stdout or r.stderr).strip()[-300:], "canais": []}
    try:
        canais = postiz("integrations:list", timeout=60)
    except RuntimeError as e:
        return {"instalado": True, "logado": True, "erro": str(e), "canais": []}
    canais = canais if isinstance(canais, list) else canais.get("integrations", [])
    return {"instalado": True, "logado": True, "erro": "",
            "canais": [{"id": c.get("id"), "rede": c.get("identifier"), "nome": c.get("name"), "foto": c.get("picture"),
                        "desativado": bool(c.get("disabled"))} for c in canais]}


def regras(canal_id):
    """Regras e campos de um canal no Postiz (o que cada ajuste faz)."""
    return postiz("integrations:settings", canal_id, timeout=60)


# ------------------------------------------------------------------ calendário
def _arq(obra):
    return PROJETOS / obra / "07_publicacao" / "calendario.json"


def ler(obra):
    d = ler_json(_arq(obra), {})
    cfg = {**CONFIG_PADRAO, **d.get("config", {})}
    cfg["ajustes"] = {**CONFIG_PADRAO["ajustes"], **d.get("config", {}).get("ajustes", {})}
    return {"config": cfg, "uploads": d.get("uploads", {}), "itens": d.get("itens", [])}


def gravar(obra, d):
    _arq(obra).parent.mkdir(parents=True, exist_ok=True)
    d["itens"].sort(key=lambda x: (x["data"], x["hora"], list(REDES).index(x["rede"]) if x["rede"] in REDES else 9))
    gravar_json(_arq(obra), d)


def _kit(obra, ep):
    return ler_json(Episodio(obra, ep).publicacao / "kit.json", {})


def arquivos(obra, ep, peca, rede):
    """Arquivo(s) da entrega para a peça: vídeo e capa/miniatura; o Wattpad aponta o .html e as imagens."""
    e = Episodio(obra, ep)
    sg, tit = e.sigla(), e.titulo_ep()
    ent = e.entrega
    if peca == "completo":
        return {"video": str(ent / f"{sg}_Ep{e.ep}_{tit}_16x9.mp4"), "capa": str(ent / f"miniatura_ep{e.ep}.jpg")}
    if peca.startswith("parte:"):
        n = int(peca.split(":")[1])
        return {"video": str(ent / f"{sg}_Ep{e.ep}_Parte{n:02d}_9x16.mp4"), "capa": str(ent / "capas_partes" / f"capa_parte_{n:02d}.jpg")}
    html = next(iter(sorted(ent.glob("wattpad_cap*.html"))), None)
    return {"html": str(html) if html else "", "imagens": str(ent / "wattpad_imagens")}


def textos(obra, ep, peca, rede):
    """Texto e título que vão na rede, tirados do kit do episódio."""
    k = _kit(obra, ep)
    if peca == "completo":
        y = k.get("youtube", {})
        return y.get("titulo", ""), y.get("descricao", "")
    if peca.startswith("parte:"):
        n = int(peca.split(":")[1])
        p = next((x for x in k.get("partes", []) if x["n"] == n), {})
        return p.get("short_titulo", ""), p.get("legenda", "")
    w = k.get("wattpad", {})
    return w.get("titulo_capitulo", ""), "Colar o .html no editor do Wattpad; imagens: veja a aba Publicação."


def _item(data_, hora, ep, peca, rede, origem="sugestao"):
    return {"id": uuid.uuid4().hex[:10], "data": data_, "hora": hora, "ep": ep, "peca": peca, "rede": rede,
            "estado": "planejado", "titulo": None, "texto": None, "postiz_id": None, "origem": origem, "nota": "", "erro": ""}


def sugerir(obra, inicio, eps, redes=None, wattpad="d0", intervalo=0):
    """Plano padrão (manual de postagem): D1 YouTube completo + Parte 1; 1 parte por dia; o episódio seguinte começa no dia
    seguinte à última parte (+ intervalo). Wattpad: "d0" = todos os capítulos na véspera do D1 (o autor: "Wattpad sempre
    primeiro"); "vespera" = cada capítulo na véspera do seu episódio. Refazer só mexe em itens da sugestão ainda planejados."""
    d = ler(obra); cfg = d["config"]
    redes = redes or cfg["redes_curtas"]
    feitos = {(x["ep"], x["peca"], x["rede"]) for x in d["itens"] if x["estado"] != "planejado" or x["origem"] == "manual"}
    d["itens"] = [x for x in d["itens"] if not (x["origem"] == "sugestao" and x["estado"] == "planejado")]
    dia = date.fromisoformat(inicio)
    novos = []
    if wattpad == "d0":
        novos += [_item((dia - timedelta(days=1)).isoformat(), cfg["hora_wattpad"], f"{int(e):02d}", "capitulo", "wattpad") for e in eps]
    for k, ep in enumerate(eps):
        ep = f"{int(ep):02d}"
        n_partes = len(_kit(obra, ep).get("partes", [])) or len(Episodio(obra, ep).partes())
        if wattpad == "vespera":
            novos.append(_item((dia - timedelta(days=1)).isoformat(), cfg["hora_wattpad"], ep, "capitulo", "wattpad"))
        novos.append(_item(dia.isoformat(), cfg["hora_youtube"], ep, "completo", "youtube"))
        for n in range(1, n_partes + 1):
            for r in redes:
                novos.append(_item((dia + timedelta(days=n - 1)).isoformat(), cfg["hora_curtos"], ep, f"parte:{n}", r))
        dia = dia + timedelta(days=n_partes + intervalo)
    novos = [x for x in novos if (x["ep"], x["peca"], x["rede"]) not in feitos]
    eps_cfg = Episodio(obra, eps[0]).cfg.get("episodios", {})
    for x in novos:                                   # capítulo já publicado no Wattpad (ex.: o cap. 1) entra como feito
        if x["rede"] == "wattpad" and eps_cfg.get(x["ep"], {}).get("status") == "publicado":
            x["estado"] = "feito_manual"; x["nota"] = "já publicado no Wattpad"
    d["itens"] += novos
    gravar(obra, d)
    return {"ok": True, "novos": len(novos), "mantidos": len(feitos)}


def painel(obra):
    d = ler(obra)
    hoje = date.today().isoformat()
    for x in d["itens"]:
        tit, txt = textos(obra, x["ep"], x["peca"], x["rede"])
        x["titulo_final"] = x["titulo"] if x["titulo"] is not None else tit
        x["texto_final"] = x["texto"] if x["texto"] is not None else txt
        x["arquivos"] = arquivos(obra, x["ep"], x["peca"], x["rede"])
        x["atrasado"] = x["estado"] == "planejado" and x["data"] < hoje
        x["integravel"] = x["rede"] in CANAL
    eps = sorted(p.name[2:] for p in (PROJETOS / obra / "07_publicacao").glob("ep[0-9][0-9]") if (p / "kit.json").exists())
    partes = {}
    for e in eps:                       # quantas partes cada episódio tem
        try:
            from .obra import Episodio
            partes[e] = len(Episodio(obra, e).partes())
        except Exception:
            partes[e] = len((ler_json(PROJETOS / obra / "07_publicacao" / f"ep{e}" / "kit.json", {}) or {}).get("partes", [])) or 8
    return {"obra": obra, "config": d["config"], "itens": d["itens"], "redes": REDES, "episodios": eps, "hoje": hoje, "partes": partes}


def salvar_item(obra, item):
    d = ler(obra)
    x = next((i for i in d["itens"] if i["id"] == item.get("id")), None)
    if x is None:
        x = _item(item["data"], item.get("hora") or d["config"]["hora_curtos"], f"{int(item['ep']):02d}", item["peca"], item["rede"], "manual")
        d["itens"].append(x)
    if x["estado"] == "agendado" and any(k in item and item[k] != x[k] for k in ("data", "hora", "texto", "titulo")):
        raise RuntimeError("este post já está agendado no Postiz: cancele o agendamento antes de editar")
    for k in ("data", "hora", "texto", "titulo", "nota", "rede", "peca"):
        if k in item:
            x[k] = item[k]
    if "ep" in item:
        x["ep"] = f"{int(item['ep']):02d}"
    if x["origem"] == "sugestao" and any(k in item for k in ("data", "hora", "texto", "titulo")):
        x["origem"] = "editado"          # editado à mão: refazer a sugestão não mexe mais nele
    gravar(obra, d)
    return {"ok": True, "id": x["id"]}


def marcar(obra, id_, estado, link=""):
    """Marca feito à mão (Wattpad ou postado fora do app), ou volta para planejado."""
    d = ler(obra)
    x = next(i for i in d["itens"] if i["id"] == id_)
    if estado not in ("feito_manual", "planejado", "pulado"):
        raise RuntimeError("estado inválido")
    if x["estado"] == "agendado":
        raise RuntimeError("cancele o agendamento no Postiz antes")
    x["estado"] = estado; x["link"] = link; x["marcado_em"] = time.strftime("%Y-%m-%d %H:%M")
    gravar(obra, d)
    # a Entrega mostra o mesmo registro
    from . import publicacao
    pl, pc = publicacao.PLATAFORMA_DE.get(x["rede"]), publicacao.peca_entrega(x["peca"])
    if pl:
        if estado == "feito_manual":
            publicacao.registrar(obra, x["ep"], pl, pc, link, _do_calendario=True)
        else:
            publicacao.desfazer(obra, x["ep"], pl, pc, _do_calendario=True)
    return {"ok": True}


def excluir(obra, id_):
    d = ler(obra)
    x = next(i for i in d["itens"] if i["id"] == id_)
    if x["estado"] == "agendado":
        raise RuntimeError("cancele o agendamento no Postiz antes de excluir")
    d["itens"] = [i for i in d["itens"] if i["id"] != id_]
    gravar(obra, d)
    return {"ok": True}


def mover(obra, id_, data_):
    return salvar_item(obra, {"id": id_, "data": data_})


# ------------------------------------------------------------------ agendar no Postiz (roda como job do motor)
def _iso_utc(data_, hora, fuso):
    sinal = -1 if fuso.startswith("-") else 1
    hh, mm = map(int, fuso[1:].split(":"))
    loc = datetime.fromisoformat(f"{data_}T{hora}:00").replace(tzinfo=timezone(sinal * timedelta(hours=hh, minutes=mm)))
    return loc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canal(canais, rede):
    for c in canais:
        if c["rede"] in CANAL[rede] and not c["desativado"]:
            return c["id"]
    raise RuntimeError(f"{REDES[rede]}: canal não conectado no Postiz")


def _subir(d, caminho, log):
    """Sobe o arquivo uma vez só (o mesmo vídeo serve ao TikTok, ao Instagram e ao Shorts)."""
    p = Path(caminho)
    if not p.exists():
        raise RuntimeError(f"arquivo não encontrado: {p.name} (rode a entrega do episódio)")
    st = p.stat()
    u = d["uploads"].get(str(p))
    if u and u.get("tamanho") == st.st_size and u.get("mtime") == int(st.st_mtime):
        return u["url"]
    log.write(f"enviando {p.name} ({st.st_size / 1e6:.0f} MB)…\n"); log.flush()
    r = postiz("upload", str(p), timeout=3600)
    url = r.get("path") if isinstance(r, dict) else None
    if not url:
        raise RuntimeError(f"upload sem URL: {str(r)[:200]}")
    d["uploads"][str(p)] = {"url": url, "tamanho": st.st_size, "mtime": int(st.st_mtime)}
    return url


def agendar(obra, ids, log):
    """Sobe a mídia e cria o post agendado no Postiz para cada item (só redes integradas e itens planejados)."""
    d = ler(obra); cfg = d["config"]
    canais = conexao()
    if not canais["logado"]:
        raise RuntimeError("o Postiz não está conectado")
    ok, falhas = [], []
    for x in d["itens"]:
        if x["id"] not in ids or x["estado"] != "planejado" or x["rede"] not in CANAL:
            continue
        try:
            canal = _canal(canais["canais"], x["rede"])
            tit, txt = textos(obra, x["ep"], x["peca"], x["rede"])
            tit = x["titulo"] if x["titulo"] is not None else tit
            txt = x["texto"] if x["texto"] is not None else txt
            arq = arquivos(obra, x["ep"], x["peca"], x["rede"])
            url = _subir(d, arq["video"], log)
            gravar(obra, d)                                   # guarda o upload mesmo se o post falhar
            ajustes = dict(cfg["ajustes"].get(x["rede"], {}))
            if x["rede"] in ("shorts", "youtube"):
                ajustes["title"] = tit[:100]
            args = ["posts:create", "-c", txt, "-m", url, "-s", _iso_utc(x["data"], x["hora"], cfg["fuso"]), "-i", canal,
                    "--settings", json.dumps(ajustes, ensure_ascii=False)]
            r = postiz(*args, timeout=600)
            pid = _id_post(r)
            x.update(estado="agendado", postiz_id=pid, erro="", agendado_em=time.strftime("%Y-%m-%d %H:%M"))
            ok.append(x["id"])
            log.write(f"agendado: Ep {x['ep']} {x['peca']} {REDES[x['rede']]} {x['data']} {x['hora']} → {pid}\n"); log.flush()
        except Exception as e:
            x.update(estado="planejado", erro=str(e)[:300])
            falhas.append(f"{x['ep']} {x['peca']} {x['rede']}: {e}")
            log.write(f"FALHOU: {falhas[-1]}\n"); log.flush()
        gravar(obra, d)
    return f"{len(ok)} post(s) agendado(s) no Postiz" + (f" · {len(falhas)} com erro (veja a aba Postagem)" if falhas else "")


def _id_post(r):
    """O id do post criado (o formato da resposta varia: objeto, lista ou {posts:[…]})."""
    if isinstance(r, list) and r:
        r = r[0]
    if isinstance(r, dict):
        for k in ("postId", "id"):
            if r.get(k):
                return r[k]
        for v in r.values():
            if isinstance(v, (list, dict)):
                pid = _id_post(v)
                if pid:
                    return pid
    return None


def cancelar(obra, id_):
    d = ler(obra)
    x = next(i for i in d["itens"] if i["id"] == id_)
    if x["estado"] != "agendado":
        raise RuntimeError("este item não está agendado")
    if x.get("postiz_id"):
        postiz("posts:delete", x["postiz_id"], timeout=120)
    x.update(estado="planejado", postiz_id=None)
    gravar(obra, d)
    return {"ok": True}


def sincronizar(obra):
    """Lê no Postiz o que já foi publicado ou deu erro."""
    d = ler(obra)
    ag = [x for x in d["itens"] if x["estado"] in ("agendado", "erro") and x.get("postiz_id")]
    if not ag:
        return {"ok": True, "mudou": 0}
    ini = min(x["data"] for x in ag); fim = max(x["data"] for x in ag)
    r = postiz("posts:list", "--startDate", f"{ini}T00:00:00Z", "--endDate", f"{(date.fromisoformat(fim) + timedelta(days=2)).isoformat()}T00:00:00Z", timeout=120)
    posts = r.get("posts", r) if isinstance(r, dict) else r
    por_id = {p.get("id"): p for p in posts if isinstance(p, dict)}
    mudou = 0
    for x in ag:
        p = por_id.get(x["postiz_id"])
        if not p:
            continue
        st = str(p.get("status") or p.get("state") or "").upper()
        novo = "publicado" if st in ("PUBLISHED", "PUBLISH") else "erro" if st in ("ERROR", "FAILED") else x["estado"]
        if p.get("releaseURL"):
            x["link"] = p["releaseURL"]
        if novo != x["estado"]:
            x["estado"] = novo; x["erro"] = str(p.get("error") or "")[:300]; mudou += 1
    gravar(obra, d)
    return {"ok": True, "mudou": mudou}


# ------------------------------------------------------------------ login (fluxo de dispositivo) e abrir pasta
LOGIN = {"proc": None}


def iniciar_login():
    """Abre o login do Postiz: o CLI mostra um código e um endereço; o autor confirma no navegador (a senha é dele, não do app)."""
    import threading
    if LOGIN["proc"] and LOGIN["proc"].poll() is None:
        LOGIN["proc"].kill()
    p = subprocess.Popen([_cli(), "auth:login"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace")
    LOGIN["proc"] = p
    linhas, fim = [], time.time() + 25
    while time.time() < fim:
        l = p.stdout.readline()
        if not l:
            break
        linhas.append(l.strip())
        txt = "\n".join(linhas)
        cod = re.search(r"│\s+([A-Z0-9-]{4,})\s+│", txt)
        url = re.search(r"https?://\S+", txt)
        if cod and url:
            threading.Thread(target=lambda: p.wait(), daemon=True).start()   # segue esperando a confirmação
            return {"codigo": cod.group(1), "url": url.group(0)}
    raise RuntimeError("o Postiz não mostrou o código de login: " + " ".join(linhas)[-300:])


def abrir(caminho):
    """Mostra o arquivo no Explorer (só dentro das obras)."""
    p = Path(caminho).resolve()
    if not str(p).startswith(str(PROJETOS.resolve())) or not p.exists():
        raise RuntimeError("arquivo fora da obra ou inexistente")
    subprocess.Popen(["explorer", "/select,", str(p)] if p.is_file() else ["explorer", str(p)])
    return {"ok": True}
