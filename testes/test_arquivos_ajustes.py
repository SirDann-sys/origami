# Arquivos (mover só o aprovado, desfazer, hardlink sem duplicar) · ajustes (trilha, título, trechos) · postado único.
import json, os
import pytest
from motor import arquivos, ajustes, publicacao, postagem, config
from motor.obra import Episodio, ler_json, gravar_json


@pytest.fixture
def raiz(obra, tmp_path, monkeypatch):
    """Obra de teste com uma entrega antiga, um rascunho solto, uma pasta vazia fora do padrão e a pasta ouvir/."""
    monkeypatch.setattr(arquivos, "RAIZ", tmp_path)
    monkeypatch.setattr(arquivos, "PROJETOS", tmp_path / "obras")
    monkeypatch.setattr(arquivos, "ARQUIVO", tmp_path / "_arquivo")
    monkeypatch.setattr(arquivos, "LOG", tmp_path / "dados" / "arquivos_log.json")
    pub = obra / "07_publicacao" / "ep01"
    (pub / "entrega").mkdir(parents=True)
    (pub / "entrega" / "RA_Ep01_Parte01_9x16.mp4").write_bytes(b"video" * 100)
    (pub / "KIT_ANTIGO.txt").write_text("velho", encoding="utf-8")
    (pub / "kit.json").write_text("{}", encoding="utf-8")
    (obra / "lixo_vazio").mkdir()
    (tmp_path / "ouvir" / "20_grande").mkdir(parents=True)
    with open(tmp_path / "ouvir" / "20_grande" / "v.mp4", "wb") as f:
        f.truncate(arquivos.OUVIR_GRANDE + 1)
    return tmp_path


def test_inventario_e_mover_e_desfazer(raiz, obra):
    inv = {i["id"]: i for i in arquivos.inventario()["itens"]}
    pub = next(i for i in inv.values() if i["tipo"] == "publicar")
    assert pub["destino"].endswith(os.path.join("PUBLICAR", "Ep01"))
    assert any(i["rel"].endswith("KIT_ANTIGO.txt") and i["tipo"] == "arquivar" for i in inv.values())
    assert not any(i["rel"].endswith("kit.json") for i in inv.values())                 # protegido: o motor usa
    assert any(i["rel"].endswith("lixo_vazio") and i["tipo"] == "remover" for i in inv.values())
    assert not any(i["rel"].endswith("04_roteiro_audio") for i in inv.values())         # pasta padrão fica, mesmo vazia
    r = arquivos.mover([pub["id"]])                                                      # SÓ o aprovado
    assert r["movidos"] == 1 and (obra / "PUBLICAR" / "Ep01" / "RA_Ep01_Parte01_9x16.mp4").exists()
    assert (obra / "07_publicacao" / "ep01" / "KIT_ANTIGO.txt").exists()                # o resto não mexe
    assert Episodio("Obra_Teste", "01").entrega == obra / "PUBLICAR" / "Ep01"
    arquivos.desfazer(r["lote"])
    assert (obra / "07_publicacao" / "ep01" / "entrega" / "RA_Ep01_Parte01_9x16.mp4").exists()


def test_vincular_nao_duplica(tmp_path):
    a = tmp_path / "a.bin"; a.write_bytes(b"x" * 1000)
    b = tmp_path / "pub" / "b.bin"
    assert arquivos.vincular(a, b) == "link"
    assert os.path.samefile(a, b)


def test_trilha_titulo_segmentos(obra):
    ep = Episodio("Obra_Teste", "01")
    gravar_json(ep.plano_cues, {"partes": [{"parte": 1, "humor": "A", "final": "suspensao"}]})
    ajustes.salvar_trilha("Obra_Teste", "01", 1, "C", "brilho")
    assert ler_json(ep.plano_cues)["partes"][0] == {"parte": 1, "humor": "C", "final": "brilho"}
    with pytest.raises(RuntimeError):
        ajustes.salvar_trilha("Obra_Teste", "01", 1, "inventado", "brilho")
    ajustes.salvar_titulo("Obra_Teste", "01", "  O Sótão ")
    assert ep.titulo_ep() == "O Sótão"
    gravar_json(ep.plano_video, {"partes": {"1": [[1, "fundo_a", "casa"]]}, "retratos": {"narradora": {"casa": "r"}}, "narrador": "narradora"})
    with pytest.raises(RuntimeError):
        ajustes.salvar_segmentos("Obra_Teste", "01", 1, [{"fala": 2, "fundo": "fundo_b"}])  # tem de começar na fala 1
    ajustes.salvar_segmentos("Obra_Teste", "01", 1, [{"fala": 1, "fundo": "fundo_b", "figurino": "casa"}])
    assert ler_json(ep.plano_video)["partes"]["1"] == [[1, "fundo_b", "casa"]]


def test_postado_num_lugar_aparece_no_outro(obra, monkeypatch):
    monkeypatch.setattr(postagem, "PROJETOS", obra.parent)
    d = postagem.ler("Obra_Teste")
    d["itens"] = [postagem._item("2026-11-10", "19:00", "01", "parte:1", "tiktok")]
    postagem.gravar("Obra_Teste", d)
    publicacao.registrar("Obra_Teste", "01", "TikTok", "parte 1", "https://x")
    assert postagem.ler("Obra_Teste")["itens"][0]["estado"] == "feito_manual"
    postagem.marcar("Obra_Teste", d["itens"][0]["id"], "planejado")
    assert not ler_json(obra / "07_publicacao" / "ep01" / "postagens.json")["postagens"]
