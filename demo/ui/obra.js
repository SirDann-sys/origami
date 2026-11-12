// Origami · Obra nova: do arquivo bruto (RPG ou texto do autor) ao guia, à bíblia e ao elenco, passo a passo.
// O Opus lê a obra INTEIRA bloco a bloco (com o número de cada linha), divide em episódios, escreve o guia de cada um e
// consolida bíblia, inconsistências (viram decisões na Mesa), guia de arte, pronúncias e pedidos de voz.
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const O = { obra: null, d: null };
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

  function formulario() {
    $('#ob-criar').innerHTML = `<div class="ar-form">
      <label>Título da obra</label><input type="text" id="ob-tit" placeholder="ex.: A Confeitaria">
      <label>Nome da pasta (sem acento nem espaço)</label><input type="text" id="ob-pasta" placeholder="ex.: A_Confeitaria">
      <label>Sigla (nome curto nos arquivos)</label><input type="text" id="ob-sig" placeholder="ex.: Confeitaria">
      <div class="linha"><label>Fonte <select id="ob-tipo"><option value="rpg">log de RPG (Gemini etc.)</option><option value="organico">texto escrito por mim</option></select></label>
        <label>Protagonista (id curto) <input type="text" id="ob-prot" placeholder="ex.: lia" style="width:110px"></label></div>
      <div class="acoes"><button id="ob-go" class="primario">Criar obra</button></div></div>`;
    $('#ob-tit').oninput = () => { if (!$('#ob-pasta').dataset.mexido) $('#ob-pasta').value = $('#ob-tit').value.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\W+/g, '_').replace(/^_|_$/g, ''); };
    $('#ob-pasta').oninput = () => { $('#ob-pasta').dataset.mexido = 1; };
    $('#ob-go').onclick = async () => {
      const corpo = { titulo: $('#ob-tit').value.trim(), pasta: $('#ob-pasta').value.trim(), sigla: $('#ob-sig').value.trim(), tipo: $('#ob-tipo').value, protagonista: $('#ob-prot').value.trim() };
      if (!corpo.titulo || !corpo.pasta) return aviso('Preencha o título e a pasta.');
      try {
        await api('/api/obra/criar', corpo); aviso('obra criada: agora importe a fonte', true);
        const sel = $('#obra'); sel.insertAdjacentHTML('beforeend', `<option value="${esc(corpo.pasta)}">${esc(corpo.titulo)}</option>`);
        sel.value = corpo.pasta; O.obra = corpo.pasta; carregar();
      } catch (e) { aviso(e.message); }
    };
  }

  function desenhar() {
    const d = O.d;
    const ordem = ['fonte', 'ler', 'estrutura', 'guia', 'biblia'];
    const proximo = d.passos.find((p) => !p.feito)?.id;
    $('#ob-passos').innerHTML = `<h2>${esc(d.titulo)} <small>${esc(d.etapa || '')}</small></h2>
      ${d.custo_estimado ? `<p class="ctx">Custo estimado da leitura completa pelo Opus: <b>${esc(d.custo_estimado)}</b> (cada passo é retomável: se parar, continua de onde estava).</p>` : ''}
      <ol id="on-etapas" class="lista-etapas">${d.passos.map((p, i) => `<li><span class="ponto ${p.feito ? 'ok' : p.id === proximo ? 'refazer' : 'espera'}"></span><div style="flex:1">
        <div class="nome">${i + 1}. ${esc(p.nome)}</div><div class="est">${esc(p.info || (p.feito ? 'pronto' : ''))}</div>
        ${p.id === 'fonte' ? `<div class="acoes"><input type="file" id="ob-arq" multiple accept=".txt,.md,.pdf,.docx"><button id="ob-up">Importar</button></div>
          <div class="ctx">txt, md, pdf ou docx. Vários arquivos (ex.: uma sessão por arquivo) entram em sequência.</div>` :
          `<div class="acoes"><button data-passo="${p.id}" ${p.id === proximo || p.feito ? '' : 'disabled'} class="${p.id === proximo ? 'primario' : ''}">${p.feito ? 'Refazer' : 'Rodar'}</button></div>`}
      </div></li>`).join('')}</ol>
      ${d.passos[0].feito && !d.passos.every((p) => p.feito) ? `<div class="campo"><b>Fazer tudo sozinho:</b> o app roda a leitura, a divisão em episódios, o guia e a bíblia em sequência (pode fechar esta tela).
        <div class="acoes"><button id="ob-auto" class="primario">${d.auto ? 'Rodando sozinho… (parar)' : 'Rodar todos os passos'}</button></div></div>` : ''}
      ${d.passos.every((p) => p.feito) ? `<div class="campo"><b>Obra pronta para o Ep. 01.</b> Próximo: Mesa (decidir as inconsistências do Ep. 01) → Elenco (vozes pedidas) → Texto.
        <div class="acoes"><button id="ob-mesa" class="primario">Ir para a Mesa</button></div></div>` : ''}`;
    if ($('#ob-auto')) $('#ob-auto').onclick = async () => {
      try { await api('/api/obra/auto', { obra: O.obra, ligado: !d.auto }); aviso(d.auto ? 'parado' : 'o app vai rodar os passos em sequência', true); carregar(); }
      catch (e) { aviso(e.message); }
    };
    $('#ob-passos').querySelectorAll('[data-passo]').forEach((b) => b.onclick = async () => {
      try { const r = await api(`/api/obra/${b.dataset.passo}`, { obra: O.obra }); aviso(`na fila (job ${r.job})`, true); } catch (e) { aviso(e.message); }
    });
    if ($('#ob-up')) $('#ob-up').onclick = async () => {
      const fs = [...$('#ob-arq').files];
      if (!fs.length) return aviso('Escolha o arquivo.');
      for (const f of fs) {
        try {
          const r = await fetch(`/api/obra/importar?obra=${encodeURIComponent(O.obra)}&nome=${encodeURIComponent(f.name)}`, { method: 'POST', body: await f.arrayBuffer() });
          const j = await r.json(); if (!r.ok || j.erro) throw new Error(j.erro);
          aviso(`${f.name}: importado (${j.linhas} linhas no total)`, true);
        } catch (e) { aviso(`${f.name}: ${e.message}`); }
      }
      carregar();
    };
    if ($('#ob-mesa')) $('#ob-mesa').onclick = () => { document.querySelector('#abas button[data-tela="mesa"]').click(); };
    const est = d.estrutura;
    $('#ob-est').innerHTML = est ? `<h2>Episódios <small>${est.episodios.length}</small></h2><table class="reg">${est.episodios.map((e) =>
      `<tr><td>${String(e.n).padStart(2, '0')}</td><td><b>${esc(e.titulo)}</b><div class="ctx">${esc(e.resumo)}</div></td><td class="ctx">L${e.inicio}–${e.fim}</td></tr>`).join('')}</table>
      ${est.observacoes?.length ? `<ul class="ctx">${est.observacoes.map((o) => `<li>${esc(o)}</li>`).join('')}</ul>` : ''}` : '<p class="ctx">A divisão em episódios aparece aqui depois da leitura.</p>';
  }

  async function carregar() {
    if (!O.obra) return;
    try { O.d = await api(`/api/obra?obra=${encodeURIComponent(O.obra)}`); } catch (e) { $('#ob-passos').innerHTML = `<div class="bloqueio">${esc(e.message)}</div>`; return; }
    desenhar();
  }
  window.ObraNova = { abrir(obra) { O.obra = obra; formulario(); carregar(); } };
})();
