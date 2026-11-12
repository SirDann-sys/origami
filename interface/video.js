// Origami · Revisão de vídeo. Assistir a parte, pausar no problema, marcar com nota e tipo; checagens automáticas ao lado.
// A marca vira ação: "onde corrigir" leva à imagem (cenário/retrato daquele segundo) ou à fala (revisão de áudio).
// Prévia em quadros: os momentos críticos (troca de falante e de cenário, começo, cartão final) sem renderizar o vídeo.
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const tf = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`;
  const V = { obra: null, ep: null, parte: 1, d: null };
  const vid = $('#vd-video');

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
  const irTela = (t) => document.querySelector(`#abas button[data-tela="${t}"]`)?.click();

  async function ondeCorrigir(id, li) {
    let a;
    try { a = await api('/api/marca/acao', { obra: V.obra, ep: V.ep, id }); } catch (e) { return aviso(e.message); }
    const caixa = document.createElement('div'); caixa.className = 'campo'; caixa.style.marginTop = '6px';
    const botoes = [];
    if (a.marca.tipo === 'legenda') botoes.push(`<button data-ir="legenda" class="primario">Refazer a legenda da Parte ${a.parte}</button>`);
    if (a.fala) botoes.push(`<button data-ir="fala">Fala ${esc(a.fala)} (${esc(a.voz)}) na revisão de áudio</button>`);
    if (a.fundo) botoes.push(`<button data-ir="fundo">Cenário ${esc(a.fundo)}</button>`);
    if (a.retrato) botoes.push(`<button data-ir="retrato">Retrato ${esc(a.retrato)}</button>`);
    caixa.innerHTML = `<div class="ctx">${a.marca.parte === 0 ? `No 16:9 isso é a <b>Parte ${a.parte}</b>, em ${tf(a.t)}. ` : ''}Naquele segundo: ${a.fala ? `fala <b>${esc(a.fala)}</b>` : 'sem fala'}${a.fundo ? `, cenário <b>${esc(a.fundo)}</b>` : ''}.</div>
      ${a.marca.tipo === 'regra visual' ? '<div class="ctx">Regra visual (layout, luz, cor) muda o modelo do vídeo para todos os episódios: peça ao Claude e ela vale para a série.</div>' : ''}
      <div class="acoes">${botoes.join('')}</div>`;
    li.after(caixa);
    caixa.querySelectorAll('[data-ir]').forEach((b) => b.onclick = (e) => {
      e.stopPropagation();
      if (b.dataset.ir === 'legenda') {
        api('/api/marca/legenda', { obra: V.obra, ep: V.ep, parte: a.parte })
          .then((r) => aviso(`na fila (jobs ${r.jobs.join(', ')}): realinhar as palavras e refazer o vídeo da parte`, true)).catch((er) => aviso(er.message));
        return;
      }
      if (b.dataset.ir === 'fala') { irTela('revisao'); window.Revisao.irPara(V.obra, V.ep, a.parte, a.fala); return; }
      const alvo = b.dataset.ir === 'fundo' ? a.fundo : a.retrato;
      if (b.dataset.ir === 'fundo' && !a.fundo_deste_ep) aviso(`${alvo} é da biblioteca da série (veio de outro episódio): trocar muda os episódios que o usam.`);
      irTela('imagens'); window.Imagens.irPara(V.obra, V.ep, alvo);
    });
  }

  function desenhar() {
    const d = V.d;
    $('#vd-partes').innerHTML = d.partes.map((n) => `<button class="${n === V.parte ? 'on' : ''}" data-n="${n}">Parte ${n}</button>`).join('')
      + `<button class="${V.parte === 0 ? 'on' : ''}" data-n="0">Episódio 16:9</button>`;
    $('#vd-gerar-previa').disabled = V.parte === 0;          // prévia em quadros é por parte
    $('#vd-partes').querySelectorAll('button').forEach((b) => b.onclick = () => { V.parte = +b.dataset.n; carregar(true); });
    $('#vd-marcas').innerHTML = d.marcas.map((m) => `<li class="${m.estado}" data-t="${m.t}" data-id="${m.id}"><span class="t">${tf(m.t)}</span>
      <b>${esc(m.tipo)}</b> · ${esc(m.nota)}
      ${m.estado === 'aberta' ? '<span style="float:right"><button data-onde="1">onde corrigir</button> <button data-res="1">resolvida</button> <button data-apagar="1" title="marca criada sem querer">apagar</button></span>' : '<small class="ctx">✓</small>'}</li>`).join('')
      || '<li class="ctx" style="cursor:default">Nenhuma marca.</li>';
    $('#vd-marcas').querySelectorAll('li[data-t]').forEach((li) => li.onclick = async (e) => {
      if (e.target.dataset.apagar) {
        try { await api('/api/marca/apagar', { obra: V.obra, ep: V.ep, id: li.dataset.id }); carregar(false); } catch (er) { aviso(er.message); }
        return;
      }
      if (e.target.dataset.res) {
        try { await api('/api/marca/resolver', { obra: V.obra, ep: V.ep, id: li.dataset.id }); carregar(false); } catch (er) { aviso(er.message); }
        return;
      }
      if (e.target.dataset.onde) { if (!li.nextElementSibling || !li.nextElementSibling.classList.contains('campo')) ondeCorrigir(li.dataset.id, li); return; }
      vid.currentTime = +li.dataset.t; vid.pause();
    });
    $('#vd-checks').innerHTML = d.checagens.map((c) => `<li><span class="s ${c.ok === true ? 'ok' : c.ok === false ? 'no' : ''}">${c.ok === true ? '✓' : c.ok === false ? '⚠' : '·'}</span>
      <b>${esc(c.nome)}</b>: ${esc(c.msg)}</li>`).join('');
    const q = d.previa || [];
    $('#vd-previa').innerHTML = q.length ? q.map((p) => {
      const t = (p.match(/_t(-?[\d.]+)\.png$/) || [])[1];
      return `<figure><img src="/arquivo?c=${encodeURIComponent(p)}&v=${Date.now() % 1e5}" loading="lazy"><figcaption>${t ? tf(+t) : ''}</figcaption></figure>`;
    }).join('') : '<p class="ctx">Sem prévia ainda.</p>';
  }

  async function carregar(trocarVideo) {
    try { V.d = await api(`/api/video?obra=${encodeURIComponent(V.obra)}&ep=${V.ep}&parte=${V.parte}`); }
    catch (e) {
      vid.pause(); vid.removeAttribute('src'); vid.load(); V.d = null;
      $('#vd-partes').innerHTML = ''; $('#vd-marcas').innerHTML = ''; $('#vd-checks').innerHTML = ''; $('#vd-previa').innerHTML = '';
      $('#vd-checks').innerHTML = `<li><div class="bloqueio">Ep. ${esc(V.ep)}: ainda não há vídeo. ${esc(e.message.replace(/^\w+Error: /, ''))}</div></li>`;
      return;
    }
    if (trocarVideo) vid.src = V.d.existe ? `/arquivo?c=${encodeURIComponent(V.d.video)}` : '';
    desenhar();
  }

  vid.ontimeupdate = () => ($('#vd-t').textContent = tf(vid.currentTime || 0));
  $('#vd-marcar').onclick = async () => {
    const nota = $('#vd-nota').value.trim();
    if (!nota) return aviso('Escreva o que está errado nesse ponto.');
    vid.pause();
    try {
      await api('/api/marca/nova', { obra: V.obra, ep: V.ep, parte: V.parte, t: vid.currentTime, nota, tipo: $('#vd-tipo').value });
      $('#vd-nota').value = ''; aviso('marca salva', true); carregar(false);
    } catch (e) { aviso(e.message); }
  };
  $('#vd-gerar-previa').onclick = async () => {
    try { const r = await api('/api/marca/previa', { obra: V.obra, ep: V.ep, parte: V.parte }); aviso(`prévia na fila (job ${r.job}): ~1 min`, true); }
    catch (e) { aviso(e.message); }
  };
  window.Video = { abrir(obra, ep) { if (obra !== V.obra || ep !== V.ep) V.parte = 1; V.obra = obra; V.ep = ep; carregar(true); },
    atualizar(obra, ep) { if (obra !== V.obra || ep !== V.ep) return this.abrir(obra, ep); carregar(!V.d || !V.d.existe); } };
})();
