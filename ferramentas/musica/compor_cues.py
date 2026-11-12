# Compositor de deixas (cues) sincronizadas com as partes de um episódio.
# Cada parte do TikTok é um vídeo separado → cada uma ganha a sua deixa, com duração EXATA:
#   compassos = round(duração · BPM / 240);  BPM_parte = compassos · 240 / duração  (4/4)
# Harmonia em 4 vozes com condução por movimento mínimo (busca exaustiva das disposições),
# rejeitando quintas/oitavas paralelas e cruzamento de vozes. A melodia (motivo do voo: sobe até uma
# nota do acorde e desce por graus) põe nota do acorde em todo tempo forte. Dinâmica das cordas por CC1
# (crescendo/diminuendo contínuo, patches "mod-wheel" do VPO).
# Uso (env qwen): python compor_cues.py --plano plano_cues.json --saida DIR
import argparse, itertools, json, math, random
from pathlib import Path
import mido

ap = argparse.ArgumentParser()
ap.add_argument("--plano", required=True)
ap.add_argument("--saida", required=True)
a = ap.parse_args()

PPQ, BAR = 480, 1920
NOMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
PC = {n: i for i, n in enumerate(NOMES)} | {"Bb": 10, "Eb": 3}
ESCALA_RE_MENOR = {2, 4, 5, 7, 9, 10, 0}       # ré menor natural (= fá maior)
ESCALA_FA_MAIOR = ESCALA_RE_MENOR

# acordes como classes de altura; o 1º é a fundamental
ACORDE = {
    "Dm": [2, 5, 9], "Gm": [7, 10, 2], "Bb": [10, 2, 5], "F": [5, 9, 0], "C": [0, 4, 7],
    "Am": [9, 0, 4], "Eb": [3, 7, 10], "A7": [9, 1, 4, 7], "Asus4": [9, 2, 4], "Csus4": [0, 5, 7],
    "Bbadd9": [10, 2, 5, 0], "Fadd9": [5, 9, 0, 7], "Dm7": [2, 5, 9, 0],
}
PROGRESSOES = {
    "A": [["Dm", "Bb", "F", "C"], ["Dm", "Gm", "Bb", "C"]],
    "A_escuro": [["Dm", "Bb", "Gm", "A7"], ["Dm", "Eb", "Dm", "A7"]],
    "B": [["Bb", "F", "Gm", "Dm"], ["Bb", "F", "C", "Dm7"]],
    "C": [["Dm", "Eb", "Dm", "A7"], ["Dm", "Bb", "Gm", "A7"]],
    "D": [["Bb", "F", "C", "Dm"], ["Bb", "C", "F", "F"]],
    "E": [["F", "C", "Dm", "Bb"], ["F", "Am", "Bb", "C"]],      # cotidiano: fá maior claro
}
FINAIS = {   # dois últimos compassos de cada deixa
    "suspensao": ["Gm", "Asus4"], "suspensao_grave": ["Bb", "Asus4"], "tonica_escura": ["A7", "Dm"],
    "sexto_suspenso": ["C", "Bbadd9"], "dominante_aberta": ["Gm", "A7"], "brilho": ["Csus4", "Fadd9"],
    "cadencia_maior": ["C", "F"],
}
FAIXA = {"S": (69, 81), "A": (62, 74), "T": (55, 67)}      # soprano A4–A5, contralto D4–D5, tenor G3–G4


def alturas(pcs, lo, hi):
    return [p for p in range(lo, hi + 1) if p % 12 in pcs]


def paralelas(ant, nova, baixo_ant, baixo_novo):
    v_ant, v_nov = [baixo_ant] + list(ant), [baixo_novo] + list(nova)
    for i, j in itertools.combinations(range(4), 2):
        i0, i1 = (v_ant[j] - v_ant[i]) % 12, (v_nov[j] - v_nov[i]) % 12
        movem = v_ant[i] != v_nov[i] and v_ant[j] != v_nov[j]
        if movem and i0 == i1 and i0 in (0, 7):
            return True
    return False


def dispor(acorde, ant, baixo_ant, baixo_novo):
    """Melhor disposição S/A/T: todas as notas do tríade presentes, sem cruzamento nem paralelas,
    com o menor movimento total das vozes."""
    pcs = ACORDE[acorde]
    essenciais = set(pcs[:3])
    melhor, custo_min = None, 1e9
    for s in alturas(pcs, *FAIXA["S"]):
        for al in alturas(pcs, *FAIXA["A"]):
            for t in alturas(pcs, *FAIXA["T"]):
                if not (s > al > t > baixo_novo) or s - t > 19:
                    continue
                if not essenciais <= {s % 12, al % 12, t % 12, baixo_novo % 12}:
                    continue
                nova = (s, al, t)
                custo = 0 if ant is None else sum(abs(x - y) for x, y in zip(nova, ant))
                if ant is not None and paralelas(ant, nova, baixo_ant, baixo_novo):
                    custo += 100
                custo += abs(s - 74) * 0.1      # soprano perto de ré5 (centro confortável)
                if custo < custo_min:
                    melhor, custo_min = nova, custo
    return melhor


def baixo_de(acorde, ant):
    raiz = ACORDE[acorde][0]
    cands = [p for p in range(38, 51) if p % 12 == raiz]          # ré2–ré3 (cello)
    return min(cands, key=lambda p: abs(p - ant) if ant else abs(p - 43))


def motivo(acorde_ini, acorde_seg, ini, maior=False):
    """Motivo do voo em 1 compasso: tempo 1 nota do acorde, tempo 2 salta a uma nota do acorde 4–7 st acima
    (o voo), depois desce por graus da escala até uma nota do acorde seguinte no tempo 1 do próximo compasso."""
    pcs = ACORDE[acorde_ini]
    base = min(alturas(pcs, 69, 76), key=lambda p: abs(p - 72))
    picos = [p for p in alturas(pcs, base + 4, base + 8)] or [base + 7]
    pico = picos[0]
    notas = [(ini, PPQ, base, 66), (ini + PPQ, int(PPQ * 1.5), pico, 74)]
    t, alt = ini + int(PPQ * 2.5), pico
    for _ in range(3):
        alt -= 1
        while alt % 12 not in ESCALA_RE_MENOR:
            alt -= 1
        notas.append((t, PPQ // 2, alt, 60))
        t += PPQ // 2
    destino = min(alturas(ACORDE[acorde_seg], alt - 5, alt + 2), key=lambda p: abs(p - (alt - 2)))
    notas.append((ini + BAR, int(PPQ * 1.8), destino, 64))
    return notas


PENTA_FA = {5, 7, 9, 0, 2}      # fá maior pentatônico: a melodia dos sininhos nunca esbarra no acorde
RITMOS = [[(0, 1), (1, .5), (1.5, .5), (2, 1), (3, 1)], [(0, .5), (.5, .5), (1, 1), (2, 1.5), (3.5, .5)],
          [(0, 1.5), (1.5, .5), (2, .5), (2.5, .5), (3, 1)], [(0, 1), (1, 1), (2, .5), (2.5, .5), (3, 1)]]


def melodia_leve(ac, t0, fim_frase, cur, rnd):
    """Sininhos (slice of life): frase saltitante em colcheias/semínimas, tempos 1 e 3 em nota do acorde;
    o 4º compasso da frase repousa numa nota longa."""
    pent = [x for x in range(74, 89) if x % 12 in PENTA_FA]
    acordes = [x for x in range(74, 89) if x % 12 in ACORDE[ac][:3]]
    if fim_frase:
        alvo = min(acordes, key=lambda x: abs(x - cur))
        return [(t0, int(PPQ * 2.8), alvo, 62)], alvo
    notas = []
    for onset, dur in rnd.choice(RITMOS):
        if onset in (0, 2):
            perto = [x for x in acordes if abs(x - cur) <= 5] or acordes
            cur = rnd.choice(perto)
        else:
            i = min(range(len(pent)), key=lambda j: abs(pent[j] - cur))
            cur = pent[max(0, min(len(pent) - 1, i + rnd.choice([-1, 1, 1, 2, -2])))]
        notas.append((t0 + int(onset * PPQ), int(dur * PPQ * 0.85), cur, 60 + (6 if onset in (0, 2) else 0) + rnd.randint(-4, 4)))
    return notas, cur


def cue_cotidiano(parte, compassos, prog, final):
    """Humor E: piano leve em staccato, pizzicato no baixo, melodia de celesta respondida pelo glockenspiel,
    cordas só como um colchão bem baixo."""
    rnd = random.Random(parte["parte"] * 31)
    ev = {"piano": [], "cordas": [], "pizz": [], "melodia": [], "glock": []}
    cc_cordas = []
    ant = baixo_ant = None
    cur = 77
    for k, ac in enumerate(prog):
        t0 = k * BAR
        b = baixo_de(ac, baixo_ant)
        voz = dispor(ac, ant, baixo_ant, b)
        ev["pizz"] += [(t0, PPQ, b, 74), (t0 + 2 * PPQ, PPQ, b + 7, 66)]
        ev["piano"].append((t0, int(PPQ * 0.9), b + 12, 46 + rnd.randint(-3, 3)))
        for bt in (1, 2, 3):                                  # acordes curtos nos tempos 2–4 (saltitante)
            for x in (voz[1], voz[2]) if bt != 2 else (voz[2],):
                ev["piano"].append((t0 + bt * PPQ + rnd.randint(-5, 5), int(PPQ * 0.4), x, 38 + rnd.randint(-3, 3)))
        if k >= 2:
            for x in voz:
                ev["cordas"].append((t0, BAR, x, 52))
        for j in range(8):
            pos = (k + j / 8) / compassos
            env = min(1.0, pos * compassos / 2.0, (1 - pos) * compassos / 1.2 + 0.25)
            cc_cordas.append((t0 + j * BAR // 8, int(max(8, 45 * env))))
        corpo = 1 <= k < compassos - 2
        if corpo:                                             # frases de 4 compassos a partir do 2º: celesta chama, glock responde
            f = (k - 1) // 4
            notas, cur = melodia_leve(ac, t0, (k - 1) % 4 == 3, cur, rnd)
            if f % 2 == 0:
                ev["melodia"] += notas
            else:
                ev["glock"] += [(t, d, min(100, x + 12), v - 6) for t, d, x, v in notas]
                ev["melodia"] += [(t, d, x, v - 22) for t, d, x, v in notas if (t - t0) % PPQ == 0]   # celesta em eco
        if not corpo or (k - 1) % 4 == 3:                     # sininho: arpejo agudo do acorde no fim da frase
            topo = sorted(x for x in range(84, 100) if x % 12 in ACORDE[ac])
            for j, x in enumerate(topo[:4]):
                ev["glock"].append((t0 + 2 * PPQ + j * PPQ // 2, PPQ * 2, x, 50 - 4 * j))
        ant, baixo_ant = voz, b
    t0 = (compassos - 1) * BAR
    for j, x in enumerate(sorted(x for x in range(77, 92) if x % 12 in ACORDE[prog[-1]])[:4]):
        ev["melodia"].append((t0 + j * PPQ, PPQ * (4 - j), x, 56))
    return ev, cc_cordas


def cue(parte):
    random.seed(parte["parte"] * 31)
    dur = parte["duracao_s"]
    compassos = max(4, round(dur * (84 if parte["humor"] == "E" else 70) / 240))   # cotidiano anda um pouco mais
    bpm = compassos * 240 / dur
    humor, final = parte["humor"], parte["final"]
    corpo = []
    i = 0
    while len(corpo) < compassos - 2:
        corpo += PROGRESSOES[humor][i % len(PROGRESSOES[humor])]
        i += 1
    prog = corpo[: compassos - 2] + FINAIS[final]
    if humor == "E":
        ev, cc_cordas = cue_cotidiano(parte, compassos, prog, final)
        return compassos, bpm, prog, ev, cc_cordas
    ev = {"piano": [], "cordas": [], "cello": [], "celesta": []}
    cc_cordas = []
    ant = baixo_ant = None
    densidade = {"A": 0.5, "A_escuro": 0.25, "B": 0.75, "C": 0.15, "D": 1.0}[humor]
    for k, ac in enumerate(prog):
        t0 = k * BAR
        b = baixo_de(ac, baixo_ant)
        voz = dispor(ac, ant, baixo_ant, b)
        if humor != "A" or k >= 2:                    # A começa só com piano; cordas entram depois
            for p in voz:
                ev["cordas"].append((t0, BAR, p, 70))
        ev["cello"].append((t0, BAR, b, 72))
        if humor == "C":                               # ostinato de colcheias no ré grave (tensão)
            ev["cello"] = ev["cello"][:-1] + [(t0 + j * PPQ // 2, PPQ // 2 - 30, b, 60 + 8 * (j % 2)) for j in range(8)]
        # piano mão esquerda: baixo + arpejo pela disposição (1–5–8–10…), velocidade com o fraseado
        arp = [b + 12, voz[2], voz[1], voz[2], voz[0] - 12 if voz[0] - 12 > voz[1] else voz[1], voz[2], voz[1], voz[2]]
        frase = 0.85 + 0.15 * math.sin(math.pi * (k % 4) / 3)
        for j, p in enumerate(arp):
            vel = int((48 if j else 56) * frase) + random.randint(-4, 4)
            ev["piano"].append((t0 + j * PPQ // 2 + random.randint(-6, 6), int(PPQ * 0.9), p, vel))
        # melodia: motivo nos compassos 1 e 3 de cada frase de 4, conforme a densidade do humor
        if k < compassos - 2 and k % 4 in (0, 2) and random.random() < densidade and k + 1 < len(prog):
            for n in motivo(ac, prog[k + 1], t0, maior=humor == "D"):
                ev["piano"].append(n)
        # CC1 das cordas: crescendo na frase (pico no 3º compasso) e entrada/saída suaves
        for j in range(8):
            t = t0 + j * BAR // 8
            pos = (k + j / 8) / compassos
            fr = 0.55 + 0.35 * math.sin(math.pi * ((k % 4) + j / 8) / 4)
            env = min(1.0, pos * compassos / 1.5, (1 - pos) * compassos / 1.2 + 0.25)
            cc_cordas.append((t, int(max(8, min(110, 100 * fr * env)))))
        ant, baixo_ant = voz, b
    if final in ("brilho", "cadencia_maior"):
        t0 = (compassos - 1) * BAR
        for j, p in enumerate([77, 81, 84, 89]):          # fá–lá–dó–fá na celesta
            ev["celesta"].append((t0 + j * PPQ, PPQ * (4 - j), p, 58))
    return compassos, bpm, prog, ev, cc_cordas


def salvar(nome, bpm, ev, cc, arq):
    mid = mido.MidiFile(ticks_per_beat=PPQ)
    for pista, notas in ev.items():
        if not notas:
            continue
        tr = mido.MidiTrack(); mid.tracks.append(tr)
        tr.append(mido.MetaMessage("track_name", name=pista))
        tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
        e = []
        for t, d, p, v in notas:
            t = max(0, t)   # a humanização não pode adiantar a primeira nota para antes do zero
            e += [(t, 1, ("on", p, max(1, min(127, v)))), (t + d, 0, ("off", p, 0))]
        if pista in ("cordas", "cello"):
            e += [(t, 2, ("cc", 1, v)) for t, v in cc]
        e.sort(key=lambda x: (x[0], x[1]))
        tant = 0
        for t, _, (tipo, p, v) in e:
            dt = t - tant; tant = t
            if tipo == "cc":
                tr.append(mido.Message("control_change", control=p, value=v, time=dt))
            else:
                tr.append(mido.Message("note_on" if tipo == "on" else "note_off", note=p, velocity=v, time=dt))
    mid.save(arq)


plano = json.loads(Path(a.plano).read_text(encoding="utf-8"))
out = Path(a.saida); out.mkdir(parents=True, exist_ok=True)
resumo = []
for parte in plano["partes"]:
    compassos, bpm, prog, ev, cc = cue(parte)
    arq = out / f"cue_parte{parte['parte']:02d}.mid"
    salvar(f"parte{parte['parte']}", bpm, ev, cc, arq)
    resumo.append({"parte": parte["parte"], "duracao_s": parte["duracao_s"], "compassos": compassos,
                   "bpm": round(bpm, 3), "duracao_musica_s": round(compassos * 240 / bpm, 3), "harmonia": prog})
    print(f"parte {parte['parte']}: {compassos} compassos a {bpm:.2f} BPM = {compassos * 240 / bpm:.2f} s | {' '.join(prog)}")
(out / "resumo_cues.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
