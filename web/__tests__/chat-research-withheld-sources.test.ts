import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { hydrateMessagesFromApi } from "../components/chat/chat-message-projection";
import type { ApiMessage } from "../lib/argus-api";
import {
  researchDegradedCodeFromMetadata,
  researchSourcesFromMetadata,
} from "../lib/chat-discovery-sidecar";
import { mergeFinalTextMessage } from "../lib/chat-final-message";
import { researchSourcesDisplay } from "../lib/research-sources-display";

const root = join(import.meta.dir, "..");

// A withheld research answer keeps the pages it read as sources (PR #568).
// They are where Argus looked, not sources of an answer, so the client frames
// the same drawer from the backend's typed degraded code and never from
// reading the pages: no ranking, no domain list, no inference.

const SOURCE = {
  title: "Préstamo Emprendimiento Popular | Banco Popular Dominicano",
  domain: "popularenlinea.com",
  url: "https://popularenlinea.com/pyme/paginas/prestamos/emprendimineto-popular.aspx",
  source_date: "2026-09-04",
};

function researchMetadata(degraded?: { code: string }) {
  return {
    research: {
      schema_version: "argus_research/v1",
      capability_class: "balanced_lookup",
      shape: "balanced",
      sources: [SOURCE],
      rows: [],
      retrieved_at: "2026-09-09T01:21:48Z",
      anchor_symbols: [],
      peers: [],
      usage: { invocations: 0, latency_ms: 14707, cost_usd: null, cache_status: "miss" },
      follow_up: {
        schema_version: "argus_research_follow_up/v1",
        subjects: [],
        comparison_set: [],
        peer_suggestions: [],
        open_thread: { shape: "balanced", period_of_interest: null },
      },
      ...(degraded ? { degraded } : {}),
    },
  };
}

function apiMessage(metadata: Record<string, unknown>): ApiMessage {
  return {
    id: "assistant-withheld-1",
    conversation_id: "conversation-1",
    role: "assistant",
    content:
      "Encontré fuentes, pero no pude verificar con ellas las cifras de esa respuesta, así que no las citaré.",
    created_at: "2026-09-09T01:21:49Z",
    metadata,
  };
}

describe("withheld research answers keep where Argus looked", () => {
  test("the degraded code is read from the sidecar, never inferred", () => {
    expect(researchDegradedCodeFromMetadata(undefined)).toBeNull();
    expect(researchDegradedCodeFromMetadata({})).toBeNull();
    expect(researchDegradedCodeFromMetadata(researchMetadata())).toBeNull();
    expect(
      researchDegradedCodeFromMetadata({ research: { degraded: { code: "  " } } }),
    ).toBeNull();
    expect(researchDegradedCodeFromMetadata({ research: { degraded: "broken" } })).toBeNull();
    expect(
      researchDegradedCodeFromMetadata(
        researchMetadata({ code: "survey_synthesis_incomplete" }),
      ),
    ).toBe("survey_synthesis_incomplete");
  });

  test("a hydrated withheld turn carries its pages and its code together", () => {
    const withheld = hydrateMessagesFromApi([
      apiMessage(researchMetadata({ code: "survey_synthesis_incomplete" })),
    ]).messages[0];
    expect(withheld.researchSources).toEqual([SOURCE]);
    expect(withheld.researchDegradedCode).toBe("survey_synthesis_incomplete");

    const published = hydrateMessagesFromApi([apiMessage(researchMetadata())]).messages[0];
    expect(published.researchSources).toEqual([SOURCE]);
    expect(published.researchDegradedCode).toBeNull();
  });

  test("a streamed final keeps the code beside the sources it frames", () => {
    const metadata = researchMetadata({ code: "survey_synthesis_incomplete" });
    const merged = mergeFinalTextMessage(
      { id: "assistant-1", role: "ai", kind: "text", content: "" },
      {
        assistantId: "assistant-1",
        finalText: "I found sources, but could not extract today's market movers from them.",
        finalActions: [],
        researchSources: researchSourcesFromMetadata(metadata),
        researchDegradedCode: researchDegradedCodeFromMetadata(metadata),
      },
    );
    expect(merged.researchSources).toEqual([SOURCE]);
    expect(merged.researchDegradedCode).toBe("survey_synthesis_incomplete");
    // A later merge without the code keeps the one the turn already carries.
    expect(
      mergeFinalTextMessage(merged, {
        assistantId: "assistant-1",
        finalText: "same",
        finalActions: [],
      }).researchDegradedCode,
    ).toBe("survey_synthesis_incomplete");
  });

  test("the drawer is framed as where Argus looked only on a withheld turn", () => {
    const withheld = researchSourcesDisplay(true);
    expect(withheld.openKey).toBe("chat.discovery_results.sources_panel_open_withheld");
    expect(withheld.titleKey).toBe("chat.discovery_results.sources_panel_title_withheld");
    expect(withheld.noteKey).toBe("chat.discovery_results.sources_panel_note_withheld");
    expect(withheld.openFallback).not.toContain("{{count}}");

    const published = researchSourcesDisplay(false);
    expect(published.openKey).toBe("chat.discovery_results.sources_panel_open");
    expect(published.titleKey).toBe("chat.discovery_results.sources_panel_title");
    expect(published.noteKey).toBe("chat.discovery_results.sources_panel_note");
    expect(published.openFallbackOne).toBe("{{count}} source ›");
  });

  test("both languages carry the withheld framing, and it names no page or domain", () => {
    const en = JSON.parse(
      readFileSync(join(root, "public/locales/en/common.json"), "utf-8"),
    ).chat.discovery_results;
    const es = JSON.parse(
      readFileSync(join(root, "public/locales/es-419/common.json"), "utf-8"),
    ).chat.discovery_results;
    for (const key of [
      "sources_panel_open_withheld",
      "sources_panel_title_withheld",
      "sources_panel_note_withheld",
    ]) {
      expect(typeof en[key]).toBe("string");
      expect(typeof es[key]).toBe("string");
      expect(en[key]).not.toBe(es[key]);
      expect(en[key]).not.toMatch(/\.(com|do|org)\b/);
      expect(es[key]).not.toMatch(/\.(com|do|org)\b/);
      expect(en[key]).not.toContain("—");
      expect(es[key]).not.toContain("—");
    }
    expect(en.sources_panel_open_withheld).toBe("Where Cuadrao looked ›");
    expect(es.sources_panel_open_withheld).toBe("Dónde buscó Cuadrao ›");
  });

  test("every path that attaches research sources attaches the code, and the surface reads it", () => {
    const projection = readFileSync(
      join(root, "components/chat/chat-message-projection.ts"),
      "utf-8",
    );
    expect(projection).toContain("? { researchSources, researchDegradedCode }");
    expect(projection).toContain(
      "researchDegradedCode: researchDegradedCodeFromMetadata(options.finalPayload)",
    );
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    expect(chat.split("researchDegradedCode: finalResearchDegradedCode,").length).toBe(3);
    const message = readFileSync(join(root, "components/chat/ChatMessage.tsx"), "utf-8");
    expect(message).toContain(
      "researchSourcesDisplay(Boolean(message.researchDegradedCode))",
    );
    expect(message).toContain("withheld={Boolean(message.researchDegradedCode)}");
    const panel = readFileSync(
      join(root, "components/chat/DiscoverySourcesPanel.tsx"),
      "utf-8",
    );
    expect(panel).toContain("researchSourcesDisplay(withheld)");
    expect(panel).toContain("withheld = false");
  });
});
