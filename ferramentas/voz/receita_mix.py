# Gera os comandos do SoundCraft para mixar uma parte com a receita de mixagem padrão:
# - níveis-alvo por stem (LUFS medidos → ganho), já com os −4 dB pedidos pelo autor;
# - música CONSTANTE sob a voz; só sobe em silêncios ≥ 1,5 s e no fim (envelope_ducking.py);
# - cadeias: voz (EQ + compressor + sala), música (EQ com "bolso" em 2,5 kHz + plate), master (compressor + maximizador).
# Os IDs das faixas seguem a ordem de importação de uma sessão em branco (voz=2, depois +3 por stem).
# Uso (env qwen): python receita_mix.py --voz parte.wav --stems DIR --envelope env.json → JSON {imports, calls}
import argparse, json, subprocess
from pathlib import Path

FF = str(Path(__file__).resolve().parents[2] / "ffmpeg" / "ffmpeg.exe")   # ffmpeg do próprio app
ALVO_LUFS = {"piano": -29.0, "cordas": -31.0, "cello": -34.0, "celesta": -36.0,
             "melodia": -31.0, "glock": -35.0, "pizz": -33.0}
AJUSTE_AUTOR_DB = -4.0          # "música tá um pouco alta"
SOB_VOZ_DB = -7.0               # quanto a música fica abaixo do nível de pausa enquanto há fala
ORDEM = ["piano", "cordas", "cello", "celesta", "melodia", "glock", "pizz"]

ap = argparse.ArgumentParser()
ap.add_argument("--voz", required=True)
ap.add_argument("--stems", required=True)
ap.add_argument("--envelope", required=True)
a = ap.parse_args()


def lufs(arq):
    r = subprocess.run([FF, "-hide_banner", "-nostats", "-i", str(arq), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, errors="ignore").stderr
    linha = [l for l in r.splitlines() if l.strip().startswith("I:")][-1]
    return float(linha.split()[1])


stems = [s for s in ORDEM if (Path(a.stems) / f"{s}.wav").exists()]
imports = [str(Path(a.voz))] + [str(Path(a.stems) / f"{s}.wav") for s in stems]
ids = {"voz": 2} | {s: 5 + 3 * i for i, s in enumerate(stems)}
master = 2 + 3 * (len(stems) + 1) - 1          # a faixa master é criada depois das importações
env = json.loads(Path(a.envelope).read_text())["pontos"]

calls = [
    {"command": "track.rename", "params": {"track": 2, "name": "Voz"}},
    {"command": "mix.volume", "params": {"tracks": [2], "db": -1.5}},
    {"command": "mix.insert", "params": {"track": 2, "slot": 0, "plugin": "eq_7band", "params": {
        "hpf_on": 1, "hpf_freq": 75, "low_mid_freq": 280, "low_mid_gain": -1.5, "low_mid_q": 1,
        "high_mid_freq": 3500, "high_mid_gain": 1, "high_mid_q": 0.9, "high_shelf_freq": 10000, "high_shelf_gain": 1}}},
    {"command": "mix.insert", "params": {"track": 2, "slot": 1, "plugin": "compressor", "params": {
        "threshold": -24, "ratio": 2.2, "attack": 10, "release": 150, "knee": 8, "makeup": 2}}},
    {"command": "mix.insert", "params": {"track": 2, "slot": 2, "plugin": "room_reverb", "params": {
        "mix": 6, "decay": 0.5, "size": 20, "pre_delay": 8, "damping": 6000}}},
]
ganhos = {}
for s in stems:
    tr = ids[s]
    base = ALVO_LUFS[s] - lufs(Path(a.stems) / f"{s}.wav") + AJUSTE_AUTOR_DB
    ganhos[s] = round(base, 2)
    hpf = {"piano": 40, "cordas": 60, "cello": 35, "celesta": 200, "melodia": 200, "glock": 400, "pizz": 45}[s]
    calls += [
        {"command": "mix.insert", "params": {"track": tr, "slot": 0, "plugin": "eq_7band", "params": {
            "hpf_on": 1, "hpf_freq": hpf, "mid_freq": 2500, "mid_gain": -3, "mid_q": 0.7}}},
        {"command": "mix.insert", "params": {"track": tr, "slot": 1, "plugin": "plate_reverb", "params": {
            "mix": 20 if s == "cello" else 24, "decay": 3.2, "pre_delay": 25, "size": 70, "damping": 7000,
            "low_cut": 80 if s == "cello" else 150}}},
    ]
    for t, v in env:
        # v vem do envelope (−9 fala / −2 pausa); converte para o fader: pausa = base, fala = base + SOB_VOZ_DB
        val = base + (SOB_VOZ_DB if v <= -8.9 else 0.0)
        calls.append({"command": "automation.set_point", "params": {"track": tr, "param": "volume",
                                                                     "at": {"seconds": t}, "value": round(min(12.0, val), 2)}})
calls += [
    {"command": "track.new", "params": {"kind": "master", "name": "Master", "format": "stereo"}},
    {"command": "mix.insert", "params": {"track": master, "slot": 0, "plugin": "compressor", "params": {
        "threshold": -16, "ratio": 1.5, "attack": 30, "release": 200, "knee": 10, "makeup": 0}}},
    {"command": "mix.insert", "params": {"track": master, "slot": 1, "plugin": "maximizer", "params": {
        "threshold": -8.5, "ceiling": -1, "release": 80}}},
]
print(json.dumps({"imports": imports, "ids": ids, "master": master, "ganhos_db": ganhos, "calls": calls}, ensure_ascii=False))
