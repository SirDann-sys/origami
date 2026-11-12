// Origami · Estúdio de arte. Cada cena: o trecho do texto de onde saiu, o modelo do prompt com {personagem@contexto}
// (a descrição vem do guia de arte da obra, fixa), os alertas de consistência e as candidatas para escolher.
// Ao lado: o episódio anterior e a grade do perfil, para a série continuar com uma cara só.
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const img = (c) => `/arquivo?c=${encodeURIComponent(c)}`;
  const A = { obra: null, ep: null, d: null, sel: null };

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
  const escolhidaDe = (c) => c.candidatas.find((p) => c.escolhida && p.endsWith(c.escolhida));

  function lista() {
    const cs = A.d.cenas.slice().sort((a, b) => /descartad/.test(a.uso || '') - /descartad/.test(b.uso || ''));
    $('#ar-resumo').textContent = `${cs.length} · ${cs.filter((c) => c.escolhida).length} escolhidas`;
    const capasItem = `<div class="ar-item ${A.sel === '__capas' ? 'on' : ''}" data-id="__capas" style="border-color:var(--violeta2)">
        <img style="background:var(--violeta2)"><div><b>Capas e miniatura</b><div class="u">ganchos, cenas e montagem</div>
        <div class="ctx" style="font-size:12px">${A.d.capas ? `${(A.d.capas.partes || []).length} capa(s)` : 'ainda sem capas'}</div></div></div>`;
    $('#ar-lista').innerHTML = capasItem + cs.map((c) => {
      const e = escolhidaDe(c) || c.candidatas[0];
      return `<div class="ar-item ${A.sel === c.id ? 'on' : ''} ${/descartad/.test(c.uso || '') ? 'descartada' : ''}" data-id="${esc(c.id)}">
        ${e ? `<img src="${img(e)}" loading="lazy">` : '<img>'}
        <div><b>${esc(c.id)}</b><div class="u">${esc(c.uso || '')}</div>
          <div class="ctx" style="font-size:12px">${c.candidatas.length} candidata(s)${c.escolhida ? ' · ✓' : ''}</div>
          ${c.alertas.length ? `<div class="al">⚠ ${c.alertas.length} alerta(s)</div>` : ''}</div></div>`;
    }).join('') || '<p class="ctx">Nenhuma cena ainda.</p>';
    $('#ar-lista').querySelectorAll('.ar-item').forEach((el) => el.onclick = () => { A.sel = el.dataset.id; lista(); centro(); });
  }

  function chipsPersonagens() {
    return Object.entries(A.d.personagens).flatMap(([p, ctxs]) => ctxs.map((c) => `<span class="chip" data-tok="{${p}@${c}}">${p} · ${c}</span>`)).join('');
  }

  // ---------- editor das capas: cada capa aponta para uma cena; a imagem é a candidata escolhida dessa cena
  function editorCapas() {
    const sp = A.d.capas || { serie: '', total: A.d.n_partes, miniatura: { cena: '', titulo: ['', ''], sub: ['', ''], foco: [0.62, 0.5] },
      partes: Array.from({ length: A.d.n_partes }, (_, i) => ({ n: i + 1, cena: '', gancho: [''], foco: [0.5, 0.5] })) };
    const ops = (sel) => `<option value="">— escolher cena —</option>` + A.d.cenas.filter((c) => !/descartad/.test(c.uso || ''))
      .map((c) => `<option value="${esc(c.id)}" ${c.id === sel ? 'selected' : ''}>${esc(c.id)}${c.escolhida ? '' : ' (sem escolhida)'}</option>`).join('');
    const prev = (peca) => { const f = A.d.finais.find((x) => x.peca === peca); return f ? `<img src="${img(f.caminho)}" style="width:100%;border-radius:6px">` : ''; };
    // a imagem de cada capa aparece com o nome; "manual" = escolhida à mão (não segue a cena sozinha)
    const imgInfo = (alvo) => alvo.imagem ? `<div class="ctx" style="font-size:12px">imagem: ${esc(alvo.imagem.split('/').pop())}
        ${alvo.imagem_manual ? '<span class="tag">manual</span> <button class="c-voltar" type="button" title="Trocar pela candidata escolhida da cena">usar a escolhida da cena</button>' : ''}</div>`
      : '<div class="al">sem imagem: escolha a candidata da cena</div>';
    const linha = (p) => `<div class="campo" data-n="${p.n}" style="display:grid;grid-template-columns:110px 1fr;gap:10px">
        <div>${prev('parte ' + p.n) || '<div class="ctx">sem prévia</div>'}</div>
        <div><b>Parte ${p.n}</b> <select class="c-cena">${ops(p.cena)}</select>${imgInfo(p)}
          <label class="ctx">Gancho (uma linha por linha da capa)</label><textarea class="c-gancho" style="min-height:64px">${esc((p.gancho || []).join('\n'))}</textarea>
          <div class="linha"><label class="ctx">Enquadramento ← → <input type="range" class="c-foco" min="0" max="1" step="0.02" value="${(p.foco || [0.5])[0]}"></label>
            <label class="ctx">↑ ↓ <input type="range" class="c-focov" min="0" max="1" step="0.02" value="${(p.foco || [0.5, 0.5])[1] ?? 0.5}"></label>
            <label class="ctx">Descer a cena <input type="number" class="c-desce" value="${p.desce || 0}" step="20" min="0" max="600" style="width:70px"></label>
            <label class="ctx" title="Cena inteira na largura, colada nesta altura (ex.: 342), quando o recorte corta o objeto">Faixa (y) <input type="number" class="c-faixa" value="${p.faixa_y ?? ''}" step="10" min="0" max="1600" style="width:70px"></label></div></div></div>`;
    const m = sp.miniatura || {};
    $('#ar-centro').innerHTML = `<h2>Capas e miniatura <small>cada capa usa a candidata escolhida da cena</small></h2>
      <div class="ar-form"><label>Linha da série</label><input type="text" id="c-serie" value="${esc(sp.serie)}"></div>
      <h3>Miniatura do YouTube</h3>
      <div class="campo" style="display:grid;grid-template-columns:200px 1fr;gap:10px"><div>${prev('miniatura')}</div><div>
        <select id="m-cena">${ops(m.cena)}</select>${imgInfo(m)}
        <div class="linha"><label class="ctx">Enquadramento ← → <input type="range" id="m-foco" min="0" max="1" step="0.02" value="${(m.foco || [0.62])[0]}"></label>
          <label class="ctx">↑ ↓ <input type="range" id="m-focov" min="0" max="1" step="0.02" value="${(m.foco || [0.62, 0.5])[1] ?? 0.5}"></label>
          <label class="ctx" title="Espelha a cena quando o rosto cai embaixo do título"><input type="checkbox" id="m-espelhar" ${m.espelhar ? 'checked' : ''}> espelhar</label></div>
        <label class="ctx">Título (2 linhas)</label><textarea id="m-tit" style="min-height:52px">${esc((m.titulo || []).join('\n'))}</textarea>
        <label class="ctx">Subtítulo (2 linhas)</label><textarea id="m-sub" style="min-height:52px">${esc((m.sub || []).join('\n'))}</textarea></div></div>
      <h3>Capas das partes</h3>${(sp.partes || []).map(linha).join('')}
      <div class="acoes"><button id="c-salvar">Salvar</button><button id="c-montar" class="primario">Salvar e montar</button></div>`;
    const coletar = () => {
      const s2 = JSON.parse(JSON.stringify(sp));
      s2.serie = $('#c-serie').value.trim();
      const mAntes = s2.miniatura || {};
      s2.miniatura = { ...mAntes, arquivo: mAntes.arquivo || `miniatura_ep${A.ep}.jpg`, serie: s2.serie, cena: $('#m-cena').value,
        titulo: $('#m-tit').value.split('\n').map((x) => x.trim()).filter(Boolean), sub: $('#m-sub').value.split('\n').map((x) => x.trim()).filter(Boolean),
        foco: [+$('#m-foco').value, +$('#m-focov').value] };
      if ($('#m-espelhar').checked) s2.miniatura.espelhar = true; else delete s2.miniatura.espelhar;
      if (s2.miniatura.cena !== mAntes.cena) { delete s2.miniatura.imagem; delete s2.miniatura.imagem_manual; }   // cena trocada: imagem da cena nova
      if (voltar.has('mini')) { delete s2.miniatura.imagem; delete s2.miniatura.imagem_manual; }
      document.querySelectorAll('#ar-centro .campo[data-n]').forEach((el) => {
        const p = s2.partes.find((x) => x.n === +el.dataset.n);
        const cenaNova = el.querySelector('.c-cena').value;
        if (cenaNova !== p.cena || voltar.has(p.n)) { delete p.imagem; delete p.imagem_manual; }
        p.cena = cenaNova;
        p.gancho = el.querySelector('.c-gancho').value.split('\n').map((x) => x.trim()).filter(Boolean);
        p.foco = [+el.querySelector('.c-foco').value, +el.querySelector('.c-focov').value];
        const dsc = +el.querySelector('.c-desce').value;
        if (dsc !== (p.desce || 0)) p.desce_manual = true;      // ajuste do autor: o cálculo automático não mexe mais
        if (dsc) p.desce = dsc; else delete p.desce;
        const fx = el.querySelector('.c-faixa').value; if (fx !== '') p.faixa_y = +fx; else delete p.faixa_y;
      });
      s2.total = s2.partes.length;
      return s2;
    };
    const salvar = async (montar) => {
      try {
        await api('/api/arte/capas', { obra: A.obra, ep: A.ep, spec: coletar() });
        if (montar) { const r = await api('/api/arte/montar', { obra: A.obra, ep: A.ep }); aviso(`capas na fila (job ${r.job})`, true); }
        else aviso('capas salvas', true);
        carregar();
      } catch (e) { aviso(e.message); }
    };
    const voltar = new Set();      // capas marcadas para voltar à candidata escolhida da cena
    $('#ar-centro').querySelectorAll('.c-voltar').forEach((b) => b.onclick = () => {
      const campo = b.closest('.campo[data-n]');
      voltar.add(campo ? +campo.dataset.n : 'mini');
      b.replaceWith(Object.assign(document.createElement('span'), { className: 'ctx', textContent: '→ ao salvar, usa a escolhida da cena' }));
    });
    $('#c-salvar').onclick = () => salvar(false);
    $('#c-montar').onclick = () => salvar(true);
  }

  function centro(nova) {
    if (A.sel === '__capas' && !nova) return editorCapas();
    const c = nova ? { id: '', formato: 'alto', prompt: '', trecho: '', uso: '', candidatas: [], alertas: [], prompt_final: '', trecho_texto: '' }
      : A.d.cenas.find((x) => x.id === A.sel);
    if (!c) { $('#ar-centro').innerHTML = '<p class="ctx">Escolha uma cena.</p>'; return; }
    $('#ar-centro').innerHTML = `
      <h2>${nova ? 'Nova cena' : esc(c.id)} <small>${esc(c.uso || '')}</small></h2>
      ${c.alertas.map((a) => `<div class="bloqueio">⚠ ${esc(a.split(': ').slice(1).join(': '))}</div>`).join('')}
      <h3>Trecho do texto <small>de onde a cena sai</small></h3>
      ${c.trecho_texto ? `<div class="trecho">${esc(c.trecho_texto)}</div>` : '<p class="ctx">Sem trecho ligado: toda cena deve apontar para o texto.</p>'}
      <div class="ar-form">
        ${nova ? '<label>Id (letras minúsculas, números e _)</label><input type="text" id="c-id" placeholder="ex.: p03_cozinha">' : ''}
        <label>Frase do texto-mestre (liga a cena ao trecho)</label><input type="text" id="c-trecho" value="${esc(c.trecho || '')}">
        <label>Uso</label><input type="text" id="c-uso" value="${esc(c.uso || '')}" placeholder="ex.: capa parte 3 · miniatura · Wattpad">
        <label>Formato</label><select id="c-formato">${['alto', 'largo', 'quadrado', 'panorama'].map((f) => `<option ${f === c.formato ? 'selected' : ''}>${f}</option>`).join('')}</select>
        <label>Cena (em inglês). Personagens SÓ pelos botões abaixo: a descrição vem do guia de arte.</label>
        <div class="chips">${chipsPersonagens()}</div>
        <textarea id="c-prompt">${esc(c.prompt)}</textarea>
        ${c.refs_quem && c.refs_quem.length ? `<label>Aparência fixa: referências que vão junto</label><div class="chips">${c.refs_quem.map((r) => `<span class="chip ref">${esc(r)}</span>`).join('')}</div>` : ''}
        ${c.prompt_final ? `<label>Como vai para o gerador (com o guia)</label><div class="prompt-final">${esc(c.prompt_final)}</div>` : ''}
        <div class="acoes"><button id="c-salvar">Salvar cena</button>${nova ? '' : '<button id="c-gerar" class="primario">Gerar 2 candidatas</button>'}</div>
      </div>
      ${nova ? '' : `<h3>Candidatas <small>clique para ver grande e escolher</small></h3>
      ${window.blocoTriagem(c, 'arte')}
      <div class="ar-cands">${c.candidatas.map((p) => `<div class="ar-cand ${c.escolhida && p.endsWith(c.escolhida) ? 'on' : ''}" data-p="${esc(p)}">
        <img src="${img(p)}" loading="lazy">${window.marcaTriagem(c, p)}<span class="s">${esc(p.split(/[\\/]/).pop().replace('.png', ''))}</span></div>`).join('') || '<p class="ctx">Nenhuma ainda.</p>'}</div>`}`;
    const ta = $('#c-prompt');
    $('#ar-centro').querySelectorAll('.chip').forEach((ch) => ch.onclick = () => {
      const i = ta.selectionStart ?? ta.value.length; ta.value = ta.value.slice(0, i) + ch.dataset.tok + ta.value.slice(i); ta.focus();
    });
    $('#c-salvar').onclick = async () => {
      const cena = { id: nova ? $('#c-id').value.trim() : c.id, formato: $('#c-formato').value, prompt: ta.value.trim(),
        trecho: $('#c-trecho').value.trim(), uso: $('#c-uso').value.trim() };
      try { await api('/api/arte/cena', { obra: A.obra, ep: A.ep, cena }); A.sel = cena.id; aviso('cena salva', true); carregar(); }
      catch (e) { aviso(e.message); }
    };
    if ($('#c-gerar')) $('#c-gerar').onclick = async () => {
      if (c.alertas.length) return aviso('Resolva os alertas de consistência antes de gerar.');
      try { const r = await api('/api/arte/sementes', { obra: A.obra, ep: A.ep, id: c.id, n: 2 }); aviso(`na fila (job ${r.job}): 2 candidatas novas`, true); }
      catch (e) { aviso(e.message); }
    };
    // clicar abre a imagem grande; escolher é pelo botão de lá
    const cands = [...$('#ar-centro').querySelectorAll('.ar-cand')];
    cands.forEach((el, k) => el.onclick = () => window.Lightbox.abrir(
      cands.map((x) => ({ caminho: x.dataset.p, escolhida: x.classList.contains('on') })), k,
      async (arquivo) => { try { await api('/api/arte/escolher', { obra: A.obra, ep: A.ep, id: c.id, arquivo }); aviso('escolhida', true); carregar(); } catch (e) { aviso(e.message); } }));
  }

  function lado() {
    const fig = (f) => `<figure><img src="${img(f.caminho)}" loading="lazy"><figcaption>${esc(f.peca)}</figcaption></figure>`;
    $('#ar-ant-ep').textContent = A.d.anterior ? `Ep. ${A.d.anterior.ep}` : '';
    $('#ar-anterior').innerHTML = A.d.anterior ? A.d.anterior.finais.map(fig).join('') : '<p class="ctx">Primeiro episódio: ele é a referência.</p>';
    $('#ar-refs').innerHTML = (A.d.referencias || []).map((r) => `<figure><img src="${img(r.caminho)}" loading="lazy"><figcaption>${esc(r.quem)} · ${esc(r.vista)}</figcaption></figure>`).join('')
      || '<p class="ctx">Sem referências: as personagens saem só pela descrição do guia.</p>';
    $('#ar-finais').innerHTML = A.d.finais.map(fig).join('') || '<p class="ctx">Ainda não montadas.</p>';
    // grade do perfil: o mais novo primeiro (como o TikTok mostra), 3 colunas, recorte 3:4
    const capas = A.d.grade.slice().reverse().flatMap((g) => g.capas.slice().reverse());
    const n = Math.max(9, Math.ceil(capas.length / 3) * 3);
    $('#ar-grade').innerHTML = Array.from({ length: n }, (_, i) => capas[i] ? `<div><img src="${img(capas[i])}" loading="lazy"></div>` : '<div class="vazio"></div>').join('');
  }

  async function carregar() {
    try { A.d = await api(`/api/arte?obra=${encodeURIComponent(A.obra)}&ep=${A.ep}`); }
    catch (e) { $('#ar-lista').innerHTML = `<p class="ctx">${esc(e.message)}</p>`; return; }
    if (!A.d.cenas.some((c) => c.id === A.sel)) A.sel = A.d.cenas[0]?.id || null;
    lista(); centro(); lado();
  }

  $('#ar-nova').onclick = () => { A.sel = null; lista(); centro(true); };
  $('#ar-sugerir').onclick = async () => {
    try { const r = await api('/api/arte/sugerir', { obra: A.obra, ep: A.ep }); aviso(`na fila (job ${r.job}): o Opus lê o texto e propõe cenas e ganchos`, true); }
    catch (e) { aviso(e.message); }
  };
  $('#ar-montar').onclick = async () => {
    try { const r = await api('/api/arte/montar', { obra: A.obra, ep: A.ep }); aviso(`capas na fila (job ${r.job})`, true); }
    catch (e) { aviso(e.message); }
  };
  window.Arte = { abrir(obra, ep) { if (obra !== A.obra || ep !== A.ep) A.sel = null; A.obra = obra; A.ep = ep; carregar(); } };
})();
