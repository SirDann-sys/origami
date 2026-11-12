// Origami · demo estática: o service worker faz o papel do motor.
// /api/* e /estado → respostas gravadas pelo exportador (manifesto.json); /arquivo?c=… → o arquivo estático;
// qualquer POST → "indisponível na demonstração". Assim a interface roda sem nenhuma mudança.
const VERSAO = 'origami-demo-v3';
const IGNORAR = new Set(['t', 'desde']);
let manifesto = null;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil((async () => {
  for (const k of await caches.keys()) if (k !== VERSAO) await caches.delete(k);     // limpa versões antigas
  await self.clients.claim();
})()));

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
  const range = req.headers.get('Range');
  if (!range) return fetch(alvo);
  return pedaco(alvo, range);
}

// Vídeo e áudio pedem pedaços (Range) para poder pular. Nem toda hospedagem estática responde 206,
// então o próprio worker corta o pedaço: baixa o arquivo uma vez (Cache API) e responde 206.
const MEMORIA = new Map();                                    // últimos arquivos inteiros, para não reler a cada pedaço
async function inteiro(alvo) {
  if (MEMORIA.has(alvo)) return MEMORIA.get(alvo);
  const cache = await caches.open(VERSAO);
  let r = await cache.match(alvo);
  if (!r) {
    r = await fetch(alvo);
    if (!r.ok) return null;
    await cache.put(alvo, r.clone());
  }
  const dado = { buf: await r.arrayBuffer(), tipo: r.headers.get('Content-Type') || 'application/octet-stream' };
  MEMORIA.set(alvo, dado);
  if (MEMORIA.size > 3) MEMORIA.delete(MEMORIA.keys().next().value);
  return dado;
}

async function pedaco(alvo, range) {
  const d = await inteiro(alvo);
  if (!d) return fetch(alvo);
  const total = d.buf.byteLength;
  const m = /bytes=(\d*)-(\d*)/.exec(range) || [];
  let ini, fim;
  if (m[1] === '' && m[2]) { ini = Math.max(0, total - Number(m[2])); fim = total - 1; }   // "bytes=-500": os últimos 500
  else { ini = Number(m[1] || 0); fim = m[2] ? Math.min(Number(m[2]), total - 1) : total - 1; }
  if (ini >= total) return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${total}` } });
  return new Response(d.buf.slice(ini, fim + 1), {
    status: 206,
    headers: { 'Content-Type': d.tipo, 'Content-Range': `bytes ${ini}-${fim}/${total}`,
               'Content-Length': String(fim - ini + 1), 'Accept-Ranges': 'bytes' },
  });
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
