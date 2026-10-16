import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { useSidebarPreference } from "../components/sidebar/useSidebarPreference";
import { readStored, writeStored, removeStored } from "../lib/browser-storage";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(() => GlobalRegistrator.unregister());

test("first Business visit expands, remembered choices follow the person, and Personal stays separate", async () => {
  removeStored("cuadrao:business:sidebar_modes");
  writeStored("argus:sidebar_mode", "collapsed");
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  function Probe({ id, surface = "business" }: { id: string; surface?: string }) {
    const rail = useSidebarPreference(surface, id);
    return <button onClick={rail.toggleSidebar}>{`${rail.sidebarMode}:${rail.isSidebarOpen}`}</button>;
  }
  try {
    await act(async () => root.render(<Probe id="owner" />));
    expect(container.textContent).toBe("expanded:true");
    await act(async () => container.querySelector("button")!.click());
    expect(container.textContent).toBe("collapsed:false");
    expect(readStored("cuadrao:business:sidebar_modes")).toBe('{"owner":"collapsed"}');
    await act(async () => root.render(<Probe id="accountant" />));
    expect(container.textContent).toBe("expanded:true");
    await act(async () => root.render(<Probe id="owner" />));
    expect(container.textContent).toBe("collapsed:false");
    await act(async () => root.render(<Probe id="owner" surface="personal" />));
    expect(container.textContent).toBe("collapsed:false");
    await act(async () => container.querySelector("button")!.click());
    expect(container.textContent).toBe("collapsed:true");
    expect(readStored("argus:sidebar_mode")).toBe("collapsed");
  } finally { await act(async () => root.unmount()); container.remove(); removeStored("cuadrao:business:sidebar_modes"); removeStored("argus:sidebar_mode"); }
});
