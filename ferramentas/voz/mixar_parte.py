# Mixa UMA parte no SoundCraft pelo modo script (soundcraft-cli script), sem MCP: a receita aprovada no piloto
# (receita_mix.py) vira um arquivo "ID JSON" por linha. Depois aplica o acabamento do fim (corte em voz + 4,5 s e
# fade-out de 0,8 s). Imprime UMA linha de resumo (economia de tokens).
# Uso (env qwen): python mixar_parte.py --voz parte_NN.wav --stems DIR --saida parte_NN_tiktok.wav --sessao X.soundcraft
import argparse, json, re, subprocess, sys, tempfile
from pathlib import Path
import numpy as np, soundfile as sf
from comum import ler_wav, gravar_wav

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from caminhos import PY, SOUNDCRAFT_CLI as CLI
AQUI = Path(__file__).resolve().parent

ap = argparse.ArgumentParser()
ap.add_argument("--voz", required=True)
ap.add_argument("--stems", required=True)
ap.add_argument("--saida", required=True)
ap.add_argument("--sessao", required=True)
ap.add_argument("--cauda", type=float, default=4.5, help="segundos depois do fim da voz")
a = ap.parse_args()

tmp = Path(tempfile.mkdtemp(prefix="mix_"))
env = tmp / "envelope.json"
env.write_text(subprocess.run([PY, str(AQUI / "envelope_ducking.py"), "--voz", a.voz, "--min_pausa", "1.5",
                               "--rampa_sobe", "1.2", "--rampa_desce", "0.4"], capture_output=True, text=True, check=True).stdout)
rec = json.loads(subprocess.run([PY, str(AQUI / "receita_mix.py"), "--voz", a.voz, "--stems", a.stems, "--envelope", str(env)],
                                capture_output=True, text=True, check=True).stdout)
voz_dur = sf.info(a.voz).duration
linhas = ['session.new {"name": "%s", "sample_rate": 48000}' % Path(a.sessao).stem]
for arq in rec["imports"]:
    linhas.append("file.import_audio " + json.dumps({"path": str(Path(arq).resolve()), "at": 0}))
for c in rec["calls"]:
    linhas.append(f"{c['command']} {json.dumps(c['params'], ensure_ascii=False)}")
bruto = tmp / "bounce.wav"
linhas.append("file.bounce_mix " + json.dumps({"path": str(bruto), "format": "wav", "bit_depth": "24", "start": 0,
                                              "end": {"seconds": round(voz_dur + 2.0 + 3.5, 2)}}))
linhas.append("session.save_as " + json.dumps({"path": str(Path(a.sessao).resolve()), "replace": True}))
script = tmp / "mix.txt"
script.write_text("\n".join(linhas) + "\n", encoding="utf-8")
r = subprocess.run([CLI, "script", str(script)], capture_output=True, text=True, errors="ignore")
if r.returncode != 0 or not bruto.exists():
    raise SystemExit(f"falhou: {r.stdout[-800:]} {r.stderr[-800:]}")
m = re.search(r'"lufs":\s*(-?[\d.]+)', r.stdout)
# acabamento do fim
x, sr = ler_wav(bruto, mono=False)
x = x[: int((voz_dur + a.cauda) * sr)].copy()
f = int(0.8 * sr)
x[-f:] *= np.linspace(1, 0, f)[:, None] if x.ndim == 2 else np.linspace(1, 0, f)
gravar_wav(a.saida, x, sr)
print(f"ok {Path(a.saida).name} | {len(x) / sr:.1f} s | LUFS {m.group(1) if m else '?'} | ganhos {rec['ganhos_db']}")
