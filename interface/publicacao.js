// Origami · Publicação: kit pronto para copiar, entrega peça por peça e registro do que foi postado (o app nunca posta).
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const P = { obra: null, ep: null, d: null };
  async function api(caminho, corpo) {
    const r = await fetch(caminho, corpo ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) } : {});
    const j = await r.json();
    if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    return j;
  }
  function aviso(txt, info) {
    const d = document.createElement('div'); d.className = 'aviso' + (info ? ' info' : ''); d.textContent = txt;
    $('#avisos').appendChild(d); setTimeout(() => d.remove(), info ? 3000 : 9000);
  }
  const textos = [];
  const campo = (rotulo, txt) => {
    textos.push(txt);
    return `<div class="campo"><div class="cab"><b>${esc(rotulo)}</b><button data-copiar="${textos.length - 1}">Copiar</button></div><pre>${esc(txt)}</pre></div>`;
  };

  function kit() {
    textos.length = 0;
    const k = P.d.kit;
    const btn = '<div class="acoes"><button id="pb-gerar-kit">' + (k ? 'Refazer o kit' : 'Gerar o kit (Opus)') + '</button></div>';
    if (!k) { $('#pb-kit').innerHTML = '<p class="ctx">Ainda não há kit para este episódio.</p>' + btn; ligarKit(); return; }
    let h = '<h3>YouTube · episódio completo</h3>' + campo('Título', k.youtube.titulo) + campo('Descrição', k.youtube.descricao);
    h += '<h3>Partes (TikTok · Reels · Shorts)</h3>';
    for (const p of k.partes) h += `<h3 style="margin-top:14px">Parte ${p.n}</h3>` + campo('Título do Short', p.short_titulo) + campo('Legenda (TikTok / Instagram)', p.legenda);
    h += '<h3>Outros</h3>' + campo('Comentário fixado', k.comentario_fixado) + campo('Rótulo de IA (sempre)', k.rotulo_ia);
    if (k.wattpad) h += campo('Wattpad · título do capítulo', k.wattpad.titulo_capitulo);
    const wi = P.d.wattpad_imagens || [];
    if (wi.length) {
      h += '<h3>Imagens do capítulo <small>sempre DEPOIS da frase que revela a cena (nunca antes: seria spoiler)</small></h3>';
      h += wi.map((w) => `<div class="campo" style="display:grid;grid-template-columns:120px 1fr;gap:10px"><img src="/arquivo?c=${encodeURIComponent(w.imagem)}" style="width:100%;border-radius:6px">
        <div><b>${w.topo ? 'Topo do capítulo (área acima do título)' : 'No meio do texto'}</b> · ${esc(w.id)}
        ${w.topo ? '' : `<div class="ctx">Procure (Ctrl+F) e insira numa linha nova logo depois de:</div><pre>${esc(w.depois_de)}</pre>`}
        ${w.achou || w.topo ? '' : '<div class="bloqueio">A frase da cena não foi achada no texto: confira o trecho na aba Arte.</div>'}</div></div>`).join('');
    }
    $('#pb-kit').innerHTML = h + btn; ligarKit();
    $('#pb-kit').querySelectorAll('[data-copiar]').forEach((b) => b.onclick = async () => {
      try { await navigator.clipboard.writeText(textos[+b.dataset.copiar]); aviso('copiado', true); } catch { aviso('não consegui copiar; selecione o texto'); }
    });
  }

  function ligarKit() {
    const b = $('#pb-gerar-kit'); if (!b) return;
    b.onclick = async () => { try { const r = await api('/api/publicacao/kit', { obra: P.obra, ep: P.ep }); aviso(`kit na fila (job ${r.job})`, true); } catch (e) { aviso(e.message); } };
  }

  function lado() {
    $('#pb-pasta').innerHTML = `${esc(P.d.pasta_entrega)} <button id="pb-abrir" style="padding:2px 10px">Abrir pasta</button>`;
    $('#pb-abrir').onclick = () => api('/api/postagem/abrir', { caminho: P.d.pasta_entrega }).catch((e) => aviso(e.message));
    $('#pb-itens').innerHTML = P.d.entregaveis.map((x) => `<li><span class="${x.entregue ? 'ok' : 'no'}">${x.entregue ? '✓' : x.pronto ? '○' : '✗'}</span> ${esc(x.nome)}
      ${!x.pronto ? '<small class="ctx">(ainda não existe)</small>' : !x.entregue ? `<button data-so="${esc(x.grupo)}" style="padding:1px 8px">entregar</button>` : ''}</li>`).join('');
    $('#pb-itens').querySelectorAll('[data-so]').forEach((b) => b.onclick = () => entregar([b.dataset.so]));
    const pecas = ['episódio completo', ...(P.d.kit?.partes || []).map((p) => `parte ${p.n}`), 'capítulo'];
    const feito = (pl, pc) => P.d.postagens.find((x) => x.plataforma === pl && x.peca === pc);
    $('#pb-registro').innerHTML = `<table class="reg"><tr><th>peça</th>${P.d.plataformas.map((p) => `<th>${esc(p)}</th>`).join('')}</tr>` +
      pecas.map((pc) => `<tr><td>${esc(pc)}</td>${P.d.plataformas.map((pl) => {
        const f = feito(pl, pc);
        return `<td class="${f ? 'feito' : 'vazio'}" data-pl="${esc(pl)}" data-pc="${esc(pc)}" title="${f ? esc(f.data + ' ' + (f.link || '')) : 'marcar como postado'}">${f ? f.data.slice(5, 10) : ''}</td>`;
      }).join('')}</tr>`).join('') + '</table>';
    $('#pb-registro').querySelectorAll('td[data-pl]').forEach((td) => td.onclick = async () => {
      const acao = td.classList.contains('feito') ? 'desfazer' : 'registrar';
      try { await api(`/api/publicacao/${acao}`, { obra: P.obra, ep: P.ep, plataforma: td.dataset.pl, peca: td.dataset.pc }); carregar(); }
      catch (e) { aviso(e.message); }
    });
  }

  async function entregar(so) {
    try { const r = await api('/api/publicacao/entregar', { obra: P.obra, ep: P.ep, so }); aviso(`entrega na fila (job ${r.job})`, true); }
    catch (e) { aviso(e.message); }
  }
  async function carregar() {
    try { P.d = await api(`/api/publicacao?obra=${encodeURIComponent(P.obra)}&ep=${P.ep}`); }
    catch (e) {
      P.d = null; $('#pb-itens').innerHTML = ''; $('#pb-registro').innerHTML = ''; $('#pb-pasta').textContent = '';
      $('#pb-kit').innerHTML = `<div class="bloqueio">Ep. ${esc(P.ep)}: ainda não há o que publicar. ${esc(e.message.replace(/^\w+Error: /, ''))}</div>`;
      return;
    }
    kit(); lado();
  }
  $('#pb-entregar').onclick = () => entregar(null);
  window.Pub = { abrir(obra, ep) { P.obra = obra; P.ep = ep; carregar(); } };
})();
