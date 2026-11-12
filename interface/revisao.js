// Origami · Revisão de áudio fala por fala. Ouvir → clicar no ponto → a fala abre → editar/regerar/escolher versão.
// A correção vai para a fila do motor, que refaz só a parte (montar → trilha → mix → tempos → vídeo).
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const mmss = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
  const arq = (c) => `/arquivo?c=${encodeURIComponent(c)}&t=${Date.now()}`;
  const CORES = ['#a770ff', '#4cc8e8', '#f0b545', '#4cc38a', '#f06a9f', '#9aa6bd'];
  const R = { obra: null, ep: null, parte: 1, dados: null, sel: null };
  const audio = $('#rv-audio'), audioFala = $('#rv-audio-fala'), cv = $('#rv-onda');

  async function api(caminho, corpo) {
    const r = await fetch(caminho, corpo ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) } : {});
    const j = await r.json();
    if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    return j;
  }
  const corVoz = (v) => CORES[Math.max(0, R.dados.vozes.indexOf(v)) % CORES.length];

  function desenhar() {
    const d = R.dados; if (!d) return;
    const w = cv.width = cv.clientWidth * devicePixelRatio, h = cv.height = 140 * devicePixelRatio;
    const g = cv.getContext('2d'); g.clearRect(0, 0, w, h);
    const x = (t) => t / d.duracao * w;
    // faixas das falas (cor da voz) e a selecionada
    for (const f of d.falas) {
      if (f.inicio == null) continue;
      g.fillStyle = corVoz(f.voz) + (R.sel === f.chave ? '55' : '1c');
      g.fillRect(x(f.inicio), 0, Math.max(2, x(f.fim) - x(f.inicio)), h);
      if (f.revisar) { g.fillStyle = '#f0b545'; g.fillRect(x(f.inicio), 0, Math.max(2, x(f.fim) - x(f.inicio)), 5 * devicePixelRatio); }
    }
    // onda
    const n = d.picos.length, meio = h / 2;
    g.fillStyle = '#d9cfff';
    for (let i = 0; i < n; i++) { const a = d.picos[i] * (h * 0.44); g.fillRect(i / n * w, meio - a, Math.max(1, w / n), a * 2); }
    // cursor
    g.fillStyle = '#ffffff'; g.fillRect(x(audio.currentTime || 0), 0, 2 * devicePixelRatio, h);
  }

  function falaEm(t) {
    const fs = R.dados.falas.filter((f) => f.inicio != null);
    return fs.find((f) => t >= f.inicio && t <= f.fim + (f.pausa || 0)) || fs.reduce((m, f) => (Math.abs(f.inicio - t) < Math.abs(m.inicio - t) ? f : m), fs[0]);
  }

  function lista() {
    $('#rv-falas').innerHTML = R.dados.falas.map((f) => `
      <li data-k="${f.chave}" class="${R.sel === f.chave ? 'on' : ''}">
        <span class="k">${f.chave}<br>${f.inicio != null ? mmss(f.inicio) : ''}</span>
        <span><span class="v" style="color:${corVoz(f.voz)}">${esc(f.voz)}</span>${f.revisar ? ' <span class="alerta">⚠ ouvir</span>' : ''}
          ${f.aprovada_manual ? ' <span class="ctx">✓ aprovada</span>' : ''}<br>${esc(f.texto)}</span></li>`).join('');
    $('#rv-falas').querySelectorAll('li').forEach((li) => li.onclick = () => selecionar(li.dataset.k, true));
    const rev = R.dados.falas.filter((f) => f.revisar).length;
    $('#rv-resumo').innerHTML = `${R.dados.falas.length} falas · ${R.dados.duracao.toFixed(1)} s` + (rev ? ` · <span class="alerta">${rev} para ouvir</span>` : ' · nenhuma marcada pelo conferidor');
  }

  function painel() {
    const f = R.dados.falas.find((x) => x.chave === R.sel);
    if (!f) return;
    const outras = f.versoes.filter((v) => v.nome !== 'atual');
    $('#rv-fala').innerHTML = (R.dados.publicado ? `<div class="bloqueio">Episódio publicado: aqui é só para ouvir. Correções geram uma versão nova e não mudam o que já foi postado.</div>` : '') + `
      <h2>${f.chave} <small style="color:${corVoz(f.voz)}">${esc(f.voz)}</small> <small>${esc(f.estilo)}</small></h2>
      <div class="linha"><button id="f-ouvir">▶ Ouvir só esta fala</button><button id="f-contexto">▶ Ouvir no contexto (−2 s)</button></div>
      <label class="ctx">Texto da fala</label>
      <textarea id="f-texto">${esc(f.texto)}</textarea>
      <div class="linha"><label>Pausa depois <input id="f-pausa" type="number" step="0.05" min="0" max="3" value="${f.pausa}"> s</label></div>
      <div class="linha">
        <button id="f-salvar" class="primario" ${R.dados.publicado ? 'disabled' : ''}>Salvar e regravar</button>
        <button id="f-regerar" ${R.dados.publicado ? 'disabled' : ''}>Nova tomada (mesmo texto)</button>
        ${f.revisar ? '<button id="f-aprovar">Está certa (falso alarme)</button>' : ''}
      </div>
      <h3>O que o conferidor ouviu</h3>
      <div class="transc">${esc(f.transcricao || '—')} <br><small>erro de leitura: ${f.erro != null ? (f.erro * 100).toFixed(0) + '%' : '—'} · tentativas: ${f.tentativas}</small></div>
      <h3>Versões <small>${outras.length ? 'as anteriores ficam guardadas' : 'só a atual'}</small></h3>
      <ul class="versoes">${f.versoes.map((v) => `<li><button data-ouvir="${esc(v.caminho)}">▶</button> ${esc(v.nome)}
        ${v.nome !== 'atual' ? `<button data-usar="${esc(v.nome)}">usar esta</button>` : ''}</li>`).join('')}</ul>`;
    const tocarTrecho = (a, b) => { audio.currentTime = Math.max(0, a); audio.play(); const fim = b; const ch = () => { if (audio.currentTime >= fim) { audio.pause(); audio.removeEventListener('timeupdate', ch); } }; audio.addEventListener('timeupdate', ch); };
    $('#f-ouvir').onclick = () => f.inicio != null ? tocarTrecho(f.inicio, f.fim + 0.1) : tocarArquivo(f.versoes[0].caminho);
    $('#f-contexto').onclick = () => f.inicio != null && tocarTrecho(f.inicio - 2, f.fim + 1.5);
    $('#rv-fala').querySelectorAll('[data-ouvir]').forEach((b) => b.onclick = () => tocarArquivo(b.dataset.ouvir));
    $('#rv-fala').querySelectorAll('[data-usar]').forEach((b) => b.onclick = () => enviar('escolher', { versao: b.dataset.usar },
      `Usar a versão "${b.dataset.usar}" (a atual fica guardada) e refazer a parte ${R.parte}?`));
    $('#f-salvar').onclick = () => enviar('corrigir', { texto: $('#f-texto').value, pausa: +$('#f-pausa').value },
      `Salvar e refazer a parte ${R.parte} (gravar a fala, remontar, trilha, mix e vídeo)?`);
    $('#f-regerar').onclick = () => enviar('corrigir', { regerar: true, pausa: +$('#f-pausa').value }, `Gravar outra tomada desta fala e refazer a parte ${R.parte}?`);
    if ($('#f-aprovar')) $('#f-aprovar').onclick = () => enviar('aprovar', {}, null);
  }

  function tocarArquivo(c) { audio.pause(); audioFala.src = arq(c); audioFala.play(); }

  async function enviar(acao, extra, pergunta) {
    if (pergunta && !(await confirmar(pergunta))) return;
    try {
      const r = await api(`/api/fala/${acao}`, { obra: R.obra, ep: R.ep, chave: R.sel, ...extra });
      if (r.ok === false) return avisoR(r.msg || 'nada mudou', true);
      avisoR(acao === 'aprovar' ? `${R.sel}: aprovada` : `${R.sel}: na fila do motor (só a parte ${R.parte} será refeita)`, true);
      carregar();
    } catch (e) { avisoR(e.message); }
  }

  // confirmação dentro da página (sem diálogos do navegador)
  function confirmar(txt) {
    return new Promise((ok) => {
      const d = document.createElement('div'); d.className = 'aviso info';
      d.innerHTML = `${esc(txt)}<div class="acoes"><button class="primario">Sim</button><button>Cancelar</button></div>`;
      $('#avisos').appendChild(d);
      const [s, n] = d.querySelectorAll('button');
      s.onclick = () => { d.remove(); ok(true); }; n.onclick = () => { d.remove(); ok(false); };
    });
  }
  function avisoR(txt, info) {
    const d = document.createElement('div'); d.className = 'aviso' + (info ? ' info' : ''); d.textContent = txt;
    $('#avisos').appendChild(d); setTimeout(() => d.remove(), info ? 4000 : 9000);
  }

  function selecionar(k, tocar) {
    R.sel = k; lista(); painel(); desenhar();
    const f = R.dados.falas.find((x) => x.chave === k);
    $('#rv-falas').querySelector(`li[data-k="${k}"]`)?.scrollIntoView({ block: 'nearest' });
    if (tocar && f && f.inicio != null) { audio.currentTime = f.inicio; }
  }

  async function carregar() {
    try { R.dados = await api(`/api/revisao?obra=${encodeURIComponent(R.obra)}&ep=${R.ep}&parte=${R.parte}`); }
    catch (e) {
      audio.pause(); audio.removeAttribute('src'); audio.load(); audioFala.pause();
      $('#rv-partes').innerHTML = ''; $('#rv-falas').innerHTML = ''; $('#rv-resumo').innerHTML = ''; $('#rv-tempo').textContent = '';
      $('#rv-fala').innerHTML = `<div class="bloqueio">Ep. ${esc(R.ep)}: nada para revisar ainda. ${esc(e.message.replace(/^\w+Error: /, ''))}</div>`;
      R.dados = null; R.sel = null; cv.getContext('2d').clearRect(0, 0, cv.width, cv.height); return;
    }
    $('#rv-partes').innerHTML = R.dados.partes.map((n) => `<button class="${n === R.parte ? 'on' : ''}" data-n="${n}">Parte ${n}</button>`).join('');
    $('#rv-partes').querySelectorAll('button').forEach((b) => b.onclick = () => { R.parte = +b.dataset.n; R.sel = null; carregar(); });
    // recarregar a mesma parte não volta o áudio ao começo : guarda a posição e devolve depois de carregar
    const novo = arq(R.dados.audio), pos = audio.currentTime, mesma = audio.dataset.src === novo;
    audio.src = novo; audio.dataset.src = novo;
    if (mesma && pos) audio.addEventListener('loadedmetadata', () => { audio.currentTime = Math.min(pos, audio.duration || pos); }, { once: true });
    if (!R.dados.falas.some((f) => f.chave === R.sel)) R.sel = (R.dados.falas.find((f) => f.revisar) || R.dados.falas[0]).chave;
    lista(); painel(); desenhar(); aprovacao();
  }

  // portão: legenda, vídeos e entrega só depois que você ouve e aprova o áudio do episódio
  function aprovacao() {
    const a = R.dados.aprovacao, el = $('#rv-aprovacao');
    if (!a || a.publicado) { el.innerHTML = ''; return; }
    const ouvir = a.ouvir.length ? ` · ${a.ouvir.length} fala(s) marcada(s) para ouvir: ${a.ouvir.map(esc).join(', ')}` : '';
    if (a.aprovado) {
      el.innerHTML = `<div class="rv-ap ok"><span class="rv-ap-st">✓ Áudio aprovado</span><span class="ctx">em ${esc(a.em)}. A legenda e os vídeos podem ser feitos.</span></div>`;
      return;
    }
    if (a.sem_mix.length) {
      el.innerHTML = `<div class="rv-ap espera"><span class="rv-ap-st">Áudio em produção</span><span class="ctx">faltam as partes ${a.sem_mix.join(', ')}. Quando ficarem prontas, ouça e aprove aqui.</span></div>`;
      return;
    }
    el.innerHTML = `<div class="rv-ap a-aprovar"><div><span class="rv-ap-st">Ouça e aprove o áudio</span>
      <span class="ctx">Partes a aprovar: ${a.partes_a_aprovar.join(', ')}${ouvir}. A legenda e os vídeos só começam depois da sua aprovação.</span></div>
      <div class="acoes" style="margin:0"><button id="rv-ap-gerar" class="primario">Aprovar e gerar os vídeos</button><button id="rv-ap-so">Só aprovar</button></div></div>`;
    const ir = async (gerar) => {
      try { const r = await api('/api/fala/aprovar_audio', { obra: R.obra, ep: R.ep, gerar });
        avisoR(gerar ? `Áudio aprovado. Vídeos na fila (jobs ${r.jobs[0]}–${r.jobs[r.jobs.length - 1]}).` : 'Áudio aprovado.', true); carregar(); }
      catch (e) { avisoR(e.message); }
    };
    $('#rv-ap-gerar').onclick = () => ir(true);
    $('#rv-ap-so').onclick = () => ir(false);
  }

  cv.onclick = (ev) => {
    if (!R.dados) return;
    const t = (ev.offsetX / cv.clientWidth) * R.dados.duracao;
    audio.currentTime = t;
    selecionar(falaEm(t).chave, false);
  };
  $('#rv-play').onclick = () => (audio.paused ? audio.play() : audio.pause());
  audio.onplay = () => ($('#rv-play').textContent = '❚❚ Pausar');
  audio.onpause = () => ($('#rv-play').textContent = '▶ Ouvir');
  audio.ontimeupdate = () => {
    if (!R.dados) return;
    $('#rv-tempo').textContent = `${mmss(audio.currentTime)} / ${mmss(R.dados.duracao)}`;
    const f = falaEm(audio.currentTime);
    document.querySelectorAll('#rv-falas li').forEach((li) => li.classList.toggle('tocando', f && li.dataset.k === f.chave));
    desenhar();
  };
  document.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && $('#revisao').classList.contains('on') && !/TEXTAREA|INPUT/.test(document.activeElement.tagName)) {
      e.preventDefault(); audio.paused ? audio.play() : audio.pause();
    }
  });
  window.addEventListener('resize', desenhar);

  window.Revisao = {
    abrir(obra, ep) { if (obra !== R.obra || ep !== R.ep) { R.parte = 1; R.sel = null; } R.obra = obra; R.ep = ep; carregar(); },
    // vindo de uma marca da revisão de vídeo: abre a parte já na fala daquele segundo
    irPara(obra, ep, parte, chave) { R.obra = obra; R.ep = ep; R.parte = parte; R.sel = chave; carregar(); },
  };
})();
