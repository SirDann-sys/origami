# Revisão de áudio fala por fala (plano, seção 5): ouvir a parte, clicar no ponto, achar a fala, corrigir e propagar.
# Tudo o que muda passa pelo roteiro/gravacao.json e pela fila do motor: o worker refaz só a parte afetada
# (montar → deixa → stems → mix → tempos → vídeo), exatamente como o `origami fala` da linha de comando.
import time
import numpy as np
import soundfile as sf
from .obra import Episodio, ler_json, gravar_json

N_PICOS = 1600


def picos(wav, n=N_PICOS):
    """Forma de onda reduzida (máximo absoluto por fatia), 0..1, para desenhar sem mandar o wav inteiro."""
    y, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    y = np.abs(y).max(axis=1)
    if len(y) < n:
        return y.tolist(), len(y) / sr
    corte = len(y) // n * n
    p = y[:corte].reshape(n, -1).max(axis=1)
    return np.round(p / max(p.max(), 1e-6), 3).tolist(), len(y) / sr


def versoes(ep, chave):
    out = [{"nome": "atual", "caminho": str(ep.fala_wav(chave))}] if ep.fala_wav(chave).exists() else []
    for f in sorted(ep.falas_dir.glob(f"{chave}_*.wav"), key=lambda p: p.stat().st_mtime, reverse=True):
        out.append({"nome": f.stem[len(chave) + 1:], "caminho": str(f)})
    return out


def parte(obra, ep_, n):
    ep = Episodio(obra, ep_)
    if not ep.roteiro_arq.exists():
        raise RuntimeError(f"o Ep. {ep.ep} ainda não tem roteiro de áudio: comece pela Mesa e pelo Texto")
    n = int(n)
    audio = ep.mix_wav(n) if ep.mix_wav(n).exists() else ep.parte_wav(n)
    if not audio.exists():
        raise RuntimeError(f"o áudio do Ep. {ep.ep} ainda não foi gravado. O roteiro existe; a gravação acontece em "
                           "\"Produzir episódio\", na Mesa, depois que todas as vozes estiverem no Elenco")
    pk, dur = picos(audio)
    tempos = {f["fala"]: f for f in (ler_json(ep.tempos, {"partes": {}})["partes"].get(str(n)) or [])}
    reg = ler_json(ep.gravacao, {"falas": {}})["falas"]
    elenco = ep.cfg.get("elenco", {})
    falas = []
    for i, f in enumerate(ep.parte(n)["falas"], 1):
        k = f"{n:02d}_{i:02d}"
        r, t = reg.get(k, {}), tempos.get(i, {})
        falas.append({"chave": k, "voz": f["voz"], "texto": f["texto"], "estilo": f.get("estilo", ""), "pausa": f.get("pausa", 0.45),
                      "inicio": t.get("inicio"), "fim": t.get("fim"), "conferida": r.get("conferida", False),
                      "revisar": bool(r.get("revisar")) and not r.get("aprovada_manual"), "aprovada_manual": r.get("aprovada_manual", False),
                      "erro": r.get("erro_leitura"), "transcricao": r.get("transcricao", ""), "tentativas": r.get("tentativas", 0),
                      "versoes": versoes(ep, k)})
    return {"obra": obra, "ep": ep.ep, "parte": n, "partes": ep.partes(), "audio": str(audio), "duracao": dur, "picos": pk,
            "vozes": sorted({f["voz"] for f in falas}), "elenco": elenco, "falas": falas,
            "tempos_ok": bool(tempos), "publicado": _publicado(ep), "aprovacao": _aprovacao(ep, reg)}


def _aprovacao(ep, reg):
    """Estado do portão do áudio + quantas falas do episódio inteiro o conferidor marcou para ouvir."""
    from .aprovacao import estado
    e = estado(ep.obra, ep.ep)
    e["ouvir"] = sorted(k for k, r in reg.items() if r.get("revisar") and not r.get("aprovada_manual"))
    return e


def _publicado(ep):
    st = ep.cfg.get("episodios", {}).get(ep.ep, {})
    return st.get("status") == "publicado"


def _travar(ep):
    """Episódio já publicado: o que está nas redes não muda. Corrigir exige destravar no projeto.json (decisão do autor)."""
    st = ep.cfg.get("episodios", {}).get(ep.ep, {})
    if st.get("status") == "publicado" and not st.get("permitir_correcao"):
        raise RuntimeError("episódio publicado: só para ouvir. Para corrigir, destrave em projeto.json → "
                           f"episodios.{ep.ep}.permitir_correcao = true (gera versão nova; o que já foi postado não muda)")


def _propagar(c, obra, ep_, n, regerar=None):
    from .worker import enfileirar_cadeia
    extra = {"regerar": regerar} if regerar else None
    return enfileirar_cadeia(c, obra, ep_, [n], ate="video", params_extra=extra)


def corrigir(c, obra, ep_, chave, texto=None, pausa=None, regerar=False):
    """Edita a fala no roteiro (texto/pausa) e/ou pede outra tomada; enfileira a propagação só da parte."""
    ep = Episodio(obra, ep_)
    _travar(ep)
    pp, ff = (int(x) for x in chave.split("_"))
    rot = ep.roteiro
    fala = next(x for x in rot["partes"] if x["parte"] == pp)["falas"][ff - 1]
    mudou = []
    if texto is not None and texto.strip() and texto.strip() != fala["texto"]:
        fala["texto"] = texto.strip(); mudou.append("texto")
    if pausa is not None and float(pausa) != float(fala.get("pausa", 0.45)):
        fala["pausa"] = round(float(pausa), 2); mudou.append("pausa")
    if mudou:
        gravar_json(ep.roteiro_arq, rot)
    if not mudou and not regerar:
        return {"ok": False, "msg": "nada mudou"}
    lote, ids = _propagar(c, obra, ep_, pp, [chave] if regerar and "texto" not in mudou else None)
    return {"ok": True, "mudou": mudou or ["nova tomada"], "lote": lote, "jobs": ids}


def escolher(c, obra, ep_, chave, versao):
    """Põe uma versão guardada no lugar da atual (a atual vira _vN) e propaga a partir da montagem."""
    ep = Episodio(obra, ep_)
    _travar(ep)
    atual, alvo = ep.fala_wav(chave), ep.falas_dir / f"{chave}_{versao}.wav"
    if not alvo.exists():
        raise RuntimeError(f"versão não encontrada: {alvo.name}")
    n = 1
    while (ep.falas_dir / f"{chave}_v{n}.wav").exists():
        n += 1
    guardada = ep.falas_dir / f"{chave}_v{n}.wav"
    atual.replace(guardada)
    alvo.replace(atual)
    reg = ler_json(ep.gravacao)
    r = reg["falas"].setdefault(chave, {})
    r.update(conferida=True, refazer=False, revisar=False, aprovada_manual=True,
             escolha_manual=f"{versao} em {time.strftime('%Y-%m-%d %H:%M')} (anterior guardada como v{n})")
    gravar_json(ep.gravacao, reg)
    pp = int(chave[:2])
    from .worker import enfileirar_cadeia
    lote, ids = enfileirar_cadeia(c, obra, ep_, [pp], de="montar", ate="video")
    return {"ok": True, "guardada": guardada.name, "lote": lote, "jobs": ids}


def aprovar(obra, ep_, chave):
    """Falso alarme do Whisper (ex.: "pro/para o"): aprova a fala como está, registrado."""
    ep = Episodio(obra, ep_)
    reg = ler_json(ep.gravacao)
    reg["falas"][chave].update(aprovada_manual=True, revisar=False, aprovada_em=time.strftime("%Y-%m-%d %H:%M"))
    gravar_json(ep.gravacao, reg)
    return {"ok": True}
