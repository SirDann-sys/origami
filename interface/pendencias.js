// Origami · "O que precisa de você". Fica no topo da coluna Etapas da Mesa, com o número no menu.
// O piloto automático faz todo o resto sozinho; aqui aparecem só os portões do autor (decidir, aprovar o texto, escolher
// vozes, ouvir o áudio, confirmar imagens) e os erros que pararam o episódio. Cada cartão leva à tela certa.
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
  const P = { obra: null, ep: null, d: null };

  function desenhar() {
    const d = P.d, el = $('#pendencias');
    if (!d || !el) return;
    const total = d.pendencias.length + d.outras.length;
    const badge = $('#pend-n');
    badge.hidden = !total; badge.textContent = total;
    const cartao = (p, outroEp) => `<li class="pend ${p.bloqueia ? 'bloq' : ''}" data-tela="${esc(p.tela)}" ${outroEp ? `data-ep="${esc(p.ep)}"` : ''}>
        ${outroEp ? `<b>Ep. ${esc(p.ep)}</b> · ` : ''}${esc(p.texto)} <span class="ir">abrir ›</span></li>`;
    el.innerHTML = `
      <div class="piloto ${d.piloto ? 'on' : ''}">
        <label><input type="checkbox" id="pl-ligar" ${d.piloto ? 'checked' : ''}> <b>Piloto automático</b></label>
        <span class="ctx">${d.piloto ? 'o app faz tudo sozinho e só para nos itens abaixo' : 'desligado: nada anda sozinho neste episódio'}</span>
      </div>
      <h2>O que precisa de você <small>${d.pendencias.length ? `${d.pendencias.length} neste episódio` : 'nada neste episódio'}</small></h2>
      <ul class="pend-lista">${d.pendencias.map((p) => cartao(p)).join('') || '<li class="ctx">Tudo certo por aqui.</li>'}
        ${d.outras.map((p) => cartao(p, true)).join('')}</ul>
      ${d.piloto && d.log.length ? `<details class="ctx"><summary>o que o piloto fez por último</summary><pre>${esc(d.log.join('\n'))}</pre></details>` : ''}`;
    el.querySelectorAll('li.pend').forEach((li) => li.onclick = async () => {
      if (li.dataset.ep && window.abrirEpisodio) await window.abrirEpisodio(P.obra, li.dataset.ep);
      if (li.dataset.tela && li.dataset.tela !== 'mesa') window.trocarTela(li.dataset.tela);
    });
    $('#pl-ligar').onchange = async (e) => {
      try {
        await api('/api/piloto/ligar', { obra: P.obra, ep: P.ep, ligado: e.target.checked });
        window.avisoInfo && window.avisoInfo(e.target.checked ? 'Piloto automático ligado: o episódio anda sozinho e te chama só quando precisar.' : 'Piloto automático desligado.');
        atualizar(P.obra, P.ep);
      } catch (er) { window.avisoErro && window.avisoErro(er.message); e.target.checked = !e.target.checked; }
    };
  }

  async function atualizar(obra, ep) {
    P.obra = obra; P.ep = ep;
    try { P.d = await api(`/api/pendencias?obra=${encodeURIComponent(obra)}&ep=${ep}`); } catch { return; }
    desenhar();
  }
  window.Pendencias = { atualizar };
})();
