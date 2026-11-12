// Origami · Texto: ler o texto-mestre como leitor, ver o alarme de erro crítico e as notas, escrever/reescrever e aprovar.
// O mestre só é escrito sem decisões pendentes, e só é aprovado sem alerta crítico aberto.
'use strict';
(function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const T = { obra: null, ep: null, d: null, editando: false };
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
  const inl = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|[^*\w])\*(?!\s)(.+?)\*(?![*\w])/g, '$1<i>$2</i>');

  function leitura(md) {
    return md.split(/\n\s*\n/).map((b) => {
      const l = b.trim();
      if (!l) return '';
      if (l === '---') return '<div class="sep">* * *</div>';
      if (l.startsWith('# ')) return `<h1>${inl(l.slice(2))}</h1>`;
      if (l.startsWith('## ')) return `<h2>${inl(l.slice(3))}</h2>`;
      if (l.split('\n').every((x) => x.trim().startsWith('>'))) return l.split('\n').map((x) => `<blockquote>${inl(x.replace(/^\s*>\s?/, ''))}</blockquote>`).join('');
      return `<p>${inl(l.replace(/\n/g, ' '))}</p>`;
    }).join('');
  }

  function relatorio(r) {
    if (!r) return '';
    const li = (xs) => xs.map((x) => `<li>${esc(x)}</li>`).join('');
    return `<div class="campo" style="margin-top:8px"><b>Relatório (${esc(r.data)})</b>
      <p>${r.partes.map((p) => `P${p.parte}: ${p.palavras} pal. ≈ ${p.segundos}s`).join(' · ')}</p>
      ${r.erros.length ? `<p style="color:var(--erro)">Erros:</p><ul>${li(r.erros)}</ul>` : '<p style="color:var(--ok)">Sem erros de duração, voz ou cenário.</p>'}
      ${r.repeticoes.length ? `<p style="color:var(--aviso)">Repetições (ouvir com atenção):</p><ul>${li(r.repeticoes)}</ul>` : ''}
      ${r.vozes_novas.length ? `<p>Vozes novas (decidir na Mesa): ${esc(r.vozes_novas.join(', '))}</p>` : ''}
      ${r.fundos_novos.length ? `<p>Cenários novos (gerar na Arte): ${esc(r.fundos_novos.join(', '))}</p>` : ''}
      ${r.observacoes.length ? `<ul class="ctx">${li(r.observacoes)}</ul>` : ''}
      ${(r.erros.length || r.repeticoes.length) ? `<div class="acoes"><button id="tx-rot-ok" title="Você leu o relatório e o roteiro pode seguir assim: o piloto automático continua.">Conferi: pode seguir assim</button></div>` : ''}</div>`;
  }

  function desenhar() {
    const d = T.d;
    const pend = d.pendentes.length;
    const ocupado = window.motorJob && ['mestre', 'revisar', 'alarme', 'corrigir', 'roteiro'].includes(window.motorJob.tipo) && window.motorJob.ep === T.ep;
    if (d.publicado) {
      $('#tx-cab').innerHTML = `<div class="bloqueio">Episódio publicado: texto só para leitura.</div>`;
    }
    if (!d.publicado) $('#tx-cab').innerHTML = d.existe
      ? `<div class="linha"><b>${d.palavras} palavras</b> · ${d.aprovado ? '<span style="color:var(--ok)">✓ aprovado</span>' : '<span style="color:var(--aviso)">aguardando sua aprovação</span>'}
         · ${d.versoes.length} versão(ões) anterior(es) guardada(s)</div>` : '';
    if (!d.existe) $('#tx-texto').innerHTML = `<p class="ctx">Ainda não há texto-mestre para este episódio.</p>`;
    else if (T.editando) $('#tx-texto').innerHTML = `<textarea id="tx-edit">${esc(d.texto)}</textarea>
      <div class="acoes"><button id="tx-salvar" class="primario">Salvar edição</button><button id="tx-cancelar">Cancelar</button></div>`;
    else $('#tx-texto').innerHTML = leitura(d.texto);

    $('#tx-acoes').innerHTML = (ocupado ? `<div class="bloqueio">⏳ O motor está trabalhando neste texto agora. Aguarde: quando terminar, esta tela atualiza sozinha.</div>` : '') + (pend ? `<div class="bloqueio">Decisões pendentes neste episódio (${d.pendentes.join(', ')}): decida na Mesa antes de escrever.</div>` : '') + `
      <h2>${d.existe ? 'Revisar' : 'Escrever'} <small>Opus, com o guia e as decisões</small></h2>
      <textarea id="tx-instr" placeholder="${d.existe ? 'O que mudar (ex.: a cena da cozinha está longa; plante a pista do rádio mais cedo)' : 'Instrução opcional para esta versão'}"></textarea>
      <div class="acoes">
        ${d.existe
          ? `<button id="tx-ajustar" class="primario" ${d.publicado || ocupado ? 'disabled' : ''} title="Mantém o texto atual e as correções; muda só o que você pediu">Ajustar com instrução</button>
             <button id="tx-editar">Editar à mão</button><button id="tx-alarme">Rodar o alarme</button>
             <button id="tx-aprovar" ${d.aprovado ? 'disabled' : ''}>Aprovar</button>
             <button id="tx-escrever" ${pend || d.publicado || ocupado ? 'disabled' : ''} title="Escreve um texto novo a partir da fonte: as correções feitas se perdem">Reescrever do zero…</button>`
          : `<button id="tx-escrever" class="primario" ${pend || d.publicado || ocupado ? 'disabled' : ''}>Escrever texto-mestre</button>`}
      </div>
      ${d.existe ? '<p class="ctx">"Ajustar" parte do texto atual e preserva o que você já corrigiu. "Reescrever do zero" só se o capítulo inteiro precisar mudar.</p>' : ''}
      ${d.aprovado && !d.publicado ? `<h2 style="margin-top:16px">Roteiro (quem fala o quê) <small>só texto: nada é gravado aqui</small></h2>
        <p class="ctx">Divide o capítulo em partes curtas e marca quem fala cada frase, as pausas, o clima da música e os cenários. A gravação das vozes só acontece em <b>Produzir episódio</b>, na Mesa, depois que todas as vozes do roteiro existirem no Elenco.</p>
        <div class="acoes"><button id="tx-roteiro" class="primario">${d.roteiro ? 'Refazer roteiro' : 'Gerar roteiro (quem fala o quê)'}</button></div>
        ${relatorio(d.relatorio)}` : ''}`;
    const al = d.alarme.alertas || [];
    $('#tx-al-data').textContent = d.alarme.data ? `conferido em ${d.alarme.data}` : '';
    const abertos = al.filter((a) => a.estado === 'aberto');
    const critAb = abertos.filter((a) => a.gravidade === 'critico').length;
    const pode = !d.publicado;
    $('#tx-alertas').innerHTML = (critAb && pode ? `<div class="acoes" style="margin-bottom:10px"><button id="tx-corr-crit" class="primario">Corrigir os ${critAb} crítico(s) com o Opus</button></div>` : '') +
      (al.length ? al.map((a) => `<div class="alerta-card ${a.gravidade} ${a.estado}">
        <b>${a.gravidade === 'critico' ? 'CRÍTICO' : 'atenção'}</b> · ${esc(a.problema)}
        <q>${esc(a.trecho)}</q><div class="ctx">Sugestão: ${esc(a.sugestao)}</div>
        ${a.nota ? `<div class="ctx"><i>${esc(a.nota)}</i></div>` : ''}
        ${a.estado === 'aberto' && pode ? `<div class="acoes">
            <button data-corr="${a.id}">Corrigir com o Opus</button>
            <button data-al="${a.id}" data-e="corrigido">Corrigi à mão</button>
            <button data-al="${a.id}" data-e="ignorado">Ignorar…</button></div>` : `<small class="ctx">${esc(a.estado)}</small>`}
      </div>`).join('') : `<p class="ctx">${d.alarme.data ? 'Nenhum problema encontrado.' : 'Ainda não conferido.'}</p>`);
    const corrigir = async (ids) => {
      try { const r = await api('/api/texto/corrigir', { obra: T.obra, ep: T.ep, ids }); aviso(`correção na fila (job ${r.job}): troca só os trechos apontados`, true); }
      catch (e) { aviso(e.message); }
    };
    if ($('#tx-corr-crit')) $('#tx-corr-crit').onclick = () => corrigir(null);
    $('#tx-alertas').querySelectorAll('[data-corr]').forEach((b) => b.onclick = () => corrigir([+b.dataset.corr]));
    $('#tx-notas').innerHTML = d.notas ? d.notas.split('\n').map((l) => /^\s*[-\d]/.test(l) ? `<p>${inl(l.trim())}</p>` : '').join('') : '';

    const job = async (acao) => {
      try { const r = await api(`/api/texto/${acao}`, { obra: T.obra, ep: T.ep, instrucao: $('#tx-instr').value.trim() }); aviso(`na fila do motor (job ${r.job})`, true); }
      catch (e) { aviso(e.message); }
    };
    $('#tx-escrever').onclick = () => {
      if (!d.existe) return job('escrever');
      const b = $('#tx-escrever');
      if (b.dataset.confirma) return job('escrever');
      b.dataset.confirma = 1; b.textContent = 'Confirmar: reescrever do zero (perde as correções)'; b.classList.add('primario');
    };
    if ($('#tx-ajustar')) $('#tx-ajustar').onclick = () => {
      if (!$('#tx-instr').value.trim()) return aviso('Escreva o que mudar.');
      job('revisar');
    };
    if ($('#tx-alarme')) $('#tx-alarme').onclick = () => job('alarme');
    if (ocupado) document.querySelectorAll('#tx-acoes button, #tx-alertas button').forEach((b) => { b.disabled = true; });
    if ($('#tx-roteiro')) $('#tx-roteiro').onclick = () => job('roteiro');
    if ($('#tx-editar')) $('#tx-editar').onclick = () => { T.editando = true; desenhar(); };
    if ($('#tx-aprovar')) $('#tx-aprovar').onclick = async () => {
      try { await api('/api/texto/aprovar', { obra: T.obra, ep: T.ep }); aviso('texto-mestre aprovado', true); carregar(); } catch (e) { aviso(e.message); }
    };
    if ($('#tx-salvar')) $('#tx-salvar').onclick = async () => {
      try { await api('/api/texto/salvar', { obra: T.obra, ep: T.ep, texto: $('#tx-edit').value }); T.editando = false; aviso('salvo (a versão anterior ficou guardada)', true); carregar(); }
      catch (e) { aviso(e.message); }
    };
    if ($('#tx-cancelar')) $('#tx-cancelar').onclick = () => { T.editando = false; desenhar(); };
    if ($('#tx-rot-ok')) $('#tx-rot-ok').onclick = async () => {
      try { await api('/api/texto/roteiro_ok', { obra: T.obra, ep: T.ep }); aviso('anotado: o roteiro segue assim', true); carregar(); } catch (e) { aviso(e.message); }
    };
    $('#tx-alertas').querySelectorAll('[data-al]').forEach((b) => b.onclick = async () => {
      let nota = '';
      if (b.dataset.e === 'ignorado') {
        const card = b.closest('.alerta-card');
        if (!card.querySelector('textarea')) {
          card.insertAdjacentHTML('beforeend', '<textarea placeholder="Por que manter? (fica registrado)"></textarea><div class="acoes"><button class="primario" data-confirma="1">Confirmar: manter assim</button></div>');
          card.querySelector('[data-confirma]').onclick = async () => {
            const n = card.querySelector('textarea').value.trim();
            if (!n) return aviso('Escreva o motivo em uma frase.');
            try { await api('/api/texto/alerta', { obra: T.obra, ep: T.ep, id: b.dataset.al, estado: 'ignorado', nota: 'mantido: ' + n }); carregar(); } catch (e) { aviso(e.message); }
          };
        }
        return;
      }
      try { await api('/api/texto/alerta', { obra: T.obra, ep: T.ep, id: b.dataset.al, estado: b.dataset.e, nota }); carregar(); } catch (e) { aviso(e.message); }
    });
  }

  async function carregar() {
    try { T.d = await api(`/api/texto?obra=${encodeURIComponent(T.obra)}&ep=${T.ep}`); }
    catch (e) { $('#tx-texto').innerHTML = esc(e.message); return; }
    desenhar();
  }
  window.Texto = { abrir(obra, ep) { T.editando = false; T.obra = obra; T.ep = ep; carregar(); }, ocupado: () => T.editando };
})();
