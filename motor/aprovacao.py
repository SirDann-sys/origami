# Portão "áudio aprovado": os vídeos, a legenda e a entrega só entram na fila depois que o autor ouve e aprova o
# áudio do episódio na Revisão de áudio. Evita descobrir um erro de áudio depois de renderizar todos os vídeos.
#   projeto.json → episodios.NN.audio_aprovado = {"em": data, "mix": {parte: sha1 da mixagem}}
#   Se a mixagem de uma parte muda depois (fala corrigida, pronúncia), só essa parte volta para "a aprovar".
import time
from .obra import Episodio, ler_json, gravar_json, atualizar_json, sha1_arquivo

# o que depende do áudio estar aprovado (o resto da cadeia, inclusive capas e Wattpad, não espera)
DEPOIS_DO_AUDIO = ("tempos", "video", "video16x9", "entregar")


def _publicado(ep):
    st = ep.cfg.get("episodios", {}).get(ep.ep, {})
    return st.get("status") == "publicado" and st.get("feito_a_mao", True)


def estado(obra, ep_, c=None):
    """{"aprovado", "partes_a_aprovar", "sem_mix", "em"}: aprovado = toda parte tem mixagem e ela é a mesma que o autor ouviu."""
    ep = Episodio(obra, ep_)
    if _publicado(ep):
        return {"aprovado": True, "partes_a_aprovar": [], "sem_mix": [], "em": "publicado", "publicado": True}
    reg = ep.cfg.get("episodios", {}).get(ep.ep, {}).get("audio_aprovado") or {}
    ouvidas = reg.get("mix", {})
    sem_mix, a_aprovar = [], []
    for n in ep.partes():
        wav = ep.mix_wav(n)
        if not wav.exists():
            sem_mix.append(n); continue
        if ouvidas.get(str(n)) != sha1_arquivo(wav, c):
            a_aprovar.append(n)
    return {"aprovado": not sem_mix and not a_aprovar, "partes_a_aprovar": a_aprovar, "sem_mix": sem_mix, "em": reg.get("em")}


def aprovar(obra, ep_, c=None):
    ep = Episodio(obra, ep_)
    falta = [n for n in ep.partes() if not ep.mix_wav(n).exists()]
    if falta:
        raise RuntimeError(f"ainda não há áudio mixado das partes {falta}: produza o áudio primeiro")
    reg = {"em": time.strftime("%Y-%m-%d %H:%M"), "mix": {str(n): sha1_arquivo(ep.mix_wav(n), c) for n in ep.partes()}}
    atualizar_json(ep.raiz / "projeto.json", lambda cfg: cfg.setdefault("episodios", {}).setdefault(ep.ep, {}).__setitem__("audio_aprovado", reg))
    return {"ok": True}
