// Origami · Fila e custo. O que o motor fez, faz e vai fazer (com erro legível, log, cancelar e pausar)
// e quanto custou: dólares do Opus por tarefa e episódio, horas de máquina por tipo de etapa.
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const F = { obra: null, timer: null };
  const ESTADOS = { na_fila: 'na fila', rodando: 'rodando', pronto: 'pronto', pulado: 'nada mudou', erro: 'ERRO', cancelado: 'cancelado', cancelando: 'cancelando' };
  async function api(caminho, corpo) {
    const r = await fetch(caminho, corpo ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo ?? {}) } : (corpo === null ? { method: 'POST' } : {}));
    const j = await r.json();
    if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    return j;
  }
  function aviso(txt, info) {
    const d = document.createElement('div'); d.className = 'aviso' + (info ? ' info' : ''); d.textContent = txt;
    $('#avisos').appendChild(d); setTimeout(() => d.remove(), info ? 3000 : 9000);
  }
  const dur = (s) => s == null ? '' : s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}min ${s % 60}s` : `${(s / 3600).toFixed(1)}h`;
  const quando = (t) => t ? new Date(t * 1000).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';

  async function carregar() {
    let f, e;
    try { [f, e] = await Promise.all([api(`/api/fila?obra=${encodeURIComponent(F.obra)}`), api('/estado')]); }
    catch (er) { $('#fl-estado').innerHTML = `<span style="color:var(--erro)">Não consegui ler a fila: ${esc(er.message)}</span>`; return; }
    $('#fl-estado').innerHTML = `${e.pausado ? '<b style="color:var(--aviso)">PAUSADO</b>' : '<b style="color:var(--ok)">trabalhando normalmente</b>'}
      · ${f.contagem.rodando} rodando · ${f.contagem.na_fila} na fila ${f.contagem.erro ? `· <span style="color:var(--erro)">${f.contagem.erro} com erro</span>` : ''}
      <button id="fl-pausa">${e.pausado ? 'Retomar' : 'Pausar a fila'}</button>`;
    $('#fl-pausa').onclick = async () => { try { await api(e.pausado ? '/retomar' : '/pausar', {}); carregar(); } catch (er) { aviso(er.message); } };
    $('#fl-jobs').innerHTML = `<tr><th>#</th><th>etapa</th><th>ep.</th><th>estado</th><th>tempo</th><th>resultado</th><th></th></tr>` + f.jobs.map((j) => `
      <tr class="fl-${j.estado}"><td>${j.id}</td><td>${esc(j.nome)}${j.parte ? ` · P${j.parte}` : ''}</td><td>${esc(j.ep)}</td>
        <td>${ESTADOS[j.estado] || esc(j.estado)}<div class="ctx">${quando(j.criado)}</div></td><td>${dur(j.duracao)}</td>
        <td class="fl-res">${esc(j.erro || j.resumo || '')}${j.espera_ate && j.estado === 'na_fila' && j.espera_ate * 1000 > Date.now() ? `<div class="ctx">volta sozinho às ${new Date(j.espera_ate * 1000).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</div>` : ''}</td>
        <td>${j.tem_log ? `<button data-log="${j.id}">log</button>` : ''}${['na_fila', 'rodando'].includes(j.estado) ? ` <button data-cancel="${j.id}">cancelar</button>` : ''}${j.estado === 'erro' ? ` <button data-reenviar="${j.id}" title="Enfileira de novo com os mesmos parâmetros (depois de corrigir a causa)">tentar de novo</button>` : ''}</td></tr>`).join('');
    $('#fl-jobs').querySelectorAll('[data-reenviar]').forEach((b) => b.onclick = async () => {
      try { const r = await api('/api/reenviar', { id: +b.dataset.reenviar }); aviso(`de novo na fila (job ${r.job})`, true); carregar(); } catch (er) { aviso(er.message); }
    });
    $('#fl-jobs').querySelectorAll('[data-log]').forEach((b) => b.onclick = async () => {
      try { const l = await api(`/api/log?id=${b.dataset.log}`); $('#fl-log').innerHTML = `<h3>Log do trabalho #${b.dataset.log}</h3><pre>${esc(l.texto)}</pre>`; } catch (er) { aviso(er.message); }
    });
    $('#fl-jobs').querySelectorAll('[data-cancel]').forEach((b) => b.onclick = async () => {
      try { const r = await api(`/cancelar/${b.dataset.cancel}`, {}); aviso(r.ok ? 'cancelado' : 'não deu para cancelar', !!r.ok); carregar(); } catch (er) { aviso(er.message); }
    });
    try {
      const c = await api(`/api/custo?obra=${encodeURIComponent(F.obra)}`);
      const linhas = (o, fmt) => Object.entries(o).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${fmt(v)}</td></tr>`).join('') || '<tr><td class="ctx">—</td></tr>';
      $('#fl-custo').innerHTML = `
        <div class="campo"><b>Opus (texto): US$ ${c.ia_total_usd.toFixed(2)}</b></div>
        <h3>Por episódio</h3><table class="reg">${linhas(c.ia_por_ep, (v) => `US$ ${v.toFixed(2)}`)}</table>
        <h3>Por tarefa</h3><table class="reg">${linhas(c.ia, (v) => `US$ ${v.usd.toFixed(2)} · ${v.chamadas}× · ${(v.entrada / 1000).toFixed(0)}k tokens lidos`)}</table>
        <h3>Máquina (horas de trabalho do motor)</h3><table class="reg">${linhas(c.maquina_h, (v) => `${v} h`)}</table>
        <h3>Máquina por episódio</h3><table class="reg">${linhas(c.maquina_por_ep_h, (v) => `${v} h`)}</table>`;
    } catch (er) { $('#fl-custo').innerHTML = esc(er.message); }
  }
  window.Fila = {
    abrir(obra) {
      F.obra = obra; carregar();
      clearInterval(F.timer);
      F.timer = setInterval(() => { if ($('#fila').classList.contains('on')) carregar(); }, 4000);
    },
  };
})();
