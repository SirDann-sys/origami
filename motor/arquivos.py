# Organização dos arquivos. Nada se move sem o autor aprovar na tela "Arquivos".
#   inventario() → o que existe, o tamanho, o que é e para onde iria (com o motivo)
#   mover(ids)   → move SÓ os itens aprovados; cada movimento fica em dados/arquivos_log.json (dá para desfazer)
#   Meta: obras/<obra>/PUBLICAR/EpNN/ com as peças finais (vídeos, 16x9, capas, miniatura, wattpad), sem cópias
#   duplicadas (a entrega passa a usar hardlink); rascunhos, pilotos e cópias velhas vão para _arquivo/ (nunca apagados).
import json, os, shutil, time
from pathlib import Path
from .config import RAIZ, PROJETOS, DADOS
from .obra import Episodio, ler_json, gravar_json

ARQUIVO = RAIZ / "_arquivo"
LOG = DADOS / "arquivos_log.json"
OUVIR_GRANDE = 100 * 1024 * 1024         # na pasta ouvir/, o que passa disto é cópia de vídeo/episódio (não escuta)


def _tam(p):
    p = Path(p)
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _vazia(p):
    return p.is_dir() and not any(p.rglob("*"))


def _protegidos(ep):
    """O que o motor lê ou escreve nesta pasta de publicação: nunca sai do lugar."""
    from .etapas import wattpad_saidas
    prot = {"arte", "entrega", "kit.json", "postagens.json", "calendario.json"}
    try:
        prot |= {p.name for p in wattpad_saidas(ep, None)}
    except Exception:
        prot |= {p.name for p in ep.publicacao.glob("wattpad_cap*")}
    return prot


def inventario():
    itens = []

    def add(id_, caminho, tipo, descricao, destino, marcado=True):
        p = Path(caminho)
        if not p.exists():
            return
        itens.append({"id": id_, "caminho": str(p), "rel": str(p.relative_to(RAIZ)), "tamanho": _tam(p), "tipo": tipo,
                      "descricao": descricao, "destino": str(destino) if destino else "", "marcado": marcado})

    for obra in sorted(x for x in PROJETOS.iterdir() if (x / "projeto.json").exists()):
        pub = obra / "07_publicacao"
        for d in sorted(pub.glob("ep[0-9][0-9]")) if pub.exists() else []:
            n = d.name[2:]
            ep = Episodio(obra.name, n)
            antiga, nova = d / "entrega", obra / "PUBLICAR" / f"Ep{n}"
            if antiga.exists() and any(antiga.rglob("*")) and not nova.exists():
                add(f"pub:{obra.name}:{n}", antiga, "publicar", f"Peças finais do Ep. {n} (vídeos, capas, Wattpad): passam a morar em PUBLICAR", nova)
            prot = _protegidos(ep)
            for f in sorted(d.iterdir()):
                if f.name in prot:
                    continue
                if f.name.startswith("capa_wattpad"):        # capa da série no Wattpad: peça final, não rascunho
                    add(f"pub:{f.relative_to(RAIZ)}", f, "mover", "Capa da série no Wattpad (peça final)", obra / "PUBLICAR" / "Serie" / f.name)
                    continue
                add(f"arq:{f.relative_to(RAIZ)}", f, "arquivar", "Rascunho/versão antiga solta na pasta de publicação",
                    ARQUIVO / f.relative_to(RAIZ))
        from .obra_nova import PASTAS
        padrao = {Path(p).parts[0] for p in PASTAS} | {"PUBLICAR", "06_video"}
        for f in sorted(obra.iterdir()):
            if f.is_dir() and f.name.startswith("_"):
                add(f"arq:{f.relative_to(RAIZ)}", f, "arquivar", "Piloto/teste antigo da obra", ARQUIVO / f.relative_to(RAIZ))
            elif _vazia(f) and f.name not in padrao:      # as pastas padrão de toda obra ficam, mesmo vazias
                add(f"vazia:{f.relative_to(RAIZ)}", f, "remover", "Pasta vazia que não faz parte do padrão da obra", None)
    ouvir = RAIZ / "ouvir"
    if ouvir.exists():
        for f in sorted(ouvir.iterdir()):
            t = _tam(f)
            if f.name in ("LEIA.txt",):
                continue
            if f.name.startswith("MANUAL_DE_POSTAGEM"):
                add(f"arq:{f.relative_to(RAIZ)}", f, "arquivar", "Manual de postagem antigo (datas vencidas; o calendário da aba Postagem substitui)",
                    ARQUIVO / f.relative_to(RAIZ))
            elif t >= OUVIR_GRANDE:
                add(f"arq:{f.relative_to(RAIZ)}", f, "arquivar", "Cópia de vídeo/episódio do piloto (as peças finais ficam em PUBLICAR)",
                    ARQUIVO / f.relative_to(RAIZ))
            else:
                add(f"arq:{f.relative_to(RAIZ)}", f, "arquivar", "Escuta antiga (teste de voz/trilha): pode ficar", ARQUIVO / f.relative_to(RAIZ), marcado=False)
    return {"itens": itens, "total": sum(i["tamanho"] for i in itens if i["marcado"]),
            "historico": [{"lote": l["lote"], "em": l["em"], "n": len(l["movidos"])} for l in ler_json(LOG, {"lotes": []})["lotes"][-10:]]}


def mover(ids):
    inv = {i["id"]: i for i in inventario()["itens"]}
    lote = {"lote": time.strftime("%Y%m%d-%H%M%S"), "em": time.strftime("%Y-%m-%d %H:%M"), "movidos": []}
    falhas = []
    for id_ in ids:
        it = inv.get(id_)
        if not it:
            falhas.append(f"{id_}: não está mais no inventário"); continue
        de = Path(it["caminho"])
        try:
            if it["tipo"] == "remover":
                if _vazia(de):
                    shutil.rmtree(de)
                    lote["movidos"].append({"de": str(de), "para": None, "tipo": "remover"})
                continue
            para = Path(it["destino"])
            if para.exists():
                falhas.append(f"{it['rel']}: o destino já existe ({para})"); continue
            para.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(de), str(para))
            lote["movidos"].append({"de": str(de), "para": str(para), "tipo": it["tipo"]})
        except OSError as ex:
            falhas.append(f"{it['rel']}: {ex}")
    if lote["movidos"]:
        d = ler_json(LOG, {"lotes": []})
        d["lotes"].append(lote)
        gravar_json(LOG, d)
    # o que foi para PUBLICAR: as cópias iguais às do motor viram hardlink (o mesmo arquivo, sem ocupar espaço de novo)
    economia = 0
    for m in lote["movidos"]:
        if m["tipo"] == "publicar":
            obra, n = Path(m["para"]).parents[1].name, Path(m["para"]).name[2:]
            economia += deduplicar(Episodio(obra, n))
    return {"ok": not falhas, "movidos": len(lote["movidos"]), "falhas": falhas, "lote": lote["lote"],
            "economia_gb": round(economia / 1e9, 2)}


def desfazer(lote_id):
    d = ler_json(LOG, {"lotes": []})
    lote = next((l for l in d["lotes"] if l["lote"] == lote_id), None)
    if not lote:
        raise RuntimeError("lote não encontrado")
    voltou, falhas = 0, []
    for m in reversed(lote["movidos"]):
        try:
            if m["tipo"] == "remover":
                Path(m["de"]).mkdir(parents=True, exist_ok=True)
            elif Path(m["para"]).exists() and not Path(m["de"]).exists():
                Path(m["de"]).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(m["para"], m["de"])
            else:
                falhas.append(m["de"]); continue
            voltou += 1
        except OSError as ex:
            falhas.append(f"{m['de']}: {ex}")
    d["lotes"] = [l for l in d["lotes"] if l["lote"] != lote_id]
    gravar_json(LOG, d)
    return {"ok": not falhas, "voltou": voltou, "falhas": falhas}


# ------------------------------------------------------------------ entrega sem cópia
def vincular(orig, dest):
    """dest passa a ser o MESMO arquivo que orig (hardlink no mesmo disco); se não der, copia."""
    orig, dest = Path(orig), Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".vinculando")
    try:
        if tmp.exists():
            tmp.unlink()
        os.link(orig, tmp)
        os.replace(tmp, dest)
        return "link"
    except OSError:
        if tmp.exists():
            tmp.unlink()
        shutil.copy2(orig, dest)
        return "copia"


def deduplicar(ep):
    """Cópias na entrega idênticas às saídas do motor viram hardlink. Devolve os bytes economizados."""
    from .etapas import entregaveis
    from .obra import sha1_arquivo
    salvo = 0
    for orig, nome, _ in entregaveis(ep):
        dest = ep.entrega / nome
        if not orig.exists() or not dest.exists():
            continue
        try:
            if os.path.samefile(orig, dest):
                continue
        except OSError:
            continue
        if orig.stat().st_size == dest.stat().st_size and sha1_arquivo(orig) == sha1_arquivo(dest):
            if vincular(orig, dest) == "link":
                salvo += orig.stat().st_size
    return salvo
