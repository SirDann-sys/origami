# Grava um roteiro de áudio inteiro (etapa 5 do plano): fala por fala, com o perfil de cada voz no
# VoiceStudio/OmniVoice (voz.json → perfil_voicestudio), na velocidade, semente e acabamento da receita.
# Em fases, para nunca ter dois modelos disputando os 6 GB da GPU:
#   1) --fase gerar   : só o VoiceStudio na GPU; gera as falas que faltam (ou as marcadas para refazer).
#   2) --fase conferir: o Whisper confere as falas novas; erro acima do limite → marca "refazer" com nova
#      semente (até 3 tentativas). Repetir gerar → conferir até não sobrar nada.
#   3) --fase montar  : cola as falas de cada parte com as pausas do roteiro.
# Saída: <saida>/falas/PP_FF.wav, <saida>/partes/parte_PP.wav, <saida>/gravacao.json
# Uso (env qwen): python gravar_roteiro.py --fase gerar|conferir|montar --roteiro ep01.json --elenco projeto.json --saida DIR [--partes 1 2]
import argparse, subprocess, sys, tempfile, time
from pathlib import Path
import numpy as np, requests
from comum import BANCO, MODELOS, ler_json, gravar_json, ler_wav, gravar_wav, aparar_silencio, wer, carregar_pronuncia, aplicar_pronuncia

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from caminhos import VOICESTUDIO          # porta do config.json
API = VOICESTUDIO + "/generate"
FLUSH = VOICESTUDIO + "/system/flush-memory"
FFMPEG = str(Path(__file__).resolve().parents[2] / "ffmpeg" / "ffmpeg.exe")   # ffmpeg do próprio app
LIMITE_ERRO, TENTATIVAS = 0.15, 3

ap = argparse.ArgumentParser()
ap.add_argument("--fase", choices=["gerar", "conferir", "montar"], required=True)
ap.add_argument("--roteiro", required=True)
ap.add_argument("--elenco", required=True, help="projeto.json da obra (campo elenco: personagem -> id da voz)")
ap.add_argument("--saida", required=True)
ap.add_argument("--partes", type=int, nargs="*", default=None)
a = ap.parse_args()

roteiro, elenco = ler_json(a.roteiro), ler_json(a.elenco).get("elenco", {})
_sem_voz = sorted({f["voz"] for p in roteiro["partes"] for f in p["falas"]} - set(elenco))
if _sem_voz and a.fase == "gerar":     # falha cedo, antes de gastar falas do lote
    raise SystemExit("vozes sem elenco (escolha na aba Elenco): " + ", ".join(_sem_voz))
# pronúncia (como a voz deve ler cada palavra):
# global (voz/pronuncia_global.json) + a da obra (01_biblia/pronuncia.json, ao lado do projeto.json); a da obra vence
_pron_obra = Path(a.elenco).parent / "01_biblia" / "pronuncia.json"
PRONUNCIA = carregar_pronuncia({"pronuncia": str(_pron_obra)} if _pron_obra.exists() else roteiro)
saida = Path(a.saida)
(saida / "falas").mkdir(parents=True, exist_ok=True)
(saida / "partes").mkdir(parents=True, exist_ok=True)
arq_reg = saida / "gravacao.json"
registro = ler_json(arq_reg) if arq_reg.exists() else {"falas": {}}


def falas():
    for parte in roteiro["partes"]:
        if a.partes and parte["parte"] not in a.partes:
            continue
        for i, fala in enumerate(parte["falas"], 1):
            yield parte, f"{parte['parte']:02d}_{i:02d}", fala


def gerar(texto, voz_id, tentativa):
    info = ler_json(BANCO / voz_id / "voz.json")
    rc = info["receita"]
    dados = {"text": aplicar_pronuncia(texto, PRONUNCIA), "language": "pt", "seed": int(rc.get("seed", 7)) + 100 * tentativa, "engine": "omnivoice",
             "effect_preset": rc.get("effect_preset", "warm"), "speed": rc.get("speed", 0.9), "num_step": rc.get("num_step", 64)}
    if info.get("perfil_voicestudio"):
        dados["profile_id"] = info["perfil_voicestudio"]   # referência + transcrição em cache no app
        r = requests.post(API, timeout=900, data=dados)
    else:
        with open(BANCO / voz_id / "ref.wav", "rb") as fh:
            r = requests.post(API, timeout=900, data=dados, files={"ref_audio": ("ref.wav", fh, "audio/wav")})
    r.raise_for_status()
    with tempfile.TemporaryDirectory() as t:
        b, l = Path(t) / "b.wav", Path(t) / "l.wav"
        b.write_bytes(r.content)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(b), "-af", "deesser=i=0.4:m=0.5:f=0.5",
                        "-c:a", "pcm_s24le", str(l)], check=True)
        y, sr = ler_wav(l)
    return aparar_silencio(y, sr, limiar_db=-50, folga_s=0.06), sr


t0 = time.time()
if a.fase == "gerar":
    # libera o cache de GPU do VoiceStudio antes do lote: com 6 GB, o cache retido deixa cada fala ~10× mais lenta
    try:
        requests.post(FLUSH, timeout=30)
    except requests.RequestException:
        pass
    for parte, chave, fala in falas():
        reg = registro["falas"].get(chave)
        if reg and not reg.get("refazer"):
            continue
        tent = reg["tentativas"] if reg else 0
        # o cache de GPU do VoiceStudio cresce a cada fala até encher os 6 GB (aí cada fala fica ~10× mais lenta);
        # liberar antes de cada geração mantém ~15 s por fala
        try:
            requests.post(FLUSH, timeout=30)
        except requests.RequestException:
            pass
        t1 = time.time()
        y, sr = gerar(fala["texto"], elenco[fala["voz"]], tent)
        gravar_wav(saida / "falas" / f"{chave}.wav", y, sr)
        registro["falas"][chave] = {"voz": fala["voz"], "texto": fala["texto"], "tentativas": tent + 1,
                                    "conferida": False, "refazer": False, "duracao": round(len(y) / sr, 2),
                                    "historico": (reg or {}).get("historico", [])}
        gravar_json(arq_reg, registro)
        print(f"{chave} {fala['voz']:7s} {len(y) / sr:5.1f} s em {time.time() - t1:5.1f} s", flush=True)

elif a.fase == "conferir":
    import torch, librosa
    from transformers import pipeline
    asr = pipeline("automatic-speech-recognition", model=str(MODELOS / "whisper-large-v3-turbo"), dtype=torch.float16, device="cuda:0")
    for parte, chave, fala in falas():
        reg = registro["falas"].get(chave)
        if not reg or reg.get("conferida"):
            continue
        y, sr = ler_wav(saida / "falas" / f"{chave}.wav")
        transc = asr({"raw": librosa.resample(y, orig_sr=sr, target_sr=16000), "sampling_rate": 16000},
                     generate_kwargs={"language": "portuguese"})["text"].strip()
        erro = wer(fala["texto"], transc)
        reg.update(conferida=True, erro_leitura=round(erro, 3), transcricao=transc)
        reg["historico"].append(round(erro, 3))
        ruim = erro > LIMITE_ERRO
        reg["refazer"] = ruim and reg["tentativas"] < TENTATIVAS
        reg["revisar"] = ruim and reg["tentativas"] >= TENTATIVAS
        if reg["refazer"]:
            # guarda a versão atual caso a próxima saia pior
            (saida / "falas" / f"{chave}.wav").replace(saida / "falas" / f"{chave}_t{reg['tentativas']}.wav")
        print(f"{chave} erro {erro:.2f}{'  -> REFAZER' if reg['refazer'] else ''}{'  -> REVISAR' if reg['revisar'] else ''}", flush=True)
    gravar_json(arq_reg, registro)
    pend = [k for k, r in registro["falas"].items() if r.get("refazer")]
    print("pendentes para refazer:", pend)

else:  # montar
    for parte in roteiro["partes"]:
        if a.partes and parte["parte"] not in a.partes:
            continue
        pedacos, sr = [], 24000
        for i, fala in enumerate(parte["falas"], 1):
            y, sr = ler_wav(saida / "falas" / f"{parte['parte']:02d}_{i:02d}.wav")
            pedacos += [y, np.zeros(int(float(fala.get("pausa", 0.45)) * sr), dtype="float32")]
        audio = np.concatenate(pedacos[:-1])
        gravar_wav(saida / "partes" / f"parte_{parte['parte']:02d}.wav", audio / (np.abs(audio).max() + 1e-9) * 0.89, sr)
        print(f"PARTE {parte['parte']}: {len(audio) / sr:.1f} s", flush=True)

print(f"fase {a.fase} ok em {time.time() - t0:.0f} s")
