# Origami — caminhos e constantes do motor. Nada específico de obra aqui.
# Tudo parte da pasta do próprio app (mover a pasta não quebra nada).
# O que fica fora dela (Git Bash, SoundCraft, portas dos serviços) vem de config.json, na raiz (ver config.exemplo.json).
# ORIGAMI_DEMO=1 abre só a interface sobre as obras de exemplo/ (sem GPU, sem IA).
import json, os, shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ORIGAMI = RAIZ
INTERFACE = RAIZ / "interface"
DEMO = os.environ.get("ORIGAMI_DEMO") == "1"
PROJETOS = RAIZ / ("exemplos" if DEMO else "obras")
VOZES = RAIZ / "vozes"
FERRAMENTAS = RAIZ / "ferramentas"
RECURSOS = RAIZ / "recursos"
DADOS = RAIZ / "dados" / ("demo" if DEMO else "")
DB = DADOS / "origami.db"
LOGS = DADOS / "logs"

_cfg = json.loads((RAIZ / "config.json").read_text(encoding="utf-8")) if (RAIZ / "config.json").exists() else {}

PY = str(RAIZ / "ambientes" / "qwen" / "Scripts" / "python.exe")
BASH = _cfg.get("bash") or shutil.which("bash") or "bash"
FFMPEG = str(RAIZ / "ffmpeg" / "ffmpeg.exe")
COMFY_DIR = RAIZ / "comfyui"
SOUNDCRAFT_CLI = _cfg.get("soundcraft_cli") or shutil.which("soundcraft-cli") or "soundcraft-cli"


def resolver(p):
    """Caminho de dado → arquivo real (igual a ferramentas/caminhos.resolver): relativo = à pasta do app; absoluto que
    não existe mais (pasta movida) → o mesmo final dentro da pasta atual."""
    p = Path(p)
    if not p.is_absolute():
        return p.resolve() if p.exists() else RAIZ / p      # relativo à pasta atual (linha de comando) ou à do app
    if p.exists():
        return p
    for i in range(1, len(p.parts)):
        alt = RAIZ.joinpath(*p.parts[i:])
        if alt.exists():
            return alt
    return p

SCRIPTS = {
    "gravar": FERRAMENTAS / "voz" / "gravar_roteiro.py",
    "mixar": FERRAMENTAS / "voz" / "mixar_parte.py",
    "receita": FERRAMENTAS / "voz" / "receita_mix.py",
    "envelope": FERRAMENTAS / "voz" / "envelope_ducking.py",
    "cues": FERRAMENTAS / "musica" / "compor_cues.py",
    "stems": FERRAMENTAS / "musica" / "renderizar_stems.py",
    "imagens": FERRAMENTAS / "video" / "gerar_imagens.py",
    "tempos": FERRAMENTAS / "video" / "tempos.py",
    "compor": FERRAMENTAS / "video" / "compor.py",
    "ep16x9": FERRAMENTAS / "video" / "episodio_16x9.sh",
    "capas": FERRAMENTAS / "video" / "capas_ep.py",
    "wattpad": FERRAMENTAS / "video" / "wattpad_cap.py",
    "acabamento": FERRAMENTAS / "video" / "acabamento_rosto.py",
    "conferir_imagem": FERRAMENTAS / "video" / "conferir_imagem.py",
}

VOICESTUDIO = _cfg.get("voicestudio", "http://127.0.0.1:3900")
COMFY = _cfg.get("comfy", "http://127.0.0.1:8188")
PORTA_API = int(os.environ.get("ORIGAMI_PORTA") or _cfg.get("porta", 3950))

# receita do episódio completo (aprovada no piloto): partes sem fade + 0,4 s de respiro, −16 LUFS
RESPIRO_S = 0.4
LOUDNORM_EP = "loudnorm=I=-16:TP=-1.5:LRA=11"
# a deixa musical só é recomposta se a duração da parte mudar mais que isto
TOL_DURACAO_S = 0.05
