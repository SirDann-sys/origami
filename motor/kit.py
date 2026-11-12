# Kit de postagem: o trabalhador escreve ganchos, legendas, título e nomes dos capítulos (frases reais do
# texto, sem spoiler); o motor põe os tempos dos capítulos (das partes mixadas + 0,4 s de respiro, igual ao 16:9)
# e os rodapés fixos da marca e da obra. Saída: 07_publicacao/epNN/kit.json (a aba Publicação mostra e copia).
import time
import soundfile as sf
from .config import RESPIRO_S
from .obra import Episodio, ler_json, gravar_json
from . import trabalhador, texto, mesa


def tempos_capitulos(ep):
    t, out = 0.0, []
    for n in ep.partes():
        out.append(t)
        t += sf.info(str(ep.mix_wav(n))).duration + RESPIRO_S
    return out


def mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def gerar(ep, log=None):
    if not ep.roteiro_arq.exists():
        raise RuntimeError("falta o roteiro de áudio do episódio")
    faltam = [n for n in ep.partes() if not ep.mix_wav(n).exists()]
    if faltam:
        raise RuntimeError(f"faltam as mixagens das partes {faltam} (os capítulos do YouTube usam a duração real)")
    n = int(ep.ep)
    ant = Episodio(ep.obra, n - 1) if n > 1 else None
    cfg, marca = ep.cfg, ep.marca
    entrada = {"obra": cfg.get("titulo"), "assinatura": cfg.get("assinatura"), "episodio": {"numero": n, "titulo": ep.titulo_ep(), "partes": len(ep.partes())},
               "mestre": texto._sem_notas(ep.mestre.read_text(encoding="utf-8")) if ep.mestre.exists() else "",
               "roteiro": ep.roteiro, "guia_episodio": mesa.mapa(ep.obra, ep.ep),
               "kit_anterior": ler_json(ant.publicacao / "kit.json") if ant else None}
    r, _ = trabalhador.rodar("kit", entrada, ep.obra, log=log, ep=ep.ep)
    ts = tempos_capitulos(ep)
    caps = "\n".join(f"{mmss(t)} {nome}" for t, nome in zip(ts, r["capitulos"]))
    div = cfg.get("divulgacao", {})
    kit = {"ep": ep.ep, "gerado": time.strftime("%Y-%m-%d %H:%M"),
           "youtube": {"titulo": r["youtube_titulo"],
                       "descricao": f"{r['youtube_topo'].strip()}\n\n⏱️ Capítulos\n{caps}\n\n{marca.get('rodape_youtube', '')}".strip(),
                       "miniatura": f"entrega/miniatura_ep{ep.ep}.jpg"},
           "partes": [{"n": p["n"], "short_titulo": p["short_titulo"],
                       "legenda": p["legenda"].strip() + ("\n\n" + div["rodape_legenda"] if div.get("rodape_legenda") else "")}
                      for p in r["partes"]],
           "comentario_fixado": r["comentario_fixado"],
           "wattpad": {"titulo_capitulo": f"Episódio {n} · {ep.titulo_ep()}"},
           "rotulo_ia": marca.get("rotulo_ia", "")}
    if ep.publicacao.joinpath("kit.json").exists():
        ep.publicacao.joinpath("kit.json").replace(ep.publicacao / f"kit_{time.strftime('%Y%m%d_%H%M%S')}.json")
    gravar_json(ep.publicacao / "kit.json", kit)
    return f"kit: título + {len(kit['partes'])} legendas + {len(r['capitulos'])} capítulos"
