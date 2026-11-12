// Origami · Imagens do vídeo: cenários e retratos NOVOS do episódio (os antigos ficam na biblioteca e são reaproveitados).
// Retrato de personagem novo só depois de a descrição dele entrar no guia de arte da obra (a mesma vale para sempre).
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const img = (c) => `/arquivo?c=${encodeURIComponent(c)}&t=${Date.now() % 100000}`;
  const I = { obra: null, ep: null, d: null, sel: null };
  async function api(caminho, corpo) {
    const r = await fetch(caminho, corpo ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) } : {});
    const j = await r.json();
    if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    return j;
  }
  function aviso(txt, info) {
    const d = document.createElement('div'); d.className = 'aviso' + (info ? ' info' : ''); d.textContent = txt;
    $('#avisos').appendChild(d); setTimeout(() => d.remove(), info ? 4000 : 9000);
  }
  const post = async (acao, corpo, ok) => {
    try { const r = await api(`/api/imagens/${acao}`, { obra: I.obra, ep: I.ep, ...corpo }); if (ok) aviso(typeof ok === 'function' ? ok(r) : ok, true); carregar(); }
    catch (e) { aviso(e.message); }
  };

  function lista() {
    const it = I.d.itens;
    $('#iv-resumo').textContent = it.length ? `${it.filter((x) => x.final).length}/${it.length} prontas` : '';
    $('#iv-lista').innerHTML = it.map((x) => `<div class="ar-item ${I.sel === x.id ? 'on' : ''}" data-id="${esc(x.id)}">
        ${x.final || x.candidatas[0] ? `<img src="${img(x.final || x.candidatas[0])}">` : '<img>'}
        <div><b>${esc(x.id)}</b><div class="u">${esc(x.tipo)}</div>
        <div class="ctx" style="font-size:12px">${x.final ? '✓ pronta' : x.escolhida ? 'escolhida: falta finalizar' : `${x.candidatas.length} candidata(s)`}</div>
        ${x.sem_guia ? '<div class="al">⚠ personagem fora do guia de arte</div>' : ''}</div></div>`).join('')
      || '<p class="ctx">Nenhuma imagem nova neste episódio (tudo reaproveitado) ou o roteiro ainda não foi gerado.</p>';
    $('#iv-lista').querySelectorAll('.ar-item').forEach((el) => el.onclick = () => { I.sel = el.dataset.id; lista(); centro(); });
    const prontas = it.filter((x) => x.escolhida && !x.final).map((x) => x.id);
    $('#iv-faltam').innerHTML = (I.d.faltam.length ? `<div class="bloqueio" style="margin-top:10px">O vídeo ainda precisa de: ${esc(I.d.faltam.join(', '))}</div>` : '')
      + (prontas.length ? `<div class="acoes"><button id="iv-final" class="primario">Finalizar ${prontas.length} escolhida(s) (ampliar)</button></div>` : '');
    if ($('#iv-final')) $('#iv-final').onclick = () => post('finalizar', { ids: prontas }, (r) => `na fila (job ${r.job}): ampliando`);
  }

  function centro() {
    const x = I.d.itens.find((y) => y.id === I.sel);
    if (!x) { $('#iv-centro').innerHTML = '<p class="ctx">Escolha uma imagem.</p>'; return; }
    const guia = x.sem_guia ? `<div class="bloqueio">O <b>rosto</b> de <b>${esc(x.personagem)}</b> ainda não está no guia de arte. Descreva-o uma vez (em inglês, como os outros):
      vale para este retrato, para os próximos episódios e para as capas.</div>
      <div class="ar-form"><label>Rosto para o retrato (de frente)</label><input type="text" id="iv-dr" placeholder="a man in his late fifties, short graying black hair, sharp calm eyes, expensive dark suit">
      <label>No contexto de trabalho/rotina, para as capas (opcional; se vazio, mantém o que o guia já tem)</label><input type="text" id="iv-dh">
      <label>Fora do trabalho (opcional)</label><input type="text" id="iv-df">
      <div class="acoes"><button id="iv-cad" class="primario">Cadastrar no guia de arte</button></div></div>` : '';
    const ref = x.tipo === 'retrato' ? (x.referencia
      ? `<div class="campo" style="display:flex;gap:12px;align-items:center"><img src="${img(x.referencia)}" style="width:90px;border-radius:8px">
          <div><b>Rosto oficial de ${esc(x.personagem)}</b><div class="ctx">As candidatas são geradas a partir dele: o mesmo rosto em todo episódio.</div></div></div>`
      : `<div class="campo ctx">Personagem novo: o retrato que você finalizar vira o <b>rosto oficial</b> dele para sempre (escolha com calma).</div>`) : '';
    $('#iv-centro').innerHTML = `<h2>${esc(x.id)} <small>${esc(x.tipo)} · ${esc(x.formato)}</small></h2>${guia}${ref}
      <div class="ar-form"><label>Descrição (inglês)</label><textarea id="iv-p">${esc(x.prompt)}</textarea>
      <div class="acoes"><button id="iv-salvar">Salvar descrição</button><button id="iv-gerar" class="primario" ${x.sem_guia ? 'disabled' : ''}>Gerar 2 candidatas</button></div></div>
      ${x.tipo === 'fundo' ? `<div class="campo"><b>Já existe esse lugar na série?</b> <span class="ctx">Use o da biblioteca: o mesmo lugar aparece igual em todos os episódios.</span>
        <div class="linha"><select id="iv-bib-sel">${I.d.biblioteca.filter((b) => b.id.startsWith('fundo_')).map((b) => `<option>${esc(b.id)}</option>`).join('')}</select>
        <select id="iv-hor"><option value="">mesmo horário</option><option value="manha">de manhã</option><option value="dia">de dia</option><option value="tarde">à tarde</option><option value="noite">à noite</option></select>
        <button id="iv-reusar">Usar este no lugar de ${esc(x.id)}</button></div>
        <div class="ctx">Outro horário? O app gera uma versão do MESMO lugar (a imagem original é a referência), só mudando a luz.</div></div>` : ''}
      <h3>Candidatas <small>clique para ver grande e escolher</small></h3>${window.blocoTriagem(x, 'imagens')}
      <div class="ar-cands">${x.candidatas.map((p) => `<div class="ar-cand ${x.escolhida && p.endsWith(x.escolhida) ? 'on' : ''}" data-p="${esc(p)}">
        <img src="${img(p)}">${window.marcaTriagem(x, p)}<span class="s">${esc(p.split(/[\\/]/).pop().replace('.png', ''))}</span></div>`).join('') || '<p class="ctx">Nenhuma ainda.</p>'}</div>
      ${x.final ? `<h3>Final (ampliada)</h3><img src="${img(x.final)}" style="max-width:100%;border-radius:10px">` : ''}`;
    if ($('#iv-cad')) $('#iv-cad').onclick = () => {
      const r = $('#iv-dr').value.trim(); if (!r) return aviso('Descreva o rosto do personagem.');
      post('personagem', { personagem: x.personagem, retrato: r, trabalho: $('#iv-dh').value.trim(), fora: $('#iv-df').value.trim() }, 'personagem cadastrado no guia de arte');
    };
    if ($('#iv-reusar')) $('#iv-reusar').onclick = () => post('reusar', { id: x.id, existente: $('#iv-bib-sel').value, horario: $('#iv-hor').value },
      (r) => r.gerar ? `trocado por ${r.usa}: gere as candidatas dessa variante (mesmo lugar, outro horário)` : `trocado em ${r.trocas} trecho(s) do vídeo`);
    $('#iv-salvar').onclick = () => post('item', { item: { id: x.id, prompt: $('#iv-p').value.trim() } }, 'descrição salva');
    $('#iv-gerar').onclick = () => post('sementes', { id: x.id, n: 2 }, (r) => `na fila (job ${r.job}): 2 candidatas`);
    // clicar abre a imagem grande; escolher é pelo botão de lá
    const cands = [...$('#iv-centro').querySelectorAll('.ar-cand')];
    cands.forEach((el, k) => el.onclick = () => window.Lightbox.abrir(
      cands.map((c) => ({ caminho: c.dataset.p, escolhida: c.classList.contains('on') })), k,
      (arquivo) => post('escolher', { id: x.id, arquivo }, 'escolhida')));
  }

  function bib() {
    $('#iv-bib').innerHTML = I.d.biblioteca.map((b) => `<figure><img src="${img(b.caminho)}" loading="lazy"><figcaption>${esc(b.id)}</figcaption></figure>`).join('');
  }

  async function carregar() {
    try { I.d = await api(`/api/imagens?obra=${encodeURIComponent(I.obra)}&ep=${I.ep}`); }
    catch (e) { $('#iv-lista').innerHTML = `<div class="bloqueio">${esc(e.message)}</div>`; return; }
    if (!I.d.itens.some((x) => x.id === I.sel)) I.sel = I.d.itens[0]?.id || null;
    lista(); centro(); bib();
  }
  window.Imagens = {
    abrir(obra, ep) { if (obra !== I.obra || ep !== I.ep) I.sel = null; I.obra = obra; I.ep = ep; carregar(); },
    irPara(obra, ep, id) { I.obra = obra; I.ep = ep; I.sel = id; carregar(); },
  };
})();
