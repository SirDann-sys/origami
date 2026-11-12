# Piloto automático: anda sozinho, nunca passa um portão do autor, não insiste em erro, não refaz por código novo.
import json, time
import pytest
from motor import db, piloto
from motor.obra import Episodio, ler_json, gravar_json


def _cfg(raiz, **ep01):
    arq = raiz / "projeto.json"
    c = json.loads(arq.read_text(encoding="utf-8"))
    c["episodios"]["01"].update(ep01)
    arq.write_text(json.dumps(c), encoding="utf-8")


def _fila(c):
    return [(r["tipo"], json.loads(r["params"] or "{}")) for r in c.execute("SELECT tipo, params FROM job WHERE estado='na_fila' ORDER BY id")]


def _limpa(c):
    c.execute("UPDATE job SET estado='pronto' WHERE estado='na_fila'")


@pytest.fixture
def ep(obra):
    _cfg(obra, piloto=True)
    return Episodio("Obra_Teste", "01")


def test_escreve_o_mestre_e_para_na_aprovacao(banco, ep):
    c = banco
    (ep.roteiro_arq).unlink()
    assert piloto.passo(ep, c) == "escrevendo o texto-mestre"
    assert _fila(c)[0][0] == "mestre"
    _limpa(c)
    ep.mestre.parent.mkdir(parents=True, exist_ok=True)
    ep.mestre.write_text("# Ep\n---\nTexto.\n", encoding="utf-8")
    assert piloto.passo(ep, c) is None                       # portão: o autor aprova o mestre
    assert any(p["id"] == "mestre" for p in piloto.pendencias("Obra_Teste", "01", c))


def test_decisao_pendente_bloqueia(banco, ep):
    c = banco
    gravar_json(ep.raiz / "01_biblia" / "decisoes.json", {"regras": [], "itens": [
        {"id": "I-01", "eps": ["01"], "estado": "pendente", "titulo": "x", "tipo": "inconsistencia", "opcoes": ["a"]}]})
    assert piloto.passo(ep, c) is None
    assert piloto.pendencias("Obra_Teste", "01", c)[0]["id"] == "decisoes"


def test_corrige_alerta_critico_uma_vez(banco, ep):
    c = banco
    ep.mestre.parent.mkdir(parents=True, exist_ok=True)
    ep.mestre.write_text("# Ep\n---\nTexto.\n", encoding="utf-8")
    gravar_json(ep.mestre.parent / "ep01_alarme.json", {"alertas": [{"id": 1, "gravidade": "critico", "estado": "aberto"}]})
    assert piloto.passo(ep, c) == "corrigindo os alertas críticos do texto"
    _limpa(c)
    assert piloto.passo(ep, c) is None                       # a mesma versão do texto não é corrigida duas vezes


def test_erro_vira_pendencia_e_nao_repete(banco, ep):
    c = banco
    ep.roteiro_arq.unlink()
    jid = db.enfileirar(c, "mestre", "Obra_Teste", "01")
    db.terminar(c, jid, "erro", erro="falhou")
    assert piloto.passo(ep, c) is None
    assert any(p["id"] == "erro_mestre" for p in piloto.pendencias("Obra_Teste", "01", c))


def test_audio_antes_de_tudo_e_portao_do_audio(banco, ep, monkeypatch):
    c = banco
    ep.mestre.parent.mkdir(parents=True, exist_ok=True)
    ep.mestre.write_text("# Ep\n---\nTexto.\n", encoding="utf-8")
    _cfg(ep.raiz, piloto=True, mestre_aprovado=True)
    gravar_json(ep.publicacao / "kit.json", {})
    gravar_json(ep.plano_cues, {"partes": []})
    feito = piloto.passo(ep, c)
    assert feito == "produzindo o áudio"
    tipos = [t for t, _ in _fila(c)]
    assert tipos[0] == "sincronizar" and tipos[-1] == "episodio" and "video" not in tipos and "tempos" not in tipos


def test_voz_sem_elenco_bloqueia_o_audio(banco, ep):
    c = banco
    ep.mestre.parent.mkdir(parents=True, exist_ok=True)
    ep.mestre.write_text("# Ep\n---\nTexto.\n", encoding="utf-8")
    _cfg(ep.raiz, piloto=True, mestre_aprovado=True)
    cfg = json.loads(ep.projeto.read_text(encoding="utf-8")); cfg["elenco"] = {}; ep.projeto.write_text(json.dumps(cfg), encoding="utf-8")
    gravar_json(ep.publicacao / "kit.json", {})
    gravar_json(ep.plano_cues, {"partes": []})
    feito = piloto.passo(ep, c)
    assert feito != "produzindo o áudio"
    assert any(p["id"] == "elenco" for p in piloto.pendencias("Obra_Teste", "01", c))


def test_nao_age_com_fila_ocupada(banco, ep):
    c = banco
    db.enfileirar(c, "kit", "Obra_Teste", "01")
    assert piloto.avancar(c) is None


def test_prazo_da_pre_escolhida(banco, ep):
    from motor import triagem
    gravar_json(ep.assets, {"itens": [{"id": "fundo_a", "pre_escolhida": "fundo_a_s1.png", "prazo_escolha": time.time() - 1},
                                      {"id": "fundo_b", "pre_escolhida": "fundo_b_s1.png", "prazo_escolha": time.time() + 999}]})
    assert triagem.aplicar_prazos(ep, "imagens") == ["fundo_a"]
    its = {x["id"]: x for x in ler_json(ep.assets)["itens"]}
    assert its["fundo_a"]["escolhida"] == "fundo_a_s1.png" and its["fundo_a"]["escolha_auto"]
    assert "escolhida" not in its["fundo_b"]


def test_desce_sugerido():
    from motor.triagem import desce_sugerido
    assert desce_sugerido({"assunto_y": [0.6, 1]}) == 0          # já está abaixo do título
    assert desce_sugerido({"assunto_y": [0.2, 0.8]}) == 380      # sobe até y=384: desce até 760
    assert desce_sugerido({"assunto_y": [0.0, 1]}) == 600         # limite


def test_volta_tokens():
    from motor.triagem import _volta_tokens
    assert _volta_tokens("A young woman with long blonde hair at the desk", "{ana@trabalho} at the desk") == "{ana@trabalho} at the desk"
    assert _volta_tokens("Close-up of one white cup on a dry sink, one warm lamp", "{lia@fora} by the sink") == "Close-up of one white cup on a dry sink, one warm lamp"
    assert _volta_tokens("{ana@trabalho}, exactly two cups", "{ana@trabalho} at the desk").startswith("{ana")


def test_freio_de_acao_repetida(banco, ep, monkeypatch):
    c = banco
    monkeypatch.setattr(piloto, "REPETE", {}); monkeypatch.setattr(piloto, "TRAVADOS", {})
    for _ in range(4):
        assert not piloto._repetindo("Obra_Teste", "01", "produzindo o áudio", c)
    db.enfileirar(c, "voz", "Obra_Teste", "01", lote="Obra_Teste|01|piloto")
    assert piloto._repetindo("Obra_Teste", "01", "produzindo o áudio", c)        # 5ª igual em 30 min: freia
    assert ("Obra_Teste", "01") in piloto.TRAVADOS
    assert c.execute("SELECT estado FROM job").fetchone()[0] == "cancelado"
    assert any(p["id"] == "travado" for p in piloto.pendencias("Obra_Teste", "01", c))
    piloto.ligar("Obra_Teste", "01", True)                                        # religar destrava
    assert ("Obra_Teste", "01") not in piloto.TRAVADOS


def test_nivel_preservar_nao_reescreve(obra):
    from motor import texto
    (obra / "00_fonte").mkdir(exist_ok=True)
    (obra / "00_fonte" / "texto_limpo.txt").write_text("# Obra\n## Capítulo 1 — Começo\nEu cheguei tarde.\n\n— Você demorou — ele disse.\n", encoding="utf-8")
    (obra / "01_biblia" / "guia_completo.md").write_text("## Ep. 01 · Começo (L1–5)\n- tudo\n", encoding="utf-8")
    cfg = json.loads((obra / "projeto.json").read_text(encoding="utf-8")); cfg["tipo"] = "organico"
    (obra / "projeto.json").write_text(json.dumps(cfg), encoding="utf-8")
    ep = Episodio("Obra_Teste", "01")
    assert texto.nivel_ia(ep) == "preservar"
    r, _ = texto._mestre_preservado(ep)
    assert "Eu cheguei tarde." in r["mestre_md"] and "— Você demorou — ele disse." in r["mestre_md"]
    assert "## Capítulo 1 — Começo" in r["mestre_md"] and r["inventados"] == [] and r["palavras"] == 7
