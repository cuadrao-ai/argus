import { createServer } from 'node:http';
const stamp = '2026-09-25T12:00:00Z';
createServer((req, res) => {
  res.setHeader('Content-Type', 'application/json');
  if (req.url === '/auth/v1/user') {
    const token = req.headers.authorization?.split(' ')[1];
    let id;
    try { id = JSON.parse(Buffer.from(token.split('.')[1], 'base64url')).sub; } catch { /* Synthetic requests only. */ }
    if (!id) { res.writeHead(401); res.end('{}'); return; }
    res.end(JSON.stringify({ id, email: `${id}@example.invalid`, aud: 'authenticated', role: 'authenticated', app_metadata: {}, user_metadata: {}, created_at: stamp })); return;
  }
  if (req.url?.startsWith('/api/v1/public/receipts/')) {
    res.end(JSON.stringify({ status: 'available', created_at: stamp, payload: { schema_version: 2, kind: 'turns', turns: [{ kind: 'answer', question: 'Synthetic public receipt', answer: 'Receipt ![receipt image](https://tracking.example.invalid/receipt.png) [Safe receipt link](https://example.org/)', content_language: 'en', framing: 'answer_not_advice', provenance_mark: 'tested_with_argus' }] } })); return;
  }
  if (req.url === '/health') { res.end('{}'); return; }
  res.writeHead(404); res.end('{}');
}).listen(5688, '127.0.0.1');
