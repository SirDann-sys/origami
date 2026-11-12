# Testes do Origami. Rodar de dentro da pasta do app:
#   ambientes\qwen\Scripts\python.exe -m pytest testes -q
# Nada aqui mexe nas obras reais: o banco é temporário e as obras de teste são criadas em pastas temporárias.
import sys
from pathlib import Path
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Banco do motor num arquivo temporário (o dados/origami.db real nunca é tocado)."""
    from motor import db, worker
    monkeypatch.setattr(db, "DB", tmp_path / "teste.db")
    monkeypatch.setattr(db, "_PRONTO", {"esquema": False})
    monkeypatch.setattr(worker, "LOGS", tmp_path / "logs")
    (tmp_path / "logs").mkdir()
    c = db.conectar()
    yield c
    c.close()


@pytest.fixture
def obra(tmp_path, monkeypatch):
    """Uma obra mínima numa pasta temporária (projeto.json + roteiro de 2 partes), com PROJETOS apontando para lá."""
    import json
    from motor import config, obra as obra_mod, mesa
    proj = tmp_path / "obras"
    raiz = proj / "Obra_Teste"
    (raiz / "04_roteiro_audio").mkdir(parents=True)
    (raiz / "01_biblia").mkdir()
    cfg = {"titulo": "Obra Teste", "sigla": "OT", "marca": "recursos/marca/padrao/marca.json",
           "elenco": {"narradora": "voz_x"}, "episodios": {"01": {"titulo": "Começo"}}}
    (raiz / "projeto.json").write_text(json.dumps(cfg), encoding="utf-8")
    rot = {"partes": [{"parte": 1, "falas": [{"voz": "narradora", "texto": "Olá."}]},
                      {"parte": 2, "falas": [{"voz": "narradora", "texto": "Tchau."}]}]}
    (raiz / "04_roteiro_audio" / "ep01.json").write_text(json.dumps(rot), encoding="utf-8")
    (raiz / "01_biblia" / "decisoes.json").write_text(json.dumps({"regras": [], "itens": []}), encoding="utf-8")
    for m in (config, obra_mod, mesa):
        monkeypatch.setattr(m, "PROJETOS", proj, raising=False)
    monkeypatch.setattr(config, "LOGS", tmp_path / "logs_obra")       # nada de teste no log real (piloto.log)
    return raiz
