# Banco do Origami (SQLite em WAL): fila de jobs, artefatos (para a propagação incremental) e cache de hashes.
# É índice e fila; o conteúdo continua nos arquivos da obra (roteiro, gravacao.json, wavs, mp4).
import json, sqlite3, time
from .config import DB

ESQUEMA = """
CREATE TABLE IF NOT EXISTS job(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL, obra TEXT NOT NULL, ep TEXT NOT NULL, parte INTEGER,
  params TEXT DEFAULT '{}', prioridade INTEGER DEFAULT 0, lote TEXT,
  estado TEXT NOT NULL DEFAULT 'na_fila',          -- na_fila | rodando | pronto | pulado | erro | cancelado
  criado REAL, inicio REAL, fim REAL, resumo TEXT, erro TEXT, log TEXT);
CREATE INDEX IF NOT EXISTS job_estado ON job(estado, prioridade, id);
CREATE TABLE IF NOT EXISTS artefato(
  chave TEXT PRIMARY KEY, assinatura TEXT, entradas TEXT, gerado REAL, job INTEGER);
CREATE TABLE IF NOT EXISTS hash_arquivo(
  caminho TEXT PRIMARY KEY, mtime_ns INTEGER, tamanho INTEGER, sha1 TEXT);
CREATE TABLE IF NOT EXISTS marca(            -- revisão: o autor marca um ponto do áudio ou do vídeo
  id INTEGER PRIMARY KEY AUTOINCREMENT, obra TEXT, ep TEXT, parte INTEGER, t_seg REAL, midia TEXT,
  nota TEXT, fala TEXT, classe TEXT, resolvida INTEGER DEFAULT 0, criada REAL);
CREATE TABLE IF NOT EXISTS consumo(
  id INTEGER PRIMARY KEY AUTOINCREMENT, quando REAL, obra TEXT, ep TEXT, tarefa TEXT, modelo TEXT,
  entrada INTEGER, saida INTEGER, cache_leitura INTEGER, segundos REAL);
"""


_PRONTO = {"esquema": False}
MAX_TENTATIVAS = 3          # um job que derruba o motor (ou falha por serviço fora do ar) volta à fila até 3 vezes


def _migrar(c):
    """Colunas novas: tentativas (contador de quedas/retomadas) e espera_ate (job adiado: limite do Claude,
    serviço reiniciando). Bancos antigos ganham as colunas sem perder nada."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(job)")}
    if "tentativas" not in cols:
        c.execute("ALTER TABLE job ADD COLUMN tentativas INTEGER DEFAULT 0")
    if "espera_ate" not in cols:
        c.execute("ALTER TABLE job ADD COLUMN espera_ate REAL")


def conectar():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=30, isolation_level=None, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    if not _PRONTO["esquema"]:          # o esquema roda uma vez por processo
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(ESQUEMA)
        _migrar(c)
        _PRONTO["esquema"] = True
    return c


def enfileirar(c, tipo, obra, ep, parte=None, params=None, prioridade=0, lote=None):
    cur = c.execute("INSERT INTO job(tipo,obra,ep,parte,params,prioridade,lote,criado) VALUES(?,?,?,?,?,?,?,?)",
                    (tipo, obra, ep, parte, json.dumps(params or {}, ensure_ascii=False), prioridade, lote, time.time()))
    return cur.lastrowid


def proximo(c):
    """Pega o próximo job da fila (prioridade maior primeiro; depois a ordem de chegada) e o marca como rodando."""
    c.execute("BEGIN IMMEDIATE")
    try:
        j = c.execute("SELECT * FROM job WHERE estado='na_fila' AND (espera_ate IS NULL OR espera_ate <= ?) "
                      "ORDER BY prioridade DESC, id LIMIT 1", (time.time(),)).fetchone()
        if j:
            c.execute("UPDATE job SET estado='rodando', inicio=? WHERE id=?", (time.time(), j["id"]))
        c.execute("COMMIT")
        return j
    except Exception:
        c.execute("ROLLBACK")
        raise


def terminar(c, jid, estado, resumo=None, erro=None, log=None):
    c.execute("UPDATE job SET estado=?, fim=?, resumo=?, erro=?, log=? WHERE id=?",
              (estado, time.time(), resumo, erro, log, jid))


def recuperar(c):
    """Depois de uma queda, o que estava rodando volta para a fila, contando a tentativa: um job que derruba o motor
    toda vez para em "erro" na 3ª, em vez de derrubá-lo para sempre. Pedido de cancelamento órfão vira cancelado."""
    c.execute("UPDATE job SET estado='cancelado', fim=?, erro='cancelado pelo autor' WHERE estado='cancelando'", (time.time(),))
    c.execute("UPDATE job SET estado='erro', fim=?, erro='o motor parou 3 vezes durante este job (ver o log)' "
              "WHERE estado='rodando' AND COALESCE(tentativas,0) + 1 >= ?", (time.time(), MAX_TENTATIVAS))
    return c.execute("UPDATE job SET estado='na_fila', inicio=NULL, tentativas=COALESCE(tentativas,0)+1 WHERE estado='rodando'").rowcount


def adiar(c, jid, segundos, motivo, contar=True):
    """Devolve o job à fila para tentar de novo depois (serviço fora do ar, limite do Claude)."""
    c.execute("UPDATE job SET estado='na_fila', inicio=NULL, espera_ate=?, erro=?, tentativas=COALESCE(tentativas,0)+? WHERE id=?",
              (time.time() + segundos, motivo, 1 if contar else 0, jid))


def artefato(c, chave):
    return c.execute("SELECT * FROM artefato WHERE chave=?", (chave,)).fetchone()


def gravar_artefato(c, chave, assinatura, entradas, jid):
    c.execute("INSERT OR REPLACE INTO artefato(chave,assinatura,entradas,gerado,job) VALUES(?,?,?,?,?)",
              (chave, assinatura, json.dumps(entradas, ensure_ascii=False), time.time(), jid))
