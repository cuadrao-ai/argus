import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import spanish from "@/public/locales/es-419/common.json";
import { translate } from "./support/i18n-instance";

const copy = spanish.business.activity_feed;
const openapi = readFileSync(new URL("../../docs/api/openapi.yaml", import.meta.url), "utf8");
const itemSchema = openapi.match(/^    ActivityItem:\n(?: {5,}.*\n)+/m);
assert.ok(itemSchema, "the published activity item");
const actions: string[] = Bun.YAML.parse(itemSchema[0]).ActivityItem.properties.action.enum;
const areas = ["records", "documents", "business"] as const;
const groups = ["files", "reviews", "approvals", "settings"] as const;

// Vary the response independently of the action, so a web-side lookup cannot pass.
const items = [...actions, "untranslated_action"].map((action, i) => ({
  id: String(i), occurred_at: "2026-11-25T10:00:00Z", action,
  actor: { kind: "member", shown_as: "name", display_name: `[row ${i}]` },
  object: null, area: areas[i % areas.length], group: groups[i % groups.length],
  restricted: i % 2 === 0,
}));

mock.module("@/lib/business-activity-api", () => ({
  getBusinessActivity: async () => ({ items, next_cursor: null }),
}));
mock.module("@/components/business-app/actividad/activity-sample", () => ({
  fixtureItems: () => items,
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz?view=activity", width: 1440 });
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
});
let cleanup = async () => {};
afterEach(async () => { await cleanup(); });
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(mode: "live" | "fixture") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { default: ActivityDraft } = await import("@/components/business-app/actividad/ActivityDraft");
  const context = { source: { mode }, chosen: { space_id: "sample" }, openPanel: () => {} } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const i18n = await translate("es-419");
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  await act(async () => root.render(
    <I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><ActivityDraft /></BusinessContext.Provider></I18nextProvider>,
  ));
  return {
    rows: () => [...host.querySelectorAll('[data-surface-block="history"] li')],
    click: async (selector: string, label: string) => {
      const control = [...document.querySelectorAll<HTMLElement>(selector)].find(node => node.textContent === label);
      assert.ok(control, label);
      await act(async () => control.click());
    },
  };
}

test("every feed action uses the supplied area and managers-only mark", async () => {
  const page = await mount("live");
  const rows = page.rows();
  assert.equal(rows.length, items.length);
  items.forEach((item, i) => {
    const row = rows[i];
    assert.ok(row.textContent.includes(item.actor.display_name));
    assert.ok(row.textContent.includes(copy.areas[item.area]), item.action);
    assert.equal(!!row.querySelector(`[aria-label="${copy.managers_only}"]`), item.restricted, item.action);
  });
  assert.ok(rows.at(-1)?.textContent.includes(copy.actions.other));
});

test("Actividad filters every feed action by its supplied area and group", async () => {
  const page = await mount("fixture");
  const filters = [
    ...groups.map(group => ({ tab: copy.filters.action, label: copy.groups[group], items: items.filter(item => item.group === group) })),
    ...areas.map(area => ({ tab: copy.filters.area, label: copy.areas[area], items: items.filter(item => item.area === area) })),
  ];
  for (const filter of filters) {
    await page.click("button", copy.filters.title);
    await page.click('[role="tab"]', filter.tab);
    await page.click("label", filter.label);
    await page.click("button", spanish.business.transactions.layout.filters.apply);
    while ([...document.querySelectorAll("button")].some(node => node.textContent === copy.load_more)) {
      await page.click("button", copy.load_more);
    }
    const rows = page.rows();
    assert.equal(rows.length, filter.items.length, filter.label);
    filter.items.forEach((item, i) => assert.ok(rows[i].textContent.includes(item.actor.display_name), item.action));
    await page.click('[data-testid="activity-filter-chips"] button', copy.filters.clear);
  }
});
