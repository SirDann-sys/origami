// Origami · Elenco: as vozes da obra (banco compartilhado). Criar voz = descrever (gênero, idade, tom), gerar 4
// candidatas lendo uma fala real do personagem, ouvir e aprovar. A aprovada entra no elenco e fecha a decisão da Mesa.
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const arq = (c) => `/arquivo?c=${encodeURIComponent(c)}`;
  const E = { obra: null, ep: null, d: null };
  const player = new Audio();
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
  const tocar = (c) => { player.src = arq(c); player.play(); };
  const opts = (xs, sel) => xs.map((x) => `<option ${x === sel ? 'selected' : ''}>${esc(x)}</option>`).join('');

  function desenhar() {
    const d = E.d;
    $('#el-lista').innerHTML = d.elenco.map((e) => `<div class="campo"><div class="cab"><b>${esc(e.personagem)}</b>
        <button data-ouvir="${esc(e.ref)}">▶ ouvir</button></div><div class="ctx">${esc(e.nome)}</div>
        <small class="ctx">${esc(e.voz)} · ${esc(e.receita.instruct || '')} · semente ${esc(e.receita.seed)}</small></div>`).join('');
    // pedidos de voz (decididos na Mesa ou vindos do roteiro): ficam aqui até a voz ser aprovada
    const pedidos = d.precisa.map((p) => {
      const temCand = (d.candidatas[p.personagem] || []).length;
      return `<div class="campo"><div class="cab"><b>${esc(p.personagem)}</b>${p.origem ? ` <small class="ctx">${esc(p.origem)} · Ep. ${esc(p.ep)}</small>` : ` <small class="ctx">Ep. ${esc(p.ep)}</small>`}
        <button data-criar="${esc(p.personagem)}" class="primario">${temCand ? 'Gerar mais' : 'Criar agora'}</button></div>
        <div class="ctx">${esc(p.descricao)}</div>${temCand ? `<small class="ctx">${temCand} candidata(s) esperando você ouvir →</small>` : ''}</div>`;
    });
    const pendDec = d.decisoes.map((x) => `<li><b>${esc(x.id)}</b> ${esc(x.titulo)} <small class="ctx">(decida na Mesa)</small></li>`);
    $('#el-pend').innerHTML = (pedidos.join('') + (pendDec.length ? `<ul>${pendDec.join('')}</ul>` : '')) || '<p class="ctx">Nenhuma voz pendente.</p>';
    const sug = E.criar || E.form?.personagem || d.precisa[0]?.personagem || '';
    const ped = d.precisa.find((p) => p.personagem === sug) || {};
    const f0 = E.form && E.form.personagem === sug ? E.form : null;          // o que o autor já escolheu para este personagem
    const s = f0 || ped.sugestao || {};
    $('#el-form').innerHTML = `
      ${ped.descricao ? `<div class="campo ctx"><b>${esc(sug)}</b>: ${esc(ped.descricao)}</div>` : ''}
      <label>Personagem (id curto, minúsculas: ex.: diretor, lia, tomas)</label><input type="text" id="el-p" value="${esc(sug)}">
      <div class="linha"><label>Gênero <select id="el-g">${opts(d.opcoes.generos, s.genero || 'masculina')}</select></label>
        <label>Idade <select id="el-i">${opts(d.opcoes.idades, s.idade || 'meia-idade')}</select></label>
        <label>Tom <select id="el-t">${opts(d.opcoes.tons, s.tom || 'grave')}</select></label>
        <label>Velocidade <input type="number" id="el-v" value="${f0?.velocidade ?? 0.92}" step="0.02" min="0.7" max="1.2"></label></div>
      <label>Frase de teste: inteira e fluente, no jeito do personagem (é ela que define a voz para a série toda)</label>
      <textarea id="el-f" placeholder="Nenhuma fala boa no roteiro: use Sugerir frases">${esc(f0 ? f0.frase : (d.frases[sug] || ''))}</textarea>
      <div class="acoes"><button id="el-sugerir">Sugerir frases de teste (Opus)</button></div><div id="el-sug">${E.sugHtml && E.sugPara === sug ? E.sugHtml : ''}</div>
      <div class="acoes"><button id="el-gerar" class="primario">Gerar 4 candidatas</button></div>`;
    const guardar = () => { E.form = { personagem: $('#el-p').value.trim().toLowerCase(), genero: $('#el-g').value, idade: $('#el-i').value,
      tom: $('#el-t').value, velocidade: +$('#el-v').value, frase: $('#el-f').value }; };
    ['#el-g', '#el-i', '#el-t', '#el-v', '#el-f'].forEach((q) => { $(q).oninput = guardar; $(q).onchange = guardar; });
    const ligarSug = () => $('#el-sug').querySelectorAll('[data-f]').forEach((el) => el.onclick = () => { $('#el-f').value = E.sugFrases[+el.dataset.f]; guardar(); });
    if (E.sugHtml && E.sugPara === sug) ligarSug();
    $('#el-sugerir').onclick = async () => {
      const pers = $('#el-p').value.trim().toLowerCase();
      if (!pers) return aviso('Preencha o personagem.');
      $('#el-sug').innerHTML = '<p class="ctx">O Opus está escrevendo 3 frases no jeito do personagem (~10 s)…</p>';
      try {
        const r = await api('/api/elenco/frases', { obra: E.obra, personagem: pers });
        E.sugFrases = r.frases; E.sugPara = pers;
        E.sugHtml = r.frases.map((f, i) => `<div class="campo" style="cursor:pointer" data-f="${i}">${i === r.recomendada ? '★ ' : ''}${esc(f)}</div>`).join('')
          + `<p class="ctx">★ ${esc(r.motivo)} · clique numa frase para usar</p>`;
        $('#el-sug').innerHTML = E.sugHtml; ligarSug();
        if (!$('#el-f').value.trim()) $('#el-f').value = r.frases[r.recomendada] || r.frases[0];
        guardar();
      } catch (e) { $('#el-sug').innerHTML = ''; aviso(e.message); }
    };
    $('#el-p').onchange = () => { E.criar = $('#el-p').value.trim().toLowerCase(); E.form = null; desenhar(); };
    $('#el-gerar').onclick = async () => {
      const corpo = { obra: E.obra, ep: E.ep, personagem: $('#el-p').value.trim().toLowerCase(), genero: $('#el-g').value, idade: $('#el-i').value,
        tom: $('#el-t').value, velocidade: +$('#el-v').value, frase: $('#el-f').value.trim() };
      if (/\.\.\.|…|—/.test(corpo.frase) || corpo.frase.split(/\s+/).length < 10) {
        if (!$('#el-gerar').dataset.ok) { $('#el-gerar').dataset.ok = 1; return aviso('A frase está curta ou quebrada (reticências/travessão): isso esconde o timbre. Use "Sugerir frases" ou clique de novo para gerar assim mesmo.'); }
      }
      if (!/^[a-z_]+$/.test(corpo.personagem) || !corpo.frase) return aviso('Preencha o personagem (só letras minúsculas) e a frase.');
      try { const r = await api('/api/elenco/candidatas', corpo); aviso(`na fila (job ${r.job}): ~1 min por candidata`, true); }
      catch (e) { aviso(e.message); }
    };
    $('#el-cands').innerHTML = Object.entries(d.candidatas).map(([p, cs]) => `<h3>${esc(p)}</h3>` + cs.map((c) => `
      <div class="linha"><button data-ouvir="${esc(c.arquivo)}">▶</button>
        <span>${esc(c.info.genero)} · ${esc(c.info.idade)} · ${esc(c.info.tom)} · semente ${esc(c.info.seed)} · vel. ${esc(c.info.velocidade)}</span>
        <button data-aprovar="${esc(c.arquivo)}" data-p="${esc(p)}">aprovar esta</button></div>`).join('')).join('') || '<p class="ctx">Nenhuma candidata ainda.</p>';
    document.querySelectorAll('#elenco [data-ouvir]').forEach((b) => b.onclick = () => tocar(b.dataset.ouvir));
    document.querySelectorAll('#elenco [data-criar]').forEach((b) => b.onclick = () => { if (E.criar !== b.dataset.criar) E.form = null; E.criar = b.dataset.criar; desenhar(); $('#el-f').focus(); });
    document.querySelectorAll('#elenco [data-aprovar]').forEach((b) => b.onclick = async () => {
      try { const r = await api('/api/elenco/aprovar', { obra: E.obra, personagem: b.dataset.p, arquivo: b.dataset.aprovar }); aviso(`aprovada: ${r.voz}`, true); carregar(); }
      catch (e) { aviso(e.message); }
    });
  }
  async function carregar() {
    try { E.d = await api(`/api/elenco?obra=${encodeURIComponent(E.obra)}`); } catch (e) { $('#el-lista').innerHTML = esc(e.message); return; }
    desenhar();
  }
  window.Elenco = { abrir(obra, ep) { E.obra = obra; E.ep = ep; carregar(); } };
})();
