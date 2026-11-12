# Origami — linha de comando. Saída curta de propósito (economia de tokens quando o Claude opera o motor).
#   origami produzir OBRA EP [--partes 3 5] [--de mix] [--ate video] [--forcar mix,video|tudo]
#   origami fala OBRA EP PP_FF [--texto "..."] [--pausa 0.6] [--regerar] [--tudo]   (corrige e propaga)
#   origami plano OBRA EP            o que está desatualizado agora (sem contar a propagação)
#   origami rodar                    roda a fila até esvaziar (primeiro plano)
#   origami servidor                 worker + API HTTP em 127.0.0.1:3950 (para o app)
#   origami fila [--n 20]            últimos jobs
#   origami cancelar ID | origami limpar
#   origami imagens OBRA EP [--so ID ...] [--sementes 2] | origami ampliar OBRA EP [--so ID ...]
#   origami arte OBRA EP [--so ID ...] [--sementes 2] [--ampliar] [--verificar] [--ignorar_alertas]
#                                   cenas de divulgação com o guia de arte da obra (--verificar: só mostra prompts e alertas)
#   origami entregar OBRA EP [--so parte:3 16x9 capas miniatura wattpad]   copia para 07_publicacao/epNN/entrega
import argparse, json, sys, time
from . import db
from .obra import Episodio, ler_json, gravar_json
from .etapas import ETAPAS, CADEIA, desatualizada, voz_pendentes
from .worker import laco, servidor, enfileirar_cadeia, cancelar


def main(argv=None):
    for f in (sys.stdout, sys.stderr):           # acentos certos no console do Windows
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="origami")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("produzir"); p.add_argument("obra"); p.add_argument("ep")
    p.add_argument("--partes", type=int, nargs="*"); p.add_argument("--de", choices=CADEIA); p.add_argument("--ate", choices=CADEIA)
    p.add_argument("--forcar"); p.add_argument("--ja", action="store_true", help="roda a fila em seguida")
    f = sub.add_parser("fala"); f.add_argument("obra"); f.add_argument("ep"); f.add_argument("fala", help="PP_FF, ex.: 02_06")
    f.add_argument("--texto"); f.add_argument("--pausa", type=float); f.add_argument("--regerar", action="store_true")
    f.add_argument("--tudo", action="store_true", help="inclui o vídeo 16:9 do episódio"); f.add_argument("--ja", action="store_true")
    pl = sub.add_parser("plano"); pl.add_argument("obra"); pl.add_argument("ep")
    sub.add_parser("rodar"); sub.add_parser("limpar")
    sv = sub.add_parser("servidor"); sv.add_argument("--so_api", action="store_true", help="sem worker (outro processo usa a GPU)")
    fi = sub.add_parser("fila"); fi.add_argument("--n", type=int, default=20)
    ca = sub.add_parser("cancelar"); ca.add_argument("id", type=int)
    for nome in ("imagens", "ampliar"):
        im = sub.add_parser(nome); im.add_argument("obra"); im.add_argument("ep"); im.add_argument("--so", nargs="*")
        im.add_argument("--sementes", type=int, default=2); im.add_argument("--ja", action="store_true")
    ar = sub.add_parser("arte"); ar.add_argument("obra"); ar.add_argument("ep"); ar.add_argument("--so", nargs="*")
    ar.add_argument("--sementes", type=int, default=2); ar.add_argument("--ampliar", action="store_true")
    ar.add_argument("--verificar", action="store_true"); ar.add_argument("--ignorar_alertas", action="store_true")
    ar.add_argument("--ja", action="store_true")
    en = sub.add_parser("entregar"); en.add_argument("obra"); en.add_argument("ep"); en.add_argument("--so", nargs="*")
    en.add_argument("--ja", action="store_true")
    a = ap.parse_args(argv)
    c = db.conectar()

    if a.cmd == "produzir":
        forcar = "tudo" if a.forcar == "tudo" else (a.forcar.split(",") if a.forcar else None)
        lote, ids = enfileirar_cadeia(c, a.obra, a.ep, a.partes, a.de, a.ate, forcar, portao=False)
        print(f"lote {lote}: jobs {ids[0]}–{ids[-1]} ({', '.join(CADEIA[CADEIA.index(a.de or CADEIA[0]):CADEIA.index(a.ate or CADEIA[-1]) + 1])})")
        if a.ja:
            laco(drenar=True)

    elif a.cmd == "fala":
        ep = Episodio(a.obra, a.ep)
        pp, ff = (int(x) for x in a.fala.split("_"))
        rot = ep.roteiro
        fala = next(x for x in rot["partes"] if x["parte"] == pp)["falas"][ff - 1]
        if a.texto:
            print(f"antes : {fala['texto']}\ndepois: {a.texto}"); fala["texto"] = a.texto
        if a.pausa is not None:
            fala["pausa"] = a.pausa
        if a.texto or a.pausa is not None:
            gravar_json(ep.roteiro_arq, rot)
        extra = {"regerar": [a.fala]} if a.regerar else None
        lote, ids = enfileirar_cadeia(c, a.obra, a.ep, [pp], ate=None if a.tudo else "video", params_extra=extra)
        print(f"propagação enfileirada (lote {lote}, jobs {ids[0]}–{ids[-1]}): só a parte {pp} será refeita")
        if a.ja:
            laco(drenar=True)

    elif a.cmd == "plano":
        ep = Episodio(a.obra, a.ep)
        pend = voz_pendentes(ep)
        print(f"voz      : {len(pend)} fala(s) a gravar" + (f" ({', '.join(pend[:10])}{'…' if len(pend) > 10 else ''})" if pend else ""))
        for t in CADEIA[2:]:
            e = ETAPAS[t]
            alvos = ep.partes() if e["escopo"] == "parte" else [None]
            try:
                d = [n for n in alvos if desatualizada(ep, t, n, c)[0]]
                txt = ("desatualizada" if d else "em dia") if e["escopo"] == "ep" else (f"partes {d}" if d else "em dia")
                if "entradas" in e:
                    from .etapas import situacao
                    novo = [n for n in alvos if situacao(ep, t, n, c)[0] == "codigo novo"]
                    if novo:
                        txt += " · código novo" + (f" nas partes {novo}" if e["escopo"] == "parte" else "") + " (--forcar " + t + ")"
            except Exception as ex:
                txt = f"sem dados ainda ({type(ex).__name__})"
            print(f"{t:<9}: {txt}")
        print("(etapas depois de algo desatualizado também serão refeitas, na propagação)")

    elif a.cmd == "rodar":
        laco(drenar=True)
    elif a.cmd == "servidor":
        servidor(so_api=a.so_api)
    elif a.cmd == "fila":
        for r in reversed(c.execute("SELECT * FROM job ORDER BY id DESC LIMIT ?", (a.n,)).fetchall()):
            dur = f"{r['fim'] - r['inicio']:5.0f}s" if r["fim"] and r["inicio"] else "     "
            print(f"#{r['id']:<4} {r['tipo']:<11} {r['obra'][:18]:<18} ep{r['ep']} {r['estado']:<9} {dur} {(r['resumo'] or r['erro'] or '')[:90]}")
    elif a.cmd == "cancelar":
        print("ok" if cancelar(c, a.id) else "job não encontrado")
    elif a.cmd == "limpar":
        n = c.execute("DELETE FROM job WHERE estado IN ('pronto','pulado','cancelado') AND fim < ?", (time.time() - 7 * 86400,)).rowcount
        print(f"{n} job(s) antigos removidos")
    elif a.cmd in ("imagens", "ampliar"):
        Episodio(a.obra, a.ep)
        params = {"so": a.so, "sementes": a.sementes, "ampliar": a.cmd == "ampliar"}
        jid = db.enfileirar(c, "imagens", a.obra, f"{int(a.ep):02d}", params=params)
        print(f"job {jid}: {a.cmd}")
        if a.ja:
            laco(drenar=True)

    elif a.cmd == "arte":
        ep = Episodio(a.obra, a.ep)
        if a.verificar:
            from .etapas import montar_prompts
            assets, alertas = montar_prompts(ep)
            for it in assets["itens"]:
                if not a.so or it["id"] in a.so:
                    print(f"{it['id']}: {it['prompt'][:160]}…")
            print("ALERTAS:\n  " + "\n  ".join(alertas) if alertas else "sem alertas de consistência")
            return
        params = {"so": a.so, "sementes": a.sementes, "ampliar": a.ampliar, "ignorar_alertas": a.ignorar_alertas}
        print(f"job {db.enfileirar(c, 'arte', a.obra, f'{int(a.ep):02d}', params=params)}: arte")
        if a.ja:
            laco(drenar=True)
    elif a.cmd == "entregar":
        Episodio(a.obra, a.ep)
        print(f"job {db.enfileirar(c, 'entregar', a.obra, f'{int(a.ep):02d}', params={'so': a.so})}: entregar")
        if a.ja:
            laco(drenar=True)


if __name__ == "__main__":
    main()
