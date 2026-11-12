# Visão da operação: a fila do motor (o que fez, faz e vai fazer, com erro legível e log) e o custo
# (tokens/dólares do Opus por tarefa e episódio; horas de máquina por tipo de etapa).
import json, time
from collections import defaultdict
from .config import LOGS, PROJETOS
from .etapas import ETAPAS

NOME = {"sincronizar": "Conferir roteiro", "voz": "Gravar falas", "montar": "Montar partes", "cue": "Compor trilha", "stems": "Instrumentos",
        "mix": "Mixar", "episodio": "Episódio (áudio)", "tempos": "Tempos das palavras", "video": "Vídeos 9:16", "video16x9": "Episódio 16:9",
        "capas": "Capas", "wattpad": "Wattpad", "entregar": "Entrega", "imagens": "Imagens do vídeo", "arte": "Imagens das cenas",
        "mestre": "Texto-mestre", "revisar": "Ajustar texto", "alarme": "Alarme", "corrigir": "Corrigir trechos", "roteiro": "Roteiro de áudio", "kit": "Kit",
        "cenas": "Sugerir cenas", "elenco": "Candidatas de voz", "previa": "Prévia em quadros",
        "triagem": "Triagem das imagens (Opus)", "obra": "Obra nova", "amostra": "Amostra de pronúncia", "postagem": "Agendar postagem"}


def fila(c, obra=None, n=80):
    q = "SELECT * FROM job" + (" WHERE obra=?" if obra else "") + " ORDER BY id DESC LIMIT ?"
    rows = c.execute(q, ((obra, n) if obra else (n,))).fetchall()
    agora = time.time()
    out = []
    for r in rows:
        dur = (r["fim"] or agora) - r["inicio"] if r["inicio"] else None
        out.append({"id": r["id"], "tipo": r["tipo"], "nome": NOME.get(r["tipo"], r["tipo"]), "obra": r["obra"], "ep": r["ep"],
                    "parte": r["parte"], "estado": r["estado"], "criado": r["criado"], "duracao": round(dur) if dur else None,
                    "resumo": r["resumo"], "erro": r["erro"], "espera_ate": r["espera_ate"] if "espera_ate" in r.keys() else None,
                    "tem_log": bool(r["log"]) or (LOGS / f"job_{r['id']}.log").exists()})
    contagem = {e: c.execute("SELECT COUNT(*) FROM job WHERE estado=?" + (" AND obra=?" if obra else ""),
                             ((e, obra) if obra else (e,))).fetchone()[0] for e in ("na_fila", "rodando", "erro")}
    return {"jobs": out, "contagem": contagem}


def log(id_, linhas=150):
    arq = LOGS / f"job_{int(id_)}.log"
    if not arq.exists():
        return {"id": id_, "texto": "(sem log)"}
    t = arq.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"id": id_, "texto": "\n".join(t[-linhas:]), "total_linhas": len(t)}


def custo(c, obra):
    """Opus: custo.jsonl da obra (tarefa, ep, dólares, tokens). Máquina: soma da duração dos jobs, por recurso e episódio."""
    ia = defaultdict(lambda: {"usd": 0.0, "entrada": 0, "saida": 0, "chamadas": 0})
    ia_ep = defaultdict(float)
    arq = PROJETOS / obra / "custo.jsonl"
    if arq.exists():
        for l in arq.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(l)
            except json.JSONDecodeError:
                continue
            k = ia[r.get("tarefa", "?")]
            k["usd"] += r.get("custo_usd", 0) or 0; k["entrada"] += r.get("entrada", 0); k["saida"] += r.get("saida", 0); k["chamadas"] += 1
            ia_ep[r.get("ep") or "—"] += r.get("custo_usd", 0) or 0
    maq = defaultdict(float)
    maq_ep = defaultdict(float)
    for r in c.execute("SELECT tipo, ep, inicio, fim FROM job WHERE obra=? AND estado='pronto' AND inicio IS NOT NULL AND fim IS NOT NULL", (obra,)):
        rec = ETAPAS.get(r["tipo"], {}).get("recurso", "cpu")
        maq[rec] += r["fim"] - r["inicio"]
        maq_ep[r["ep"]] += r["fim"] - r["inicio"]
    return {"obra": obra,
            "ia": {k: {**v, "usd": round(v["usd"], 2)} for k, v in sorted(ia.items(), key=lambda x: -x[1]["usd"])},
            "ia_total_usd": round(sum(v["usd"] for v in ia.values()), 2),
            "ia_por_ep": {k: round(v, 2) for k, v in sorted(ia_ep.items())},
            "maquina_h": {k: round(v / 3600, 2) for k, v in sorted(maq.items(), key=lambda x: -x[1])},
            "maquina_por_ep_h": {k: round(v / 3600, 2) for k, v in sorted(maq_ep.items())}}
