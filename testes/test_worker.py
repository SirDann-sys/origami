# O worker não cai: erro de serviço volta à fila, limite do Claude espera, queda conta tentativas.
import time
import pytest
from motor import db, worker, etapas
from motor.trabalhador import LimiteClaude


def _etapa(fn, recurso="cpu"):
    return dict(recurso=recurso, escopo="ep", sempre=True, rodar=fn)


@pytest.fixture
def etapas_falsas(monkeypatch, obra):
    def ok(ep, partes, params, log, c):
        return "feito"

    def servico(ep, partes, params, log, c):
        raise RuntimeError("o servidor de voz não respondeu em 4 min")

    def quebra(ep, partes, params, log, c):
        raise ValueError("bug de verdade")

    def limite(ep, partes, params, log, c):
        raise LimiteClaude("limite do plano do Claude", time.time() + 3600)

    novas = {"t_ok": _etapa(ok), "t_servico": _etapa(servico), "t_quebra": _etapa(quebra), "t_limite": _etapa(limite, "claude"),
             "t_claude2": _etapa(ok, "claude")}
    monkeypatch.setattr(etapas, "ETAPAS", {**etapas.ETAPAS, **novas})
    monkeypatch.setattr(worker, "ETAPAS", etapas.ETAPAS)
    monkeypatch.setattr(worker, "ocioso", lambda: None)
    monkeypatch.setattr(worker, "DRENAR_ESPERA_S", 0)
    monkeypatch.setattr(worker, "vigia_cancelamento", lambda: None)
    monkeypatch.setitem(worker.ESTADO, "eventos", [])
    monkeypatch.setitem(worker.ESTADO, "recurso", None)
    return obra


def _estado(c, jid):
    return dict(c.execute("SELECT * FROM job WHERE id=?", (jid,)).fetchone())


def test_erros_nao_derrubam_o_worker(banco, etapas_falsas):
    c = banco
    j_ok = db.enfileirar(c, "t_ok", "Obra_Teste", "01")
    j_serv = db.enfileirar(c, "t_servico", "Obra_Teste", "01")
    j_bug = db.enfileirar(c, "t_quebra", "Obra_Teste", "01")
    j_lim = db.enfileirar(c, "t_limite", "Obra_Teste", "01")
    j_cl2 = db.enfileirar(c, "t_claude2", "Obra_Teste", "01")
    j_fim = db.enfileirar(c, "t_ok", "Obra_Teste", "01")
    worker._laco(drenar=True, saida=lambda s: None)

    assert _estado(c, j_ok)["estado"] == "pronto"
    s = _estado(c, j_serv)                                   # serviço fora do ar: volta à fila em 1 min, conta tentativa
    assert s["estado"] == "na_fila" and s["tentativas"] == 1 and s["espera_ate"] > time.time()
    assert _estado(c, j_bug)["estado"] == "erro" and "bug de verdade" in _estado(c, j_bug)["erro"]
    lim = _estado(c, j_lim)                                  # limite do Claude: espera sem gastar tentativa
    assert lim["estado"] == "na_fila" and lim["tentativas"] == 0 and lim["espera_ate"] > time.time() + 3000
    assert _estado(c, j_cl2)["estado"] == "na_fila" and _estado(c, j_cl2)["espera_ate"] > time.time() + 3000   # os outros do Claude esperam junto
    assert _estado(c, j_fim)["estado"] == "pronto"           # e a fila seguiu depois de tudo isso
    tipos = {(e["tipo"], e["estado"]) for e in worker.ESTADO["eventos"]}
    assert ("t_quebra", "erro") in tipos and ("t_limite", "espera") in tipos and ("t_ok", "pronto") in tipos


def test_servico_desiste_na_terceira(banco, etapas_falsas):
    c = banco
    j = db.enfileirar(c, "t_servico", "Obra_Teste", "01")
    for _ in range(3):
        c.execute("UPDATE job SET espera_ate=NULL WHERE id=?", (j,))
        worker._laco(drenar=True, saida=lambda s: None)
    assert _estado(c, j)["estado"] == "erro"


def test_recuperar_depois_de_queda(banco):
    c = banco
    a = db.enfileirar(c, "voz", "X", "01")
    b = db.enfileirar(c, "voz", "X", "01")
    d = db.enfileirar(c, "voz", "X", "01")
    c.execute("UPDATE job SET estado='rodando' WHERE id IN (?,?)", (a, b))
    c.execute("UPDATE job SET tentativas=2 WHERE id=?", (b,))
    c.execute("UPDATE job SET estado='cancelando' WHERE id=?", (d,))
    assert db.recuperar(c) == 1
    assert _estado(c, a)["estado"] == "na_fila" and _estado(c, a)["tentativas"] == 1
    assert _estado(c, b)["estado"] == "erro"               # 3ª queda no mesmo job: para de derrubar o motor
    assert _estado(c, d)["estado"] == "cancelado"


def test_proximo_respeita_espera(banco):
    c = banco
    a = db.enfileirar(c, "voz", "X", "01")
    db.enfileirar(c, "voz", "X", "01")
    db.adiar(c, a, 600, "teste")
    assert db.proximo(c)["id"] != a


def test_quando_volta():
    import datetime as dt
    from motor.trabalhador import quando_volta
    base = dt.datetime(2026, 11, 6, 15, 0).timestamp()
    h = lambda m: dt.datetime.fromtimestamp(quando_volta(m, base)).strftime("%d %H:%M")
    assert h("You've hit your session limit · resets 5:40pm (America/Sao_Paulo)") == "06 17:42"
    assert h("resets 1am") == "07 01:02"
    assert h("usage limit · resets Nov 9, 3pm") == "09 15:02"
    assert h("hit your limit") == "06 15:30"


def test_json_atomico_e_trava(tmp_path):
    import threading
    from motor.obra import atualizar_json, ler_json
    arq = tmp_path / "p.json"

    def soma(d):
        d["n"] = d.get("n", 0) + 1
    ts = [threading.Thread(target=lambda: [atualizar_json(arq, soma) for _ in range(25)]) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert ler_json(arq)["n"] == 200                        # nenhuma mudança perdida com 8 threads
    assert not list(tmp_path.glob(".*.tmp"))
