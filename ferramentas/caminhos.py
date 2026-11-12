# Caminhos do Origami para os scripts de ferramentas/ (voz, musica, video). Tudo relativo à pasta do app:
# os scripts não precisam saber onde o app está instalado.
# O que fica FORA da pasta (SoundCraft, Git Bash) e as portas dos serviços vêm de config.json, na raiz,
# igual ao motor (motor/config.py).
# Uso num script:  sys.path.insert(0, str(Path(__file__).resolve().parents[1])); from caminhos import ...
import json, shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
_cfg = json.loads((RAIZ / "config.json").read_text(encoding="utf-8")) if (RAIZ / "config.json").exists() else {}

PY = str(RAIZ / "ambientes" / "qwen" / "Scripts" / "python.exe")
FFMPEG = str(RAIZ / "ffmpeg" / "ffmpeg.exe")
FERRAMENTAS = RAIZ / "ferramentas"
VOZES = RAIZ / "vozes"
MODELOS = RAIZ / "modelos"
RECURSOS = RAIZ / "recursos"
MARCA_PADRAO = RECURSOS / "marca" / "padrao" / "marca.json"
PRONUNCIA_GLOBAL = RECURSOS / "pronuncia_global.json"
COMFY_DIR = RAIZ / "comfyui"

VOICESTUDIO = _cfg.get("voicestudio", "http://127.0.0.1:3900").rstrip("/")
COMFY = _cfg.get("comfy", "http://127.0.0.1:8188").rstrip("/")
SOUNDCRAFT_CLI = _cfg.get("soundcraft_cli") or shutil.which("soundcraft-cli") or "soundcraft-cli"


def resolver(p):
    """Caminho de dado (marca, símbolo…) → arquivo real. Relativo = relativo à pasta do app. Absoluto que não existe
    mais (a pasta foi movida) → procura o mesmo final dentro da pasta atual."""
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
