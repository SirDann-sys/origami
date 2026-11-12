# As etapas da cadeia de criação, cada uma embrulhando o script já validado no piloto (sem reescrever nada).
# Cada etapa declara:
#   recurso  : quem usa (cpu | gpu:voz | gpu:whisper | gpu:imagem | nvenc) → o worker libera a GPU na troca
#   escopo   : "ep" (uma vez por episódio) ou "parte" (uma por parte; o job pode pedir várias de uma vez)
#   entradas : tudo de que o resultado depende (sha1 de arquivos, valores, e o sha1 do PRÓPRIO script).
#              Se a assinatura das entradas não mudou e as saídas existem, a etapa é pulada.
#              Mudar uma fala refaz só a parte dela. Mudar SÓ o script (entradas iguais) não refaz nada sozinho:
#              a Mesa mostra "código novo disponível" e o autor aplica (job com "forcar"). Ver `situacao`.
#   saidas   : arquivos que precisam existir
#   rodar    : executa e devolve UMA linha de resumo (o log completo vai para logs/job_N.log)
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
import requests
from .config import (PY, BASH, FFMPEG, SCRIPTS, VOICESTUDIO, FERRAMENTAS, RESPIRO_S, LOUDNORM_EP, TOL_DURACAO_S)
from .obra import ler_json, gravar_json, sha1_arquivo, sha1_valor

PROC_ATUAL = {"p": None}       # o subprocesso em execução (para o cancelamento)


class Cancelado(Exception):
    pass


LIMITE_PADRAO_MIN = 240       # nenhum comando de etapa pode passar disto (um comando travado não para a fila)


def executar(cmd, log, cwd=None, limite_min=None):
    """Roda um comando, manda tudo para o log e devolve as últimas linhas. Erro → exceção com o fim do log.
    Passou do limite → mata a árvore de processos e dá erro (o worker segue com a fila)."""
    import os, threading
    log.write(f"\n$ {' '.join(map(str, cmd))}\n"); log.flush()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    p = subprocess.Popen([str(x) for x in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd, env=env,
                         text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    do_worker = threading.get_ident() == PROC_ATUAL.get("thread")
    if do_worker:
        PROC_ATUAL["p"] = p
    limite = (limite_min or LIMITE_PADRAO_MIN) * 60
    estourou, fim = threading.Event(), threading.Event()

    def vigia():                  # acorda no fim normal (fim.set) ou no limite
        if not fim.wait(limite) and p.poll() is None:
            estourou.set()
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    threading.Thread(target=vigia, daemon=True).start()
    linhas = []
    try:
        for l in p.stdout:
            log.write(l)
            if l.strip() and not any(w in l for w in ("Warning", "warn(", "FutureWarning")):
                linhas = (linhas + [l.rstrip()])[-12:]
        p.wait()
    finally:
        fim.set()
        if do_worker:
            PROC_ATUAL["p"] = None
        log.flush()
    if p.returncode != 0:
        if getattr(p, "_cancelado", False):
            raise Cancelado()
        if estourou.is_set():
            raise RuntimeError(f"passou de {limite // 60} min e foi interrompido: {Path(str(cmd[1] if len(cmd) > 1 else cmd[0])).name}")
        raise RuntimeError(f"rc {p.returncode}: " + " | ".join(linhas[-4:]))
    return linhas


def sha_script(nome):
    return sha1_arquivo(SCRIPTS[nome])


def dur_wav(p):
    import soundfile as sf
    return sf.info(str(p)).duration


# ------------------------------------------------------------------ sincronizar
def sinc_rodar(ep, partes, params, log, c):
    """Roteiro → gravacao.json: fala com texto ou voz diferente vira "refazer" (a versão antiga fica guardada)."""
    reg = ler_json(ep.gravacao, {"falas": {}})
    regerar = set(params.get("regerar", []))
    mudou = []
    for p in ep.roteiro["partes"]:
        for i, f in enumerate(p["falas"], 1):
            k = f"{p['parte']:02d}_{i:02d}"
            r = reg["falas"].get(k)
            if not r:
                continue
            editada = r.get("texto") != f["texto"] or r.get("voz") != f["voz"]
            if not editada and k not in regerar:
                continue
            wav = ep.fala_wav(k)
            if wav.exists():
                n = 1
                while (ep.falas_dir / f"{k}_v{n}.wav").exists():
                    n += 1
                wav.replace(ep.falas_dir / f"{k}_v{n}.wav")
                log.write(f"{k}: versão anterior guardada como {k}_v{n}.wav\n")
            if editada:      # texto novo: começa do zero (3 tentativas na conferência)
                r.update(texto=f["texto"], voz=f["voz"], tentativas=0)
            r.update(refazer=True, conferida=False, revisar=False)
            mudou.append(k)
    if mudou:
        gravar_json(ep.gravacao, reg)
    return f"{len(mudou)} fala(s) para gravar de novo" + (f": {', '.join(mudou)}" if mudou else "")


# ------------------------------------------------------------------ voz (gerar + conferir)
def voz_pendentes(ep):
    reg = ler_json(ep.gravacao, {"falas": {}})["falas"]
    pend = []
    for n in ep.partes():
        for k in ep.chaves_falas(n):
            r = reg.get(k)
            if not r or r.get("refazer") or not r.get("conferida") or not ep.fala_wav(k).exists():
                pend.append(k)
    return pend


def voz_rodar(ep, partes, params, log, c):
    try:
        requests.get(VOICESTUDIO + "/profiles", timeout=5).raise_for_status()
    except requests.RequestException:
        raise RuntimeError("o servidor de voz não respondeu (ver dados/logs/voicestudio.log) e reenvie o job")
    base = [PY, SCRIPTS["gravar"], "--roteiro", ep.roteiro_arq, "--elenco", ep.projeto, "--saida", ep.audio]
    ps = sorted({int(k[:2]) for k in voz_pendentes(ep)})
    for rodada in range(4):                       # gerar → conferir até não sobrar nada (3 tentativas por fala)
        executar(base + ["--fase", "gerar", "--partes", *ps], log, cwd=SCRIPTS["gravar"].parent)
        try:
            requests.post(VOICESTUDIO + "/system/flush-memory", timeout=30)
        except requests.RequestException:
            pass
        executar(base + ["--fase", "conferir", "--partes", *ps], log, cwd=SCRIPTS["gravar"].parent)
        reg = ler_json(ep.gravacao)["falas"]
        if not any(reg[k].get("refazer") for k in reg if int(k[:2]) in ps):
            break
    reg = ler_json(ep.gravacao)["falas"]
    revisar = [k for k in reg if int(k[:2]) in ps and reg[k].get("revisar") and not reg[k].get("aprovada_manual")]
    return f"falas gravadas e conferidas nas partes {ps}" + (f" | REVISAR (ouvir): {', '.join(revisar)}" if revisar else "")


# ------------------------------------------------------------------ montar
def montar_entradas(ep, n, c):
    p = ep.parte(n)
    return {"falas": [sha1_arquivo(ep.fala_wav(k), c) for k in ep.chaves_falas(n)],
            "pausas": [float(f.get("pausa", 0.45)) for f in p["falas"]], "script": sha_script("gravar")}


def montar_rodar(ep, partes, params, log, c):
    executar([PY, SCRIPTS["gravar"], "--fase", "montar", "--roteiro", ep.roteiro_arq, "--elenco", ep.projeto,
              "--saida", ep.audio, "--partes", *partes], log, cwd=SCRIPTS["gravar"].parent)
    return " ".join(f"P{n}={dur_wav(ep.parte_wav(n)):.1f}s" for n in partes)


# ------------------------------------------------------------------ trilha: deixa (cue) + stems
def cue_info(ep, n):
    plano = ler_json(ep.plano_cues)
    if not plano:
        raise RuntimeError(f"falta {ep.plano_cues} (humor e final de cada parte)")
    return plano, next(x for x in plano["partes"] if x["parte"] == n)


def cue_entradas(ep, n, c):
    _, info = cue_info(ep, n)
    d = dur_wav(ep.parte_wav(n))
    return {"dur": round(round(d / TOL_DURACAO_S) * TOL_DURACAO_S, 3), "humor": info.get("humor"),
            "final": info.get("final"), "script": sha_script("cues")}


def cue_rodar(ep, partes, params, log, c):
    plano, _ = cue_info(ep, partes[0])
    for x in plano["partes"]:
        if x["parte"] in partes:                  # duração exata: a deixa fecha com voz + 2 s
            d = round(dur_wav(ep.parte_wav(x["parte"])), 3)
            x["duracao_voz_s"], x["duracao_s"] = d, round(d + 2.0, 3)
    gravar_json(ep.plano_cues, plano)
    with tempfile.TemporaryDirectory() as t:
        so = dict(plano, partes=[x for x in plano["partes"] if x["parte"] in partes])
        gravar_json(Path(t) / "plano.json", so)
        linhas = executar([PY, SCRIPTS["cues"], "--plano", Path(t) / "plano.json", "--saida", Path(t) / "cues"], log,
                          cwd=SCRIPTS["cues"].parent)
        for n in partes:
            ep.cue_mid(n).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(t) / "cues" / f"cue_parte{n:02d}.mid", ep.cue_mid(n))
    return " | ".join(l.split("|")[0].strip() for l in linhas if l.startswith("parte"))


def stems_entradas(ep, n, c):
    return {"cue": sha1_arquivo(ep.cue_mid(n), c), "script": sha_script("stems")}


def stems_saidas(ep, n):
    return [ep.stems_dir(n) / "piano.wav"]


def stems_rodar(ep, partes, params, log, c):
    for n in partes:
        executar([PY, SCRIPTS["stems"], "--midi", ep.cue_mid(n), "--saida", ep.stems_dir(n)], log, cwd=SCRIPTS["stems"].parent)
    return f"stems das partes {partes}"


# ------------------------------------------------------------------ mixagem (SoundCraft por script)
def mix_entradas(ep, n, c):
    return {"voz": sha1_arquivo(ep.parte_wav(n), c),
            "stems": {f.name: sha1_arquivo(f, c) for f in sorted(ep.stems_dir(n).glob("*.wav"))},
            "scripts": [sha_script(s) for s in ("mixar", "receita", "envelope")]}


def mix_rodar(ep, partes, params, log, c):
    out = []
    for n in partes:
        ep.sessao(n).parent.mkdir(parents=True, exist_ok=True)
        l = executar([PY, SCRIPTS["mixar"], "--voz", ep.parte_wav(n), "--stems", ep.stems_dir(n), "--saida", ep.mix_wav(n),
                      "--sessao", ep.sessao(n)], log, cwd=SCRIPTS["mixar"].parent)
        out.append(f"P{n}: " + l[-1].split("|")[2].strip() if l and "|" in l[-1] else f"P{n}")
    return " · ".join(out)


# ------------------------------------------------------------------ episódio completo (áudio)
def epi_entradas(ep, n, c):
    return {"partes": [sha1_arquivo(ep.mix_wav(k), c) for k in ep.partes()], "respiro": RESPIRO_S, "loud": LOUDNORM_EP}


def epi_rodar(ep, partes, params, log, c):
    sys.path.insert(0, str(FERRAMENTAS / "voz"))
    from comum import ler_wav, gravar_wav
    import numpy as np
    ped = []
    for k in ep.partes():
        y, sr = ler_wav(ep.mix_wav(k), mono=False)
        ped += [y, np.zeros((int(RESPIRO_S * sr), 2), dtype="float32")]
    bruto = ep.mix_dir / "_episodio_bruto.wav"
    gravar_wav(bruto, np.concatenate(ped[:-1]), sr)
    executar([FFMPEG, "-y", "-loglevel", "error", "-i", bruto, "-af", LOUDNORM_EP, "-ar", "48000", "-c:a", "pcm_s24le",
              ep.episodio_wav()], log)
    bruto.unlink()
    return f"{ep.episodio_wav().name} {dur_wav(ep.episodio_wav()) / 60:.1f} min"


# ------------------------------------------------------------------ tempos (Whisper por palavra)
def tempos_entradas(ep, n, c):
    p = ep.parte(n)
    return {"falas": [sha1_arquivo(ep.fala_wav(k), c) for k in ep.chaves_falas(n)],
            "textos": [f["texto"] for f in p["falas"]], "pausas": [f.get("pausa", 0.45) for f in p["falas"]],
            "script": sha_script("tempos")}


def tempos_saidas_ok(ep, n):
    t = ler_json(ep.tempos)
    return bool(t) and str(n) in t["partes"]


def tempos_rodar(ep, partes, params, log, c):
    executar([PY, SCRIPTS["tempos"], "--roteiro", ep.roteiro_arq, "--falas", ep.falas_dir, "--saida", ep.tempos,
              "--partes", *partes], log, cwd=SCRIPTS["tempos"].parent)
    return f"tempos por palavra das partes {partes}"


# ------------------------------------------------------------------ vídeo 9:16 por parte
def rotulo(ep, n):
    return f"EPISÓDIO {int(ep.ep)} · PARTE {n}/{len(ep.partes())}"


def cor_txt(cor):
    return ",".join(str(int(x)) for x in cor)


def estilo_entradas(ep, c):
    """O que vem da obra/marca e muda a cara do vídeo: mudar a marca ou o destaque refaz os vídeos."""
    return {"marca": sha1_arquivo(ep.marca_arq, c), "destaque": cor_txt(ep.destaque()),
            "simbolos": [sha1_arquivo(ep.marca[k], c) for k in ("simbolo_branco", "simbolo_cor")]}


def cartao_args(ep, n):
    total = len(ep.partes())
    return ["--cartao", "parte", "--proxima", f"PARTE {n + 1}/{total}"] if n < total else ["--cartao", "fim"]


def video_entradas(ep, n, c):
    pv = ler_json(ep.plano_video)
    return {"tempos": sha1_valor(ler_json(ep.tempos)["partes"].get(str(n))), "audio": sha1_arquivo(ep.mix_wav(n), c),
            "imagens": {i: sha1_arquivo(ep.imagens / f"{i}.png", c) for i in ep.imagens_da_parte(n)},
            "plano": sha1_valor({k: pv[k] for k in ("titulo_tela", "narrador", "nomes", "retratos")} | {"segs": pv["partes"][str(n)]}),
            "rotulo": rotulo(ep, n), "cartao": cartao_args(ep, n), "estilo": estilo_entradas(ep, c), "script": sha_script("compor")}


def video_rodar(ep, partes, params, log, c):
    ep.video_ep.mkdir(parents=True, exist_ok=True)
    falta = [i for n in partes for i in ep.imagens_da_parte(n) if not (ep.imagens / f"{i}.png").exists()]
    if falta:
        raise RuntimeError(f"faltam imagens: {sorted(set(falta))} (rode: origami imagens / ampliar)")
    total = len(ep.partes())
    for n in partes:
        executar([PY, SCRIPTS["compor"], "--formato", "vertical", "--parte", n, "--plano", ep.plano_video, "--tempos", ep.tempos,
                  "--imagens", ep.imagens, "--audio", ep.mix_wav(n), "--saida", ep.video_parte(n), "--rotulo", rotulo(ep, n),
                  "--marca", ep.marca_arq, "--destaque", cor_txt(ep.destaque()), "--ep", int(ep.ep), *cartao_args(ep, n),
                  "--titulo_meta", f"Parte {n}/{total}"],
                 log, cwd=SCRIPTS["compor"].parent)
    return f"vídeos 9:16 das partes {partes}"


# ------------------------------------------------------------------ vídeo 16:9 do episódio
def rotulo_16x9(ep):
    return f"EPISÓDIO {int(ep.ep)} · {ep.titulo_ep().upper()}"


def v169_entradas(ep, n, c):
    ids = sorted({i for k in ep.partes() for i in ep.imagens_da_parte(k)})
    return {"audio": sha1_arquivo(ep.episodio_wav(), c), "mix": [sha1_arquivo(ep.mix_wav(k), c) for k in ep.partes()],
            "tempos": sha1_arquivo(ep.tempos, c), "plano": sha1_arquivo(ep.plano_video, c),
            "imagens": {i: sha1_arquivo(ep.imagens / f"{i}.png", c) for i in ids},
            "rotulo": rotulo_16x9(ep), "estilo": estilo_entradas(ep, c),
            "scripts": [sha_script("compor"), sha_script("ep16x9")]}


def v169_rodar(ep, partes, params, log, c):
    import os
    ep.video_ep.mkdir(parents=True, exist_ok=True)
    m = ep.marca
    env = {"MARCA": str(ep.marca_arq), "DESTAQUE": cor_txt(ep.destaque()), "ARTISTA": f"{m['nome']} · {m['assinatura']}",
           "COMENTARIO": m["handle"], "DIREITOS": m["direitos"]}
    os.environ.update(env)     # o executar() herda o ambiente
    try:
        executar([BASH, SCRIPTS["ep16x9"], ep.raiz, ep.ep, len(ep.partes()), ep.episodio_wav(), ep.video_16x9(), rotulo_16x9(ep)],
                 log, cwd=SCRIPTS["ep16x9"].parent)
    finally:
        for k in env:
            os.environ.pop(k, None)
    return f"{ep.video_16x9().name}"


# ------------------------------------------------------------------ imagens (só sob pedido: envolvem escolha)
def imagens_rodar(ep, partes, params, log, c):
    from .servicos import garantir_comfy
    garantir_comfy(log)
    cmd = [PY, SCRIPTS["imagens"], "--lista", ep.assets, "--saida", ep.imagens]
    if params.get("ampliar"):
        cmd.append("--ampliar")
    else:
        cmd += ["--sementes", params.get("sementes", 2)]
    if params.get("so"):
        cmd += ["--so", *params["so"]]
    linhas = executar(cmd, log, cwd=SCRIPTS["imagens"].parent)
    extra = ""
    if params.get("ampliar") and params.get("so"):
        from .imagens_video import registrar_referencias
        novos = registrar_referencias(ep, params["so"], log)
        extra = f" · rosto oficial: {', '.join(novos)}" if novos else ""
    return f"{len([l for l in linhas if l.strip()])} linhas; " + (linhas[-1] if linhas else "") + extra


# ------------------------------------------------------------------ arte de divulgação (guia de arte da obra)
def guia_arte(ep):
    g = ler_json(ep.raiz / "01_biblia" / "guia_arte.json")
    if not g:
        raise RuntimeError(f"falta {ep.raiz / '01_biblia' / 'guia_arte.json'} (estilo e personagens da obra)")
    return g


def montar_prompts(ep):
    """Cenas do episódio → prompts completos: {ana@trabalho} vira a descrição fixa do guia; o estilo vem do guia.
    Devolve (assets, alertas). Alertas = consistência: símbolo antes da hora, personagem/contexto inexistente."""
    import re
    g, cenas = guia_arte(ep), ler_json(ep.arte_assets)
    if not cenas:
        raise RuntimeError(f"falta {ep.arte_assets} (as cenas do episódio)")
    alertas, itens = [], []
    for it in cenas["itens"]:
        def troca(m):
            quem, _, ctx = m.group(1).partition("@")
            d = g["personagens"].get(quem, {})
            if (ctx or ep.contexto_padrao()) not in d:
                alertas.append(f"{it['id']}: personagem/contexto desconhecido {{{m.group(1)}}}")
                return m.group(0)
            return d[ctx or ep.contexto_padrao()]
        prompt = re.sub(r"\{([a-z_]+(?:@[a-z_]+)?)\}", troca, it["prompt"])
        for nome, s in g.get("simbolos", {}).items():
            if int(ep.ep) < s["desde_ep"] and any(w in prompt.lower() for w in s["palavras"]):
                alertas.append(f"{it['id']}: '{nome}' só aparece a partir do Ep. {s['desde_ep']:02d}")
        extra = {} if it.get("refs") else referencias_da_cena(ep, g, it["prompt"])
        if g.get("estilo_capas") and g["estilo_capas"].strip()[:40] not in prompt:
            # a receita das capas autorais (uma luz, frio e escuro, topo vazio) entra em toda arte de divulgação
            prompt = prompt.rstrip(". ") + ". " + g["estilo_capas"].strip()
        itens.append(dict(it, prompt=prompt, **extra))
    return {"estilo": g["estilo"], "itens": itens}, alertas


def referencias_da_cena(ep, g, prompt):
    """Aparência fixa nas capas: cada personagem da cena entra também como IMAGEM de
    referência, não só pela descrição. Guia de arte → "referencias_capa": {personagem: {contexto: {"frente": arq, "costas": arq}}},
    recortes das peças já aprovadas. Por contexto: a personagem com o uniforme de trabalho não serve para a cena fora dele.
    A vista sai da frase da cena ("from behind"… → costas). Até 3 por imagem.
    Devolve {"refs": [...], "refs_quem": ["ana (frente)", …]} ou {} quando o guia não tem referências."""
    import re
    refs_guia = g.get("referencias_capa", {})
    if not refs_guia:
        return {}
    costas = re.compile(r"from behind|back to (?:the )?(?:viewer|camera)|backs? of (?:the |her |his |their )?heads?|seen from the back", re.I)
    refs, quem = [], []
    for frase in re.split(r"(?<=[.;])\s+", prompt):
        for m in re.finditer(r"\{([a-z_]+)(?:@([a-z_]+))?\}", frase):
            p, ctx = m.group(1), m.group(2) or ep.contexto_padrao()
            vista = "costas" if costas.search(frase) else "frente"
            arq = refs_guia.get(p, {}).get(ctx, {}).get(vista)
            if not arq or any(q.startswith(p + " ") for q in quem) or len(refs) >= 3:
                continue
            caminho = ep.raiz / arq
            if caminho.exists():
                refs.append(str(caminho)); quem.append(f"{p} ({ctx}, {vista})")
    return {"refs": refs, "refs_quem": quem} if refs else {}


def arte_rodar(ep, partes, params, log, c):
    from .servicos import garantir_comfy
    assets, alertas = montar_prompts(ep)
    if alertas and not params.get("ignorar_alertas"):
        raise RuntimeError("consistência: " + " | ".join(alertas))
    garantir_comfy(log)
    lista = ep.arte / "_assets_montado.json"
    gravar_json(lista, assets)
    cmd = [PY, SCRIPTS["imagens"], "--lista", lista, "--saida", ep.arte]   # candidatas em arte/candidatas/, ampliadas em arte/
    cmd += ["--ampliar"] if params.get("ampliar") else ["--sementes", params.get("sementes", 2)]
    if params.get("so"):
        cmd += ["--so", *params["so"]]
    linhas = executar(cmd, log, cwd=SCRIPTS["imagens"].parent)
    extra = ""
    if params.get("ampliar"):
        extra = pos_ampliar_arte(ep, params.get("so"), log)
    return (linhas[-1] if linhas else "ok") + (f" | alertas ignorados: {len(alertas)}" if alertas else "") + extra


def pos_ampliar_arte(ep, so, log):
    """Depois de ampliar a escolhida de cada cena: registra de qual candidata veio (a capa passa a usar a ampliada) e,
    se a triagem viu rosto grande de frente, aplica o acabamento de rosto (camada 2) com as tags da ficha."""
    from .obra import atualizar_json
    g = guia_arte(ep)
    feitos, acab = [], []

    def marcar(d):
        for it in d["itens"]:
            if (so and it["id"] not in so) or not it.get("escolhida") or not (ep.arte / f"{it['id']}.png").exists():
                continue
            it["ampliada_de"] = it["escolhida"]
            feitos.append(it["id"])
            info = (it.get("triagem") or {}).get("resultado", {}).get(it["escolhida"], {})
            quem = [p for p in info.get("rostos", []) if p in g.get("tags_rosto", {})]
            if g.get("acabamento_rosto") and info.get("rosto_grande_de_frente") and quem and len(quem) == len(info.get("rostos", [])):
                acab.append((it["id"], quem))
    atualizar_json(ep.arte_assets, marcar, {"itens": []})
    for id_, quem in acab:
        arq = ep.arte / f"{id_}.png"
        bruto = ep.arte / f"{id_}_sem_acabamento.png"
        shutil.copy2(arq, bruto)
        try:
            executar([PY, SCRIPTS["acabamento"], "--entrada", bruto, "--saida", arq, "--guia", ep.raiz / "01_biblia" / "guia_arte.json",
                      "--personagens", ",".join(quem)], log, cwd=SCRIPTS["acabamento"].parent, limite_min=20)
        except RuntimeError as ex:          # sem acabamento a imagem ainda serve: não derruba a etapa
            shutil.copy2(bruto, arq)
            log.write(f"acabamento de rosto falhou em {id_}: {ex}\n")
    if ep.capas_spec.exists():
        from .arte import resolver_imagens
        atualizar_json(ep.capas_spec, lambda s: [s.update(resolver_imagens(ep, s, cena_escolhida=i)) for i in feitos])
    return (f" | ampliadas: {', '.join(feitos)}" if feitos else "") + (f" | rosto acabado: {', '.join(i for i, _ in acab)}" if acab else "")


def triagem_rodar(ep, partes, params, log, c):
    from . import triagem
    return triagem.triar(ep, params.get("alvo", "arte"), params.get("so"), log)


def capas_spec(ep):
    s = ler_json(ep.capas_spec)
    if not s:
        raise RuntimeError(f"falta {ep.capas_spec} (cena e gancho de cada parte + miniatura)")
    return s


def capas_saidas(ep, n):
    s = capas_spec(ep); d = Path(s["saida"]) if Path(s["saida"]).is_absolute() else ep.arte / s["saida"]
    out = [d / f"capa_parte_{p['n']:02d}.jpg" for p in s.get("partes", [])]
    return out + ([d / s["miniatura"]["arquivo"]] if "miniatura" in s else [])


def capas_entradas(ep, n, c):
    s = capas_spec(ep)
    imgs = [p.get("imagem") for p in s.get("partes", [])] + ([s["miniatura"].get("imagem")] if "miniatura" in s else [])
    return {"spec": sha1_valor(s), "imagens": [sha1_arquivo(ep.arte / i, c) if i else None for i in imgs],
            "marca": sha1_arquivo(ep.marca_arq, c), "script": sha_script("capas")}


def capas_rodar(ep, partes, params, log, c):
    from .arte import capas_prontas
    ok, falta = capas_prontas(ep)
    if not ok:
        raise RuntimeError(falta + " (aba Arte)")
    l = executar([PY, SCRIPTS["capas"], "--spec", ep.capas_spec, "--marca", ep.marca_arq], log, cwd=ep.arte)
    return f"{len([x for x in l if x.startswith('ok')])} peças"


# ------------------------------------------------------------------ capítulo do Wattpad
def wattpad_saidas(ep, n):
    import re
    base = f"wattpad_cap{int(ep.ep):02d}_{re.sub(r'[^0-9A-Za-zÀ-ú]+', '_', ep.titulo_ep()).strip('_')}"
    return [ep.publicacao / f"{base}.html", ep.publicacao / f"{base}.txt"]


def wattpad_entradas(ep, n, c):
    if not ep.mestre.exists():
        raise RuntimeError(f"falta o texto-mestre {ep.mestre}")
    return {"mestre": sha1_arquivo(ep.mestre, c), "titulo": ep.titulo_ep(), "marca": sha1_arquivo(ep.marca_arq, c),
            "script": sha_script("wattpad")}


def wattpad_rodar(ep, partes, params, log, c):
    l = executar([PY, SCRIPTS["wattpad"], "--mestre", ep.mestre, "--saida", ep.publicacao, "--ep", int(ep.ep),
                  "--titulo", ep.titulo_ep(), "--marca", ep.marca_arq], log, cwd=SCRIPTS["wattpad"].parent)
    return l[-1] if l else "ok"


# ------------------------------------------------------------------ entrega (pasta de publicação, peça por peça)
def entregaveis(ep):
    """(origem, nome na entrega, grupo). Grupos: parte:N, 16x9, capas, miniatura, wattpad."""
    sg, e, tit = ep.sigla(), ep.ep, ep.titulo_ep()
    itens = [(ep.video_parte(n), f"{sg}_Ep{e}_Parte{n:02d}_9x16.mp4", f"parte:{n}") for n in ep.partes()]
    itens.append((ep.video_16x9(), f"{sg}_Ep{e}_{tit}_16x9.mp4", "16x9"))
    if ep.capas_spec.exists():
        for s in capas_saidas(ep, None):
            grupo = "miniatura" if not s.name.startswith("capa_parte") else "capas"
            itens.append((s, ("capas_partes/" if grupo == "capas" else "") + s.name, grupo))
    if ep.mestre.exists():
        itens += [(s, s.name, "wattpad") for s in wattpad_saidas(ep, None)]
        from .publicacao import imagens_wattpad
        for k, w in enumerate(imagens_wattpad(ep)):
            itens.append((Path(w["imagem"]), f"wattpad_imagens/{'00_topo' if w['topo'] else f'{k:02d}'}_{w['id']}.png", "wattpad"))
    return itens


def entregar_rodar(ep, partes, params, log, c):
    so = set(params.get("so") or [])
    copiados, faltam = [], []
    for orig, nome, grupo in entregaveis(ep):
        if so and grupo not in so and grupo.split(":")[0] not in so:
            continue
        if not orig.exists():
            faltam.append(nome); continue
        dest = ep.entrega / nome
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if dest.exists() and os.path.samefile(orig, dest):
                continue                          # já é o mesmo arquivo (hardlink)
        except OSError:
            pass
        # hardlink em vez de cópia: a pasta de publicação não ocupa o disco de novo
        from .arquivos import vincular
        vincular(orig, dest); copiados.append(nome)
    return f"{len(copiados)} arquivo(s) em {ep.entrega}" + (f" | FALTAM: {', '.join(faltam)}" if faltam else "")


# ------------------------------------------------------------------ texto: mestre + alarme pelo trabalhador
def mestre_rodar(ep, partes, params, log, c):
    from . import texto
    return texto.escrever(ep, params.get("instrucao", ""), log)


def roteiro_rodar(ep, partes, params, log, c):
    from . import roteiro
    return roteiro.gerar(ep, log)


def elenco_rodar(ep, partes, params, log, c):
    from . import elenco
    try:
        requests.get(VOICESTUDIO + "/profiles", timeout=5).raise_for_status()
    except requests.RequestException:
        raise RuntimeError("o servidor de voz não respondeu (ver dados/logs/voicestudio.log) e reenvie")
    return elenco.gerar_candidatas(ep.obra, params["personagem"], params["genero"], params["idade"], params["tom"],
                                   params["frase"], params.get("velocidade", 0.92), params.get("n", 4), log)


def kit_rodar(ep, partes, params, log, c):
    from . import kit
    return kit.gerar(ep, log)


def revisar_rodar(ep, partes, params, log, c):
    from . import texto
    return texto.revisar(ep, params.get("instrucao", ""), log)


def corrigir_rodar(ep, partes, params, log, c):
    from . import texto
    return texto.corrigir_alertas(ep, params.get("ids"), log)


def cenas_rodar(ep, partes, params, log, c):
    from . import arte
    return arte.sugerir(ep, log)


def amostra_rodar(ep, partes, params, log, c):
    from . import pronuncia
    return pronuncia.amostra(ep.obra, params["personagem"], params["texto"])


def postagem_rodar(ep, partes, params, log, c):
    from . import postagem
    return postagem.agendar(ep.obra, set(params.get("ids", [])), log)


def previa_rodar(ep, partes, params, log, c):
    """Quadros sem legenda nos momentos críticos de uma parte (antes de renderizar tudo, ou para conferir uma marca)."""
    from .revvideo import momentos_criticos, previa_dir
    n = int(params["parte"])
    ts = params.get("tempos") or momentos_criticos(ep, n)
    d = previa_dir(ep); d.mkdir(parents=True, exist_ok=True)
    for velho in d.glob(f"parte_{n:02d}_t*.png"):
        velho.unlink()
    total = len(ep.partes())
    executar([PY, SCRIPTS["compor"], "--formato", "vertical", "--parte", n, "--plano", ep.plano_video, "--tempos", ep.tempos,
              "--imagens", ep.imagens, "--audio", ep.mix_wav(n), "--saida", d / f"parte_{n:02d}.mp4", "--rotulo", rotulo(ep, n),
              "--marca", ep.marca_arq, "--destaque", cor_txt(ep.destaque()), "--ep", int(ep.ep), *cartao_args(ep, n),
              "--quadros", ",".join(str(x) for x in ts)], log, cwd=SCRIPTS["compor"].parent)
    return f"prévia da parte {n}: {len(ts)} quadros"


def obra_rodar(ep, partes, params, log, c):
    """Assistente de obra nova: um passo por job (ler, estrutura, guia, bíblia)."""
    from . import obra_nova as on
    passo = params["passo"]
    return {"ler": on.ler, "estrutura": on.estruturar, "guia": on.guiar, "biblia": on.consolidar}[passo](ep.obra, log)


def alarme_rodar(ep, partes, params, log, c):
    from . import texto
    al = texto.alarme(ep, log)
    crit = sum(1 for a in al if a["gravidade"] == "critico")
    return f"alarme: {crit} crítico(s), {len(al) - crit} atenção"


# ------------------------------------------------------------------ registro
ETAPAS = {
    "sincronizar": dict(recurso="cpu", escopo="ep", rodar=sinc_rodar, sempre=True),
    "voz":        dict(recurso="gpu:voz", escopo="ep", rodar=voz_rodar, precisa=lambda ep, c: bool(voz_pendentes(ep))),
    "montar":     dict(recurso="cpu", escopo="parte", entradas=montar_entradas, saidas=lambda ep, n: [ep.parte_wav(n)], rodar=montar_rodar),
    "cue":        dict(recurso="cpu", escopo="parte", entradas=cue_entradas, saidas=lambda ep, n: [ep.cue_mid(n)], rodar=cue_rodar),
    "stems":      dict(recurso="cpu", escopo="parte", entradas=stems_entradas, saidas=stems_saidas, rodar=stems_rodar),
    "mix":        dict(recurso="cpu", escopo="parte", entradas=mix_entradas, saidas=lambda ep, n: [ep.mix_wav(n)], rodar=mix_rodar),
    "episodio":   dict(recurso="cpu", escopo="ep", entradas=epi_entradas, saidas=lambda ep, n: [ep.episodio_wav()], rodar=epi_rodar),
    "tempos":     dict(recurso="gpu:whisper", escopo="parte", entradas=tempos_entradas, saidas_ok=tempos_saidas_ok, rodar=tempos_rodar),
    "video":      dict(recurso="nvenc", escopo="parte", entradas=video_entradas, saidas=lambda ep, n: [ep.video_parte(n)], rodar=video_rodar),
    "video16x9":  dict(recurso="nvenc", escopo="ep", entradas=v169_entradas, saidas=lambda ep, n: [ep.video_16x9()], rodar=v169_rodar),
    "imagens":    dict(recurso="gpu:imagem", escopo="ep", rodar=imagens_rodar, sempre=True),
    "arte":       dict(recurso="gpu:imagem", escopo="ep", rodar=arte_rodar, sempre=True),
    "capas":      dict(recurso="cpu", escopo="ep", entradas=capas_entradas, saidas=capas_saidas, rodar=capas_rodar),
    "wattpad":    dict(recurso="cpu", escopo="ep", entradas=wattpad_entradas, saidas=wattpad_saidas, rodar=wattpad_rodar),
    "entregar":   dict(recurso="cpu", escopo="ep", rodar=entregar_rodar, sempre=True),
    "mestre":     dict(recurso="claude", escopo="ep", rodar=mestre_rodar, sempre=True),
    "alarme":     dict(recurso="claude", escopo="ep", rodar=alarme_rodar, sempre=True),
    "roteiro":    dict(recurso="claude", escopo="ep", rodar=roteiro_rodar, sempre=True),
    "elenco":     dict(recurso="gpu:voz", escopo="ep", rodar=elenco_rodar, sempre=True),
    "kit":        dict(recurso="claude", escopo="ep", rodar=kit_rodar, sempre=True),
    "corrigir":   dict(recurso="claude", escopo="ep", rodar=corrigir_rodar, sempre=True),
    "revisar":    dict(recurso="claude", escopo="ep", rodar=revisar_rodar, sempre=True),
    "cenas":      dict(recurso="claude", escopo="ep", rodar=cenas_rodar, sempre=True),
    "previa":     dict(recurso="cpu", escopo="ep", rodar=previa_rodar, sempre=True),
    "postagem":   dict(recurso="rede", escopo="ep", rodar=postagem_rodar, sempre=True),
    "amostra":    dict(recurso="gpu:voz", escopo="ep", rodar=amostra_rodar, sempre=True),
    "obra":       dict(recurso="claude", escopo="ep", rodar=obra_rodar, sempre=True),
    "triagem":    dict(recurso="claude", escopo="ep", rodar=triagem_rodar, sempre=True),
}
# a cadeia completa de um episódio, na ordem (agrupada por modelo na GPU: voz → whisper → nvenc)
CADEIA = ["sincronizar", "voz", "montar", "cue", "stems", "mix", "episodio", "tempos", "video", "video16x9",
          "capas", "wattpad", "entregar"]

# do que cada etapa da cadeia depende: se uma etapa falha, só caem as que dependem dela
DEPENDE = {"voz": ["sincronizar"], "montar": ["voz"], "cue": ["montar"], "stems": ["cue"], "mix": ["stems", "montar"],
           "episodio": ["mix"], "tempos": ["montar"], "video": ["tempos", "mix"], "video16x9": ["tempos", "episodio"],
           "capas": [], "wattpad": [], "entregar": ["episodio", "video", "video16x9", "capas", "wattpad"]}


def dependentes(tipo):
    """Todas as etapas da cadeia que dependem (direta ou indiretamente) de `tipo`."""
    out, novo = set(), {tipo}
    while novo:
        novo = {t for t, ds in DEPENDE.items() if t not in out and any(d in novo or d in out for d in ds)} - out
        out |= novo
    return out


def chave(ep, tipo, n):
    return f"{ep.obra}|{ep.ep}|{tipo}|{n if n is not None else '-'}"


CHAVES_CODIGO = ("script", "scripts")


def _sem_codigo(ent):
    """As entradas sem o sha1 dos scripts (ida e volta pelo JSON, para comparar com o que está guardado no banco)."""
    return {k: v for k, v in json.loads(json.dumps(ent, ensure_ascii=False)).items() if k not in CHAVES_CODIGO}


def situacao(ep, tipo, n, c):
    """Devolve (situação, assinatura, entradas). Situação:
      "em dia"      → saídas existem e nada mudou;
      "refazer"     → faltam saídas, nunca rodou ou mudou alguma ENTRADA (fala, imagem, marca, tempos…);
      "codigo novo" → as entradas são as mesmas e só o código (script/etapa) mudou.
    Código novo não refaz episódio pronto sozinho (uma correção pequena num script não deve custar uma hora de
    renderização): a Mesa avisa e só roda quando o autor aplicar."""
    e = ETAPAS[tipo]
    ent = e["entradas"](ep, n, c)
    ass = sha1_valor(ent)
    ok_saida = e["saidas_ok"](ep, n) if "saidas_ok" in e else all(Path(s).exists() for s in e["saidas"](ep, n))
    reg = c.execute("SELECT assinatura, entradas FROM artefato WHERE chave=?", (chave(ep, tipo, n),)).fetchone()
    if not ok_saida or not reg:
        return "refazer", ass, ent
    if reg[0] == ass:
        return "em dia", ass, ent
    try:
        antigas = json.loads(reg[1]) if reg[1] else None
    except ValueError:
        antigas = None
    if isinstance(antigas, dict) and _sem_codigo(antigas) == _sem_codigo(ent):
        return "codigo novo", ass, ent
    return "refazer", ass, ent


def desatualizada(ep, tipo, n, c):
    """Devolve (precisa_rodar, assinatura, entradas). Só código novo NÃO conta como precisa rodar (ver `situacao`);
    para aplicar, o job vai com "forcar"."""
    e = ETAPAS[tipo]
    if e.get("sempre"):
        return True, None, None
    if "precisa" in e:
        return e["precisa"](ep, c), None, None
    sit, ass, ent = situacao(ep, tipo, n, c)
    return sit == "refazer", ass, ent
