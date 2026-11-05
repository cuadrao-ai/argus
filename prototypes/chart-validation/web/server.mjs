import http from 'node:http';
import { readFile } from 'node:fs/promises';
const routes = {
  '/fonts/inter.woff2': [new URL('../../../web/app/fonts/InterVariable.woff2', import.meta.url), 'font/woff2'],
  '/fonts/space-grotesk.woff2': [new URL('../../../web/app/fonts/SpaceGrotesk[wght].woff2', import.meta.url), 'font/woff2'],
  '/': [new URL('./index.html', import.meta.url), 'text/html'],
  '/app.mjs': [new URL('./app.mjs', import.meta.url), 'text/javascript'],
  '/model.mjs': [new URL('./model.mjs', import.meta.url), 'text/javascript'],
  '/style.css': [new URL('./style.css', import.meta.url), 'text/css'],
  '/visual-style.json': [new URL('../fixtures/visual-style.json', import.meta.url), 'application/json'],
  '/fixtures.json': [new URL('../fixtures/series.json', import.meta.url), 'application/json'],
  '/charts.mjs': [new URL('../../../web/node_modules/lightweight-charts/dist/lightweight-charts.standalone.production.mjs', import.meta.url), 'text/javascript'],
};
const server = http.createServer(async (request, response) => {
  const route = routes[new URL(request.url, 'http://localhost').pathname];
  if (!route) { response.writeHead(404).end(); return; }
  try { response.writeHead(200, { 'Content-Type': route[1], 'Cache-Control': 'no-store' }).end(await readFile(route[0])); }
  catch (error) { response.writeHead(500).end(String(error)); }
});
server.listen(Number(process.env.PORT || 4179), '127.0.0.1', () => console.log(`Chart prototype: http://127.0.0.1:${server.address().port}`));
