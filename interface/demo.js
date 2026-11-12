// Origami · modo demonstração: faixa no topo e tour guiado pelas telas principais.
// Só é ativado quando o motor responde /api/ambiente com demo = true (app.js chama Demo.iniciar).
window.Demo = (function () {
  const REPO = 'https://github.com/SirDann-sys/origami';
  const CHAVE = 'origami.demo.tour';

  const PASSOS = [
    { tela: 'mesa', titulo: 'Mesa do episódio',
      texto: 'O painel de cada episódio: o que acontece no texto, as decisões que o autor tomou e a cadeia de produção, do texto à entrega. Com o piloto automático ligado, o app anda sozinho e só para nos portões do autor.' },
    { tela: 'texto', titulo: 'Texto-mestre',
      texto: 'O capítulo que vira áudio, vídeo e Wattpad. O nível de IA define o quanto ela mexe: aqui está em "preservar", e o texto do autor fica intacto. À direita, o relatório do roteiro com quem fala cada frase.' },
    { tela: 'revisao', titulo: 'Áudio',
      texto: 'Cada fala gravada com a voz do personagem e conferida por transcrição automática. Ao lado da forma de onda, a mixagem com a trilha composta para a parte. Os vídeos só são feitos depois que o autor ouve e aprova.' },
    { tela: 'imagens', titulo: 'Imagens e triagem',
      texto: 'Cenários e retratos gerados localmente. Um modelo de visão faz a triagem: aprova, reprova com o motivo e reescreve o pedido quando nenhuma imagem passa.' },
    { tela: 'arte', titulo: 'Arte e capas',
      texto: 'Cada cena nasce de uma frase do texto, com as personagens descritas pela ficha do guia de arte. O app compõe as capas e mostra como elas ficam na grade do perfil.' },
    { tela: 'video', titulo: 'Vídeo',
      texto: 'O resultado: a parte narrada em 9:16, com legenda palavra a palavra, cartão de quem está falando e trilha. Dê play.' },
    { tela: 'pub', titulo: 'Entrega e kit',
      texto: 'Títulos, descrições, legendas e capítulos prontos para copiar, e as peças finais numa pasta. O autor posta; o app nunca posta sozinho.' },
    { tela: 'fila', titulo: 'Fila e custo',
      texto: 'Tudo passa por uma fila única que divide uma GPU de 6 GB entre voz, imagem, transcrição e vídeo. O custo de cada tarefa de IA fica registrado.' },
  ];

  let i = -1, balao = null, alvo = null;

  function el(tag, cls, txt) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }

  function lembrar() { try { localStorage.setItem(CHAVE, '1'); } catch {} }
  function jaViu() { try { return localStorage.getItem(CHAVE) === '1'; } catch { return false; } }

  function faixa() {
    const f = el('div', 'demo-faixa');
    f.setAttribute('role', 'note');
    f.append(el('span', 'demo-selo', 'DEMONSTRAÇÃO'));
    f.append(el('span', 'demo-txt', 'somente leitura · obra de exemplo'));
    const b = el('button', 'demo-btn', 'Fazer o tour');
    b.type = 'button';
    b.onclick = () => comecar();
    f.append(b);
    const a = el('a', 'demo-link', 'Código no GitHub');
    a.href = REPO; a.target = '_blank'; a.rel = 'noopener noreferrer';
    f.append(a);
    document.querySelector('header').append(f);
  }

  function telaPequena() {
    if (window.innerWidth >= 900) return;
    const m = el('div', 'demo-pequena');
    const c = el('div', 'demo-cartao');
    c.append(el('b', null, 'Feito para tela de computador'));
    c.append(el('p', null, 'O Origami é um app de desktop. Para ver as telas inteiras, abra este endereço num computador.'));
    const ok = el('button', 'demo-btn', 'Ver mesmo assim');
    ok.type = 'button';
    ok.onclick = () => m.remove();
    c.append(ok);
    m.append(c);
    document.body.append(m);
  }

  function limpar() {
    if (alvo) alvo.classList.remove('demo-alvo');
    alvo = null;
    if (balao) balao.remove();
    balao = null;
  }

  function posicionar() {
    if (!balao) return;
    const r = alvo ? alvo.getBoundingClientRect() : { right: 220, top: 120, height: 0 };
    const h = balao.offsetHeight, vh = window.innerHeight;
    balao.style.left = Math.round(r.right + 16) + 'px';
    balao.style.top = Math.round(Math.max(12, Math.min(r.top + r.height / 2 - 40, vh - h - 12))) + 'px';
    balao.style.setProperty('--seta', Math.round(Math.max(18, Math.min(r.top + r.height / 2 - parseFloat(balao.style.top), h - 18))) + 'px');
  }

  function mostrar(n) {
    limpar();
    i = n;
    if (i >= PASSOS.length) return fim();
    const p = PASSOS[i];
    if (typeof window.trocarTela === 'function') window.trocarTela(p.tela);
    alvo = document.querySelector(`#abas button[data-tela="${p.tela}"]`);
    if (alvo) alvo.classList.add('demo-alvo');
    balao = el('div', 'demo-balao');
    balao.setAttribute('role', 'dialog');
    balao.setAttribute('aria-label', p.titulo);
    balao.append(el('small', null, `${i + 1} de ${PASSOS.length}`));
    balao.append(el('b', null, p.titulo));
    balao.append(el('p', null, p.texto));
    const acoes = el('div', 'demo-acoes');
    const sair = el('button', 'demo-sair', 'Sair do tour');
    sair.type = 'button';
    sair.onclick = () => { lembrar(); limpar(); };
    const volta = el('button', 'demo-btn demo-sec', 'Voltar');
    volta.type = 'button';
    volta.disabled = i === 0;
    volta.onclick = () => mostrar(i - 1);
    const prox = el('button', 'demo-btn', i === PASSOS.length - 1 ? 'Concluir' : 'Próximo');
    prox.type = 'button';
    prox.onclick = () => mostrar(i + 1);
    acoes.append(sair, volta, prox);
    balao.append(acoes);
    document.body.append(balao);
    posicionar();
    prox.focus({ preventScroll: true });
  }

  function fim() {
    lembrar();
    if (typeof window.trocarTela === 'function') window.trocarTela('mesa');
    balao = el('div', 'demo-balao demo-final');
    balao.setAttribute('role', 'dialog');
    balao.append(el('b', null, 'Fique à vontade'));
    balao.append(el('p', null, 'Explore as telas como quiser: nesta demonstração nada é gravado. A produção de verdade roda no computador do autor, com GPU, modelos locais e o Claude para as tarefas de texto.'));
    const acoes = el('div', 'demo-acoes');
    const a = el('a', 'demo-btn', 'Ver o código');
    a.href = REPO; a.target = '_blank'; a.rel = 'noopener noreferrer';
    const ok = el('button', 'demo-btn demo-sec', 'Fechar');
    ok.type = 'button';
    ok.onclick = () => limpar();
    acoes.append(ok, a);
    balao.append(acoes);
    document.body.append(balao);
    alvo = null;
    balao.style.left = '50%'; balao.style.top = '50%';
  }

  function comecar() { mostrar(0); }

  document.addEventListener('keydown', (e) => {
    if (!balao) return;
    if (e.key === 'Escape') { lembrar(); limpar(); }
    if (e.key === 'ArrowRight' && i < PASSOS.length) mostrar(i + 1);
    if (e.key === 'ArrowLeft' && i > 0) mostrar(i - 1);
  });
  window.addEventListener('resize', posicionar);
  // quem clica noutra tela no meio do tour assume a navegação: o balão sai em vez de apontar para a tela errada
  document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('#abas button');
    if (b && balao && b !== alvo) { lembrar(); limpar(); }
  }, true);

  function iniciar(op = {}) {
    document.body.classList.add('modo-demo');
    faixa();
    telaPequena();
    const passo = parseInt(new URLSearchParams(location.hash.slice(1)).get('tour'), 10);   // #tour=3 abre o passo 3
    if (passo >= 1) return setTimeout(() => mostrar(passo - 1), 600);
    if (op.tour !== false && !jaViu() && window.innerWidth >= 900) setTimeout(comecar, 600);
  }

  return { iniciar, comecar };
})();
