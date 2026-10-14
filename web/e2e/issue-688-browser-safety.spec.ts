import { expect, test, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { installBreakpointFixture } from './support/breakpoint-fixture';
const stamp = '2026-09-25T12:00:00Z';
const draft = 'Private draft belonging only to account A';
const key = 'sb-127-auth-token';
function session(id: string, revision = 1) {
  const user = { id, email: `${id}@example.invalid`, aud: 'authenticated', role: 'authenticated', app_metadata: {}, user_metadata: {}, created_at: stamp };
  const exp = Math.floor(Date.now() / 1000) + 3600;
  const part = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return { access_token: `${part({ alg: 'none' })}.${part({ sub: id, exp, revision })}.fixture`, refresh_token: `fixture-${id}-${revision}`, expires_at: exp, expires_in: 3600, token_type: 'bearer', user };
}
async function identity(page: Page, id: string | null, broadcast = true, revision = 1) {
  const value = id ? session(id, revision) : null;
  await page.evaluate(({ key, value, broadcast }) => {
    document.cookie = `${key}=${value ? 'base64-' + btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '') : ''}; Path=/; SameSite=Lax${value ? '' : '; Max-Age=0'}`;
    if (broadcast) { const channel = new BroadcastChannel(key); channel.postMessage({ event: value ? 'SIGNED_IN' : 'SIGNED_OUT', session: value }); channel.close(); }
  }, { key, value, broadcast });
}
async function setup(page: Page, content = 'Account A private conversation', language: 'en' | 'es-419' = 'en') {
  const writes: { path: string; authorization: string | undefined; body: unknown }[] = [];
  await page.context().route('**/*', route => {
    const url = new URL(route.request().url());
    return url.hostname === '127.0.0.1' && url.port !== '54321' ? route.continue() : route.abort();
  });
  await installBreakpointFixture(page, { emptyChat: true, theme: 'light', language });
  await page.route('**/api/v1/me', async route => {
    await route.fulfill({ json: { user: { id: 'account-a', email: 'account-a@example.invalid', display_name: 'Account A', language, onboarding: { completed: true, stage: 'completed', language_confirmed: true } }, account_kind: 'registered', guest: null, capabilities: { can_create_additional_conversation: true, can_manage_conversation: true, can_manage_account: true, can_use_omnisearch: true }, public_account_access_enabled: false } });
  });
  await page.route('**/api/v1/conversations/*/messages**', route => route.fulfill({ json: { items: [{ id: 'fixture-message', role: 'assistant', content, created_at: stamp, metadata: {} }], next_cursor: null } }));
  await page.route('**/api/v1/conversations', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    writes.push({ path: 'create', authorization: route.request().headers().authorization, body: route.request().postDataJSON() });
    await route.fulfill({ json: { conversation: { id: 'recovered-conversation', title: 'Recovered', created_at: stamp, updated_at: stamp, language: 'en' } } });
  });
  await page.route('**/api/v1/chat/stream', async route => {
    writes.push({ path: 'stream', authorization: route.request().headers().authorization, body: route.request().postDataJSON() });
    await route.fulfill({ contentType: 'text/event-stream', body: `data: ${JSON.stringify({ type: 'final', payload: { stage_outcome: 'ready_to_respond', assistant_response: 'Safe fixture answer', message_id: 'fixture-final', conversation_id: 'conversation-alpha' } })}\n\ndata: [DONE]\n\n` });
  });
  await page.goto('/');
  await identity(page, 'account-a', false);
  await page.goto('/chat?conversation=conversation-alpha');
  await expect(page.getByTestId('chat-input')).toBeEnabled();
  return writes;
}
async function shot(page: Page, name: string) {
  if (!process.env.ISSUE_688_EVIDENCE_DIR) return;
  mkdirSync(process.env.ISSUE_688_EVIDENCE_DIR, { recursive: true });
  await page.screenshot({ path: resolve(process.env.ISSUE_688_EVIDENCE_DIR, `${name}.png`), animations: 'disabled' });
}
for (const account of ['account-b', null]) {
  test(`two-tab ${account ? 'account switch' : 'logout'} invalidates stale draft`, async ({ page, context }) => {
    const writes = await setup(page);
    await page.getByTestId('chat-input').fill(draft);
    const other = await context.newPage(); await other.goto('/');
    await identity(other, account);
    await expect(page.getByRole('alert').filter({ hasText: 'Your account changed' })).toBeVisible();
    await expect(page.getByTestId('chat-input')).toHaveCount(0);
    await expect(page.getByText('Account A private conversation', { exact: true })).toHaveCount(0);
    expect(writes).toEqual([]);
    await shot(page, account ? 'account-switch' : 'logout');
  });
}
test('same-user refresh preserves draft and sends with refreshed identity', async ({ page, context }) => {
  const writes = await setup(page); await page.getByTestId('chat-input').fill(draft);
  const other = await context.newPage(); await other.goto('/'); await identity(other, 'account-a', true, 2);
  await expect(page.getByTestId('chat-input')).toHaveText(draft);
  await page.getByTestId('chat-input').press('Enter');
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].path).toBe('stream');
  const token = writes[0].authorization!.split(' ')[1];
  expect(JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString())).toMatchObject({ sub: 'account-a', revision: 2 });
});
test('private, research and shared Markdown never request remote images', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', request => { if (request.url().includes('tracking.example.invalid')) requests.push(request.url()); });
  await setup(page);
  const content = (name: string) => `${name} ![${name} image](https://tracking.example.invalid/${name}.png) [Safe link](https://example.org/)`;
  const items = [
    { id: 'private', metadata: {} },
    { id: 'research', metadata: { research: { sources: [{ title: 'Source', domain: 'example.org', url: 'https://example.org/' }] } } },
    { id: 'shared', metadata: { shared_conversation: { snapshot_at: stamp } } },
  ].map(entry => ({ ...entry, role: 'assistant', content: content(entry.id), created_at: stamp }));
  await page.route('**/api/v1/conversations/*/messages**', route => route.fulfill({ json: { items, next_cursor: null } }));
  const response = await page.reload();
  expect(response?.headers()['content-security-policy']).toContain("img-src 'self' data:");
  for (const entry of items) await expect(page.getByText(`${entry.id} image`, { exact: false }).first()).toBeVisible();
  await expect(page.getByTestId('research-sources-open')).toBeVisible();
  expect(requests).toEqual([]);
  expect(await page.locator('img[src*="tracking.example.invalid"]').count()).toBe(0);
  await expect(page.getByRole('link', { name: 'Safe link', exact: true })).toHaveCount(3);
  expect(await page.evaluate(() => new Promise<boolean>(resolve => { const image = new Image(); image.onload = () => resolve(image.naturalWidth > 0); image.onerror = () => resolve(false); image.src = '/icons/cuadrao-192.png'; }))).toBe(true);
  await shot(page, 'markdown-images');
});
for (const phase of ['stream', '404', 'create', 'initial-create'] as const) {
  test(`account switch during pending ${phase} cannot resend under B`, async ({ page, context }) => {
    const writes = await setup(page);
    let release!: () => void;
    const held = new Promise<void>(resolve => { release = resolve; });
    let reached = false;
    let heldResponseFinished = false;
    await page.route('**/api/v1/chat/stream', async route => {
      writes.push({ path: 'stream', authorization: route.request().headers().authorization, body: route.request().postDataJSON() });
      if (phase !== 'create' && phase !== 'initial-create') { reached = true; await held; }
      await route.fulfill(phase === 'stream' ? { contentType: 'text/event-stream', body: 'data: {"type":"token","content":"Late private answer"}\n\ndata: [DONE]\n\n' } : { status: 404, json: { detail: 'Conversation not found', code: 'not_found' } }).catch(() => {});
      if (phase === 'stream' || phase === '404') heldResponseFinished = true;
    });
    if (phase === 'create' || phase === 'initial-create') await page.route('**/api/v1/conversations', async route => {
      if (route.request().method() !== 'POST') return route.fallback();
      writes.push({ path: 'create', authorization: route.request().headers().authorization, body: route.request().postDataJSON() });
      reached = true; await held;
      await route.fulfill({ json: { conversation: { id: 'recovered-conversation', title: 'Recovered', created_at: stamp, updated_at: stamp } } }).catch(() => {});
      heldResponseFinished = true;
    });
    if (phase === 'initial-create') { await page.goto('/chat'); }
    await page.getByTestId('chat-input').fill(draft); await page.getByTestId('chat-input').press('Enter');
    await expect.poll(() => reached).toBe(true);
    const other = await context.newPage(); await other.goto('/'); await identity(other, 'account-b');
    await expect(page.getByRole('alert').filter({ hasText: 'Your account changed' })).toBeVisible();
    release();
    await expect.poll(() => heldResponseFinished).toBe(true);
    await expect(page.getByTestId('chat-input')).toHaveCount(0);
    expect(writes.map(write => write.path)).toEqual(phase === 'initial-create' ? ['create'] : phase === 'create' ? ['stream', 'create'] : ['stream']);
    for (const write of writes) expect(JSON.parse(Buffer.from(write.authorization!.split('.')[1], 'base64url').toString()).sub).toBe('account-a');
    await shot(page, `switch-pending-${phase}`);
  });
}
test('ordinary submission rejects changed cookie even before cross-tab event', async ({ page, context }) => {
  const writes = await setup(page); await page.getByTestId('chat-input').fill(draft);
  const other = await context.newPage(); await other.goto('/'); await identity(other, 'account-b', false);
  await page.getByTestId('chat-input').press('Enter');
  await expect(page.getByRole('alert').filter({ hasText: 'Your account changed' })).toBeVisible();
  expect(writes).toEqual([]);
});
test('same-user 404 creates a replacement and resends once', async ({ page }) => {
  const writes = await setup(page); let failed = false;
  await page.route('**/api/v1/chat/stream', async route => {
    if (failed) return route.fallback(); failed = true;
    writes.push({ path: 'stream-404', authorization: route.request().headers().authorization, body: route.request().postDataJSON() });
    await route.fulfill({ status: 404, json: { detail: 'Conversation not found', code: 'not_found' } });
  });
  await page.getByTestId('chat-input').fill(draft); await page.getByTestId('chat-input').press('Enter');
  await expect.poll(() => writes.map(write => write.path)).toEqual(['stream-404', 'create', 'stream']);
  await expect(page.getByText('Safe fixture answer', { exact: true })).toBeVisible();
  for (const write of writes) expect(JSON.parse(Buffer.from(write.authorization!.split('.')[1], 'base64url').toString()).sub).toBe('account-a');
  await shot(page, 'same-user-404-recovery');
});
test('public receipt Markdown produces no external image request', async ({ page }) => {
  const requests: string[] = [];
  await page.route('**/*', route => {
    if (new URL(route.request().url()).hostname === '127.0.0.1') return route.continue();
    requests.push(route.request().url()); return route.abort();
  });
  await page.goto('/r/synthetic-public-receipt-688');
  await expect(page.getByText('receipt image', { exact: false }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Safe receipt link', exact: true })).toBeVisible();
  expect(requests.filter(url => url.includes('tracking.example.invalid'))).toEqual([]);
  await shot(page, 'public-receipt-images');
});
for (const recentsState of ['successful', 'failed', 'held'] as const) {
test(`explicit guest claim retains destination identity with ${recentsState} Recents refresh`, async ({ page }) => {
  const writes = await setup(page);
  const failRecents = recentsState === 'failed';
  const holdRecents = recentsState === 'held';
  let releaseHistory = () => {};
  const historyReady = new Promise<void>(resolve => { releaseHistory = resolve; });
  let historyReleased = false;
  let converted = false;
  let pendingAction: unknown = null;
  let recentsRefreshes = 0;
  let handoffs = 0;
  let logins = 0;
  if (recentsState !== 'successful') await page.route('**/api/v1/conversations?**', async route => {
    if (!converted || route.request().method() !== 'GET') return route.fallback();
    recentsRefreshes += 1;
    if (holdRecents) { await historyReady; historyReleased = true; return route.fallback(); }
    return route.fulfill({ status: 503, json: { code: 'unavailable', detail: 'Synthetic Recents outage' } });
  });
  await page.route('**/api/v1/me', route => route.fulfill({ json: {
    user: { id: converted ? 'account-b' : 'account-a', email: converted ? 'account-b@example.invalid' : null, display_name: converted ? 'Account B' : null, language: 'en', onboarding: { completed: true, stage: 'completed', language_confirmed: true } },
    account_kind: converted ? 'registered' : 'guest', guest: converted ? null : { expires_at: new Date(Date.now() + 3600000).toISOString(), workspace_id: 'synthetic-guest' },
    capabilities: { can_create_additional_conversation: converted, can_manage_conversation: converted, can_manage_account: converted, can_use_omnisearch: true }, public_account_access_enabled: true,
  } }));
  await page.route('**/api/v1/auth/guest/handoffs', route => {
    handoffs += 1;
    if (handoffs > 1) return route.fulfill({ status: 409, json: { code: 'handoff_consumed' } });
    pendingAction = route.request().postDataJSON().pending_action;
    return route.fulfill({ json: { handoff_id: 'synthetic-handoff', expires_at: new Date(Date.now() + 3600000).toISOString() } });
  });
  await page.route('**/auth/v1/user', route => route.fulfill({ json: session('account-b').user }));
  await page.route('**/api/v1/auth/login', route => {
    logins += 1;
    if (logins > 1) return route.fulfill({ json: { user: session('account-b').user, session: session('account-b'), guest_claim: null } });
    converted = true;
    return route.fulfill({ json: { user: session('account-b').user, session: session('account-b'), guest_claim: { conversation_id: 'conversation-alpha', pending_action: pendingAction } } });
  });
  if (holdRecents) {
    await page.route('**/api/v1/conversations/*/messages**', route => route.fulfill({ json: { items: [{ id: 'synthetic-confirmation', role: 'assistant', content: 'Ready for a synthetic simulation', created_at: stamp, metadata: { confirmation_card: { version: 'argus_confirmation/v1', status: 'awaiting_confirmation', title: 'Ready to test', strategy_label: 'Buy and hold', rows: [{ key: 'assets', label: 'Assets', value: 'AAPL' }], actions: [{ id: 'run', type: 'run_backtest', label: 'Run test' }] } } }], next_cursor: null } }));
    await page.route('**/api/v1/me/usage', route => route.fulfill({ json: { allowances: Object.fromEntries(['compute', 'grounding', 'execution'].map(kind => [kind, { hour: null, day: null, guest_session: null, available_now: kind !== 'execution' || converted, limiting_window: null }])) } }));
  }
  await page.reload();
  if (holdRecents) {
    await page.getByRole('button', { name: 'Run backtest', exact: true }).click({ timeout: 10000 });
    await page.getByRole('dialog').getByRole('button', { name: 'Sign in', exact: true }).click({ timeout: 5000 });
  } else await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByPlaceholder('Email address').fill('account-b@example.invalid');
  await dialog.getByPlaceholder('Password', { exact: true }).fill('Synthetic-fixture-password-688');
  await dialog.getByRole('button', { name: 'Sign in', exact: true }).click();
  try {
    if (recentsState !== 'successful') {
      await expect.poll(() => recentsRefreshes).toBeGreaterThan(0);
    }
    await expect(dialog).toHaveCount(0);
    if (holdRecents) {
      await expect.poll(() => writes.map(write => write.path), { timeout: 5000 }).toEqual(['stream']);
      expect(historyReleased).toBe(false);
      expect(pendingAction).toMatchObject({ reason: 'simulation_limit' });
    } else await expect(page.getByText('Account A private conversation', { exact: true })).toBeVisible();
    if (!holdRecents) await expect(page.getByTestId('chat-input')).toBeEnabled();
    if (holdRecents) {
      expect((writes[0].body as { action: { type: string } }).action.type).toBe('run_backtest');
      expect(JSON.parse(Buffer.from(writes[0].authorization!.split('.')[1], 'base64url').toString()).sub).toBe('account-b');
      await shot(page, 'guest-claim-held-recents');
      releaseHistory();
      await expect.poll(() => historyReleased).toBe(true);
      await expect(page.getByText('Safe fixture answer', { exact: true })).toBeVisible();
      expect(writes.map(write => write.path)).toEqual(['stream']);
    } else {
      expect(writes).toEqual([]);
      await page.getByTestId('chat-input').fill('New deliberate message after guest claim');
      await page.getByTestId('chat-input').press('Enter');
      await expect.poll(() => writes.map(write => write.path)).toEqual(['stream']);
      expect(JSON.parse(Buffer.from(writes[0].authorization!.split('.')[1], 'base64url').toString()).sub).toBe('account-b');
    }
    expect({ handoffs, logins }).toEqual({ handoffs: 1, logins: 1 });
    if (!holdRecents) await shot(page, failRecents ? 'guest-claim-recents-failure' : 'guest-claim');
  } finally { releaseHistory(); }
});
}
test('account change notice uses Spanish resources', async ({ page, context }) => {
  const writes = await setup(page, 'Conversación privada A', 'es-419');
  await page.getByTestId('chat-input').fill(draft);
  const other = await context.newPage(); await other.goto('/'); await identity(other, 'account-b');
  await expect(page.getByRole('alert').filter({ hasText: 'Tu cuenta cambió' })).toBeVisible();
  await expect(page.getByTestId('chat-input')).toHaveCount(0);
  expect(writes).toEqual([]);
  await shot(page, 'account-switch-es-419');
});
test('cold guest first send bootstraps its own identity and submits once', async ({ page }) => {
  const writes = await setup(page);
  await identity(page, null, false);
  let bootstrapped = false;
  await page.route('**/api/v1/me', route => route.fulfill(bootstrapped ? { json: {
    user: { id: 'account-a', email: null, language: 'en', onboarding: { completed: true, stage: 'completed', language_confirmed: true } }, account_kind: 'guest',
    guest: { expires_at: new Date(Date.now() + 3600000).toISOString(), workspace_id: 'synthetic-guest' }, capabilities: { can_create_additional_conversation: false, can_manage_conversation: false, can_manage_account: false, can_use_omnisearch: true }, public_account_access_enabled: true,
  } } : { status: 401, json: { code: 'not_authenticated' } }));
  await page.route('**/auth/v1/user', route => route.fulfill({ json: session('account-a').user }));
  await page.route('**/api/v1/auth/guest', route => {
    bootstrapped = true;
    return route.fulfill({ json: { authenticated: true, reused: false, renewed_after_expiry: false, public_account_access_enabled: true, account_kind: 'guest', session: session('account-a') } });
  });
  await page.goto('/chat');
  await page.getByTestId('chat-input').fill('First synthetic guest question');
  await page.getByTestId('chat-input').press('Enter');
  await expect.poll(() => writes.filter(write => write.path === 'stream').length).toBe(1);
  await expect(page.getByText('Safe fixture answer', { exact: true })).toBeVisible();
  for (const write of writes) expect(JSON.parse(Buffer.from(write.authorization!.split('.')[1], 'base64url').toString()).sub).toBe('account-a');
  await shot(page, 'cold-guest-first-send');
});
