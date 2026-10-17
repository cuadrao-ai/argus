import { handleReminderRequest } from "./handler.ts";

Deno.serve((request: Request) => handleReminderRequest(request, Deno.env.toObject()));
