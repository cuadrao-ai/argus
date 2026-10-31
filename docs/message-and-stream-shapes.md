# Message and stream shapes

This file records shapes that already exist in the repo. It does not add fields.

`scripts/publish_message_stream_shapes.py` reads the producers named below and writes every marked block. Backend CI and docs CI run that script and fail when the committed blocks are not the rewrite.

`Message` in `src/argus/api/schemas.py` owns the saved-message wire object. The OpenAPI component `Message` in `docs/api/openapi.yaml` is the FastAPI schema of that model, published on `PaginatedMessages`. `ApiMessage` in `web/lib/argus-api.ts` repeats the same fields for fetches.

Chat stream frames are the objects `sse_data` sends. `parseChatStreamFrame` in `web/lib/argus-api.ts` turns those frames into `ChatStreamEvent`. `Message` in `web/components/chat/types.ts` is the UI row. Hydration builds it from a saved message or from a parsed final.

## Saved message fields

<!-- message-fields -->
| Field | Required |
| --- | --- |
| `id` | yes |
| `conversation_id` | yes |
| `role` | yes |
| `content` | yes |
| `created_at` | yes |
| `metadata` | no |
<!-- /message-fields -->

`role` is the `MessageRole` literal.

<!-- message-roles -->
- `user`
- `assistant`
- `system`
- `tool`
<!-- /message-roles -->

`created_at` is a date-time. `metadata` is an object or null. The model types it as `dict[str, Any] | None`, and the OpenAPI property allows any additional properties. The model does not name keys inside `metadata`.

Persisted writers under `src/argus/api` set `role` to `user` or `assistant`. The model still accepts `system` and `tool`.

## Emitted stream frames

`sse_data` in `src/argus/api/chat/streaming.py` writes `data: {json}\n\n`. `sse_done` writes `data: [DONE]\n\n`. `sse_keepalive` writes `: keepalive\n\n`. A keepalive has no `data:` line, so the parser ignores it.

The OpenAPI 200 response for `POST /api/v1/chat/stream` is `type: string`. It does not list frames.

JSON `type` strings on `sse_data` payloads:

<!-- frame-types -->
- `final`
- `stage_outcome`
- `stage_start`
- `token`
<!-- /frame-types -->

### `stage_start`

`type` and `stage` are always present. `stage` is a string. The list is every `WorkflowNode` value, every `emit_substage` stage argument, and every string `stage` on a `stage_start` or tool-progress frame.

<!-- stage-values -->
- `clarify`
- `confirm`
- `discovery_search`
- `discovery_verify`
- `execute`
- `explain`
- `interpret`
- `next_step`
- `research_search`
<!-- /stage-values -->

`detail` is sent only when `emit_substage` is called with a detail argument and that argument is non-empty. These calls pass a detail argument.

<!-- substage-detail -->
- `discovery_search`
- `research_search`
<!-- /substage-detail -->

These calls do not.

<!-- substage-no-detail -->
- `discovery_verify`
<!-- /substage-no-detail -->

`tool_progress` is a `ToolProgress` dump from `src/argus/domain/tool_contracts.py`, including the `LocalizedText` fields. `interpolation_args` values are `ToolScalar`.

<!-- tool-progress-fields -->
- `locale_key`
- `interpolation_args`
- `call_id`
- `tool_name`
<!-- /tool-progress-fields -->

The frame does not reject other `stage` strings.

### `token`

`type` and `content`. `content` is a string. `agent.py` may rewrite `content` before it sends the frame.

### `stage_outcome`

`type` and `outcome`. `outcome` is a string. `StageOutcome` in `src/argus/agent_runtime/stages/interpret_types.py` names these graph literals.

<!-- stage-outcomes -->
- `needs_clarification`
- `ready_for_confirmation`
- `await_user_reply`
- `await_approval`
- `approved_for_execution`
- `execution_succeeded`
- `execution_failed_recoverably`
- `execution_failed_terminally`
- `ready_to_respond`
- `end_run`
<!-- /stage-outcomes -->

The frame does not validate `outcome` against that literal.

### `final`

`type` and `payload`. `payload` is an object.

Four call sites send a closed literal.

A missing confirmation checkpoint in `src/argus/api/routers/agent.py` sends these payload keys. `recovery` comes from the spread, and only when recovery is present.

<!-- checkpoint-final-keys -->
- `stage_outcome`
- `assistant_response`
- `message_id`
- `recovery`
<!-- /checkpoint-final-keys -->

`complete_retest_turn` sends these payload keys. `public_confirmation_projection` removes `canonical_launch_payload_hash` at every level.

<!-- retest-final-keys -->
- `stage_outcome`
- `message_id`
- `confirmation`
- `confirmation_payload`
- `active_confirmation_reference`
- `artifact_references`
- `retest_receipt`
<!-- /retest-final-keys -->

`failed_retest_turn` sends these payload keys. `retry_last_turn` is assigned only when the saved retry is a dict, and that object keeps these keys.

<!-- retest-failure-keys -->
- `stage_outcome`
- `assistant_response`
- `message_id`
- `recovery`
- `retest_receipt`
- `retry_last_turn`
<!-- /retest-failure-keys -->

<!-- retest-retry-keys -->
- `message`
- `action`
<!-- /retest-retry-keys -->

Confirmation cancellation sends these payload keys. The script reads the replay payload and writes the block when `complete_confirmation_cancellation` returns the same keys.

<!-- cancel-final-keys -->
- `stage_outcome`
- `assistant_response`
- `message_id`
- `confirmation_cancelled`
<!-- /cancel-final-keys -->

`confirmation_cancelled` has these keys. The script writes the block when the replay literal and the assignment in `complete_confirmation_cancellation` use the same keys.

<!-- cancel-id-keys -->
- `confirmation_id`
<!-- /cancel-id-keys -->

The graph turn does not use a closed payload. `agent.py` copies the runtime final, sets `message_id`, and passes the dict through `reader_chat_result`. That function drops private prose keys and sets `artifact_presentation_kind`. Other keys are whatever the runtime result still holds. This file does not close that object.

Keys the chat UI reads from that object, and that the emitters assign when the matching case runs, are `confirmation`, `run`, and `backtest_job`. `apply_result_link_outcome` sets `run` when it publishes a run. `reply_rewrites` is set on the same dict only when the visible reply rewrite count is greater than zero. The record is `{"em_dash": count}`.

### `error`

`type`, `code`, `message`, `message_id`, and `recovery`. `retry_last_turn` is included only when the saved metadata value is a dict.

Initialization failure sends `code` `agent_runtime_failure`. A stream exception sends `code` `finalization_failed` or `agent_runtime_failure`. `code` is not a closed enum on the frame.

### `done`

The frame is `data: [DONE]`. It has no JSON object and no `message_id`.

## Parser events

`parseChatStreamFrame` returns these events for `data:` frames.

| Wire | Parser event | Parser data |
| --- | --- | --- |
| `stage_start` | `stage_start` | `stage` string. `tool_progress` when `parseToolProgress` accepts it. `detail` when it is a non-empty string. |
| `stage_outcome` | `stage_outcome` | `outcome` string. A missing outcome becomes `""`. |
| `token` | `token` | `text` from `content`, or from `text` when `content` is absent. |
| `final` | `final` | The `payload` object. A missing payload becomes `{}`. |
| `error` | `error` | `detail` from `message`, or from `detail` when `message` is absent. `code` when it is a string. `message_id` when it is a string. `recovery` and `retry_last_turn` when each is an object. |
| `[DONE]` | `done` | `message_id` set to null. |

JSON `type` comparisons in `parseChatStreamFrame` that are absent from the emitted JSON type block:

<!-- parser-only -->
- `error`
- `title`
<!-- /parser-only -->

An `event:` line returns that event name and the JSON object unchanged. `sse_data` does not write `event:` lines.

`ChatStreamEvent` also names `status`, `confirmation`, and `result`. The `data:` parser never returns those names.

`ChatFinalPayload` is a hand-written view of the open final object. Its `final_response_payload` field is the exception. `scripts/generate_chat_final_response_type.py` generates `ChatFinalResponsePayload` from `FinalResponsePayload` in `src/argus/agent_runtime/state/models.py`.

`ChatInterface` applies a `title` event to the history list. It reads `conversation_id` and `title`. After a turn, `schedulePostTurnHistoryRefresh` loads titles from the conversation list.

## UI messages

`Message` in `web/components/chat/types.ts` requires `id` and `role`. `role` is `user` or `ai`. `content` is optional. The type has no `conversation_id` and no `created_at`. Its other fields are optional projections. The type file is the list of those fields.

`hydrateTextMessageFromApi` keeps `role` `user` as `user`. Every other wire role becomes `ai`.

## Untyped gaps

- `Message.metadata` has no key schema.
- The chat stream OpenAPI body is `type: string`.
- A graph-turn `final.payload` is an open dict.
- `stage` and `outcome` are unconstrained strings on the frame.
- `ChatStreamEvent` names `status`, `confirmation`, and `result` with no `data:` producer.
- `ChatFinalPayload` is hand-written, except `final_response_payload`.

## Producer and consumer gaps

Sent frames map as the parser table says. `token.content` becomes `text`. `error.message` becomes `detail`. `final.payload` becomes the event data. `[DONE]` becomes `done` with `message_id` null. `ChatInterface` reads `detail` after that mapping, and it reads `confirmation`, `run`, and `backtest_job` from the final object.
