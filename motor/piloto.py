# Piloto automático. Com a fila parada, o
# motor olha cada episódio com o piloto ligado e põe na fila o PRÓXIMO passo possível. Ele NUNCA passa um portão do autor:
#   decisões da Mesa · aprovar o texto-mestre · escalar as vozes · ouvir e aprovar o áudio · (confirmar imagens: a
#   pré-escolhida da triagem vale sozinha depois do prazo).
# Não refaz por código novo (usa etapas.situacao) e não insiste num passo que deu erro: vira pendência para o autor.
# Ligar: Mesa → "Piloto automático" (projeto.json → episodios.NN.piloto = true). Obra nova: entrada.auto = true.
import hashlib, json, time
from .obra import Episodio, ler_json, atualizar_json
from . import db

AVISADAS = set()          # pendências já avisadas nesta sessão (o aviso do Windows sai uma vez só)
REPETE = {}               # (obra, ep, ação) → [instantes]: a mesma ação 5 vezes em 30 min sem avançar = freio
TRAVADOS = {}             # (obra, ep) → ação que travou (vira pendência; some quando o autor reenviar algo ou reiniciar)


# ------------------------------------------------------------------ utilidades
def _ultimo(c, obra, ep, tipo):
    return c.execute("SELECT estado, erro, fim FROM job WHERE obra=? AND ep=? AND tipo=? ORDER BY id DESC LIMIT 1",
                     (obra, ep, tipo)).fetchone()


def _na_fila(c, obra, ep, tipo=None):
    q = "SELECT 1 FROM job WHERE obra=? AND ep=? AND estado IN ('na_fila','rodando','cancelando')"
    return c.execute(q + (" AND tipo=?" if tipo else ""), (obra, ep, tipo) if tipo else (obra, ep)).fetchone() is not None


def _errou(c, obra, ep, tipo, depois=0):
    """O último job deste tipo deu erro? Erro ANTERIOR a `depois` (ex.: a mixagem que faltava já existe) não conta."""
    u = _ultimo(c, obra, ep, tipo)
    return u is not None and u["estado"] == "erro" and (u["fim"] or 0) > depois


def _sha(p):
    return hashlib.sha1(p.read_bytes()).hexdigest() if p.exists() else None


def _precisa(ep, tipos, c):
    """Alguma das etapas (com entradas) precisa rodar? Saída faltando ou entrada ainda inexistente = precisa."""
    from .etapas import ETAPAS, situacao, voz_pendentes
    for t in tipos:
        e = ETAPAS[t]
        try:
            if t == "voz":
                if voz_pendentes(ep):
                    return True
                continue
            if "entradas" not in e:
                continue
            alvos = ep.partes() if e["escopo"] == "parte" else [None]
            if any(situacao(ep, t, n, c)[0] == "refazer" for n in alvos):
                return True
        except Exception:
            return True
    return False


# ------------------------------------------------------------------ o que precisa do autor
def pendencias(obra, ep_, c=None):
    """Lista do que espera o autor neste episódio: [{id, texto, tela, bloqueia, prazo?}]. Usada pela Mesa e pelo piloto."""
    from . import mesa
    from .aprovacao import estado as estado_audio
    c = c or db.conectar()
    ep = Episodio(obra, ep_)
    st = ep.cfg.get("episodios", {}).get(ep.ep, {})
    out = []
    if st.get("status") == "publicado":
        return out
    add = lambda id_, texto, tela, bloqueia=True, **kw: out.append({"id": id_, "texto": texto, "tela": tela, "bloqueia": bloqueia, **kw})
    if (obra, ep.ep) in TRAVADOS:
        add("travado", f"O piloto repetiu \"{TRAVADOS[(obra, ep.ep)]}\" 5 vezes sem avançar e parou. Veja a Fila e o log (piloto.log); "
            "desligue e ligue o piloto para tentar de novo.", "fila")
    pend = [d["id"] for d in mesa.decisoes(obra, ep.ep) if d["estado"] == "pendente"]
    if pend:
        add("decisoes", f"Decidir na Mesa: {', '.join(pend)}", "mesa")
    for t in ("mestre", "alarme", "corrigir", "roteiro", "voz", "montar", "cue", "stems", "mix", "episodio", "tempos", "video",
              "video16x9", "capas", "wattpad", "entregar", "kit", "cenas", "arte", "imagens", "triagem"):
        u = _ultimo(c, obra, ep.ep, t)
        if u and u["estado"] == "erro":
            if t == "kit" and ep.roteiro_arq.exists():       # o kit esperava as mixagens: se elas vieram depois, o erro caducou
                try:
                    mixes = [ep.mix_wav(k) for k in ep.partes()]
                    if all(m.exists() for m in mixes) and max(m.stat().st_mtime for m in mixes) > (u["fim"] or 0):
                        continue
                except Exception:
                    pass
            add(f"erro_{t}", f"Erro em {t}: {(u['erro'] or '')[:160]}. Corrija e reenvie (aba Fila).", "fila")
    if not ep.mestre.exists():
        return out
    if not st.get("mestre_aprovado"):
        from .texto import _alarme_arq
        al = ler_json(_alarme_arq(ep), {"alertas": []})["alertas"]
        crit = [a for a in al if a["gravidade"] == "critico" and a["estado"] == "aberto"]
        add("mestre", "Ler e aprovar o texto-mestre" + (f" ({len(crit)} alerta(s) crítico(s) abertos)" if crit else ""), "texto")
        return out
    if not ep.roteiro_arq.exists():
        return out
    rel = ler_json(ep.roteiro_arq.with_name(f"ep{ep.ep}_relatorio.json"), {})
    # áudio já aprovado = o autor já ouviu o roteiro inteiro: o relatório antigo não é mais pendência
    if (rel.get("erros") or rel.get("repeticoes")) and not st.get("roteiro_conferido") and not st.get("audio_aprovado"):
        add("roteiro", f"Conferir o roteiro: {len(rel.get('erros', []))} erro(s), {len(rel.get('repeticoes', []))} repetição(ões)", "texto")
    elenco = ep.cfg.get("elenco", {})
    sem_voz = sorted({f["voz"] for p in ep.roteiro["partes"] for f in p["falas"]} - set(elenco))
    if sem_voz:
        add("elenco", f"Escolher as vozes de: {', '.join(sem_voz)}", "elenco")
    try:
        ea = estado_audio(obra, ep.ep, c)
        if not ea["sem_mix"] and not ea["aprovado"]:
            add("audio", f"Ouvir e aprovar o áudio (partes {ea['partes_a_aprovar']})", "revisao")
    except Exception:
        pass
    from .triagem import _alvo
    for alvo, tela in (("imagens", "imagens"), ("arte", "arte")):
        arq, _ = _alvo(ep, alvo)
        for it in ler_json(arq, {"itens": []})["itens"]:
            if it.get("sem_candidata_boa") and not it.get("escolhida"):
                add(f"sem_{it['id']}", f"Nenhuma imagem passou na triagem em {it['id']} depois de 3 rodadas: escolha ou ajuste o pedido", tela)
            elif it.get("pre_escolhida") and not it.get("escolhida"):
                add(f"conf_{it['id']}", f"Confirmar a imagem de {it['id']} (senão vale a pré-escolhida às "
                    f"{time.strftime('%d/%m %H:%M', time.localtime(it.get('prazo_escolha', 0)))})", tela, bloqueia=False)
    return out


# ------------------------------------------------------------------ o próximo passo
def _enfileirar(c, ep, tipo, params=None, prioridade=0):
    return db.enfileirar(c, tipo, ep.obra, ep.ep, params=params or {}, prioridade=prioridade, lote=f"{ep.obra}|{ep.ep}|piloto")


def passo(ep, c):
    """Enfileira o próximo passo do episódio, se houver. Devolve uma frase do que fez (ou None)."""
    from .worker import enfileirar_cadeia
    from .aprovacao import estado as estado_audio, DEPOIS_DO_AUDIO
    from . import mesa, triagem
    from .texto import _alarme_arq
    obra, n = ep.obra, ep.ep
    st = ep.cfg.get("episodios", {}).get(n, {})
    if st.get("status") == "publicado" or _na_fila(c, obra, n):
        return None
    if any(d["estado"] == "pendente" for d in mesa.decisoes(obra, n)):
        return None

    # ---- texto
    if not ep.mestre.exists():
        if _errou(c, obra, n, "mestre"):
            return None
        _enfileirar(c, ep, "mestre"); return "escrevendo o texto-mestre"
    if not st.get("mestre_aprovado"):
        al = ler_json(_alarme_arq(ep), {"alertas": []})["alertas"]
        crit = [a for a in al if a["gravidade"] == "critico" and a["estado"] == "aberto"]
        sha = _sha(ep.mestre)
        # regra: alerta crítico sempre se corrige. Uma tentativa automática por versão do texto.
        if crit and st.get("piloto_corrigido") != sha and not _errou(c, obra, n, "corrigir"):
            atualizar_json(ep.projeto, lambda cfg: cfg["episodios"][n].update(piloto_corrigido=sha))
            _enfileirar(c, ep, "corrigir"); return "corrigindo os alertas críticos do texto"
        return None
    if not ep.roteiro_arq.exists():
        if _errou(c, obra, n, "roteiro"):
            return None
        _enfileirar(c, ep, "roteiro"); return "montando o roteiro de áudio"
    bloqueios = {p["id"] for p in pendencias(obra, n, c) if p["bloqueia"]}
    # um erro só segura o que depende dele (ex.: o kit de postagem falhar não trava o áudio)
    erro_em = lambda *tipos: any(f"erro_{t}" in bloqueios for t in tipos)
    audio_livre = not ({"roteiro", "elenco"} & bloqueios) and not erro_em("sincronizar", "voz", "montar", "cue", "stems", "mix", "episodio")

    # ---- áudio (primeiro: é o que o autor precisa ouvir)
    if audio_livre and ep.plano_cues.exists() and _precisa(ep, ["voz", "montar", "cue", "stems", "mix", "episodio"], c):
        enfileirar_cadeia(c, obra, n, ate="episodio")
        return "produzindo o áudio"

    # ---- imagens do vídeo: gerar → triagem → (prazo/confirmação) → ampliar
    triagem.aplicar_prazos(ep, "imagens")
    feito = _imagens(ep, c, "imagens")
    if feito:
        return feito

    # ---- arte de divulgação: cenas → gerar → triagem → ampliar (+ rosto) → capas
    if not ep.arte_assets.exists() or not ler_json(ep.arte_assets, {"itens": []})["itens"]:
        if not _errou(c, obra, n, "cenas"):
            _enfileirar(c, ep, "cenas"); return "sugerindo as cenas das capas"
    else:
        triagem.aplicar_prazos(ep, "arte")
        feito = _imagens(ep, c, "arte")
        if feito:
            return feito

    # ---- vídeos (só com o áudio aprovado e todas as imagens finais)
    ea = estado_audio(obra, n, c)
    try:
        faltam = sorted({i for k in ep.partes() for i in ep.imagens_da_parte(k) if not (ep.imagens / f"{i}.png").exists()})
    except RuntimeError:
        faltam = ["(plano de vídeo)"]
    if ea["aprovado"] and not faltam and not erro_em("tempos", "video", "video16x9") \
            and _precisa(ep, ["tempos", "video", "video16x9"], c):
        enfileirar_cadeia(c, obra, n, de="tempos", ate="video16x9")
        return "renderizando os vídeos"

    # ---- kit de postagem: usa a duração real das mixagens (precisa do áudio pronto)
    mixes = [ep.mix_wav(k) for k in ep.partes()]
    if all(m.exists() for m in mixes) and not (ep.publicacao / "kit.json").exists()             and not _errou(c, obra, n, "kit", depois=max(m.stat().st_mtime for m in mixes)):
        _enfileirar(c, ep, "kit"); return "escrevendo o kit de postagem"

    # ---- capas e Wattpad
    from .arte import capas_prontas
    if capas_prontas(ep)[0] and _precisa(ep, ["capas"], c) and not _errou(c, obra, n, "capas"):
        _enfileirar(c, ep, "capas"); return "montando as capas"
    if _precisa(ep, ["wattpad"], c) and not _errou(c, obra, n, "wattpad"):
        _enfileirar(c, ep, "wattpad"); return "gerando o capítulo do Wattpad"

    # ---- entrega: copia o que for novo para a pasta de publicação
    if ea["aprovado"] and _entrega_desatualizada(ep) and not _errou(c, obra, n, "entregar"):
        _enfileirar(c, ep, "entregar"); return "entregando as peças"
    return None


def _imagens(ep, c, alvo):
    """Uma etapa do ciclo de imagens (vídeo ou arte), se houver. Devolve a frase ou None."""
    from .triagem import _alvo, candidatas, precisa_triagem, SEMENTES
    arq, pasta = _alvo(ep, alvo)
    itens = [it for it in ler_json(arq, {"itens": []})["itens"] if "descartad" not in (it.get("uso") or "")]
    if alvo == "imagens":
        final = lambda it: (ep.imagens / f"{it['id']}.png").exists()
        tipo = "imagens"
    else:
        final = lambda it: it.get("escolhida") and it.get("ampliada_de") == it.get("escolhida") and (ep.arte / f"{it['id']}.png").exists()
        tipo = "arte"
    if _errou(c, ep.obra, ep.ep, tipo) or _errou(c, ep.obra, ep.ep, "triagem"):
        return None
    # gerar (sem candidata ainda, ou a triagem pediu outra rodada)
    gerar = [it["id"] for it in itens if not final(it) and not it.get("escolhida")
             and (not candidatas(pasta, it["id"]) or it.get("mais_sementes"))]
    if gerar:
        def prep(d):
            for it in d["itens"]:
                if it["id"] in gerar:
                    usadas = [int(p.stem.rsplit("_s", 1)[1]) for p in candidatas(pasta, it["id"])]
                    if usadas:
                        it["seed"] = max(usadas) + 1
                    it.pop("mais_sementes", None)
        atualizar_json(arq, prep, {"itens": []})
        _enfileirar(c, ep, tipo, {"so": gerar, "sementes": SEMENTES})
        return f"gerando imagens ({alvo}): {', '.join(gerar)}"
    tri = [i for i in precisa_triagem(ep, alvo) if not next((x for x in itens if x["id"] == i), {}).get("sem_candidata_boa")]
    if tri:
        _enfileirar(c, ep, "triagem", {"alvo": alvo, "so": tri})
        return f"triando imagens ({alvo}): {', '.join(tri)}"
    ampliar = [it["id"] for it in itens if it.get("escolhida") and not final(it)]
    if ampliar:
        _enfileirar(c, ep, tipo, {"so": ampliar, "ampliar": True})
        return f"finalizando imagens ({alvo}): {', '.join(ampliar)}"
    return None


def _entrega_desatualizada(ep):
    from .etapas import entregaveis
    try:
        for orig, nome, _ in entregaveis(ep):
            if not orig.exists():
                continue
            dest = ep.entrega / nome
            if not dest.exists() or dest.stat().st_mtime < orig.stat().st_mtime:
                return True
    except Exception:
        return False
    return False


# ------------------------------------------------------------------ obra nova encadeada
def passo_obra(obra, cfg, c):
    from . import obra_nova
    ent = cfg.get("entrada", {})
    if not ent.get("auto") or _na_fila(c, obra, "00"):
        return None
    painel = obra_nova.painel(obra)
    for p in painel["passos"]:
        if p["id"] == "fonte":
            if not p["feito"]:
                return None
            continue
        if not p["feito"]:
            u = c.execute("SELECT estado FROM job WHERE obra=? AND ep='00' AND tipo='obra' AND params LIKE ? ORDER BY id DESC LIMIT 1",
                          (obra, f'%"{p["id"]}"%')).fetchone()
            if u and u["estado"] == "erro":
                return None
            db.enfileirar(c, "obra", obra, "00", params={"passo": p["id"]}, lote=f"{obra}|00|piloto")
            return f"obra nova: {p['nome'].lower()}"
    atualizar_json(PROJETOS_ARQ(obra), lambda d: d.setdefault("entrada", {}).update(auto=False))
    return None


def PROJETOS_ARQ(obra):
    from .config import PROJETOS
    return PROJETOS / obra / "projeto.json"


# ------------------------------------------------------------------ o laço (chamado pelo worker com a fila vazia)
def avancar(c):
    from .config import PROJETOS
    agora = time.time()
    if c.execute("SELECT 1 FROM job WHERE estado IN ('rodando','cancelando') OR (estado='na_fila' AND COALESCE(espera_ate,0) <= ?)",
                 (agora,)).fetchone():
        return None
    for pasta in sorted(PROJETOS.iterdir()):
        cfg = ler_json(pasta / "projeto.json")
        if not cfg:
            continue
        feito = passo_obra(pasta.name, cfg, c)
        if feito:
            _evento(pasta.name, "00", feito)
            return feito
        for n, st in sorted(cfg.get("episodios", {}).items()):
            if not st.get("piloto") or st.get("status") == "publicado":
                continue
            if (pasta.name, n) in TRAVADOS:
                continue
            try:
                ep = Episodio(pasta.name, n)
                feito = passo(ep, c)
                if feito and _repetindo(pasta.name, n, feito, c):
                    feito = None
                _avisar_pendencias(pasta.name, n, c)
            except Exception as ex:          # um episódio com problema não para os outros
                _log(f"{pasta.name} ep{n}: {type(ex).__name__}: {ex}")
                continue
            if feito:
                _evento(pasta.name, n, feito)
                return feito
    return None


def _repetindo(obra, ep, acao, c):
    """Freio: a mesma ação 5 vezes em 30 min = algo não avança (entrada impossível de calcular, etapa que sempre
    "não muda nada"). Cancela o que acabou de pôr na fila, trava o episódio e chama o autor."""
    agora = time.time()
    k = (obra, ep, acao)
    REPETE[k] = [t for t in REPETE.get(k, []) if agora - t < 1800] + [agora]
    if len(REPETE[k]) < 5:          # 3 rodadas de imagens são legítimas; 5 iguais em 30 min não
        return False
    c.execute("UPDATE job SET estado='cancelado', erro='freio do piloto: ação repetida sem avançar' "
              "WHERE obra=? AND ep=? AND estado='na_fila' AND lote LIKE '%|piloto'", (obra, ep))
    TRAVADOS[(obra, ep)] = acao
    _log(f"{obra} ep{ep}: FREIO — '{acao}' 5 vezes em 30 min sem avançar")
    return True


def _evento(obra, ep, texto):
    from .worker import ESTADO
    _log(f"{obra} ep{ep}: {texto}")
    ESTADO["eventos"].append({"t": time.time(), "job": None, "tipo": "piloto", "obra": obra, "ep": ep, "estado": "piloto", "texto": texto})


def _avisar_pendencias(obra, ep, c):
    from .worker import ESTADO
    for p in pendencias(obra, ep, c):
        k = (obra, ep, p["id"], p["texto"][:60])
        if k in AVISADAS:
            continue
        AVISADAS.add(k)
        ESTADO["eventos"].append({"t": time.time(), "job": None, "tipo": "pendencia", "obra": obra, "ep": ep,
                                  "estado": "pendencia", "texto": p["texto"], "tela": p["tela"]})


def _log(txt):
    from .config import LOGS
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        with open(LOGS / "piloto.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + txt + "\n")
    except OSError:
        pass


def ligar(obra, ep_, ligado=True):
    ep = Episodio(obra, ep_)
    TRAVADOS.pop((obra, ep.ep), None)                       # desligar/ligar destrava o freio
    for k in [k for k in REPETE if k[:2] == (obra, ep.ep)]:
        REPETE.pop(k)
    atualizar_json(ep.projeto, lambda cfg: cfg.setdefault("episodios", {}).setdefault(ep.ep, {}).update(piloto=bool(ligado)))
    return {"ok": True, "piloto": bool(ligado)}
