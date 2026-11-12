# O worker do Origami: o ÚNICO processo que usa a GPU. Pega um job por vez da fila (SQLite), descobre o que está
# desatualizado, roda a etapa, registra os artefatos e passa ao próximo. Na troca de recurso libera a GPU.
# Modos: drenar (roda até a fila esvaziar e sai) ou servidor (fica no ar com uma API HTTP local para o app).
import subprocess
import json, threading, time, traceback
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .config import LOGS, PORTA_API, DEMO
from . import db
from .obra import Episodio
from .etapas import ETAPAS, CADEIA, PROC_ATUAL, Cancelado, desatualizada, situacao, chave
from .servicos import liberar, abrir_espaco

ESTADO = {"pausado": False, "job": None, "recurso": None, "parar": False, "eventos": []}
DRENAR_ESPERA_S = 90          # drenar (CLI) espera um job adiado por até isto; mais que isso fica para o app


def rodar_job(c, j):
    ep = Episodio(j["obra"], j["ep"])
    e = ETAPAS[j["tipo"]]
    params = json.loads(j["params"] or "{}")
    LOGS.mkdir(parents=True, exist_ok=True)
    arq_log = LOGS / f"job_{j['id']}.log"
    with open(arq_log, "a", encoding="utf-8") as log:
        log.write(f"=== job {j['id']} {j['tipo']} {j['obra']} ep{j['ep']} parte={j['parte']} {params}\n")
        # portão: legenda, vídeos e entrega só depois que o autor aprova o áudio (confere na hora de rodar, porque o
        # áudio pode ter sido refeito depois que a fila foi montada)
        from .aprovacao import DEPOIS_DO_AUDIO, estado as estado_audio
        if j["tipo"] in DEPOIS_DO_AUDIO and not params.get("sem_portao"):
            ea = estado_audio(j["obra"], j["ep"], c)
            if not ea["aprovado"]:
                quais = ea["partes_a_aprovar"] or ea["sem_mix"]
                return "pulado", f"esperando você aprovar o áudio (partes {quais}) na Revisão de áudio", str(arq_log)
        if e["escopo"] == "parte":
            alvo = [j["parte"]] if j["parte"] else (params.get("partes") or ep.partes())
        else:
            alvo = [None]
        pend, so_codigo = [], []
        for n in alvo:
            precisa, ass, ent = desatualizada(ep, j["tipo"], n, c)
            if precisa or params.get("forcar"):
                pend.append((n, ass, ent))
            elif "entradas" in e and situacao(ep, j["tipo"], n, c)[0] == "codigo novo":
                so_codigo.append(n)
        if so_codigo:
            log.write(f"só o código mudou ({so_codigo}): não refeito; aplicar pela Mesa (código novo disponível)\n")
        if not pend:
            return "pulado", ("só o código mudou: aplique pela Mesa se quiser" if so_codigo else "nada mudou"), str(arq_log)
        partes = [n for n, _, _ in pend if n is not None]
        resumo = e["rodar"](ep, partes, params, log, c)
        for n, ass, ent in pend:
            if ass is None and "entradas" in e:          # forçado sem assinatura calculada
                _, ass, ent = desatualizada(ep, j["tipo"], n, c)
            if ass:
                db.gravar_artefato(c, chave(ep, j["tipo"], n), ass, ent, j["id"])
        return "pronto", resumo, str(arq_log)


def vigia_cancelamento():
    """Outro processo (CLI ou app) pede o cancelamento marcando o job como 'cancelando' no banco."""
    c = db.conectar()
    while not ESTADO["parar"]:
        j = ESTADO["job"]
        if j and PROC_ATUAL["p"]:
            r = c.execute("SELECT estado FROM job WHERE id=?", (j["id"],)).fetchone()
            if r and r[0] == "cancelando":
                PROC_ATUAL["p"]._cancelado = True
                # kill() mataria só o processo pai; taskkill /T derruba também os filhos (compor.py, ffmpeg)
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(PROC_ATUAL["p"].pid)], capture_output=True)
        time.sleep(1.5)


TRAVA = {"f": None}


def travar_worker():
    """Um worker só (dois workers disputariam a GPU).
    Trava de arquivo do próprio Windows (msvcrt.locking): é solta sozinha quando o processo morre, mesmo morto à força.
    (Um arquivo com o PID ficaria órfão e falharia quando o Windows reaproveitasse o número.)"""
    import msvcrt, os
    from .config import DADOS
    DADOS.mkdir(parents=True, exist_ok=True)
    f = open(DADOS / "worker.lock", "a+")
    try:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        raise SystemExit("já existe um worker do Origami rodando. Use a fila (os jobs entram nele) ou feche o outro antes.")
    f.seek(0); f.truncate(); f.write(str(os.getpid())); f.flush()
    TRAVA["f"] = f
    return f


def laco(drenar=False, saida=print):
    travar_worker()
    _laco(drenar, saida)


def _passageiro(ex):
    """Falha que passa sozinha (serviço reiniciando, conexão recusada): o job volta à fila em 1 min, até 3 vezes."""
    import requests
    if isinstance(ex, (requests.ConnectionError, requests.Timeout, ConnectionError, TimeoutError)):
        return True
    txt = str(ex)
    return any(s in txt for s in ("servidor de voz não respondeu", "servidor de voz fechou", "ComfyUI não subiu",
                                  "Connection refused", "ConnectionRefused", "Max retries exceeded"))


def _registrar_erro(c, j, ex, saida):
    msg = str(ex) if isinstance(ex, RuntimeError) else f"{type(ex).__name__}: {ex}"
    try:
        (LOGS / f"job_{j['id']}.log").open("a", encoding="utf-8").write(traceback.format_exc())
    except OSError:
        pass
    if _passageiro(ex) and (j["tentativas"] or 0) + 1 < db.MAX_TENTATIVAS:
        db.adiar(c, j["id"], 60, f"tentando de novo em 1 min: {msg}")
        saida(f"#{j['id']:<4} {j['tipo']:<11} ADIADO | {msg}")
        return
    db.terminar(c, j["id"], "erro", erro=msg, log=str(LOGS / f"job_{j['id']}.log"))
    saida(f"#{j['id']:<4} {j['tipo']:<11} ERRO   | {msg}")
    ESTADO["eventos"].append({"t": time.time(), "job": j["id"], "tipo": j["tipo"], "obra": j["obra"], "ep": j["ep"],
                              "estado": "erro", "texto": msg})
    if j["lote"]:     # cai só o que depende da etapa que falhou (o resto do lote segue)
        from .etapas import dependentes
        dep = sorted(dependentes(j["tipo"]))
        n = c.execute(f"UPDATE job SET estado='cancelado', erro=? WHERE lote=? AND estado='na_fila' AND tipo IN ({','.join('?' * len(dep))})",
                      (f"depende de {j['tipo']}, que falhou (job {j['id']})", j["lote"], *dep)).rowcount if dep else 0
        if n:
            saida(f"      {n} job(s) seguintes do lote cancelados")


def _laco(drenar=False, saida=print):
    from .trabalhador import LimiteClaude
    c = db.conectar()
    PROC_ATUAL["thread"] = threading.get_ident()      # só o que o worker roda é cancelável pela Fila
    threading.Thread(target=vigia_cancelamento, daemon=True).start()
    if (n := db.recuperar(c)):
        saida(f"{n} job(s) interrompido(s) voltaram para a fila")
    while not ESTADO["parar"]:
        if ESTADO["pausado"]:
            time.sleep(1); continue
        j = db.proximo(c)
        if not j:
            # drenar (linha de comando): sai quando não há nada para já; um job adiado por horas (limite do Claude) fica
            # na fila para o app pegar depois
            if drenar and not c.execute("SELECT 1 FROM job WHERE estado='na_fila' AND COALESCE(espera_ate,0) <= ?",
                                        (time.time() + DRENAR_ESPERA_S,)).fetchone():
                break
            ocioso()
            time.sleep(1); continue
        rec = ETAPAS[j["tipo"]]["recurso"]
        ESTADO["job"] = dict(j)
        t0 = time.time()
        try:
            # ligar/desligar serviços fica DENTRO do try: uma falha do servidor de voz vira erro do job, não do motor
            if ESTADO["recurso"] and ESTADO["recurso"] != rec:
                liberar(ESTADO["recurso"], proximo=rec)
            ESTADO["recurso"] = rec
            abrir_espaco(rec)
            estado, resumo, log = rodar_job(c, j)
            db.terminar(c, j["id"], estado, resumo=resumo, log=log)
            saida(f"#{j['id']:<4} {j['tipo']:<11} {estado:<7} {time.time() - t0:6.0f} s | {resumo}")
            ESTADO["eventos"].append({"t": time.time(), "job": j["id"], "tipo": j["tipo"], "obra": j["obra"], "ep": j["ep"],
                                      "estado": estado, "texto": resumo})
        except Cancelado:
            db.terminar(c, j["id"], "cancelado", erro="cancelado pelo autor")
            saida(f"#{j['id']:<4} {j['tipo']:<11} cancelado")
        except LimiteClaude as ex:
            # o plano do Claude acabou por agora: este job e os outros do Claude esperam a volta; o resto da fila segue
            espera = max(60, ex.ate - time.time())
            db.adiar(c, j["id"], espera, str(ex), contar=False)
            outros = [r[0] for r in c.execute("SELECT id, tipo FROM job WHERE estado='na_fila'") if ETAPAS.get(r[1], {}).get("recurso") == "claude"]
            for jid in outros:
                c.execute("UPDATE job SET espera_ate=? WHERE id=?", (ex.ate, jid))
            volta = time.strftime("%H:%M", time.localtime(ex.ate))
            saida(f"#{j['id']:<4} {j['tipo']:<11} ESPERA | limite do Claude; volta às {volta} ({len(outros)} outro(s) esperando)")
            ESTADO["eventos"].append({"t": time.time(), "job": j["id"], "tipo": j["tipo"], "obra": j["obra"], "ep": j["ep"],
                                      "estado": "espera", "texto": f"limite do Claude: continua sozinho às {volta}"})
        except Exception as ex:
            _registrar_erro(c, j, ex, saida)
        finally:
            ESTADO["job"] = None
            del ESTADO["eventos"][:-50]
    if ESTADO["recurso"]:
        liberar(ESTADO["recurso"])


def ocioso():
    """Fila vazia: o piloto automático olha os episódios em produção. Nunca derruba o worker."""
    agora = time.time()
    if agora - ESTADO.get("ocioso_t", 0) < 60:
        return
    ESTADO["ocioso_t"] = agora
    try:
        from . import piloto
        piloto.avancar(db.conectar())
    except ImportError:
        pass
    except Exception:
        try:
            (LOGS / "piloto.log").open("a", encoding="utf-8").write(time.strftime("%Y-%m-%d %H:%M ") + traceback.format_exc())
        except OSError:
            pass


# ---------------------------------------------------------------- API HTTP local (para o app Electron)
def enfileirar_cadeia(c, obra, ep, partes=None, de=None, ate=None, forcar=None, params_extra=None, prioridade=0, portao=True):
    """Enfileira a cadeia de um episódio (ou um trecho dela). Devolve (lote, ids)."""
    from .aprovacao import DEPOIS_DO_AUDIO, estado as estado_audio
    Episodio(obra, ep)       # valida
    i0 = CADEIA.index(de) if de else 0
    i1 = CADEIA.index(ate) + 1 if ate else len(CADEIA)
    lote = f"{obra}|{ep}|{time.strftime('%Y%m%d-%H%M%S')}"
    ids = []
    etapas_lote = CADEIA[i0:i1]
    # portão: com o áudio ainda não aprovado, a cadeia para no áudio; legenda, vídeos e entrega esperam a aprovação
    # na Revisão de áudio. Só a linha de comando (manutenção) passa portao=False.
    if portao and not estado_audio(obra, ep, c)["aprovado"]:
        etapas_lote = [t for t in etapas_lote if t not in DEPOIS_DO_AUDIO]
    # capas sem arte escolhida não é erro: o resto anda; as capas entram quando a arte estiver pronta
    from .arte import capas_prontas
    forcar_capas = forcar == "tudo" or bool(forcar and "capas" in forcar)
    if "capas" in etapas_lote and not forcar_capas and not capas_prontas(Episodio(obra, ep))[0]:
        etapas_lote = [t for t in etapas_lote if t != "capas"]
    for t in etapas_lote:
        p = dict(params_extra or {}) if t == "sincronizar" else {}
        if partes and ETAPAS[t]["escopo"] == "parte":
            p["partes"] = partes
        if forcar and (forcar == "tudo" or t in forcar):
            p["forcar"] = True
        if not portao:
            p["sem_portao"] = True
        ids.append(db.enfileirar(c, t, obra, f"{int(ep):02d}", params=p, prioridade=prioridade, lote=lote))
    return lote, ids


def _fim_log(nome, n):
    arq = LOGS / nome
    try:
        return arq.read_text(encoding="utf-8").splitlines()[-n:] if arq.exists() else []
    except OSError:
        return []


def cancelar(c, jid):
    j = c.execute("SELECT estado FROM job WHERE id=?", (jid,)).fetchone()
    if not j:
        return False
    if j["estado"] == "na_fila":
        c.execute("UPDATE job SET estado='cancelado', erro='cancelado pelo autor' WHERE id=?", (jid,))
    elif j["estado"] == "rodando":
        c.execute("UPDATE job SET estado='cancelando' WHERE id=?", (jid,))   # o vigia do worker mata o subprocesso
    return True


class Api(BaseHTTPRequestHandler):
    def _json(self, dados, cod=200):
        s = json.dumps(dados, ensure_ascii=False, default=str)
        if DEMO:                       # demonstração: nenhum caminho da máquina de quem abriu vai para a tela
            from .config import RAIZ
            for pref, sep in ((str(RAIZ), "\\"), (str(RAIZ).replace("\\", "/"), "/")):
                esc = lambda t: json.dumps(t, ensure_ascii=False)[1:-1]      # como o texto aparece dentro do JSON
                s = s.replace(esc(pref + sep), "").replace(esc(pref), ".")
        b = s.encode("utf-8")
        self.send_response(cod); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def log_message(self, *a):
        pass

    def _arquivo(self, caminho):
        """Serve arquivos da interface (ui/) e das obras (Projetos/), nunca fora delas."""
        import mimetypes
        from .config import INTERFACE, PROJETOS, VOZES, RAIZ
        alvo = Path(caminho)
        alvo = (alvo if alvo.is_absolute() else RAIZ / alvo).resolve()      # relativo = à pasta do app
        if not any(alvo.is_relative_to(r.resolve()) for r in (INTERFACE, PROJETOS, VOZES, RAIZ / "ouvir", RAIZ / "dados" / "amostras")) or not alvo.is_file():
            return self._json({"erro": "arquivo não encontrado"}, 404)
        tipo = mimetypes.guess_type(str(alvo))[0] or "application/octet-stream"
        if tipo.startswith("text") or tipo.endswith("javascript"):
            tipo += "; charset=utf-8"
        total = alvo.stat().st_size
        ini, fim, cod = 0, total - 1, 200
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):        # vídeo/áudio: o player pede pedaços para poder pular
            a, _, b = rng[6:].split(",")[0].partition("-")
            ini = int(a) if a else max(0, total - int(b))
            fim = min(int(b), total - 1) if a and b else total - 1
            cod = 206
        self.send_response(cod); self.send_header("Content-Type", tipo); self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fim - ini + 1)); self.send_header("Cache-Control", "no-store")
        if cod == 206:
            self.send_header("Content-Range", f"bytes {ini}-{fim}/{total}")
        self.end_headers()
        try:
            with open(alvo, "rb") as fh:
                fh.seek(ini); falta = fim - ini + 1
                while falta > 0:
                    bloco = fh.read(min(1 << 20, falta))
                    if not bloco:
                        break
                    self.wfile.write(bloco); falta -= len(bloco)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass            # o player cancelou o pedaço (normal ao pular)

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs, unquote
        from .config import INTERFACE
        from . import mesa
        c = db.conectar()
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self._arquivo(INTERFACE / "index.html")
            if u.path.startswith("/ui/"):
                return self._arquivo(INTERFACE / unquote(u.path[4:]))
            if u.path == "/arquivo":
                return self._arquivo(q["c"])
            if u.path == "/api/obras":
                return self._json(mesa.obras())
            if u.path == "/api/ambiente":
                return self._json({"demo": DEMO})
            if u.path == "/api/mesa":
                return self._json(mesa.mesa(q["obra"], q["ep"], c))
            if u.path == "/api/obra":
                from . import obra_nova
                return self._json(obra_nova.painel(q["obra"]))
            if u.path == "/api/fila":
                from . import painel
                return self._json(painel.fila(c, q.get("obra") or None))
            if u.path == "/api/log":
                from . import painel
                return self._json(painel.log(q["id"]))
            if u.path == "/api/custo":
                from . import painel
                return self._json(painel.custo(c, q["obra"]))
            if u.path == "/api/imagens":
                from . import imagens_video
                return self._json(imagens_video.painel(q["obra"], q["ep"]))
            if u.path == "/api/arte":
                from . import arte
                return self._json(arte.estudio(q["obra"], q["ep"]))
            if u.path == "/api/pronuncia":
                from . import pronuncia
                return self._json(pronuncia.painel(q["obra"]))
            if u.path == "/api/pronuncia/job":
                r = c.execute("SELECT estado, resumo, erro FROM job WHERE id=?", (int(q["id"]),)).fetchone()
                return self._json({"estado": r[0], "resumo": r[1], "erro": r[2]} if r else {"erro": "job não encontrado"})
            if u.path == "/api/postagem":
                from . import postagem
                return self._json(postagem.painel(q["obra"]))
            if u.path == "/api/postagem/conexao":
                from . import postagem
                return self._json(postagem.conexao())
            if u.path == "/api/elenco":
                from . import elenco
                return self._json(elenco.painel(q["obra"]))
            if u.path == "/api/texto":
                from . import texto
                return self._json(texto.painel(q["obra"], q["ep"]))
            if u.path == "/api/publicacao":
                from . import publicacao
                return self._json(publicacao.painel(q["obra"], q["ep"]))
            if u.path == "/api/video":
                from . import revvideo
                return self._json(revvideo.parte(q["obra"], q["ep"], q.get("parte", 1)))
            if u.path == "/api/revisao":
                from . import revisao
                return self._json(revisao.parte(q["obra"], q["ep"], q.get("parte", 1)))
            if u.path == "/api/pendencias":
                # "O que precisa de você": deste episódio + total dos episódios com o piloto ligado (o número no menu)
                from . import piloto
                from .obra import Episodio as _E
                ep = _E(q["obra"], q["ep"])
                st = ep.cfg.get("episodios", {}).get(ep.ep, {})
                todas = []
                for n, s in sorted(ep.cfg.get("episodios", {}).items()):
                    if s.get("piloto") and s.get("status") != "publicado" and n != ep.ep:
                        todas += [dict(p, ep=n) for p in piloto.pendencias(q["obra"], n, c)]
                return self._json({"pendencias": piloto.pendencias(q["obra"], ep.ep, c), "piloto": bool(st.get("piloto")),
                                   "outras": todas, "log": _fim_log("piloto.log", 8)})
            if u.path == "/api/ajustes/trilha":
                from . import ajustes
                return self._json(ajustes.trilha(q["obra"], q["ep"]))
            if u.path == "/api/ajustes/segmentos":
                from . import ajustes
                return self._json(ajustes.segmentos(q["obra"], q["ep"], q.get("parte", 1)))
            if u.path == "/api/ajustes/guia":
                from . import ajustes
                return self._json(ajustes.guia(q["obra"]))
            if u.path == "/api/arquivos":
                from . import arquivos
                return self._json(arquivos.inventario())
            if u.path == "/api/claude":
                from . import trabalhador
                agora = time.time()
                if agora - ESTADO.get("claude_t", 0) > 600:
                    ESTADO["claude"], ESTADO["claude_t"] = trabalhador.conectado(), agora
                return self._json(ESTADO["claude"])
        except Exception as ex:
            return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if u.path == "/estado":
            # a interface pergunta a cada 2 s: estado do motor + o que terminou desde a última pergunta (desde=t)
            agora = time.time()
            fila = c.execute("SELECT COUNT(*) FROM job WHERE estado='na_fila'").fetchone()[0]
            esperando = c.execute("SELECT COUNT(*), MIN(espera_ate) FROM job WHERE estado='na_fila' AND espera_ate > ?", (agora,)).fetchone()
            prox = c.execute("SELECT id, tipo, obra, ep FROM job WHERE estado='na_fila' AND (espera_ate IS NULL OR espera_ate <= ?) "
                             "ORDER BY prioridade DESC, id LIMIT 1", (agora,)).fetchone()
            erros = c.execute("SELECT COUNT(*) FROM job WHERE estado='erro' AND fim > ?", (agora - 86400,)).fetchone()[0]
            desde = float(q.get("desde") or 0)
            return self._json({"pausado": ESTADO["pausado"], "job": ESTADO["job"], "na_fila": fila, "agora": agora,
                               "esperando": esperando[0], "volta": esperando[1], "proximo": dict(prox) if prox else None,
                               "erros_24h": erros, "sem_worker": ESTADO.get("sem_worker"), "demo": DEMO,
                               "eventos": [e for e in ESTADO["eventos"] if e["t"] > desde]})
        if self.path.startswith("/jobs"):
            rows = c.execute("SELECT id,tipo,obra,ep,parte,estado,resumo,erro,criado,inicio,fim FROM job ORDER BY id DESC LIMIT 50")
            return self._json([dict(r) for r in rows])
        self._json({"erro": "rota desconhecida"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if DEMO:                       # modo demonstração: só leitura (nada é gravado, nenhum job entra na fila)
            self.rfile.read(n)
            return self._json({"erro": "Indisponível na demonstração: aqui nada é gravado nem gerado."}, 403)
        c = db.conectar()
        if self.path.startswith("/api/obra/importar"):
            from urllib.parse import urlparse, parse_qs
            from . import obra_nova
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            try:
                return self._json(obra_nova.importar(q["obra"], q["nome"], self.rfile.read(n)))
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        bruto = self.rfile.read(n) or b"{}"
        try:
            corpo = json.loads(bruto)
        except UnicodeDecodeError:          # corpo em cp1252 (cliente Windows)
            try:
                corpo = json.loads(bruto.decode("cp1252"))
            except ValueError as ex:
                return self._json({"erro": f"pedido inválido: {ex}"}, 400)
        except ValueError as ex:
            return self._json({"erro": f"pedido inválido (JSON): {ex}"}, 400)
        if self.path in ("/api/arquivos/mover", "/api/arquivos/desfazer"):
            from . import arquivos
            try:
                if ESTADO["job"] and self.path.endswith("mover"):
                    raise RuntimeError("o motor está trabalhando agora: mova os arquivos com a fila parada")
                r = arquivos.mover(corpo["ids"]) if self.path.endswith("mover") else arquivos.desfazer(corpo["lote"])
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{ex}" if isinstance(ex, RuntimeError) else f"{type(ex).__name__}: {ex}"}, 500)
        if self.path.startswith("/api/ajustes/"):
            from . import ajustes
            try:
                acao = self.path.rsplit("/", 1)[1]
                if acao == "trilha":
                    r = ajustes.salvar_trilha(corpo["obra"], corpo["ep"], corpo["parte"], corpo["humor"], corpo["final"])
                elif acao == "titulo":
                    r = ajustes.salvar_titulo(corpo["obra"], corpo["ep"], corpo["titulo"])
                elif acao == "nivel":
                    r = ajustes.salvar_nivel(corpo["obra"], corpo["ep"], corpo["nivel"], corpo.get("escopo", "ep"))
                elif acao == "publicado":
                    r = ajustes.marcar_publicado(corpo["obra"], corpo["ep"], corpo.get("publicado", True))
                elif acao == "segmentos":
                    r = ajustes.salvar_segmentos(corpo["obra"], corpo["ep"], corpo["parte"], corpo["segmentos"])
                elif acao == "guia":
                    r = ajustes.salvar_guia(corpo["obra"], corpo["campos"])
                else:
                    return self._json({"erro": "ação desconhecida"}, 404)
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{ex}" if isinstance(ex, RuntimeError) else f"{type(ex).__name__}: {ex}"}, 500)
        if self.path in ("/api/piloto/ligar", "/api/triagem/confirmar", "/api/texto/roteiro_ok", "/api/obra/auto", "/api/reenviar"):
            try:
                if self.path == "/api/piloto/ligar":
                    from . import piloto
                    r = piloto.ligar(corpo["obra"], corpo["ep"], corpo.get("ligado", True))
                elif self.path == "/api/triagem/confirmar":
                    from . import triagem
                    r = triagem.confirmar(corpo["obra"], corpo["ep"], corpo.get("alvo", "arte"), corpo["id"], corpo.get("arquivo"))
                elif self.path == "/api/texto/roteiro_ok":       # o autor conferiu o relatório do roteiro: o piloto segue
                    from .obra import Episodio as _E, atualizar_json
                    ep = _E(corpo["obra"], corpo["ep"])
                    atualizar_json(ep.projeto, lambda cfg: cfg.setdefault("episodios", {}).setdefault(ep.ep, {}).update(roteiro_conferido=True))
                    r = {"ok": True}
                elif self.path == "/api/obra/auto":              # assistente de obra nova: todos os passos em sequência
                    from .config import PROJETOS
                    from .obra import atualizar_json
                    if not (PROJETOS / corpo["obra"] / "projeto.json").exists():
                        raise RuntimeError(f"obra não encontrada: {corpo['obra']}")
                    atualizar_json(PROJETOS / corpo["obra"] / "projeto.json",
                                   lambda cfg: cfg.setdefault("entrada", {}).update(auto=bool(corpo.get("ligado", True))))
                    r = {"ok": True}
                else:                                            # reenviar um job que deu erro (mesmos parâmetros)
                    j = c.execute("SELECT tipo, obra, ep, parte, params FROM job WHERE id=?", (int(corpo["id"]),)).fetchone()
                    if not j:
                        return self._json({"erro": "job não encontrado"}, 404)
                    r = {"ok": True, "job": db.enfileirar(c, j["tipo"], j["obra"], j["ep"], j["parte"], json.loads(j["params"] or "{}"))}
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{ex}" if isinstance(ex, RuntimeError) else f"{type(ex).__name__}: {ex}"}, 500)
        if self.path == "/api/decidir":
            from . import mesa
            try:
                it = mesa.decidir(corpo["obra"], corpo["id"], corpo["escolha"], corpo.get("nota", ""), corpo.get("adiar", False))
                return self._json(it)
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if self.path.startswith("/api/elenco/"):
            from . import elenco
            try:
                acao = self.path.rsplit("/", 1)[1]
                if acao == "candidatas":
                    ep = corpo.get("ep") or "01"
                    prm = {k: corpo[k] for k in ("personagem", "genero", "idade", "tom", "frase")}
                    prm.update(velocidade=float(corpo.get("velocidade", 0.92)), n=int(corpo.get("n", 4)))
                    r = {"ok": True, "job": db.enfileirar(c, "elenco", corpo["obra"], f"{int(ep):02d}", params=prm)}
                elif acao == "aprovar":
                    r = elenco.aprovar(corpo["obra"], corpo["personagem"], corpo["arquivo"])
                elif acao == "frases":
                    r = elenco.sugerir_frases(corpo["obra"], corpo["personagem"], corpo.get("descricao", ""))
                else:
                    return self._json({"erro": "ação desconhecida"}, 404)
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if self.path.startswith("/api/obra/"):
            from . import obra_nova
            try:
                acao = self.path.rsplit("/", 1)[1]
                if acao == "criar":
                    r = obra_nova.criar(corpo["pasta"], corpo["titulo"], corpo.get("sigla", ""), corpo.get("tipo", "rpg"),
                                        corpo.get("protagonista", ""), corpo.get("conteudo", "sugestivo"))
                elif acao in ("ler", "estrutura", "guia", "biblia"):
                    r = {"ok": True, "job": db.enfileirar(c, "obra", corpo["obra"], "00", params={"passo": acao})}
                else:
                    return self._json({"erro": "ação desconhecida"}, 404)
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if self.path.startswith("/api/texto/"):
            from . import texto
            try:
                acao, o, e = self.path.rsplit("/", 1)[1], corpo["obra"], corpo["ep"]
                if acao in ("escrever", "alarme", "roteiro", "revisar"):
                    tipo = {"escrever": "mestre", "alarme": "alarme", "roteiro": "roteiro", "revisar": "revisar"}[acao]
                    r = {"ok": True, "job": db.enfileirar(c, tipo, o, f"{int(e):02d}", params={"instrucao": corpo.get("instrucao", "")})}
                elif acao == "aprovar":
                    r = texto.aprovar(o, e)
                elif acao == "salvar":
                    r = texto.salvar(o, e, corpo["texto"])
                elif acao == "alerta":
                    r = texto.anotar_alerta(o, e, corpo["id"], corpo["estado"], corpo.get("nota", ""))
                elif acao == "corrigir":
                    r = {"ok": True, "job": db.enfileirar(c, "corrigir", o, f"{int(e):02d}", params={"ids": corpo.get("ids")})}
                else:
                    return self._json({"erro": "ação desconhecida"}, 404)
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if self.path.startswith("/api/publicacao/"):
            from . import publicacao
            try:
                acao, o, e = self.path.rsplit("/", 1)[1], corpo["obra"], corpo["ep"]
                if acao == "registrar":
                    r = publicacao.registrar(o, e, corpo["plataforma"], corpo["peca"], corpo.get("link", ""))
                elif acao == "desfazer":
                    r = publicacao.desfazer(o, e, corpo["plataforma"], corpo["peca"])
                elif acao == "entregar":
                    r = {"ok": True, "job": db.enfileirar(c, "entregar", o, f"{int(e):02d}", params={"so": corpo.get("so")})}
                elif acao == "kit":
                    r = {"ok": True, "job": db.enfileirar(c, "kit", o, f"{int(e):02d}")}
                else:
                    return self._json({"erro": "ação desconhecida"}, 404)
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if self.path.startswith("/api/marca/"):
            from . import revvideo
            try:
                acao = self.path.rsplit("/", 1)[1]
                if acao == "nova":
                    r = revvideo.marcar(corpo["obra"], corpo["ep"], corpo["parte"], corpo["t"], corpo["nota"], corpo.get("tipo", "imagem"))
                elif acao == "acao":
                    r = revvideo.acao_da_marca(corpo["obra"], corpo["ep"], corpo["id"])
                elif acao == "apagar":
                    r = revvideo.apagar(corpo["obra"], corpo["ep"], corpo["id"])
                elif acao == "legenda":          # realinha as palavras da parte e refaz só o que depende disso
                    ep2 = f"{int(corpo['ep']):02d}"
                    lote, ids = enfileirar_cadeia(c, corpo["obra"], ep2, [int(corpo["parte"])], "tempos", "video16x9", ["tempos"])
                    r = {"ok": True, "jobs": ids}
                elif acao == "previa":
                    r = {"ok": True, "job": db.enfileirar(c, "previa", corpo["obra"], f"{int(corpo['ep']):02d}",
                                                          params={"parte": corpo["parte"], "tempos": corpo.get("tempos")})}
                else:
                    r = revvideo.resolver(corpo["obra"], corpo["ep"], corpo["id"], corpo.get("estado", "resolvida"))
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if self.path.startswith("/api/imagens/"):
            from . import imagens_video as iv
            try:
                acao, o, e = self.path.rsplit("/", 1)[1], corpo["obra"], corpo["ep"]
                if acao == "item":
                    r = iv.salvar_item(o, e, corpo["item"])
                elif acao == "personagem":
                    r = iv.cadastrar_personagem(o, e, corpo["personagem"], corpo["retrato"], corpo.get("trabalho", ""), corpo.get("fora", ""))
                elif acao == "escolher":
                    r = iv.escolher(o, e, corpo["id"], corpo["arquivo"])
                elif acao == "sementes":
                    r = iv.mais_sementes(c, o, e, corpo["id"], corpo.get("n", 2))
                elif acao == "finalizar":
                    r = iv.ampliar(c, o, e, corpo["ids"])
                elif acao == "reusar":
                    r = iv.reusar(o, e, corpo["id"], corpo["existente"], corpo.get("horario", ""))
                else:
                    return self._json({"erro": "ação desconhecida"}, 404)
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if self.path.startswith("/api/arte/"):
            from . import arte
            try:
                acao, o, e = self.path.rsplit("/", 1)[1], corpo["obra"], corpo["ep"]
                if acao == "cena":
                    r = arte.salvar_cena(o, e, corpo["cena"])
                elif acao == "escolher":
                    r = arte.escolher(o, e, corpo["id"], corpo["arquivo"])
                elif acao == "sementes":
                    r = arte.novas_sementes(c, o, e, corpo["id"], corpo.get("n", 2))
                elif acao == "capas":
                    r = arte.salvar_capas_editadas(o, e, corpo["spec"])
                elif acao == "sugerir":
                    r = {"ok": True, "job": db.enfileirar(c, "cenas", o, f"{int(e):02d}")}
                elif acao == "montar":
                    r = {"ok": True, "job": db.enfileirar(c, "capas", o, f"{int(e):02d}", params={"forcar": True})}
                else:
                    return self._json({"erro": "ação desconhecida"}, 404)
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if self.path.startswith("/api/pronuncia/"):
            from . import pronuncia
            try:
                acao, o = self.path.rsplit("/", 1)[1], corpo["obra"]
                if acao == "salvar":
                    r = pronuncia.salvar(o, corpo["palavra"], corpo.get("como", ""))
                elif acao == "amostra":
                    r = {"ok": True, "job": db.enfileirar(c, "amostra", o, "00", params={"personagem": corpo["personagem"], "texto": corpo["texto"]}, prioridade=5)}
                elif acao == "falas":
                    r = {"falas": pronuncia.falas_com(o, f"{int(corpo['ep']):02d}", corpo["palavra"])}
                elif acao == "regravar":
                    r = pronuncia.regravar(c, o, corpo["ep"], corpo["palavra"])
                else:
                    return self._json({"erro": "ação desconhecida"}, 404)
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if self.path.startswith("/api/postagem/"):
            from . import postagem as pg
            try:
                acao, o = self.path.rsplit("/", 1)[1], corpo.get("obra")
                if acao == "sugerir":
                    r = pg.sugerir(o, corpo["inicio"], corpo["eps"], corpo.get("redes"), corpo.get("wattpad", "d0"), int(corpo.get("intervalo", 0)))
                elif acao == "item":
                    r = pg.salvar_item(o, corpo["item"])
                elif acao == "marcar":
                    r = pg.marcar(o, corpo["id"], corpo["estado"], corpo.get("link", ""))
                elif acao == "excluir":
                    r = pg.excluir(o, corpo["id"])
                elif acao == "mover":
                    r = pg.mover(o, corpo["id"], corpo["data"])
                elif acao == "agendar":
                    r = {"ok": True, "job": db.enfileirar(c, "postagem", o, "00", params={"ids": corpo["ids"]})}
                elif acao == "cancelar":
                    r = pg.cancelar(o, corpo["id"])
                elif acao == "sincronizar":
                    r = pg.sincronizar(o)
                elif acao == "regras":
                    r = pg.regras(corpo["canal"])
                elif acao == "config":
                    d = pg.ler(o); d["config"].update(corpo["config"]); pg.gravar(o, d); r = {"ok": True}
                elif acao == "login":
                    r = pg.iniciar_login()
                elif acao == "abrir":
                    r = pg.abrir(corpo["caminho"])
                else:
                    return self._json({"erro": "ação desconhecida"}, 404)
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if self.path.startswith("/api/fala/"):
            from . import revisao
            try:
                acao = self.path.rsplit("/", 1)[1]
                if acao == "corrigir":
                    r = revisao.corrigir(c, corpo["obra"], corpo["ep"], corpo["chave"], corpo.get("texto"), corpo.get("pausa"),
                                         corpo.get("regerar", False))
                elif acao == "escolher":
                    r = revisao.escolher(c, corpo["obra"], corpo["ep"], corpo["chave"], corpo["versao"])
                elif acao == "aprovar":
                    r = revisao.aprovar(corpo["obra"], corpo["ep"], corpo["chave"])
                elif acao == "aprovar_audio":       # portão: o autor ouviu e libera legenda, vídeos e entrega
                    from . import aprovacao
                    r = aprovacao.aprovar(corpo["obra"], corpo["ep"], c)
                    if corpo.get("gerar"):
                        lote, ids = enfileirar_cadeia(c, corpo["obra"], corpo["ep"])
                        r["jobs"] = ids
                else:
                    return self._json({"erro": "ação desconhecida"}, 404)
                return self._json(r)
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if self.path == "/produzir":
            try:
                lote, ids = enfileirar_cadeia(c, corpo["obra"], corpo["ep"], corpo.get("partes"), corpo.get("de"),
                                              corpo.get("ate"), corpo.get("forcar"), corpo.get("params"))
                from .aprovacao import estado as estado_audio
                if not ids:
                    return self._json({"erro": "nada para enfileirar agora (veja a Mesa: o que falta aparece lá)"}, 400)
                return self._json({"lote": lote, "jobs": ids, "audio_aprovado": estado_audio(corpo["obra"], corpo["ep"], c)["aprovado"]})
            except Exception as ex:
                return self._json({"erro": f"{ex}" if isinstance(ex, RuntimeError) else f"{type(ex).__name__}: {ex}"}, 500)
        if self.path == "/enfileirar":
            try:
                if corpo.get("tipo") not in ETAPAS:
                    return self._json({"erro": f"etapa desconhecida: {corpo.get('tipo')}"}, 400)
                jid = db.enfileirar(c, corpo["tipo"], corpo["obra"], f"{int(corpo['ep']):02d}", corpo.get("parte"), corpo.get("params"))
                return self._json({"job": jid})
            except Exception as ex:
                return self._json({"erro": f"{type(ex).__name__}: {ex}"}, 500)
        if self.path.startswith("/cancelar/"):
            return self._json({"ok": cancelar(c, int(self.path.rsplit("/", 1)[1]))})
        if self.path in ("/pausar", "/retomar"):
            ESTADO["pausado"] = self.path == "/pausar"
            return self._json({"pausado": ESTADO["pausado"]})
        self._json({"erro": "rota desconhecida"}, 404)


def semear_demo():
    """Demonstração: o banco começa vazio, então registra como "em dia" toda etapa cujas saídas já existem nas obras de
    exemplo (sem isso a Mesa mostraria "refazer" em tudo o que está pronto)."""
    from .config import PROJETOS
    from .obra import ler_json
    c = db.conectar()
    for raiz in sorted(p for p in PROJETOS.iterdir() if (p / "projeto.json").exists()):
        for n_ep in ler_json(raiz / "projeto.json", {}).get("episodios", {}):
            ep = Episodio(raiz.name, n_ep)
            if not ep.roteiro_arq.exists():
                continue
            for tipo in CADEIA:
                e = ETAPAS[tipo]
                for n in (ep.partes() if e["escopo"] == "parte" else [None]):
                    try:
                        sit, ass, ent = situacao(ep, tipo, n, c)
                        saidas = e["saidas_ok"](ep, n) if "saidas_ok" in e else all(Path(s).exists() for s in e["saidas"](ep, n))
                    except Exception:
                        continue
                    if sit != "em dia" and saidas:
                        db.gravar_artefato(c, chave(ep, tipo, n), ass, ent, None)
    c.commit()


def servidor(so_api=False):
    """Worker + API. so_api=True: só a API e a interface (quando outro processo já é o dono da GPU)."""
    import os, sys

    class Servidor(ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            if isinstance(sys.exc_info()[1], (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
                return                                              # navegador fechou a conexão no meio: não é erro
            super().handle_error(request, client_address)

    srv = Servidor(("127.0.0.1", PORTA_API), Api)                   # porta 0 = o sistema escolhe uma livre
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    if DEMO:
        semear_demo()
    if so_api or DEMO:
        print(f"Origami{' (demonstração)' if DEMO else ''}: interface em {url}  (Ctrl+C para parar)", flush=True)
        if os.environ.get("ORIGAMI_ABRIR") == "1":             # atalho de clique duplo: abre o navegador sozinho
            import webbrowser
            threading.Timer(0.8, webbrowser.open, (url,)).start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        return
    # a trava ANTES de abrir a janela: com outro motor no ar, este não sobe
    try:
        travar_worker()
    except SystemExit as ex:
        ESTADO["sem_worker"] = str(ex)
        print(f"Origami: {ex} · só API/interface em http://127.0.0.1:{PORTA_API}", flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Origami: worker no ar, API em http://127.0.0.1:{PORTA_API}  (Ctrl+C para parar)", flush=True)
    try:
        _laco(drenar=False, saida=lambda s: print(time.strftime("%H:%M:%S ") + s, flush=True))
    except KeyboardInterrupt:
        ESTADO["parar"] = True
    srv.shutdown()
