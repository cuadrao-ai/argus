import { describe, expect, test } from "bun:test";
import { businessShellLayout } from "../components/chat/useMobileShell";

describe("businessShellLayout", () => {
  test("phone uses bottom navigation and leaves the rail unlocked", () => {
    const layout = businessShellLayout("business", true, true, true);
    expect(layout).toMatchObject({
      nav: "phone",
      businessPhone: true,
      railLocked: false,
      sidebarCollapsed: false,
      sidebarIsOpen: true,
    });
  });

  test("tablet locks the icon rail shut", () => {
    const layout = businessShellLayout("business", false, true, true);
    expect(layout).toMatchObject({
      nav: "tablet",
      businessTabletStrip: true,
      railLocked: true,
      sidebarCollapsed: true,
      sidebarIsOpen: false,
    });
  });

  test("desktop follows whether the sidebar is open", () => {
    expect(businessShellLayout("business", false, false, true)).toMatchObject({
      nav: "desktop",
      sidebarCollapsed: false,
      sidebarIsOpen: true,
      railLocked: false,
    });
    expect(businessShellLayout("business", false, false, false)).toMatchObject({
      sidebarCollapsed: true,
      sidebarIsOpen: false,
    });
  });

  test("a non-business shell has no business band", () => {
    const layout = businessShellLayout(undefined, true, true, false);
    expect(layout.businessShell).toBe(false);
    expect(layout.nav).toBeUndefined();
    expect(layout.businessPhone).toBe(false);
    expect(layout.sidebarIsOpen).toBe(true);
  });
});
