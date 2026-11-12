# O Claude como "trabalhador sem memória": cada tarefa é UMA chamada
# `claude -p` com contexto mínimo, saída JSON validada por schema e consumo registrado em <obra>/custo.jsonl.
# Texto da obra é sempre Opus (qualidade primeiro).
import json, os, subprocess, time
from pathlib import Path
from .config import ORIGAMI, PROJETOS

TAREFAS = ORIGAMI / "trabalhador"
# pasta de trabalho FORA do projeto: nenhum CLAUDE.md do repositório entra no contexto da tarefa
CWD = Path(os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", "."))) / "Origami" / "trabalhador"


class LimiteClaude(Exception):
    """O plano do Claude bateu o limite da sessão/semana. `ate` = quando volta (epoch). O worker adia os jobs do Claude
    até lá e segue com o resto da fila (mensagem do tipo "You've hit your session limit · resets 5:40pm")."""
    def __init__(self, msg, ate):
        super().__init__(msg)
        self.ate = ate


def exe_claude():
    import shutil
    for c in (Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe",
              Path.home() / ".local" / "bin" / "claude.exe"):          # instalação pelo npm ou pelo instalador nativo
        if c.exists():
            return str(c)
    return shutil.which("claude") or "claude"


def quando_volta(msg, agora=None):
    """'… resets 5:40pm (America/Sao_Paulo)' / 'resets 17:40' / 'resets Nov 9, 3pm' → epoch local (+2 min de folga).
    Sem horário legível: 30 min."""
    import re, datetime as dt
    agora = agora or time.time()
    m = re.search(r"resets\s+(?:[A-Za-z]{3}\s+\d{1,2},?\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", msg, re.I)
    if not m:
        return agora + 30 * 60
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    base = dt.datetime.fromtimestamp(agora)
    alvo = base.replace(hour=h % 24, minute=mi, second=0, microsecond=0)
    dia = re.search(r"resets\s+([A-Za-z]{3})\s+(\d{1,2})", msg)
    if dia:
        meses = "jan feb mar apr may jun jul aug sep oct nov dec".split()
        if dia.group(1).lower() in meses:
            alvo = alvo.replace(month=meses.index(dia.group(1).lower()) + 1, day=int(dia.group(2)))
            if alvo.timestamp() < agora - 86400:
                alvo = alvo.replace(year=alvo.year + 1)
    while alvo.timestamp() <= agora:
        alvo += dt.timedelta(days=1)
    return alvo.timestamp() + 120


def _erro_claude(txt):
    """Traduz o erro do Claude: limite → LimiteClaude (o job espera); login → mensagem clara (o autor precisa agir)."""
    import re
    if re.search(r"hit your .*limit|usage limit|rate limit|limit reached|resets \d", txt, re.I):
        raise LimiteClaude("limite do plano do Claude: " + txt[:160], quando_volta(txt))
    if re.search(r"not logged in|please run /login|invalid api key|authentication|oauth token", txt, re.I):
        raise RuntimeError("o Claude não está conectado nesta máquina: abra o Terminal e rode  claude auth login  (depois reenvie o job)")
    raise RuntimeError("Claude: " + txt[:400])


def conectado():
    """{"ok": bool, "motivo": str} pelo 'claude auth status' (rápido, sem gastar crédito)."""
    try:
        p = subprocess.run([exe_claude(), "auth", "status", "--json"], capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        d = json.loads(p.stdout or "{}")
        return {"ok": bool(d.get("loggedIn")), "motivo": "" if d.get("loggedIn") else "o Claude não está conectado (claude auth login)",
                "plano": d.get("subscriptionType")}
    except FileNotFoundError:
        return {"ok": False, "motivo": "o Claude Code não está instalado nesta máquina"}
    except Exception as ex:
        return {"ok": False, "motivo": f"não consegui conferir o Claude: {ex}"}


def rodar(tarefa, entrada, obra, modelo="opus", limite_min=20, log=None, ep=None):
    """Roda trabalhador/<tarefa>.md com a entrada (JSON) e devolve o JSON do schema <tarefa>.schema.json."""
    from .etapas import PROC_ATUAL, Cancelado
    CWD.mkdir(parents=True, exist_ok=True)
    schema = json.loads((TAREFAS / f"{tarefa}.schema.json").read_text(encoding="utf-8"))
    args = [exe_claude(), "-p", "--model", modelo, "--output-format", "json", "--no-session-persistence",
            "--strict-mcp-config", "--tools", "Read", "--allowedTools", "Read", "--add-dir", str(PROJETOS / obra),
            "--system-prompt-file", str(TAREFAS / f"{tarefa}.md"), "--json-schema", json.dumps(schema, ensure_ascii=False)]
    texto = "Dados da tarefa (JSON):\n" + json.dumps(entrada, ensure_ascii=False, indent=1)
    t0 = time.time()
    if log:
        log.write(f"\n[claude -p {tarefa} · {modelo}] entrada {len(texto)} caracteres\n"); log.flush()
    # Popen registrado: o botão Cancelar da Fila para também os jobs do Claude
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", cwd=CWD, env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    import threading
    do_worker = threading.get_ident() == PROC_ATUAL.get("thread")   # chamado pela interface (ex.: sugerir frases) não registra
    if do_worker:
        PROC_ATUAL["p"] = p
    try:
        saida, err = p.communicate(texto, timeout=limite_min * 60)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        p.communicate()
        raise RuntimeError(f"o Claude não respondeu em {limite_min} min na tarefa '{tarefa}' (tente de novo)")
    finally:
        if do_worker:
            PROC_ATUAL["p"] = None
    if getattr(p, "_cancelado", False):
        raise Cancelado()
    if p.returncode != 0 and not saida.strip():
        _erro_claude(err or f"saiu com código {p.returncode}")
    try:
        r = json.loads(saida)
    except json.JSONDecodeError:
        _erro_claude(saida[:400])
    u = r.get("usage", {})
    reg = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "tarefa": tarefa, "ep": ep, "modelo": next(iter(r.get("modelUsage", {}) or {}), modelo),
           "entrada": sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
           "saida": u.get("output_tokens", 0), "custo_usd": r.get("total_cost_usd", 0), "segundos": round(time.time() - t0)}
    with open(PROJETOS / obra / "custo.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    if log:
        log.write(f"[claude] {reg}\n"); log.flush()
    if r.get("is_error"):
        _erro_claude(str(r.get("result") or r.get("subtype")))
    dados = r.get("structured_output")
    if dados is None:
        try:
            dados = json.loads(r.get("result", ""))
        except (json.JSONDecodeError, TypeError):
            raise RuntimeError("Claude não devolveu o JSON pedido: " + str(r.get("result"))[:300])
    return dados, reg
