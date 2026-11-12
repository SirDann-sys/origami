// Origami · Postagem: calendário da obra (o que postar, onde e quando) + agendamento no Postiz.
// Sugerir só PLANEJA. Nada vai para as redes sem o autor clicar em "Agendar" e confirmar. O Wattpad é lembrete (sem integração).
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const G = { obra: null, d: null, cx: null, mes: null, dia: null, sel: null, confirmar: null };
  const ROT = { tiktok: 'TikTok', instagram: 'Reels', shorts: 'Shorts', youtube: 'YouTube', wattpad: 'Wattpad' };
  const EST = { planejado: 'planejado', agendado: 'agendado no Postiz', publicado: 'publicado', erro: 'erro', feito_manual: 'feito à mão', pulado: 'pulado' };
  const SEM = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];
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
  const post = (acao, corpo) => api(`/api/postagem/${acao}`, { obra: G.obra, ...corpo });
  const peca = (x) => x.peca === 'completo' ? 'episódio completo' : x.peca === 'capitulo' ? 'capítulo' : `Parte ${x.peca.split(':')[1]}`;
  const iso = (dt) => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
  const br = (s) => { const [a, m, d] = s.split('-'); return `${d}/${m}`; };

  // ---------------- conexão com o Postiz
  function conexao() {
    const c = G.cx;
    if (!c) { $('#pg-conexao').innerHTML = '<p class="ctx">Conferindo o Postiz…</p>'; return; }
    if (!c.instalado) {        // sem o Postiz instalado: só o modo manual
      $('#pg-conexao').innerHTML = `<div class="ctx"><b>Modo manual.</b> O calendário mostra o que postar em cada dia, com o texto pronto para copiar e a pasta do vídeo.
        Poste pelo app ou pelo agendador de cada rede (YouTube Studio, Meta Business Suite, TikTok no computador) e marque como feito.</div>`;
      return;
    }
    if (!c.logado) {
      $('#pg-conexao').innerHTML = `<div class="ctx"><b>Modo manual.</b> O calendário mostra o que postar em cada dia, com o texto pronto para copiar e a pasta do vídeo.
        Poste pelo app ou pelo agendador de cada rede (YouTube Studio, Meta Business Suite, TikTok no computador) e marque como feito.</div>
        <details style="margin-top:10px"><summary class="ctx">Agendar automático pelo Postiz (pago)</summary>
        <ol class="pg-passos"><li>Crie sua conta em <b>postiz.com</b> e conecte lá o TikTok, o Instagram e o YouTube.</li>
        <li>Clique em <b>Conectar</b>: aparece um código; abra o endereço no navegador e confirme.</li></ol>
        <div class="acoes"><button id="pg-login">Conectar</button><button id="pg-recheck">Já confirmei</button></div><div id="pg-codigo"></div></details>`;
      $('#pg-login').onclick = async () => {
        try { const r = await post('login', {}); $('#pg-codigo').innerHTML = `<div class="campo"><div class="ctx">Código:</div><div class="pg-cod">${esc(r.codigo)}</div>
          <div class="ctx">Abra no navegador e digite o código:</div><pre>${esc(r.url)}</pre><button id="pg-copiar-url">Copiar endereço</button></div>`;
          $('#pg-copiar-url').onclick = () => navigator.clipboard.writeText(r.url).then(() => aviso('endereço copiado', true), () => aviso('selecione o endereço e copie'));
        } catch (e) { aviso(e.message); }
      };
      $('#pg-recheck').onclick = () => carregarConexao();
      return;
    }
    const tem = (redes) => c.canais.find((x) => redes.includes(x.rede) && !x.desativado);
    const linha = (nome, redes) => { const k = tem(redes); return `<li><span class="${k ? 'ok' : 'no'}">${k ? '✓' : '✗'}</span> ${nome} ${k ? `<small class="ctx">${esc(k.nome)}</small>` : '<small class="ctx">conecte no site do Postiz</small>'}</li>`; };
    $('#pg-conexao').innerHTML = `<div class="ctx">Postiz conectado.</div><ul class="pb-itens">
      ${linha('TikTok', ['tiktok'])}${linha('Instagram', ['instagram', 'instagram-standalone'])}${linha('YouTube (Shorts e completo)', ['youtube'])}
      <li><span class="no">·</span> Wattpad <small class="ctx">sem integração: fica como lembrete</small></li></ul>
      <div class="acoes"><button id="pg-recheck">Atualizar</button></div>`;
    $('#pg-recheck').onclick = () => carregarConexao();
  }

  // ---------------- sugerir calendário
  function sugerir() {
    const d = G.d;
    const prox = new Date(); prox.setDate(prox.getDate() + ((9 - prox.getDay()) % 7 || 7));   // próxima terça
    $('#pg-sugerir').innerHTML = `<div class="ar-form">
      <label>Dia 1 (estreia no YouTube e a Parte 1)</label><input type="date" id="pg-inicio" value="${iso(prox)}">
      <label>Episódios, em ordem</label><div class="chips">${d.episodios.map((e) => `<label class="chip"><input type="checkbox" value="${e}" checked> Ep. ${e}</label>`).join('')}</div>
      <label>Vídeo curto em</label><div class="chips">${['tiktok', 'instagram', 'shorts'].map((r) => `<label class="chip"><input type="checkbox" data-rede="${r}" ${d.config.redes_curtas.includes(r) ? 'checked' : ''}> ${ROT[r]}</label>`).join('')}</div>
      <label>Wattpad</label><select id="pg-wp"><option value="d0">todos os capítulos na véspera do Dia 1</option><option value="vespera">cada capítulo na véspera do seu episódio</option></select>
      <div class="ctx">Uma parte por dia: curtos às ${esc(d.config.hora_curtos)}, YouTube às ${esc(d.config.hora_youtube)}, Wattpad às ${esc(d.config.hora_wattpad)}.
        Itens que você editou, adicionou ou que já foram agendados não mudam.</div>
      <div class="acoes"><button id="pg-sug" class="primario">Sugerir calendário</button></div></div>`;
    $('#pg-sug').onclick = async () => {
      const eps = [...$('#pg-sugerir').querySelectorAll('input[type=checkbox][value]')].filter((x) => x.checked).map((x) => x.value);
      const redes = [...$('#pg-sugerir').querySelectorAll('input[data-rede]')].filter((x) => x.checked).map((x) => x.dataset.rede);
      try { const r = await post('sugerir', { inicio: $('#pg-inicio').value, eps, redes, wattpad: $('#pg-wp').value });
        aviso(`${r.novos} post(s) planejado(s)${r.mantidos ? ` · ${r.mantidos} mantido(s)` : ''}`, true);
        G.mes = $('#pg-inicio').value.slice(0, 7); carregar(); }
      catch (e) { aviso(e.message); }
    };
  }

  // ---------------- barra de ações
  function barra() {
    const pl = G.d.itens.filter((x) => x.estado === 'planejado' && x.integravel && !x.atrasado);
    const at = G.d.itens.filter((x) => x.atrasado).length;
    const n = (e) => G.d.itens.filter((x) => x.estado === e).length;
    $('#pg-barra').innerHTML = `<button id="pg-ant">‹</button><b id="pg-mes-nome"></b><button id="pg-prox">›</button>
      <span class="pg-resumo">${n('planejado')} planejado · ${n('agendado')} agendado · ${n('publicado') + n('feito_manual')} feito${at ? ` · <span class="alerta">${at} atrasado(s)</span>` : ''}</span>
      ${G.cx && G.cx.logado ? `<button id="pg-sinc">Atualizar status</button><button id="pg-agendar" class="primario" ${pl.length ? '' : 'disabled'}>Agendar ${pl.length} planejado(s)</button>` : '<span class="ctx">modo manual: você posta e marca como feito</span>'}`;
    $('#pg-ant').onclick = () => { G.mes = mesDesloc(-1); grade(); };
    $('#pg-prox').onclick = () => { G.mes = mesDesloc(1); grade(); };
    if (!$('#pg-sinc')) return;
    $('#pg-sinc').onclick = async () => { try { const r = await post('sincronizar', {}); aviso(`status atualizado (${r.mudou} mudança(s))`, true); carregar(); } catch (e) { aviso(e.message); } };
    $('#pg-agendar').onclick = () => confirmar(pl.map((x) => x.id), `Agendar ${pl.length} post(s) no Postiz? Os vídeos sobem uma vez cada e vão para as redes nas datas do calendário.`);
  }
  function confirmar(ids, texto) {
    const box = $('#pg-confirma');
    box.hidden = false;
    box.innerHTML = `<div class="campo"><b>${esc(texto)}</b><div class="ctx">Rótulo de IA: confira nos ajustes de cada rede (TikTok, Instagram, YouTube) antes da primeira vez.</div>
      <div class="acoes"><button id="pg-sim" class="primario">Confirmar e agendar</button><button id="pg-nao">Voltar</button></div></div>`;
    $('#pg-nao').onclick = () => { box.hidden = true; };
    $('#pg-sim').onclick = async () => {
      box.hidden = true;
      try { const r = await post('agendar', { ids }); aviso(`na fila do motor (job ${r.job}): enviando e agendando`, true); } catch (e) { aviso(e.message); }
    };
  }
  function mesDesloc(k) { const [a, m] = G.mes.split('-').map(Number); const d = new Date(a, m - 1 + k, 1); return iso(d).slice(0, 7); }

  // ---------------- grade do mês (arrastar = mover de dia)
  function grade() {
    const [a, m] = G.mes.split('-').map(Number);
    $('#pg-mes-nome').textContent = new Date(a, m - 1, 1).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
    const ini = new Date(a, m - 1, 1); ini.setDate(1 - ini.getDay());
    let h = SEM.map((s) => `<div class="pg-sem">${s}</div>`).join('');
    for (let i = 0; i < 42; i++) {
      const dt = new Date(ini); dt.setDate(ini.getDate() + i); const k = iso(dt);
      const its = G.d.itens.filter((x) => x.data === k);
      h += `<div class="pg-dia ${dt.getMonth() !== m - 1 ? 'fora' : ''} ${k === G.d.hoje ? 'hoje' : ''} ${k === G.dia ? 'on' : ''}" data-d="${k}">
        <span class="n">${dt.getDate()}</span>${its.map((x) => `<span class="pg-chip ${x.rede} ${x.estado} ${x.atrasado ? 'atrasado' : ''}" draggable="${x.estado === 'planejado'}" data-id="${x.id}"
          title="${esc(`Ep. ${x.ep} · ${peca(x)} · ${ROT[x.rede]} · ${x.hora} · ${EST[x.estado]}`)}">${x.estado === 'publicado' || x.estado === 'feito_manual' ? '✓ ' : ''}${ROT[x.rede]} ${x.peca === 'completo' ? 'Ep' + x.ep : x.peca === 'capitulo' ? 'Cap' + Number(x.ep) : x.ep + '·P' + x.peca.split(':')[1]}</span>`).join('')}</div>`;
    }
    $('#pg-grade').innerHTML = h;
    $('#pg-grade').querySelectorAll('.pg-dia').forEach((el) => {
      el.onclick = (e) => { G.dia = el.dataset.d; G.sel = e.target.dataset.id || null; grade(); lado(); };
      el.ondragover = (e) => { e.preventDefault(); el.classList.add('alvo'); };
      el.ondragleave = () => el.classList.remove('alvo');
      el.ondrop = async (e) => {
        e.preventDefault(); el.classList.remove('alvo');
        const id = e.dataTransfer.getData('text/plain'); if (!id) return;
        try { await post('mover', { id, data: el.dataset.d }); G.dia = el.dataset.d; G.sel = id; carregar(); } catch (er) { aviso(er.message); }
      };
    });
    $('#pg-grade').querySelectorAll('.pg-chip[draggable=true]').forEach((c) => c.ondragstart = (e) => e.dataTransfer.setData('text/plain', c.dataset.id));
  }

  // ---------------- dia escolhido e editor do post
  function lado() {
    if (!G.dia) { $('#pg-lado').innerHTML = '<p class="ctx">Clique num dia do calendário.</p>'; return; }
    const its = G.d.itens.filter((x) => x.data === G.dia);
    const dt = new Date(G.dia + 'T12:00:00');
    let h = `<h2>${dt.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: '2-digit' })}</h2>`;
    h += its.map((x) => `<div class="pg-item ${x.id === G.sel ? 'on' : ''}" data-id="${x.id}"><span class="pg-chip ${x.rede} ${x.estado}">${ROT[x.rede]}</span>
      <b>${x.hora}</b> Ep. ${x.ep} · ${peca(x)} <small class="ctx">${EST[x.estado]}${x.erro ? ' · ⚠ ' + esc(x.erro) : ''}</small></div>`).join('') || '<p class="ctx">Nada neste dia.</p>';
    h += `<div class="acoes"><button id="pg-novo">+ Post neste dia</button></div><div id="pg-editor"></div>`;
    $('#pg-lado').innerHTML = h;
    $('#pg-lado').querySelectorAll('.pg-item').forEach((el) => el.onclick = () => { G.sel = el.dataset.id; lado(); });
    $('#pg-novo').onclick = () => editor(null);
    if (G.sel) editor(G.d.itens.find((x) => x.id === G.sel));
  }
  const opcoesPartes = (ep) => Array.from({ length: (G.d.partes || {})[ep] || 8 }, (_, i) => i + 1)
    .map((n) => `<option value="parte:${n}" ${n === 1 ? 'selected' : ''}>Parte ${n}</option>`).join('');
  function editor(x) {
    const novo = !x;
    x = x || { data: G.dia, hora: G.d.config.hora_curtos, ep: G.d.episodios[0], peca: 'parte:1', rede: 'tiktok', estado: 'planejado', titulo_final: '', texto_final: '', arquivos: {}, integravel: true };
    const trava = x.estado === 'agendado' || x.estado === 'publicado';
    const arqs = Object.entries(x.arquivos || {}).filter(([, v]) => v).map(([k, v]) => `<div class="pg-arq"><span class="ctx">${k}</span> <code>${esc(v.split(/[\\/]/).pop())}</code> <button data-abrir="${esc(v)}">Abrir pasta</button></div>`).join('');
    $('#pg-editor').innerHTML = `<div class="ar-form">
      <div class="linha"><input type="date" id="pe-data" value="${x.data}" ${trava ? 'disabled' : ''}><input type="time" id="pe-hora" value="${x.hora}" ${trava ? 'disabled' : ''}></div>
      ${novo ? `<div class="linha"><select id="pe-rede">${Object.keys(ROT).map((r) => `<option value="${r}">${ROT[r]}</option>`).join('')}</select>
        <select id="pe-ep">${G.d.episodios.map((e) => `<option>${e}</option>`).join('')}</select>
        <select id="pe-peca"><option value="completo">episódio completo</option><option value="capitulo">capítulo (Wattpad)</option>${opcoesPartes(G.d.episodios[0])}</select></div>`
        : `<div class="ctx">${ROT[x.rede]} · Ep. ${x.ep} · ${peca(x)} · <b>${EST[x.estado]}</b>${x.link ? ` · <a href="${esc(x.link)}" target="_blank">ver post</a>` : ''}</div>`}
      ${x.rede === 'youtube' || x.rede === 'shorts' || novo ? `<label>Título</label><input type="text" id="pe-titulo" value="${esc(x.titulo_final)}" ${trava ? 'disabled' : ''}>` : ''}
      <label>Texto do post <button id="pe-copiar" style="padding:0 8px">Copiar</button></label><textarea id="pe-texto" rows="7" ${trava ? 'disabled' : ''}>${esc(x.texto_final)}</textarea>
      ${arqs}
      ${x.erro ? `<div class="bloqueio">${esc(x.erro)}</div>` : ''}
      <div class="acoes">${trava ? '' : '<button id="pe-salvar">Salvar</button>'}
        ${!novo && x.estado === 'planejado' && x.integravel && G.cx && G.cx.logado ? '<button id="pe-agendar" class="primario">Agendar este</button>' : ''}
        ${x.estado === 'agendado' ? '<button id="pe-cancelar">Cancelar agendamento</button>' : ''}
        ${!novo && x.estado === 'planejado' ? '<button id="pe-feito">Marcar feito à mão</button><button id="pe-pular">Pular</button><button id="pe-excluir">Excluir</button>' : ''}
        ${!novo && (x.estado === 'feito_manual' || x.estado === 'pulado') ? '<button id="pe-voltar">Voltar para planejado</button>' : ''}</div></div>`;
    const ed = $('#pg-editor');
    ed.querySelectorAll('[data-abrir]').forEach((b) => b.onclick = () => post('abrir', { caminho: b.dataset.abrir }).catch((e) => aviso(e.message)));
    $('#pe-copiar').onclick = (e) => { e.preventDefault(); navigator.clipboard.writeText($('#pe-texto').value).then(() => aviso('texto copiado', true), () => aviso('selecione o texto e copie')); };
    const acao = async (fn, ok) => { try { await fn(); if (ok) aviso(ok, true); carregar(); } catch (e) { aviso(e.message); } };
    if ($('#pe-salvar')) $('#pe-salvar').onclick = () => acao(async () => {
      const item = { data: $('#pe-data').value, hora: $('#pe-hora').value, texto: $('#pe-texto').value };
      if ($('#pe-titulo')) item.titulo = $('#pe-titulo').value;
      if (novo) Object.assign(item, { rede: $('#pe-rede').value, ep: $('#pe-ep').value, peca: $('#pe-peca').value }); else item.id = x.id;
      const r = await post('item', { item }); G.sel = r.id; G.dia = item.data;
    }, 'salvo');
    if ($('#pe-agendar')) $('#pe-agendar').onclick = () => confirmar([x.id], `Agendar ${ROT[x.rede]} · Ep. ${x.ep} · ${peca(x)} para ${br(x.data)} às ${x.hora}?`);
    if ($('#pe-cancelar')) $('#pe-cancelar').onclick = () => acao(() => post('cancelar', { id: x.id }), 'agendamento cancelado no Postiz');
    if ($('#pe-ep')) $('#pe-ep').onchange = () => {   // as partes seguem o episódio escolhido
      const sel = $('#pe-peca'), v = sel.value;
      sel.innerHTML = '<option value="completo">episódio completo</option><option value="capitulo">capítulo (Wattpad)</option>' + opcoesPartes($('#pe-ep').value);
      if ([...sel.options].some((o) => o.value === v)) sel.value = v;
    };
    if ($('#pe-feito')) {
      $('#pe-feito').insertAdjacentHTML('beforebegin', '<input type="text" id="pe-link" placeholder="link do post (opcional)" style="flex:1;min-width:160px">');
      $('#pe-feito').onclick = () => acao(() => post('marcar', { id: x.id, estado: 'feito_manual', link: ($('#pe-link').value || '').trim() }), 'marcado como postado');
    }
    if ($('#pe-pular')) $('#pe-pular').onclick = () => acao(() => post('marcar', { id: x.id, estado: 'pulado' }), 'pulado');
    if ($('#pe-voltar')) $('#pe-voltar').onclick = () => acao(() => post('marcar', { id: x.id, estado: 'planejado' }));
    if ($('#pe-excluir')) $('#pe-excluir').onclick = () => acao(async () => { await post('excluir', { id: x.id }); G.sel = null; }, 'excluído');
  }

  // ---------------- carregar
  async function carregarConexao() { G.cx = null; conexao(); try { G.cx = await api('/api/postagem/conexao'); } catch (e) { G.cx = { instalado: true, logado: false, erro: e.message, canais: [] }; } conexao(); if (G.d) { barra(); lado(); } }
  async function carregar() {
    try { G.d = await api(`/api/postagem?obra=${encodeURIComponent(G.obra)}`); }
    catch (e) { $('#pg-lado').innerHTML = `<div class="bloqueio">${esc(e.message)}</div>`; return; }
    if (!G.mes) { const prox = G.d.itens.find((x) => x.data >= G.d.hoje); G.mes = (prox ? prox.data : G.d.hoje).slice(0, 7); }
    if (!$('#pg-sugerir').innerHTML) sugerir();
    barra(); grade(); lado();
  }
  window.Postagem = { abrir(obra) { if (obra !== G.obra) { G.mes = null; G.dia = null; G.sel = null; $('#pg-sugerir').innerHTML = ''; } G.obra = obra; carregar(); carregarConexao(); } };
})();
