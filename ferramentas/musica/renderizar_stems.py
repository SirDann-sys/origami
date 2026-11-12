# Renderiza uma composição MIDI em faixas separadas (stems), cada uma com o seu instrumento SFZ, via sfizz_render.
# Os stems vão para a mixagem no SoundCraft (volume, EQ, reverb e ducking sob a voz).
# Uso (env qwen): python renderizar_stems.py --midi tema.mid --saida DIR
import argparse, subprocess
from pathlib import Path
import mido

RAIZ = Path(__file__).resolve().parent
SFIZZ = RAIZ / "ferramentas" / "sfizz" / "bin" / "Release" / "sfizz_render.exe"
VPO = RAIZ / "sons" / "vpo" / "Virtual-Playing-Orchestra3"
PIANO = RAIZ / "sons" / "salamander" / "SalamanderGrandPiano-SFZ+FLAC-V3+20200602" / "SalamanderGrandPiano-V3+20200602.sfz"

# stem -> (pistas do MIDI que ele toca, instrumento SFZ)
STEMS = {
    "piano":   (["piano", "piano_md", "piano_me"], PIANO),
    # versões "mod-wheel": a dinâmica das cordas segue o CC1 (crescendos contínuos)
    "cordas":  (["cordas"], VPO / "Strings" / "all-strings-SEC-normal-mod-wheel-panned.sfz"),
    "cello":   (["cello"], VPO / "Strings" / "cello-SEC-normal-mod-wheel.sfz"),
    "celesta": (["celesta"], VPO / "Keys" / "celesta.sfz"),
    # humor E (cotidiano): a celesta vira a melodia, com glockenspiel e cordas em pizzicato
    "melodia": (["melodia"], VPO / "Keys" / "celesta.sfz"),
    "glock":   (["glock"], VPO / "Percussion" / "glockenspiel.sfz"),
    "pizz":    (["pizz"], VPO / "Strings" / "all-strings-SEC-pizzicato-panned.sfz"),
}
CAUDA_S = 5.0   # segundos de silêncio no fim, para o som e a ressonância terminarem

ap = argparse.ArgumentParser()
ap.add_argument("--midi", required=True)
ap.add_argument("--saida", required=True)
a = ap.parse_args()

orig = mido.MidiFile(a.midi)
tempo = next(m.tempo for t in orig.tracks for m in t if m.type == "set_tempo")
saida = Path(a.saida)
saida.mkdir(parents=True, exist_ok=True)

for stem, (pistas, sfz) in STEMS.items():
    # junta as pistas do stem numa só (tempo absoluto → delta), no canal 0
    eventos = []
    for tr in orig.tracks:
        nome = next((m.name for m in tr if m.type == "track_name"), "")
        if nome not in pistas:
            continue
        t = 0
        for m in tr:
            t += m.time
            if m.type in ("note_on", "note_off", "control_change") and not (m.type == "control_change" and m.control in (7, 91)):
                eventos.append((t, m.copy(channel=0, time=0)))
    if not eventos:
        continue
    eventos.sort(key=lambda e: (e[0], 0 if e[1].type == "note_off" else 1))
    mid = mido.MidiFile(ticks_per_beat=orig.ticks_per_beat)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=tempo))
    ant = 0
    for t, m in eventos:
        m.time = t - ant; ant = t; tr.append(m)
    tr.append(mido.MetaMessage("end_of_track", time=int(mido.second2tick(CAUDA_S, orig.ticks_per_beat, tempo))))
    arq_mid = saida / f"{stem}.mid"
    mid.save(arq_mid)
    arq_wav = saida / f"{stem}.wav"
    subprocess.run([str(SFIZZ), "--sfz", str(sfz), "--midi", str(arq_mid), "--wav", str(arq_wav),
                    "-s", "48000", "-q", "3", "-p", "256", "--use-eot"], check=True)
    print("ok", stem, arq_wav, flush=True)
