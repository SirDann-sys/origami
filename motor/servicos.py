# Serviços que dividem os 6 GB da GPU: o servidor de voz (VoiceStudio) e o ComfyUI (imagens). Os dois moram dentro
# do Origami e são ligados sozinhos quando um job precisa.
# O worker chama liberar() na troca de recurso; o Whisper e o vídeo rodam em subprocessos e liberam sozinhos.
import os, subprocess, time
import requests
from .config import VOICESTUDIO, COMFY, COMFY_DIR, LOGS, RAIZ

_comfy = {"p": None}          # ComfyUI que o próprio Origami subiu (só esse ele derruba)
_voz = {"p": None}            # servidor de voz que o próprio Origami subiu
VOZ_DIR = RAIZ / "voicestudio"


def voz_no_ar():
    try:
        return requests.get(VOICESTUDIO + "/profiles", timeout=3).ok
    except requests.RequestException:
        return False


def garantir_voz(log=None):
    """Sobe o servidor do VoiceStudio que mora em voicestudio/ (código, Python, perfis de voz e modelos), sem a janela dele.
    Se o VoiceStudio instalado já estiver aberto na mesma porta, usa esse."""
    if voz_no_ar():
        return
    py = VOZ_DIR / "servidor" / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        raise RuntimeError("o servidor de voz não está em voicestudio/servidor (e o VoiceStudio instalado está fechado)")
    if log:
        log.write("ligando o servidor de voz...\n"); log.flush()
    LOGS.mkdir(parents=True, exist_ok=True)
    porta = VOICESTUDIO.rsplit(":", 1)[-1].strip("/")
    env = {**os.environ, "OMNIVOICE_DATA_DIR": str(VOZ_DIR / "dados"), "OMNIVOICE_CACHE_DIR": str(VOZ_DIR / "cache" / "hf_cache"),
           "OMNIVOICE_PORT": porta, "PYTHONIOENCODING": "utf-8"}
    _voz["p"] = subprocess.Popen([str(py), "-m", "uvicorn", "main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", porta],
                                 cwd=VOZ_DIR / "servidor", env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                 stdout=open(LOGS / "voicestudio.log", "a", encoding="utf-8"), stderr=subprocess.STDOUT)
    for _ in range(240):
        if voz_no_ar():
            return
        if _voz["p"].poll() is not None:
            raise RuntimeError("o servidor de voz fechou ao ligar (ver dados/logs/voicestudio.log)")
        time.sleep(1)
    raise RuntimeError("o servidor de voz não respondeu em 4 min (ver dados/logs/voicestudio.log)")


def comfy_no_ar():
    try:
        return requests.get(COMFY + "/system_stats", timeout=3).ok
    except requests.RequestException:
        return False


def garantir_comfy(log):
    if comfy_no_ar():
        return
    log.write("subindo o ComfyUI...\n"); log.flush()
    LOGS.mkdir(parents=True, exist_ok=True)
    porta = COMFY.rsplit(":", 1)[-1].strip("/")           # porta do config.json
    _comfy["p"] = subprocess.Popen(
        [str(COMFY_DIR / ".venv" / "Scripts" / "python.exe"), "main.py", "--listen", "127.0.0.1", "--port", porta,
         "--reserve-vram", "1.5", "--preview-method", "latent2rgb"],
        cwd=COMFY_DIR, stdout=open(LOGS / "comfyui.log", "a", encoding="utf-8"), stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(180):
        if comfy_no_ar():
            return
        if _comfy["p"].poll() is not None:
            _comfy["p"] = None
            raise RuntimeError("o ComfyUI fechou ao ligar (ver dados/logs/comfyui.log)")
        time.sleep(1)
    raise RuntimeError("o ComfyUI não subiu em 3 min (ver dados/logs/comfyui.log)")


def _encerrar(proc):
    """Fecha um serviço que o Origami ligou, sem nunca travar o worker (antes: wait(30) sem tratar o tempo esgotado)."""
    try:
        proc.terminate(); proc.wait(30)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    except OSError:
        pass


def liberar(recurso, proximo=None):
    """Libera a GPU do recurso que acabou de ser usado. Se o próximo é o gerador de imagens (que precisa da placa quase
    inteira), o servidor de voz que o Origami ligou é desligado; ele volta sozinho no próximo job de voz."""
    if recurso == "gpu:voz":
        if proximo == "gpu:imagem" and _voz["p"] and _voz["p"].poll() is None:
            _encerrar(_voz["p"]); _voz["p"] = None
            return
        try:
            requests.post(VOICESTUDIO + "/system/flush-memory", timeout=30)
        except requests.RequestException:
            pass
    elif recurso == "gpu:imagem":
        if _comfy["p"]:
            _encerrar(_comfy["p"]); _comfy["p"] = None
        elif comfy_no_ar():
            try:
                requests.post(COMFY + "/free", json={"unload_models": True, "free_memory": True}, timeout=30)
            except requests.RequestException:
                pass


def abrir_espaco(recurso):
    """Antes de uma etapa de GPU, libera TODOS os outros donos de VRAM, não só o último que o worker usou.
    (Um ComfyUI ocioso ocupando a placa deixa o Whisper várias vezes mais lento.)"""
    if not recurso.startswith("gpu"):
        return
    for outro in ("gpu:voz", "gpu:imagem"):
        if outro != recurso:
            liberar(outro, proximo=recurso)
    if recurso == "gpu:voz":
        garantir_voz()
