// Origami · ajustes sem editar JSON. Um painel em cada tela:
//   Texto  → título do episódio          Áudio → trilha (humor e final) da parte
//   Vídeo  → cenário e figurino por trecho Arte  → guia de arte da obra (receita das capas, regras, rostos)
//   Entrega → marcar o episódio como publicado    Postagem → horários e redes do calendário
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  async function api(caminho, corpo) {
    const r = await fetch(caminho, corpo ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) } : {});
    const j = await r.json();
    if (!r.ok || j.erro) throw new Error(j.erro || r.statusText);
    return j;
  }
  const ok = (t) => window.avisoInfo && window.avisoInfo(t);
  const erro = (t) => window.avisoErro && window.avisoErro(t);
  const J = { obra: null, ep: null };
  const tela = () => document.querySelector('main.tela.on')?.id;
  const q = (o, e) => `obra=${encodeURIComponent(o)}&ep=${e}`;

  const NIVEIS = { preservar: 'preservar: o texto é do autor, a IA não reescreve', revisar: 'revisar: só corrige erros e repetições',
    expandir: 'expandir: desenvolve as cenas (até 2× o tamanho)', recriar: 'recriar: reescreve a partir da fonte (RPG)', continuar: 'continuar: escreve o que vem depois' };
  // ---------- Texto: título do episódio
  async function titulo() {
    const el = $('#aj-titulo'); if (!el) return;
    let m; try { m = await api(`/api/mesa?${q(J.obra, J.ep)}`); } catch { el.innerHTML = ''; return; }
    const atual = (m.episodios.find((e) => e.ep === J.ep) || {}).titulo || '';
    el.innerHTML = `<div class="aj-caixa"><label class="ctx">Título do episódio (vai no 16:9, no Wattpad e nos metadados)</label>
      <div class="linha"><input type="text" id="aj-tit" value="${esc(atual)}"><button id="aj-tit-ok">Salvar</button></div>
      <label class="ctx" style="margin-top:8px;display:block">Quanto a IA mexe no texto</label>
      <div class="linha"><select id="aj-nivel">${Object.entries(NIVEIS).map(([k, t]) => `<option value="${k}" ${k === m.nivel_ia ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>
        <button id="aj-nivel-ep">Neste episódio</button><button id="aj-nivel-obra">Na obra toda</button></div></div>`;
    const nivel = async (escopo) => { try { const r = await api('/api/ajustes/nivel', { obra: J.obra, ep: J.ep, nivel: $('#aj-nivel').value, escopo }); ok(r.aviso); } catch (e) { erro(e.message); } };
    $('#aj-nivel-ep').onclick = () => nivel('ep'); $('#aj-nivel-obra').onclick = () => nivel('obra');
    $('#aj-tit-ok').onclick = async () => { try { await api('/api/ajustes/titulo', { obra: J.obra, ep: J.ep, titulo: $('#aj-tit').value }); ok('título salvo'); } catch (e) { erro(e.message); } };
  }

  // ---------- Áudio: trilha da parte aberta
  async function trilha() {
    const el = $('#aj-trilha'); if (!el) return;
    let d; try { d = await api(`/api/ajustes/trilha?${q(J.obra, J.ep)}`); } catch { el.innerHTML = ''; return; }
    if (!d.partes.length) { el.innerHTML = ''; return; }
    const ops = (o, v) => Object.entries(o).map(([k, t]) => `<option value="${esc(k)}" ${k === v ? 'selected' : ''}>${esc(t)}</option>`).join('');
    el.innerHTML = `<details class="aj-caixa"><summary><b>Trilha</b> <span class="ctx">clima e final da música de cada parte</span></summary>
      <table class="reg">${d.partes.map((p) => `<tr data-p="${p.parte}"><td>Parte ${p.parte}</td><td><select class="aj-h">${ops(d.humores, p.humor)}</select></td>
        <td><select class="aj-f">${ops(d.finais, p.final)}</select></td><td><button class="aj-tr-ok">Salvar</button></td></tr>`).join('')}</table>
      <div class="ctx">Mudar recompõe só a música daquela parte no próximo Produzir; o áudio dela volta para "a aprovar".</div></details>`;
    el.querySelectorAll('.aj-tr-ok').forEach((b) => b.onclick = async () => {
      const tr = b.closest('tr');
      try { const r = await api('/api/ajustes/trilha', { obra: J.obra, ep: J.ep, parte: +tr.dataset.p, humor: tr.querySelector('.aj-h').value, final: tr.querySelector('.aj-f').value }); ok(r.aviso); }
      catch (e) { erro(e.message); }
    });
  }

  // ---------- Vídeo: cenário e figurino por trecho
  async function segmentos() {
    const el = $('#aj-segmentos'); if (!el) return;
    const aba = (document.querySelector('#vd-partes button.on')?.textContent || 'Parte 1').trim();
    if (!/^Parte\s+\d+/.test(aba)) { el.innerHTML = ''; return; }        // aba do episódio 16:9: não tem trechos próprios
    const parte = +aba.match(/\d+/)[0];
    let d; try { d = await api(`/api/ajustes/segmentos?${q(J.obra, J.ep)}&parte=${parte}`); } catch { el.innerHTML = ''; return; }
    const sel = (lista, v, cls) => `<select class="${cls}">${lista.map((x) => `<option ${x === v ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`;
    const linha = (s) => `<tr><td><select class="aj-fala">${d.falas.map((f) => `<option value="${f.n}" ${f.n === s.fala ? 'selected' : ''}>fala ${f.n}: ${esc(f.texto.slice(0, 40))}</option>`).join('')}</select></td>
      <td>${sel(d.fundos, s.fundo, 'aj-fundo')}</td><td>${sel(d.contextos, s.figurino, 'aj-fig')}</td><td><button class="aj-del" title="tirar este trecho">✕</button></td></tr>`;
    el.innerHTML = `<details class="aj-caixa"><summary><b>Cenários e figurinos</b> <span class="ctx">parte ${parte}: de que fala até que fala cada fundo vale</span></summary>
      <table class="reg" id="aj-seg-tab">${d.segmentos.map(linha).join('')}</table>
      <div class="acoes"><button id="aj-seg-mais">+ trecho</button><button id="aj-seg-ok" class="primario">Salvar</button></div>
      <div class="ctx">O vídeo desta parte é refeito no próximo Produzir.</div></details>`;
    const ligar = () => el.querySelectorAll('.aj-del').forEach((b) => b.onclick = () => b.closest('tr').remove());
    ligar();
    $('#aj-seg-mais').onclick = () => { $('#aj-seg-tab').insertAdjacentHTML('beforeend', linha({ fala: d.falas.length, fundo: d.fundos[0], figurino: d.contextos[0] })); ligar(); };
    $('#aj-seg-ok').onclick = async () => {
      const segs = [...el.querySelectorAll('#aj-seg-tab tr')].map((tr) => ({ fala: +tr.querySelector('.aj-fala').value, fundo: tr.querySelector('.aj-fundo').value, figurino: tr.querySelector('.aj-fig').value }));
      try { const r = await api('/api/ajustes/segmentos', { obra: J.obra, ep: J.ep, parte, segmentos: segs }); ok(r.aviso); } catch (e) { erro(e.message); }
    };
  }

  // ---------- Arte: guia de arte da obra
  async function guia() {
    const el = $('#aj-guia'); if (!el) return;
    let g; try { g = await api(`/api/ajustes/guia?obra=${encodeURIComponent(J.obra)}`); } catch { el.innerHTML = ''; return; }
    const linhas = (xs) => esc((xs || []).join('\n'));
    const tags = Object.entries(g.tags_rosto || {}).map(([p, t]) => `${p}: ${t}`).join('\n');
    el.innerHTML = `<details class="aj-caixa"><summary><b>Guia de arte da obra</b> <span class="ctx">vale para todas as cenas e capas</span></summary>
      <div class="ar-form">
        <label>Estilo (toda imagem)</label><textarea id="aj-g-estilo" rows="3">${esc(g.estilo || '')}</textarea>
        <label>Receita das capas (luz, paleta, topo escuro)</label><textarea id="aj-g-ecapas" rows="3">${esc(g.estilo_capas || '')}</textarea>
        <label>Regras da obra (uma por linha)</label><textarea id="aj-g-regras" rows="4">${linhas(g.regras)}</textarea>
        <label>Regras das capas (uma por linha; a triagem confere)</label><textarea id="aj-g-rcapas" rows="6">${linhas(g.regras_capas)}</textarea>
        <label>Rostos para o acabamento (personagem: tags, uma por linha)</label><textarea id="aj-g-tags" rows="4">${esc(tags)}</textarea>
        <label><input type="checkbox" id="aj-g-acab" ${g.acabamento_rosto ? 'checked' : ''}> acabamento de rosto automático (rosto grande de frente)</label>
        <label><input type="checkbox" id="aj-g-ref" ${g.capas_com_referencia ? 'checked' : ''}> usar o rosto oficial como referência nas capas</label>
        <div class="acoes"><button id="aj-g-ok" class="primario">Salvar o guia</button></div></div></details>`;
    $('#aj-g-ok').onclick = async () => {
      const lista = (id) => $(id).value.split('\n').map((x) => x.trim()).filter(Boolean);
      const tg = Object.fromEntries(lista('#aj-g-tags').map((l) => l.split(/:(.*)/s)).filter((x) => x.length > 1).map(([p, t]) => [p.trim(), t.trim()]));
      try {
        await api('/api/ajustes/guia', { obra: J.obra, campos: { estilo: $('#aj-g-estilo').value.trim(), estilo_capas: $('#aj-g-ecapas').value.trim(),
          regras: lista('#aj-g-regras'), regras_capas: lista('#aj-g-rcapas'), tags_rosto: tg, acabamento_rosto: $('#aj-g-acab').checked,
          capas_com_referencia: $('#aj-g-ref').checked } });
        ok('guia de arte salvo (vale para as próximas imagens)');
      } catch (e) { erro(e.message); }
    };
  }

  // ---------- Entrega: episódio publicado
  async function publicado() {
    const el = $('#aj-publicado'); if (!el) return;
    let m; try { m = await api(`/api/mesa?${q(J.obra, J.ep)}`); } catch { el.innerHTML = ''; return; }
    el.innerHTML = `<div class="aj-caixa">${m.publicado
      ? '<b>Episódio publicado.</b> As revisões ficam travadas. <button id="aj-pub">Desfazer</button>'
      : 'Quando terminar de postar tudo: <button id="aj-pub" class="primario">Marcar o episódio como publicado</button> <span class="ctx">(trava as revisões e desliga o piloto deste episódio)</span>'}</div>`;
    $('#aj-pub').onclick = async () => {
      try { await api('/api/ajustes/publicado', { obra: J.obra, ep: J.ep, publicado: !m.publicado }); ok(m.publicado ? 'voltou a "entregue"' : 'episódio publicado'); publicado(); }
      catch (e) { erro(e.message); }
    };
  }

  // ---------- Postagem: horários e redes
  async function calendario() {
    const el = $('#aj-cal'); if (!el) return;
    let d; try { d = await api(`/api/postagem?obra=${encodeURIComponent(J.obra)}`); } catch { el.innerHTML = ''; return; }
    const c = d.config;
    el.innerHTML = `<details class="aj-caixa"><summary><b>Horários e redes</b></summary><div class="ar-form">
      <div class="linha"><label class="ctx">Partes curtas <input type="time" id="aj-c-curtos" value="${esc(c.hora_curtos)}"></label>
        <label class="ctx">YouTube <input type="time" id="aj-c-yt" value="${esc(c.hora_youtube)}"></label>
        <label class="ctx">Wattpad <input type="time" id="aj-c-wp" value="${esc(c.hora_wattpad)}"></label></div>
      <div class="linha">${['tiktok', 'instagram', 'shorts'].map((r) => `<label class="ctx"><input type="checkbox" class="aj-c-rede" value="${r}" ${(c.redes_curtas || []).includes(r) ? 'checked' : ''}> ${esc(d.redes[r])}</label>`).join('')}</div>
      <div class="acoes"><button id="aj-c-ok">Salvar</button></div></div></details>`;
    $('#aj-c-ok').onclick = async () => {
      const config = { hora_curtos: $('#aj-c-curtos').value, hora_youtube: $('#aj-c-yt').value, hora_wattpad: $('#aj-c-wp').value,
        redes_curtas: [...el.querySelectorAll('.aj-c-rede:checked')].map((x) => x.value) };
      try { await api('/api/postagem/config', { obra: J.obra, config }); ok('horários salvos (valem para as próximas sugestões)'); } catch (e) { erro(e.message); }
    };
  }

  const POR_TELA = { texto: titulo, revisao: trilha, video: segmentos, arte: guia, pub: publicado, postagem: calendario };
  function abrir(obra, ep) {
    J.obra = obra; J.ep = ep || J.ep;
    const f = POR_TELA[tela()];
    if (f) f();
  }
  window.Ajustes = { abrir, atualizar: abrir };
  // o Vídeo troca de parte sem passar pelo app.js: acompanha o clique nas partes
  document.addEventListener('click', (e) => { if (e.target.closest('#vd-partes button')) setTimeout(segmentos, 50); });
})();
