// Origami · Arquivos. Inventário do que existe e para onde iria; NADA se move sem você marcar e confirmar.
// O que é final vai para <obra>\PUBLICAR\EpNN; rascunhos, pilotos e cópias velhas para _arquivo (nunca apagados).
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  async function api(caminho, corpo) {
    const r = await fetch(caminho, corpo ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) } : {});
    const j = await r.json();
    if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    return j;
  }
  const tam = (b) => b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : b >= 1e6 ? `${(b / 1e6).toFixed(0)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`;
  const ROT = { publicar: 'vai para PUBLICAR', mover: 'vai para PUBLICAR', arquivar: 'vai para _arquivo', remover: 'pasta vazia: remover' };
  const D = { d: null };

  function total() {
    const marcados = [...document.querySelectorAll('#aq-tab input:checked')].map((x) => D.d.itens.find((i) => i.id === x.value));
    $('#aq-total').textContent = marcados.length ? `${marcados.length} item(ns) · ${tam(marcados.reduce((s, i) => s + i.tamanho, 0))}` : 'nada marcado';
    $('#aq-mover').disabled = !marcados.length;
  }

  function desenhar() {
    const d = D.d;
    $('#aq-lista').innerHTML = `
      <p class="ctx">Marque o que pode mudar de lugar. As peças finais de cada episódio passam a morar em <b>PUBLICAR</b>; o resto vai para
        <b>_arquivo</b> (nada é apagado; dá para desfazer). A entrega deixa de duplicar os vídeos: a pasta PUBLICAR usa o mesmo arquivo do motor.</p>
      <table class="reg" id="aq-tab"><tr><th></th><th>o que é</th><th>onde está</th><th>tamanho</th><th>destino</th></tr>
      ${d.itens.map((i) => `<tr><td><input type="checkbox" value="${esc(i.id)}" ${i.marcado ? 'checked' : ''}></td>
        <td>${esc(i.descricao)}<div class="ctx">${ROT[i.tipo] || i.tipo}</div></td><td><code>${esc(i.rel)}</code></td><td>${tam(i.tamanho)}</td>
        <td><code>${esc(i.destino.replace(/^.*?Origami[\\/]/, ''))}</code></td></tr>`).join('') || '<tr><td colspan="5" class="ctx">Tudo organizado.</td></tr>'}</table>
      <div class="acoes"><span id="aq-total" class="ctx"></span><button id="aq-mover" class="primario">Mover os marcados</button></div>
      ${d.historico.length ? `<h3>Movimentos feitos</h3><ul>${d.historico.slice().reverse().map((h) => `<li>${esc(h.em)} · ${h.n} item(ns)
        <button data-lote="${esc(h.lote)}">Desfazer</button></li>`).join('')}</ul>` : ''}`;
    document.querySelectorAll('#aq-tab input').forEach((x) => x.onchange = total);
    total();
    $('#aq-mover').onclick = async () => {
      const ids = [...document.querySelectorAll('#aq-tab input:checked')].map((x) => x.value);
      const b = $('#aq-mover');
      if (!b.dataset.ok) { b.dataset.ok = '1'; b.textContent = `Confirmar: mover ${ids.length} item(ns)?`; setTimeout(() => { delete b.dataset.ok; b.textContent = 'Mover os marcados'; }, 6000); return; }
      b.disabled = true; b.textContent = 'movendo…';
      try {
        const r = await api('/api/arquivos/mover', { ids });
        window.avisoInfo(`${r.movidos} item(ns) movido(s)` + (r.economia_gb ? ` · ${r.economia_gb} GB de cópias viraram o mesmo arquivo` : ''));
        if (r.falhas.length) window.avisoErro('Não movidos: ' + r.falhas.join(' · '));
      } catch (e) { window.avisoErro(e.message); }
      carregar();
    };
    document.querySelectorAll('[data-lote]').forEach((b) => b.onclick = async () => {
      try { const r = await api('/api/arquivos/desfazer', { lote: b.dataset.lote }); window.avisoInfo(`${r.voltou} item(ns) de volta ao lugar`); } catch (e) { window.avisoErro(e.message); }
      carregar();
    });
  }

  async function carregar() {
    $('#aq-lista').innerHTML = '<p class="ctx">Medindo as pastas…</p>';
    try { D.d = await api('/api/arquivos'); } catch (e) { $('#aq-lista').innerHTML = `<div class="bloqueio">${esc(e.message)}</div>`; return; }
    desenhar();
  }
  window.Arquivos = { abrir: carregar };
})();
