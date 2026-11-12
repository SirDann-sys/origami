# Pronúncia: como a voz deve FALAR cada palavra (o texto escrito não muda). O autor escreve como soa, ouve uma
# amostra com a voz de um personagem e regrava só as falas que têm a palavra. Mesma regra da gravação: global (recursos) + a da obra (01_biblia/pronuncia.json); a da obra vence.
import json, re, sys, time, uuid
import requests
from .config import PROJETOS, RECURSOS, VOZES, DADOS, FERRAMENTAS, VOICESTUDIO, FFMPEG
from .obra import Episodio, ler_json, gravar_json

AMOSTRAS = DADOS / "amostras"


def _arq(obra):
    return PROJETOS / obra / "01_biblia" / "pronuncia.json"


def _comum():
    if str(FERRAMENTAS / "voz") not in sys.path:
        sys.path.insert(0, str(FERRAMENTAS / "voz"))
    import comum
    return comum


def painel(obra):
    d = ler_json(_arq(obra), {})
    cfg = ler_json(PROJETOS / obra / "projeto.json", {})
    return {"obra": obra, "palavras": {k: v for k, v in d.items() if not k.startswith("_")},
            "globais": {k: v for k, v in ler_json(RECURSOS / "pronuncia_global.json", {}).items() if not k.startswith("_")},
            "nota": d.get("_nota", ""), "personagens": sorted(cfg.get("elenco", {})), "narrador": cfg.get("video", {}).get("narrador") or cfg.get("pov", "").split(":")[-1],
            "amostras": ultimas_amostras(obra),
            "episodios": sorted(k for k in cfg.get("episodios", {}) if (PROJETOS / obra / "04_roteiro_audio" / f"ep{k}.json").exists())}


def ultimas_amostras(obra, n=6):
    fichas = sorted((f for f in AMOSTRAS.glob("*.json") if f.with_suffix(".wav").exists()),
                    key=lambda f: f.with_suffix(".wav").stat().st_mtime, reverse=True) if AMOSTRAS.exists() else []
    out = []
    for f in fichas:
        d = ler_json(f, {})
        if d.get("obra") == obra and f.with_suffix(".wav").exists():
            out.append({**d, "caminho": str(f.with_suffix(".wav"))})
        if len(out) >= n:
            break
    return out


def salvar(obra, palavra, como):
    palavra = palavra.strip()
    if not palavra:
        raise RuntimeError("escreva a palavra como aparece no texto")
    d = ler_json(_arq(obra), {})
    if como.strip():
        d[palavra] = como.strip()
    else:
        d.pop(palavra, None)               # vazio = voltar a falar como está escrito
    d["_nota"] = (d.get("_nota", "") + f" {time.strftime('%d/%m')}: {palavra} = {como.strip() or '(removida)'}.").strip()
    gravar_json(_arq(obra), d)
    return {"ok": True}


def amostra(obra, personagem, texto):
    """Gera a frase com a voz do personagem, já com a pronúncia aplicada (roda na fila: usa a GPU do VoiceStudio)."""
    cfg = ler_json(PROJETOS / obra / "projeto.json", {})
    voz = cfg.get("elenco", {}).get(personagem)
    if not voz:
        raise RuntimeError(f"{personagem} não tem voz no elenco")
    try:
        requests.get(VOICESTUDIO + "/profiles", timeout=5).raise_for_status()
    except requests.RequestException:
        raise RuntimeError("o servidor de voz não respondeu (ver dados/logs/voicestudio.log)")
    info = ler_json(VOZES / voz / "voz.json"); rc = info["receita"]
    c = _comum()
    dic = c.carregar_pronuncia({"pronuncia": str(_arq(obra))} if _arq(obra).exists() else {})
    falado = c.aplicar_pronuncia(texto, dic)
    dados = {"text": falado, "language": "pt", "seed": int(rc.get("seed", 7)), "engine": "omnivoice",
             "effect_preset": rc.get("effect_preset", "warm"), "speed": rc.get("speed", 0.9), "num_step": rc.get("num_step", 64)}
    try:
        if info.get("perfil_voicestudio"):
            dados["profile_id"] = info["perfil_voicestudio"]
            r = requests.post(VOICESTUDIO + "/generate", timeout=900, data=dados)
        else:
            with open(VOZES / voz / "ref.wav", "rb") as fh:
                r = requests.post(VOICESTUDIO + "/generate", timeout=900, data=dados, files={"ref_audio": ("ref.wav", fh, "audio/wav")})
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"VoiceStudio: {e} (ele está aberto?)")
    AMOSTRAS.mkdir(parents=True, exist_ok=True)
    arq = AMOSTRAS / f"{personagem}_{uuid.uuid4().hex[:6]}.wav"
    arq.write_bytes(r.content)
    # ficha ao lado do áudio: a tela lista as últimas amostras e sobrevive à atualização da tela
    gravar_json(arq.with_suffix(".json"), {"obra": obra, "personagem": personagem, "texto": texto, "falado": falado,
                                          "quando": time.strftime("%d/%m %H:%M")})
    return f"amostra pronta: {arq} | falado como: {falado}"


def falas_com(obra, ep, palavra):
    """Chaves das falas do episódio que têm a palavra (mesma fronteira de palavra da gravação)."""
    rot = ler_json(PROJETOS / obra / "04_roteiro_audio" / f"ep{ep}.json")
    rx = re.compile(rf"(?<!\w){re.escape(palavra)}(?!\w)")
    return [f"{p['parte']:02d}_{i:02d}" for p in rot["partes"] for i, f in enumerate(p["falas"], 1) if rx.search(f["texto"])]


def regravar(c, obra, ep, palavra):
    """Regrava só as falas com a palavra e refaz só as partes delas (a cadeia pula o resto)."""
    from .worker import enfileirar_cadeia
    ep = f"{int(ep):02d}"
    chaves = falas_com(obra, ep, palavra)
    if not chaves:
        raise RuntimeError(f"nenhuma fala do Ep. {ep} tem \"{palavra}\"")
    partes = sorted({int(k[:2]) for k in chaves})
    lote, ids = enfileirar_cadeia(c, obra, ep, partes, params_extra={"regerar": chaves})
    return {"ok": True, "falas": chaves, "partes": partes, "jobs": ids}
