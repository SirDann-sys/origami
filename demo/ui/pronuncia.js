// Origami · Pronúncia (no Elenco): como a voz deve falar cada palavra. O texto escrito não muda.
// Escrever como soa → ouvir uma amostra com a voz de um personagem → salvar → regravar só as falas que têm a palavra.
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const P = { obra: null, d: null, sel: null };
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
  const post = (acao, corpo) => api(`/api/pronuncia/${acao}`, { obra: P.obra, ...corpo });

  // o motor atualiza a tela quando um job termina: o que foi digitado, o "gerando…" e a amostra nova ficam guardados aqui
  const F = { palavra: null, como: null, frase: null, voz: null };
  function campo(k, padrao) { return F[k] !== null ? F[k] : padrao; }

  function desenhar() {
    const d = P.d, sel = P.sel;
    const linhas = Object.entries(d.palavras).map(([p, c]) => `<li data-p="${esc(p)}" class="${p === sel ? 'on' : ''}"><b>${esc(p)}</b> <span class="ctx">soa</span> “${esc(c)}”</li>`).join('')
      || '<li class="ctx">Nenhuma ainda: tudo é falado como está escrito.</li>';
    const amostras = (d.amostras || []).map((a, k) => `<div class="pr-amostra ${k === 0 && P.nova === a.caminho ? 'nova' : ''}">
        <div class="pr-am-cab"><b>${esc(a.personagem)}</b> <span class="ctx">${esc(a.quando)}</span>${k === 0 && P.nova === a.caminho ? ' <span class="pr-tag">nova</span>' : ''}</div>
        <div class="ctx">falou: “${esc(a.falado)}”</div>
        <audio controls preload="none" src="/arquivo?c=${encodeURIComponent(a.caminho)}" data-c="${esc(a.caminho)}"></audio></div>`).join('')
      || '<p class="ctx">As amostras que você gerar aparecem aqui, para ouvir e comparar.</p>';
    $('#el-pron').innerHTML = `<ul class="pr-lista">${linhas}</ul>
      <div class="ar-form pr-form">
        <div class="pr-par"><div><label for="pr-palavra">No texto</label><input type="text" id="pr-palavra" value="${esc(campo('palavra', sel || ''))}" placeholder="Siobhan"></div>
        <div><label for="pr-como">Como deve soar</label><input type="text" id="pr-como" value="${esc(campo('como', sel ? d.palavras[sel] : ''))}" placeholder="Xivón"></div></div>
        <label for="pr-frase">Frase para ouvir</label><input type="text" id="pr-frase" value="${esc(campo('frase', sel ? `${sel}.` : ''))}" placeholder="a palavra numa frase curta">
        <div class="linha" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px">
          <select id="pr-voz" title="Com a voz de">${d.personagens.map((p) => `<option ${p === campo('voz', d.narrador) ? 'selected' : ''}>${esc(p)}</option>`).join('')}</select>
          <button id="pr-ouvir" ${P.gerando ? 'disabled' : ''}>${P.gerando ? 'gerando a amostra…' : '▶ Ouvir amostra'}</button><button id="pr-salvar" class="primario">Salvar pronúncia</button></div>
        ${P.gerando ? '<div class="ctx" style="margin-top:6px;font-size:12px">O servidor de voz liga sozinho; a primeira amostra leva cerca de 1 minuto.</div>' : ''}
        <h3>Últimas amostras</h3><div class="pr-amostras">${amostras}</div>
        <div id="pr-regravar"></div>
        <div class="ctx" style="margin-top:8px;font-size:12px">Para voltar a falar como está escrito, apague o "como deve soar" e salve.
          ${Object.keys(d.globais).length ? `Valem também ${Object.keys(d.globais).length} pronúncia(s) gerais (abreviações e termos comuns).` : ''}</div>
      </div>`;
    $('#el-pron').querySelectorAll('li[data-p]').forEach((li) => li.onclick = () => {
      P.sel = li.dataset.p; F.palavra = F.como = F.frase = null; desenhar(); });
    [['pr-palavra', 'palavra'], ['pr-como', 'como'], ['pr-frase', 'frase'], ['pr-voz', 'voz']].forEach(([id, k]) => {
      const el = $(`#${id}`); el.oninput = el.onchange = () => { F[k] = el.value; }; });
    $('#pr-ouvir').onclick = ouvir;
    $('#pr-salvar').onclick = salvar;
    if (P.tocar) { const a = $('#el-pron').querySelector(`audio[data-c="${CSS.escape(P.tocar)}"]`); P.tocar = null; if (a) a.play().catch(() => {}); }
    if (sel) regravarUi(sel);
  }

  async function ouvir() {
    const palavra = $('#pr-palavra').value.trim(), como = $('#pr-como').value.trim();
    const frase = $('#pr-frase').value.trim() || palavra;
    if (!frase) return aviso('Escreva a palavra ou uma frase para ouvir.');
    // a amostra usa o que está nos campos agora (sem salvar): troca a palavra pelo "como soa" já no texto enviado
    const texto = palavra && como ? frase.replace(new RegExp(`(?<![\\p{L}\\d])${palavra.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![\\p{L}\\d])`, 'gu'), como) : frase;
    P.gerando = true; desenhar();
    try {
      const { job } = await post('amostra', { personagem: $('#pr-voz').value, texto });
      for (let i = 0; i < 240; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const s = await api(`/api/pronuncia/job?id=${job}`);
        if (s.estado === 'erro') throw new Error(s.erro);
        if (s.estado === 'pronto') {
          const caminho = (s.resumo.match(/amostra pronta: (.+?\.wav)/) || [])[1];
          P.nova = P.tocar = caminho;
          P.gerando = false; await carregar();
          return;
        }
      }
      throw new Error('a amostra demorou demais (a fila está ocupada?)');
    } catch (e) { aviso(e.message); }
    finally { if (P.gerando) { P.gerando = false; desenhar(); } }
  }

  async function salvar() {
    const palavra = $('#pr-palavra').value.trim(), como = $('#pr-como').value.trim();
    try { await post('salvar', { palavra, como }); aviso(como ? `salvo: ${palavra} soa "${como}"` : `${palavra}: volta a ser falado como escrito`, true);
      P.sel = como ? palavra : null; carregar(); }
    catch (e) { aviso(e.message); }
  }

  async function regravarUi(palavra) {
    const caixa = $('#pr-regravar');
    const achados = [];
    for (const ep of P.d.episodios) {
      try { const r = await post('falas', { ep, palavra }); if (r.falas.length) achados.push([ep, r.falas]); } catch {}
    }
    if (!achados.length) { caixa.innerHTML = `<div class="ctx" style="margin-top:10px">Nenhuma fala gravada tem "${esc(palavra)}".</div>`; return; }
    caixa.innerHTML = `<h3>Falas com "${esc(palavra)}"</h3>` + achados.map(([ep, fs]) => `<div class="pr-ep"><span>Ep. ${ep}: ${fs.map(esc).join(', ')}</span>
      <button data-ep="${ep}">Regravar ${fs.length === 1 ? 'esta fala' : `estas ${fs.length} falas`}</button></div>`).join('')
      + '<div class="ctx" style="font-size:12px">Regrava só essas falas e refaz só as partes delas (trilha, mixagem, legenda e vídeo).</div>';
    caixa.querySelectorAll('button[data-ep]').forEach((b) => b.onclick = async () => {
      try { const r = await post('regravar', { ep: b.dataset.ep, palavra }); aviso(`na fila: ${r.falas.length} fala(s), parte(s) ${r.partes.join(', ')}`, true); }
      catch (e) { aviso(e.message); }
    });
  }

  async function carregar() {
    try { P.d = await api(`/api/pronuncia?obra=${encodeURIComponent(P.obra)}`); desenhar(); }
    catch (e) { $('#el-pron').innerHTML = `<div class="bloqueio">${esc(e.message)}</div>`; }
  }
  window.Pronuncia = { abrir(obra) { if (obra !== P.obra) P.sel = null; P.obra = obra; carregar(); } };
})();
