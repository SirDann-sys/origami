# Utilidades compartilhadas da linha de voz. Sem nada específico de obra:
# tudo o que é da história vem do roteiro, do elenco e do banco de vozes.
import json, os, re, unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf

RAIZ = Path(__file__).resolve().parents[2]            # a pasta do Origami
BANCO = RAIZ / "vozes"
MODELOS = RAIZ / "modelos"
# Todos os modelos do Hugging Face ficam no D:, nunca no perfil do C:.
os.environ.setdefault("HF_HOME", str(MODELOS / "hf"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def ler_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def gravar_json(p, dados):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- pronúncia ----------
def carregar_pronuncia(roteiro):
    """Global (recursos/pronuncia_global.json) + a da obra (no roteiro ou num arquivo); a da obra vence."""
    dic = {}
    g = RAIZ / "recursos" / "pronuncia_global.json"
    if g.exists():
        dic.update(ler_json(g))
    p = roteiro.get("pronuncia")
    if isinstance(p, str):
        p = ler_json(p)
    dic.update(p or {})
    return dic


def aplicar_pronuncia(texto, dic):
    for escrito, falado in sorted(dic.items(), key=lambda kv: -len(kv[0])):
        # (?<!\w)/(?!\w) em vez de \b: funciona também para abreviações com ponto ("Dra.").
        texto = re.sub(rf"(?<!\w){re.escape(escrito)}(?!\w)", falado, texto)
    return texto


# ---------- elenco e banco ----------
def voz_do_personagem(elenco, personagem):
    """elenco: {"personagens": {"ana": {"voz": "id_no_banco", "direcao": "..."}}}"""
    p = elenco["personagens"][personagem]
    pasta = BANCO / p["voz"]
    info = ler_json(pasta / "voz.json")
    return {"id": p["voz"], "pasta": pasta, "ref_wav": pasta / "ref.wav",
            "ref_txt": (pasta / "ref.txt").read_text(encoding="utf-8").strip() if (pasta / "ref.txt").exists() else None,
            "descricao": info.get("descricao", ""), "direcao": p.get("direcao", ""), "info": info}


# ---------- áudio ----------
def ler_wav(p, mono=True):
    a, sr = sf.read(str(p), dtype="float32", always_2d=False)
    if mono and a.ndim == 2:
        a = a.mean(axis=1)
    return a, sr


def gravar_wav(p, a, sr):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(p), np.asarray(a, dtype="float32"), sr, subtype="PCM_24")


def normalizar_pico(a, alvo_db=-1.0):
    pico = float(np.max(np.abs(a))) or 1.0
    return a * (10 ** (alvo_db / 20) / pico)


def aparar_silencio(a, sr, limiar_db=-45, folga_s=0.05):
    env = np.abs(a)
    lim = 10 ** (limiar_db / 20) * (env.max() or 1)
    idx = np.where(env > lim)[0]
    if not len(idx):
        return a
    f = int(folga_s * sr)
    return a[max(0, idx[0] - f): min(len(a), idx[-1] + f)]


# ---------- texto para conferência ----------
def normalizar_texto(t):
    t = unicodedata.normalize("NFC", t.lower())
    t = re.sub(r"[^\w\sà-ú]", " ", t)
    return t.split()


_UN = "zero um dois três quatro cinco seis sete oito nove dez onze doze treze catorze quinze dezesseis dezessete dezoito dezenove".split()
_DEZ = "_ _ vinte trinta quarenta cinquenta sessenta setenta oitenta noventa".split()
_CEM = "_ cento duzentos trezentos quatrocentos quinhentos seiscentos setecentos oitocentos novecentos".split()


def _extenso(n):
    """Número inteiro (0 a 999.999.999) por extenso em pt-BR, como a voz fala."""
    if n < 20:
        return _UN[n]
    if n < 100:
        return _DEZ[n // 10] + ("" if n % 10 == 0 else " e " + _UN[n % 10])
    if n < 1000:
        if n == 100:
            return "cem"
        return _CEM[n // 100] + ("" if n % 100 == 0 else " e " + _extenso(n % 100))
    for base, sing, plur in ((10 ** 6, "um milhão", "milhões"), (1000, "mil", "mil")):
        if n >= base:
            q, r = divmod(n, base)
            cab = sing if q == 1 else f"{_extenso(q)} {plur}"
            if not r:
                return cab
            return cab + (" e " if r < 100 or r % 100 == 0 else " ") + _extenso(r)
    return str(n)


def numeros_por_extenso(t):
    """'de 1998' → 'de mil novecentos e noventa e oito' (o Whisper escreve número em algarismos; o roteiro, por extenso)."""
    return re.sub(r"\d{1,9}", lambda m: _extenso(int(m.group(0))), re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", t))


def wer(ref, hip, ignorar=()):
    """Erro de leitura por palavra (edição mínima / nº de palavras da referência). Números em algarismo ou por extenso
    contam igual ("1998" = "mil novecentos e noventa e oito")."""
    ign = {w for termo in ignorar for w in normalizar_texto(termo)}
    r = [w for w in normalizar_texto(numeros_por_extenso(ref)) if w not in ign]
    h = [w for w in normalizar_texto(numeros_por_extenso(hip)) if w not in ign]
    if not r:
        return 0.0
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / len(r)
