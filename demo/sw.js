// Origami · demo estática: o service worker faz o papel do motor.
// /api/* e /estado → respostas gravadas pelo exportador (manifesto.json); /arquivo?c=… → o arquivo estático;
// qualquer POST → "indisponível na demonstração". Assim a interface roda sem nenhuma mudança.
const VERSAO = 'origami-demo-v2';
const IGNORAR = new Set(['t', 'desde']);
let manifesto = null;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

function chave(url) {
  const p = [...url.searchParams.entries()].filter(([k]) => !IGNORAR.has(k)).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return url.pathname + (p.length ? '?' + p.map(([k, v]) => `${k}=${v}`).join('&') : '');
}

async function carregarManifesto() {
  if (!manifesto) manifesto = await (await fetch('/dados/manifesto.json', { cache: 'no-cache' })).json();
  return manifesto;
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}

async function api(url) {
  const m = await carregarManifesto();
  const reg = m.rotas[chave(url)];
  if (!reg) {
    if (url.pathname === '/estado') return json({ demo: true, na_fila: 0, agora: Date.now() / 1000, eventos: [] });
    return json({ erro: 'não disponível na demonstração' }, 404);
  }
  const d = await (await fetch(`/dados/${reg.f}`)).json();
  if (url.pathname === '/estado') { d.agora = Date.now() / 1000; d.eventos = []; }
  return json(d, reg.s || 200);
}

async function arquivo(req, url) {
  const c = (url.searchParams.get('c') || '').replace(/\\/g, '/').replace(/^\/+/, '');
  if (!c || c.includes('..')) return json({ erro: 'arquivo não encontrado' }, 404);
  const alvo = '/' + c.split('/').map(encodeURIComponent).join('/');
  const h = new Headers();
  const range = req.headers.get('Range');
  if (range) h.set('Range', range);                          // vídeo e áudio: o player pede pedaços
  return fetch(alvo, { headers: h });
}

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;
  if (e.request.method !== 'GET')                              // toda ação (produzir, aprovar, gerar…) é POST
    return e.respondWith(json({ erro: 'Indisponível na demonstração: aqui nada é gravado nem gerado.' }, 403));
  if (url.pathname.startsWith('/api/') || url.pathname === '/estado') return e.respondWith(api(url));
  if (url.pathname === '/arquivo') return e.respondWith(arquivo(e.request, url));
});

self.VERSAO = VERSAO;
