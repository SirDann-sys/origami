// Origami · demo estática: registra o service worker (que faz o papel do motor) e só então carrega a interface.
(function () {
  const SCRIPTS = (document.currentScript.dataset.scripts || '').split(',').filter(Boolean);   // sem script inline (CSP)
  const msg = document.getElementById('demo-carregando');

  // No app, todos os scripts rodam antes da primeira resposta do motor. Aqui eles chegam um a um: as requisições
  // esperam o último script carregar, para nenhuma tela perder a primeira atualização.
  const fetchOriginal = window.fetch.bind(window);
  let liberar;
  const pronto = new Promise((r) => { liberar = r; });
  window.fetch = (...args) => pronto.then(() => fetchOriginal(...args));

  function carregar(i) {
    if (i >= SCRIPTS.length) { window.fetch = fetchOriginal; liberar(); if (msg) msg.remove(); return; }
    const s = document.createElement('script');
    s.src = SCRIPTS[i];
    s.onload = () => carregar(i + 1);
    s.onerror = () => falhou('não consegui carregar ' + SCRIPTS[i]);
    document.body.append(s);
  }

  function falhou(txt) {
    if (msg) msg.textContent = 'A demonstração não abriu: ' + txt + '. Tente recarregar a página.';
  }

  if (!('serviceWorker' in navigator)) return falhou('este navegador não tem suporte a service worker');
  navigator.serviceWorker.register('/sw.js').then(() => {
    if (navigator.serviceWorker.controller) return carregar(0);
    navigator.serviceWorker.addEventListener('controllerchange', () => carregar(0), { once: true });
  }).catch((e) => falhou(e.message));
})();
