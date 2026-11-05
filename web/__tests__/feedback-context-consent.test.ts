import { describe, expect, test } from "bun:test";
import { feedbackContextForSubmission } from "../lib/feedback-context";

const sourceContext = {
  source: "message_more_menu",
  surface: "chat",
  conversation_id: "conversation-1",
  message_id: "message-1",
  artifact_id: "artifact-1",
  artifact_type: "result_card",
  raw_transcript: "private transcript",
  email: "person@example.com",
  url: "https://example.test/chat?token=secret",
  metadata: { authorization: "Bearer secret" },
};

describe("feedback context consent", () => {
  test("omits all conversation context without explicit consent", () => {
    expect(
      feedbackContextForSubmission(sourceContext, {
        includeConversationContext: false,
        rating: "negative",
        tags: ["incorrect"],
      }),
    ).toEqual({
      source: "message_more_menu",
      surface: "chat",
      rating: "negative",
      tags: ["incorrect"],
    });
  });

  test("includes only approved scalar conversation context with consent", () => {
    expect(
      feedbackContextForSubmission(sourceContext, {
        includeConversationContext: true,
        rating: "negative",
        tags: [],
      }),
    ).toEqual({
      source: "message_more_menu",
      surface: "chat",
      conversation_id: "conversation-1",
      message_id: "message-1",
      artifact_id: "artifact-1",
      artifact_type: "result_card",
      rating: "negative",
      tags: [],
    });
  });
});
