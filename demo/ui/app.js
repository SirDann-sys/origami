// Origami · Mesa do episódio. Um episódio por vez: mapa (guia) · decisões (uma a uma) · etapas (estado do motor).
'use strict';
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const estado = { obra: null, ep: null, dados: null, escolhas: {} };

async function api(caminho, corpo) {
  const r = await fetch(caminho, corpo ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) } : {});
  const j = await r.json();
  if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
  return j;
}

function aviso(txt, info = false) {
  const d = document.createElement('div');
  d.className = 'aviso' + (info ? ' info' : '');
  d.textContent = txt;
  $('#avisos').appendChild(d);
  setTimeout(() => d.remove(), info ? 3500 : 9000);
}

// markdown mínimo do guia: títulos, negrito, itálico, listas
function md(txt) {
  const inl = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|\W)\*(?!\s)(.+?)\*(?=\W|$)/g, '$1<i>$2</i>');
  let html = '', lista = false;
  for (const l of txt.split('\n')) {
    const item = l.match(/^\s*-\s+(.*)/);
    if (item) { if (!lista) { html += '<ul>'; lista = true; } html += `<li>${inl(item[1])}</li>`; continue; }
    if (lista) { html += '</ul>'; lista = false; }
    if (/^##?\s/.test(l)) html += `<h2>${inl(l.replace(/^##?\s+/, ''))}</h2>`;
    else if (l.trim()) html += `<p>${inl(l)}</p>`;
  }
  return html + (lista ? '</ul>' : '');
}

function desenharEpisodios() {
  const eps = estado.dados.episodios;
  $('#eps').innerHTML = eps.map((e) => `
    <div class="ep ${e.ep === estado.ep ? 'on' : ''} ${e.status === 'publicado' ? 'publicado' : ''}" data-ep="${e.ep}" title="${esc(e.titulo)} · ${esc(e.status)}">
      ${e.ep}${e.pendentes ? `<span class="n">${e.pendentes}</span>` : ''}</div>`).join('');
  $('#eps').querySelectorAll('.ep').forEach((el) => el.onclick = () => abrir(estado.obra, el.dataset.ep));
}

function desenharDecisoes() {
  const ds = estado.dados.decisoes;
  const pend = ds.filter((d) => d.estado === 'pendente').length;
  $('#dec-resumo').textContent = ds.length ? `${pend} pendente(s) de ${ds.length}` : '';
  if (!ds.length) { $('#decisoes').innerHTML = '<p class="ctx">Nenhuma decisão cai neste episódio.</p>'; return; }
  // pendentes primeiro, uma a uma (a primeira aberta)
  const ordem = [...ds].sort((a, b) => (a.estado === 'pendente' ? 0 : 1) - (b.estado === 'pendente' ? 0 : 1));
  $('#decisoes').innerHTML = ordem.map((d) => {
    const cab = `<div class="topo"><span class="tag ${d.tipo}">${d.tipo === 'producao' ? 'produção' : 'inconsistência'}</span><b>${esc(d.id)}</b></div>
      <div class="tit">${esc(d.titulo)}</div>`;
    if (d.estado !== 'pendente') {
      return `<div class="card ${d.estado}">${cab}<p class="decisao-final">${d.estado === 'adiado' ? 'Adiado' : 'Decidido'}: <b>${esc(d.decisao)}</b>
        ${d.nota ? ` — ${esc(d.nota)}` : ''} <small class="ctx">(${esc(d.data)})</small></p></div>`;
    }
    const ops = d.opcoes.map((o, i) => `
      <label class="opcao"><input type="radio" name="op-${d.id}" value="${esc(o)}" ${i === (d.recomendada ?? 0) ? 'checked' : ''}>
        <span>${esc(o)}${i === d.recomendada ? '<span class="rec">★ recomendado</span>' : ''}</span></label>`).join('');
    return `<div class="card pendente" data-id="${d.id}">${cab}<div class="ctx">${esc(d.contexto)}</div>
      ${d.recomendacao ? `<div class="recomendacao">★ ${esc(d.recomendacao)}</div>` : ''}
      ${ops}<textarea placeholder="Nota (opcional; ex.: o nome novo, se escolheu digitar)"></textarea>
      <div class="acoes"><button class="primario" data-acao="decidir">Decidir</button><button data-acao="adiar">Adiar</button></div></div>`;
  }).join('');
  $('#decisoes').querySelectorAll('.card.pendente').forEach((card) => {
    card.querySelectorAll('button').forEach((b) => b.onclick = async () => {
      const id = card.dataset.id;
      const escolha = card.querySelector('input[type=radio]:checked').value;
      const nota = card.querySelector('textarea').value.trim();
      try {
        await api('/api/decidir', { obra: estado.obra, id, escolha, nota, adiar: b.dataset.acao === 'adiar' });
        aviso(`${id}: ${b.dataset.acao === 'adiar' ? 'adiado' : 'decidido'}`, true);
        abrir(estado.obra, estado.ep);
      } catch (e) { aviso(e.message); }
    });
  });
}

function classe(est) {
  if (/^(em dia|pronto|aprovado|publicado)/.test(est)) return 'ok';
  if (/^código novo/.test(est)) return 'novo';
  if (/^falta/.test(est)) return 'falta';
  if (/^(aguardando|a fazer|sob pedido|fora da demonstração)/.test(est)) return 'espera';
  return 'refazer';
}

function desenharEtapas() {
  const d = estado.dados;
  const pend = d.decisoes.filter((x) => x.estado === 'pendente').length;
  const blq = pend ? `<div class="bloqueio">${pend} decisão(ões) pendente(s): o texto-mestre só avança depois delas (ou de adiá-las).</div>` : '';
  const prod = d.publicado ? '<p class="ctx">Episódio publicado.</p>' : d.prontidao.length
    ? `<div class="campo"><b>Para produzir falta:</b><ul>${d.prontidao.map((x) => `<li>${esc(x)}</li>`).join('')}</ul><button disabled>Produzir episódio</button></div>`
    : `<div class="campo"><b>Tudo pronto.</b> Áudio, trilha, mix, vídeos, capas e Wattpad na fila (só o que mudou é refeito).<div class="acoes"><button id="produzir" class="primario">Produzir episódio</button></div></div>`;
  $('#etapas').innerHTML = blq + prod + d.etapas.map((e) => `
    <li ${e.tela ? `data-tela="${e.tela}" style="cursor:pointer" title="abrir"` : ''}><span class="ponto ${classe(e.estado)}"></span><div><div class="nome">${esc(e.nome)}${e.tela ? ' ›' : ''}</div>
      <div class="est">${esc(e.estado)}</div><div class="quem">${esc(e.quem)}</div>
      ${e.codigo_novo && !d.publicado ? `<button class="aplicar" data-etapa="${e.id}" title="O programa desta etapa foi melhorado, mas o que ela usa não mudou. Aplicar refaz esta etapa e o que depender dela.">Aplicar o código novo</button>` : ''}</div></li>`).join('');
  $('#etapas').querySelectorAll('li[data-tela]').forEach((li) => li.onclick = () => trocarTela(li.dataset.tela));
  $('#etapas').querySelectorAll('button.aplicar').forEach((b) => b.onclick = async (ev) => {
    ev.stopPropagation();
    const t = b.dataset.etapa;
    if (!b.dataset.ok) {          // 2 cliques: refazer pode levar horas (vídeos)
      b.dataset.ok = '1'; b.textContent = 'Confirmar: refazer agora?';
      setTimeout(() => { delete b.dataset.ok; b.textContent = 'Aplicar o código novo'; }, 5000);
      return;
    }
    try { const r = await api('/produzir', { obra: estado.obra, ep: estado.ep, de: t, forcar: [t] });
      aviso(`código novo de "${t}" na fila: jobs ${r.jobs[0]}–${r.jobs[r.jobs.length - 1]} (só o que depender da mudança é refeito)`, true); }
    catch (e) { aviso(e.message); }
  });
  if ($('#produzir')) $('#produzir').onclick = async () => {
    try { const r = await api('/produzir', { obra: estado.obra, ep: estado.ep });
      aviso(`produção na fila: jobs ${r.jobs[0]}–${r.jobs[r.jobs.length - 1]}` + (r.audio_aprovado ? ''
        : '. A legenda e os vídeos esperam você ouvir e aprovar o áudio na Revisão de áudio.'), true); }
    catch (e) { aviso(e.message); }
  };
}

// telas → módulo que as desenha. "abrir" recarrega; "atualizar" (se existir) só traz dados novos sem mexer no que está
// na tela (posição do áudio/vídeo, edição em curso)
const MODULOS = { texto: ['Texto', 'Ajustes'], elenco: ['Elenco', 'Pronuncia'], revisao: ['Revisao', 'Ajustes'], arte: ['Arte', 'Ajustes'], imagens: ['Imagens'],
  video: ['Video', 'Ajustes'], pub: ['Pub', 'Ajustes'], postagem: ['Postagem', 'Ajustes'], fila: ['Fila'], obranova: ['ObraNova'] };
const SO_OBRA = { Pronuncia: 1, Postagem: 1, Fila: 1 };
function abrirModulo(nome, obra, ep, auto) {
  const m = window[nome];
  if (!m) return;
  if (nome === 'ObraNova') return m.abrir(document.querySelector('#obra').value);
  const f = auto && m.atualizar ? m.atualizar : m.abrir;
  return SO_OBRA[nome] ? f.call(m, obra) : f.call(m, obra, ep);
}

// O fim de um job não recarrega a tela em que você está mexendo (edição de texto, áudio ou vídeo tocando):
// aparece "Há resultados novos".
function telaOcupada(id) {
  const el = document.getElementById(id);
  if (!el) return false;
  if ((MODULOS[id] || []).some((n) => window[n]?.ocupado?.())) return true;
  if (el.dataset.sujo === '1') return true;
  if ([...el.querySelectorAll('audio,video')].some((x) => !x.paused && !x.ended)) return true;
  const a = document.activeElement;
  return el.contains(a) && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) && a.type !== 'range';
}
function avisoNovidade(id) {
  const el = document.getElementById(id);
  if (!el || el.querySelector('.novidade')) return;
  const b = document.createElement('div');
  b.className = 'novidade';
  b.innerHTML = 'Há resultados novos para esta tela. <button>Atualizar agora</button> <span class="ctx">(o que você está editando ou ouvindo continua até você clicar)</span>';
  b.querySelector('button').onclick = () => { b.remove(); delete el.dataset.sujo; (MODULOS[id] || []).forEach((n) => abrirModulo(n, estado.obra, estado.ep, false)); };
  el.prepend(b);
}
document.addEventListener('input', (e) => {           // marca a tela como "em edição" ao digitar nela
  const t = e.target.closest('main.tela');
  if (t && e.target.type !== 'range') t.dataset.sujo = '1';
}, true);

async function abrir(obra, ep, auto = false) {
  estado.obra = obra; estado.ep = ep;
  try { estado.dados = await api(`/api/mesa?obra=${encodeURIComponent(obra)}&ep=${ep}`); }
  catch (e) { return aviso(e.message); }
  $('#mapa').innerHTML = md(estado.dados.mapa || '_Sem entrada no guia para este episódio._');
  $('#regras').innerHTML = estado.dados.regras.map((r) => `<li>${esc(r)}</li>`).join('');
  desenharEpisodios(); desenharDecisoes(); desenharEtapas();
  const aberta = document.querySelector('main.tela.on')?.id;
  if (aberta && MODULOS[aberta]) {
    if (auto && telaOcupada(aberta)) avisoNovidade(aberta);
    else {
      const el = document.getElementById(aberta);
      delete el.dataset.sujo; el.querySelector('.novidade')?.remove();
      MODULOS[aberta].forEach((n) => abrirModulo(n, obra, ep, auto));
    }
  }
  if (window.Pendencias) window.Pendencias.atualizar(obra, ep);
  try { localStorage.setItem('origami.ultimo', JSON.stringify({ obra, ep })); } catch {}
}

// ---------- o que o motor está fazendo agora (faixa no topo + atualização automática ao terminar)
const FRASES = {
  mestre: 'O Opus está escrevendo o texto-mestre', revisar: 'O Opus está ajustando o texto (só o que você pediu)', alarme: 'O revisor está conferindo a continuidade', corrigir: 'O Opus está corrigindo os trechos apontados',
  roteiro: 'O Opus está montando o roteiro de áudio', kit: 'O Opus está escrevendo o kit de postagem', cenas: 'O Opus está sugerindo cenas e ganchos',
  sincronizar: 'Conferindo o roteiro', voz: 'Gravando as falas (VoiceStudio)', montar: 'Montando as partes', cue: 'Compondo a trilha', stems: 'Gerando os instrumentos',
  mix: 'Mixando', episodio: 'Juntando o episódio completo', tempos: 'Marcando o tempo de cada palavra', video: 'Renderizando os vídeos 9:16',
  video16x9: 'Renderizando o episódio 16:9', capas: 'Montando capas e miniatura', wattpad: 'Gerando o capítulo do Wattpad', entregar: 'Copiando a entrega',
  triagem: 'O Opus está conferindo as imagens geradas', obra: 'Preparando a obra nova', piloto: 'Piloto automático', pendencia: 'Pendência',
  imagens: 'Gerando imagens do vídeo', postagem: 'Enviando vídeos e agendando no Postiz', arte: 'Gerando imagens das cenas', elenco: 'Gerando candidatas de voz', amostra: 'Gerando a amostra de pronúncia',
};
const TEMPO_TIPICO = { mestre: '2 a 5 min', revisar: '2 a 4 min', alarme: '1 a 2 min', corrigir: '1 a 2 min', roteiro: '2 a 4 min', kit: '1 a 2 min', cenas: '1 a 3 min',
  triagem: '1 a 2 min por cena', voz: '~15 s por fala', video: '~5 min por parte', video16x9: '30 a 50 min', elenco: '~1 min por candidata', imagens: '~20 s por imagem', arte: '~20 s por imagem' };
estado.job = null; estado.jobDesde = 0;
function faixa() {
  let f = document.querySelector('#faixa-motor');
  if (!f) { f = document.createElement('div'); f.id = 'faixa-motor'; document.body.insertBefore(f, document.querySelector('header').nextSibling); }
  return f;
}
// aviso do Windows (canto da tela), para quando o app está atrás de outra janela
function notificar(titulo, corpo) {
  try {
    if (!('Notification' in window)) return;
    if (Notification.permission === 'default') Notification.requestPermission();
    if (Notification.permission === 'granted') {
      const n = new Notification(titulo, { body: corpo, icon: '/ui/origami.svg', silent: false });
      n.onclick = () => window.focus();
    }
  } catch {}
}
window.notificar = notificar;
window.avisoMotor = (txt) => { aviso(txt); notificar('Origami', txt); };   // chamado pela janela (motor religado)
// trabalhos longos: avisar no Windows também quando dão certo
const AVISA_PRONTO = new Set(['mestre', 'roteiro', 'voz', 'episodio', 'video', 'video16x9', 'capas', 'entregar', 'kit', 'cenas', 'arte', 'imagens', 'obra', 'triagem']);
estado.desde = 0;

function eventoDoMotor(e) {
  const nome = FRASES[e.tipo] || e.tipo;
  const onde = e.obra && e.ep && e.ep !== '00' ? ` · Ep. ${e.ep}` : '';
  if (e.estado === 'erro') {
    aviso(`Erro: ${nome}${onde}: ${e.texto}`);
    notificar('Origami: erro', `${nome}${onde}\n${e.texto}`);
  } else if (e.estado === 'espera') {
    aviso(`${nome}${onde}: ${e.texto}`, true);
    notificar('Origami: esperando', `${nome}${onde}\n${e.texto}`);
  } else if (e.estado === 'pronto') {
    aviso(`Pronto: ${nome}${onde}. ${e.texto || ''}`.trim(), true);
    if (AVISA_PRONTO.has(e.tipo) && !document.hasFocus()) notificar('Origami: pronto', `${nome}${onde}\n${e.texto || ''}`);
  } else if (e.estado === 'pulado' && /esperando você/.test(e.texto || '')) {
    aviso(`${nome}${onde}: ${e.texto}`, true);
  } else if (e.estado === 'piloto') {            // o piloto automático pôs algo na fila
    aviso(`Piloto${onde}: ${e.texto}`, true);
  } else if (e.estado === 'pendencia') {         // algo agora espera o autor (aviso do Windows uma vez)
    aviso(`Precisa de você${onde}: ${e.texto}`, true);
    notificar(`Origami: precisa de você${onde}`, e.texto);
  }
}

async function motor() {
  let s;
  try { s = await api(`/estado?desde=${estado.desde}`); }
  catch { $('#motor').className = 'pill off'; $('#motor').textContent = 'motor fora do ar'; faixa().style.display = 'none'; return; }
  const primeira = !estado.desde;
  estado.desde = Math.max(estado.desde, ...(s.eventos || []).map((e) => e.t), primeira ? s.agora : 0);
  $('#motor').className = 'pill on' + (s.erros_24h ? ' com-erro' : '');
  const partes = [s.job ? 'trabalhando' : (s.sem_worker ? 'só interface' : 'motor livre'), `fila ${s.na_fila}`];
  if (s.esperando) partes.push(`${s.esperando} esperando até ${new Date(s.volta * 1000).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`);
  if (s.erros_24h) partes.push(`${s.erros_24h} erro(s) hoje`);
  $('#motor').textContent = s.demo ? 'demonstração · somente leitura' : partes.join(' · ');
  $('#motor').title = s.sem_worker ? s.sem_worker : (s.proximo ? `próximo: ${FRASES[s.proximo.tipo] || s.proximo.tipo} · Ep. ${s.proximo.ep}` : 'nada na fila');
  $('#motor').onclick = () => trocarTela('fila');
  if (!primeira) (s.eventos || []).forEach(eventoDoMotor);
  const j = s.job, antes = estado.job;
  if (j && (!antes || antes.id !== j.id)) estado.jobDesde = Date.now();
  // terminou algo (ou chegou evento): atualiza a Mesa e a tela aberta, sem atropelar o que você está fazendo
  if (estado.obra && ((antes && (!j || antes.id !== j.id)) || (!primeira && (s.eventos || []).length))) abrir(estado.obra, estado.ep, true);
  estado.job = j;
  window.motorJob = j;
  const f = faixa();
  if (!j) { f.style.display = 'none'; return; }
  const seg = Math.round((Date.now() - estado.jobDesde) / 1000);
  f.style.display = 'flex';
  f.innerHTML = `<span class="spin"></span><b>${esc(FRASES[j.tipo] || j.tipo)}</b> · Ep. ${esc(j.ep)} · ${Math.floor(seg / 60)}:${String(seg % 60).padStart(2, '0')}
    ${TEMPO_TIPICO[j.tipo] ? `<span class="ctx">(costuma levar ${TEMPO_TIPICO[j.tipo]})</span>` : ''}
    <span class="ctx" style="margin-left:auto">Pode continuar navegando: quando terminar, a tela atualiza sozinha.</span>`;
}

// abas: Mesa · Revisão de áudio
document.querySelectorAll('#abas button').forEach((b) => b.onclick = () => trocarTela(b.dataset.tela));
function trocarTela(t) {
  document.querySelectorAll('#abas button').forEach((x) => x.classList.toggle('on', x.dataset.tela === t));
  document.querySelectorAll('main.tela').forEach((m) => m.classList.toggle('on', m.id === t));
  if (t === 'texto' && window.Texto) window.Texto.abrir(estado.obra, estado.ep);
  if (t === 'elenco' && window.Elenco) window.Elenco.abrir(estado.obra, estado.ep);
  if (t === 'elenco' && window.Pronuncia) window.Pronuncia.abrir(estado.obra);
  if (t === 'revisao' && window.Revisao) window.Revisao.abrir(estado.obra, estado.ep);
  if (t === 'arte' && window.Arte) window.Arte.abrir(estado.obra, estado.ep);
  if (t === 'imagens' && window.Imagens) window.Imagens.abrir(estado.obra, estado.ep);
  if (t === 'video' && window.Video) window.Video.abrir(estado.obra, estado.ep);
  if (t === 'pub' && window.Pub) window.Pub.abrir(estado.obra, estado.ep);
  if (t === 'postagem' && window.Postagem) window.Postagem.abrir(estado.obra);
  if (t === 'fila' && window.Fila) window.Fila.abrir(estado.obra);
  if (t === 'arquivos' && window.Arquivos) window.Arquivos.abrir();
  if (t === 'obranova' && window.ObraNova) window.ObraNova.abrir(document.querySelector('#obra').value);
  if (window.Ajustes) window.Ajustes.abrir(estado.obra, estado.ep);
  const el = document.getElementById(t);
  if (el) { delete el.dataset.sujo; el.querySelector('.novidade')?.remove(); }
}

(async function iniciar() {
  let obras;
  try { obras = await api('/api/obras'); }
  catch (e) {     // a tela mostra o erro em vez de ficar vazia
    document.body.insertAdjacentHTML('beforeend', `<div class="bloqueio" style="position:fixed;inset:auto 20px 20px auto;z-index:99">Não consegui ler as obras: ${esc(e.message)}. A janela tenta de novo em 5 s.</div>`);
    return setTimeout(() => location.reload(), 5000);
  }
  let amb = {}; try { amb = await api('/api/ambiente'); } catch {}
  estado.demo = !!amb.demo;
  if (!estado.demo) try { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission(); } catch {}
  $('#obra').innerHTML = obras.map((o) => `<option value="${esc(o.obra)}">${esc(o.titulo)}</option>`).join('');
  let ult = null; try { ult = JSON.parse(localStorage.getItem('origami.ultimo')); } catch {}
  const h = Object.fromEntries(new URLSearchParams(location.hash.slice(1)));   // #obra=…&ep=02 (atalho)
  if (h.ep) ult = { obra: h.obra || ult?.obra, ep: h.ep };
  const obra = ult && obras.some((o) => o.obra === ult.obra) ? ult.obra : obras[0]?.obra;
  $('#obra').value = obra;
  $('#obra').onchange = () => abrir($('#obra').value, '01');
  await abrir(obra, ult?.ep || '01');
  if (h.tela) trocarTela(h.tela);
  motor(); setInterval(motor, 2000);
  if (estado.demo && window.Demo) window.Demo.iniciar({ tour: !h.tela });
})();

// ---------- ver a imagem grande antes de escolher: ← → passa, Esc fecha, "Escolher esta" chama quem abriu
window.Lightbox = (function () {
  let lista = [], i = 0, aoEscolher = null, el = null;
  const nome = (p) => p.split(/[\/]/).pop().replace(/\.(png|jpe?g)$/i, '');
  function desenhar() {
    const p = lista[i];
    el.querySelector('img').src = `/arquivo?c=${encodeURIComponent(p.caminho)}`;
    el.querySelector('.lb-nome').textContent = `${nome(p.caminho)}${p.escolhida ? ' · escolhida' : ''}  (${i + 1} de ${lista.length})`;
    el.querySelector('.lb-escolher').hidden = !aoEscolher;
    el.querySelector('.lb-escolher').textContent = p.escolhida ? '✓ Já é a escolhida' : 'Escolher esta';
    el.querySelector('.lb-escolher').disabled = !!p.escolhida;
  }
  function fechar() { if (el) { el.remove(); el = null; document.removeEventListener('keydown', tecla); } }
  function passo(d) { i = (i + d + lista.length) % lista.length; desenhar(); }
  function tecla(e) { if (e.key === 'Escape') fechar(); else if (e.key === 'ArrowRight') passo(1); else if (e.key === 'ArrowLeft') passo(-1);
    else if (e.key === 'Enter' && aoEscolher && !lista[i].escolhida) escolher(); }
  async function escolher() { const p = lista[i]; fechar(); await aoEscolher(p.caminho); }
  return {
    abrir(itens, inicio, escolherCb) {
      fechar(); lista = itens; i = inicio || 0; aoEscolher = escolherCb || null;
      el = document.createElement('div'); el.id = 'lightbox';
      el.innerHTML = `<button class="lb-x" title="Fechar (Esc)">✕</button><button class="lb-seta ant" title="Anterior (←)">‹</button>
        <figure><img alt=""><figcaption><span class="lb-nome"></span><button class="lb-escolher primario">Escolher esta</button></figcaption></figure>
        <button class="lb-seta prox" title="Próxima (→)">›</button>`;
      document.body.appendChild(el);
      el.onclick = (e) => { if (e.target === el) fechar(); };
      el.querySelector('.lb-x').onclick = fechar;
      el.querySelector('.ant').onclick = () => passo(-1);
      el.querySelector('.prox').onclick = () => passo(1);
      el.querySelector('.lb-escolher').onclick = escolher;
      el.querySelectorAll('.lb-seta').forEach((b) => (b.hidden = lista.length < 2));
      document.addEventListener('keydown', tecla);
      desenhar();
    },
  };
})();

// para os outros módulos (pendencias.js)
window.trocarTela = trocarTela;
window.abrirEpisodio = (obra, ep) => abrir(obra, ep);
window.avisoInfo = (t) => aviso(t, true);
window.avisoErro = (t) => aviso(t);

// ---------- triagem automática das imagens: selos nas candidatas e "Confirmar" a pré-escolhida
window.marcaTriagem = function (item, caminho) {
  const nome = String(caminho).split(/[\/]/).pop();
  const t = item.triagem || {}, r = (t.resultado || {})[nome];
  if (!r) return '';
  const pos = (t.melhores || []).indexOf(nome);
  if (pos >= 0) return `<span class="tri ok" title="${esc(`nota ${r.nota}/10`)}">★ ${pos + 1}ª · ${r.nota}</span>`;
  return `<span class="tri no" title="${esc((r.problemas || []).join(' · '))}">✗ ${esc((r.problemas || ['reprovada'])[0]).slice(0, 38)}</span>`;
};
window.blocoTriagem = function (item, alvo) {
  const t = item.triagem;
  if (!t) return '';
  const pre = item.pre_escolhida, quando = item.prazo_escolha ? new Date(item.prazo_escolha * 1000).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
  let txt;
  if (item.escolhida && !item.escolha_auto) txt = '✓ Você escolheu esta imagem.';
  else if (item.escolhida && item.escolha_auto) txt = `Escolhida pela triagem (o prazo passou). Pode trocar à vontade. <button class="tri-confirmar" data-alvo="${alvo}" data-id="${esc(item.id)}">Confirmar</button>`;
  else if (pre) txt = `<b>Pré-escolhida:</b> ${esc(pre)} — vale sozinha em ${esc(quando)} se você não trocar. <button class="tri-confirmar primario" data-alvo="${alvo}" data-id="${esc(item.id)}">Confirmar esta</button>`;
  else if (item.sem_candidata_boa) txt = '<b>Nenhuma candidata passou</b> em 3 rodadas: escolha uma assim mesmo, ajuste o pedido ou gere mais.';
  else txt = 'Nenhuma aprovada ainda: o pedido foi corrigido e outra rodada vai ser gerada.';
  return `<div class="tri-bloco"><div>Triagem do Opus (${esc(t.em || '')}, rodada ${t.rodadas || 1}): ${txt}</div>${t.comentario ? `<div class="ctx">${esc(t.comentario)}</div>` : ''}</div>`;
};
document.addEventListener('click', async (e) => {
  const b = e.target.closest('.tri-confirmar');
  if (!b) return;
  e.stopPropagation();
  try {
    await api('/api/triagem/confirmar', { obra: estado.obra, ep: estado.ep, alvo: b.dataset.alvo, id: b.dataset.id });
    aviso('imagem confirmada', true);
    abrir(estado.obra, estado.ep);
  } catch (er) { aviso(er.message); }
});
