# Uma obra no disco: a pasta padrão (validada no piloto) e o que cada episódio usa.
# Convenção (igual para todas as obras; nada de nome de obra no código):
#   04_roteiro_audio/epNN.json
#   05_audio/epNN/{falas/, partes/, mix/, gravacao.json, trilha/{plano_cues.json, cues/}}
#   06_video/{assets_epNN.json, plano_video_epNN.json, tempos_epNN.json, imagens/, epNN/}
import hashlib, json
from pathlib import Path
from .config import PROJETOS, resolver


def ler_json(p, padrao=None):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else padrao


def gravar_json(p, dados):
    """Grava num arquivo temporário e troca de uma vez (uma queda no meio não deixa o arquivo cortado)."""
    import os
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    for tentativa in range(10):            # no Windows, um leitor com o arquivo aberto pode segurar a troca por instantes
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            import time
            time.sleep(0.1 * (tentativa + 1))
    os.replace(tmp, p)


_travas = {}


def trava(p):
    """Trava por arquivo: a interface (várias threads) e o worker mexem no mesmo projeto.json."""
    import threading
    k = str(Path(p).resolve()).lower()
    return _travas.setdefault(k, threading.RLock())


def atualizar_json(p, fn, padrao=None):
    """Lê, aplica fn(dados) e grava, sem perder a mudança de outra thread no meio. Devolve o que fn devolver."""
    with trava(p):
        d = ler_json(p, padrao if padrao is not None else {})
        r = fn(d)
        gravar_json(p, d)
        return r


class Episodio:
    def __init__(self, obra, ep):
        self.obra, self.ep = obra, f"{int(ep):02d}"
        self.raiz = PROJETOS / obra
        if not (self.raiz / "projeto.json").exists():
            raise SystemExit(f"obra não encontrada: {self.raiz}")
        e = self.ep
        self.projeto = self.raiz / "projeto.json"
        self.roteiro_arq = self.raiz / "04_roteiro_audio" / f"ep{e}.json"
        self.audio = self.raiz / "05_audio" / f"ep{e}"
        self.falas_dir, self.partes_dir, self.mix_dir = self.audio / "falas", self.audio / "partes", self.audio / "mix"
        self.gravacao = self.audio / "gravacao.json"
        self.trilha = self.audio / "trilha"
        self.plano_cues = self.trilha / "plano_cues.json"
        self.video = self.raiz / "06_video"
        self.assets = self.video / f"assets_ep{e}.json"
        self.plano_video = self.video / f"plano_video_ep{e}.json"
        self.tempos = self.video / f"tempos_ep{e}.json"
        self.imagens = self.video / "imagens"
        self.video_ep = self.video / f"ep{e}"
        self.mestre = self.raiz / "02_capitulos" / f"ep{e}_mestre.md"
        self.publicacao = self.raiz / "07_publicacao" / f"ep{e}"
        self.arte = self.publicacao / "arte"
        self.arte_assets = self.arte / f"assets_ep{e}.json"
        self.capas_spec = self.arte / f"capas_ep{e}.json"
        # as peças finais moram em <obra>/PUBLICAR/EpNN; um episódio com a pasta de entrega antiga continua usando-a
        antiga, nova = self.publicacao / "entrega", self.raiz / "PUBLICAR" / f"Ep{e}"
        self.entrega = antiga if antiga.exists() and not nova.exists() else nova

    # ---- dados da obra: marca e estilo (nada disso fica no código) ----
    @property
    def cfg(self):
        return ler_json(self.projeto)

    @property
    def marca_arq(self):
        m = self.cfg.get("marca")
        if not m:
            raise RuntimeError(f"projeto.json sem 'marca' ({self.projeto})")
        arq = resolver(m)
        if not arq.exists():
            raise RuntimeError(f"a marca indicada no projeto.json não existe: {m}")
        return arq

    @property
    def marca(self):
        m = ler_json(self.marca_arq)
        for k in ("simbolo_branco", "simbolo_cor"):
            if m.get(k):
                m[k] = str(resolver(m[k]))
        for k in ("cor_destaque", "cor_texto", "nome", "handle", "assinatura"):
            if k not in m:
                raise RuntimeError(f"marca sem '{k}' ({self.marca_arq})")
        return m

    def destaque(self):
        """Cor de destaque do vídeo deste episódio: exceção registrada para o episódio ou a cor da marca."""
        v = self.cfg.get("video", {})
        cor = v.get("destaque_por_ep", {}).get(self.ep) or v.get("destaque", "marca")
        return tuple(self.marca["cor_destaque"]) if cor == "marca" else tuple(cor)

    def titulo_ep(self):
        t = self.cfg.get("episodios", {}).get(self.ep, {}).get("titulo")
        if not t:
            raise RuntimeError(f"falta o título do episódio {self.ep} em projeto.json → episodios.{self.ep}.titulo")
        return t

    def contexto_padrao(self):
        """Figurino/contexto padrão das personagens (ex.: "trabalho", "casual"): vem do guia de arte."""
        g = ler_json(self.raiz / "01_biblia" / "guia_arte.json", {})
        if g.get("contexto_padrao"):
            return g["contexto_padrao"]
        for d in g.get("personagens", {}).values():
            for k in d:
                if k != "retrato":
                    return k
        return "padrao"     # obra sem guia de arte ainda

    def sigla(self):
        return self.cfg.get("sigla") or self.obra

    # ---- roteiro ----
    @property
    def roteiro(self):
        r = ler_json(self.roteiro_arq)
        if r is None:      # mensagem clara em vez de TypeError
            raise RuntimeError(f"o roteiro de áudio do Ep. {self.ep} ainda não foi gerado (aba Texto → Gerar roteiro)")
        return r

    def partes(self):
        return [p["parte"] for p in self.roteiro["partes"]]

    def parte(self, n):
        return next(p for p in self.roteiro["partes"] if p["parte"] == n)

    def chaves_falas(self, n):
        return [f"{n:02d}_{i:02d}" for i in range(1, len(self.parte(n)["falas"]) + 1)]

    # ---- arquivos de saída por parte ----
    def fala_wav(self, chave):
        return self.falas_dir / f"{chave}.wav"

    def parte_wav(self, n):
        return self.partes_dir / f"parte_{n:02d}.wav"

    def cue_mid(self, n):
        return self.trilha / "cues" / f"cue_parte{n:02d}.mid"

    def stems_dir(self, n):
        return self.trilha / "cues" / f"stems_parte{n:02d}"

    def mix_wav(self, n):
        return self.mix_dir / f"parte_{n:02d}_tiktok.wav"

    def sessao(self, n):
        return self.mix_dir / "sessoes" / f"Ep{self.ep}_Parte{n:02d}.soundcraft"

    def episodio_wav(self):
        return self.mix_dir / f"Ep{self.ep}_completo.wav"

    def video_parte(self, n):
        return self.video_ep / f"parte_{n:02d}_9x16.mp4"

    def video_16x9(self):
        padrao = self.video_ep / f"Ep{self.ep}_16x9.mp4"
        legado = list(self.video_ep.glob(f"Ep{self.ep}_*_16x9.mp4"))     # piloto feito à mão: Ep01_Arquivo_16x9.mp4
        return legado[0] if legado and not padrao.exists() else padrao

    def imagens_da_parte(self, n):
        """Ids das imagens que o vídeo da parte usa: os fundos dos segmentos e os retratos de quem fala (por figurino)."""
        pv = ler_json(self.plano_video)
        if pv is None:
            raise RuntimeError(f"falta o plano de vídeo do Ep. {self.ep} (sai junto com o roteiro)")
        segs = pv["partes"][str(n)] if isinstance(pv["partes"], dict) else pv["partes"][n - 1]
        fundos = {s[1] for s in segs}
        figs = {s[2] if len(s) > 2 else self.contexto_padrao() for s in segs}
        vozes = {f["voz"] for f in self.parte(n)["falas"]} | {pv["narrador"]}
        ids = set(fundos)
        for v in vozes:
            r = pv["retratos"].get(v)
            if isinstance(r, dict):
                ids |= {r.get(f, next(iter(r.values()))) for f in figs}
            elif r:
                ids.add(r)
        return sorted(ids)


_cache_hash = {}


def sha1_arquivo(p, c=None):
    """sha1 do conteúdo, com cache por (mtime, tamanho) no banco: não relê wav/mp4 que não mudaram."""
    p = Path(p)
    if not p.exists():
        return None
    st = p.stat()
    k = (str(p), st.st_mtime_ns, st.st_size)
    if k in _cache_hash:
        return _cache_hash[k]
    if c is not None:
        r = c.execute("SELECT sha1 FROM hash_arquivo WHERE caminho=? AND mtime_ns=? AND tamanho=?", k).fetchone()
        if r:
            _cache_hash[k] = r[0]
            return r[0]
    h = hashlib.sha1()
    with open(p, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    _cache_hash[k] = h.hexdigest()
    if c is not None:
        c.execute("INSERT OR REPLACE INTO hash_arquivo VALUES(?,?,?,?)", (*k, h.hexdigest()))
    return h.hexdigest()


def sha1_valor(v):
    return hashlib.sha1(json.dumps(v, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
