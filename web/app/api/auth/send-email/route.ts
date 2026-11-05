import { authEmailHookConfig, handleAuthEmailHook } from "@/server/emails/auth-hook";
import { resendAuthEmailSender } from "@/server/emails/resend";

export const runtime = "nodejs";

export async function POST(request: Request) {
  return handleAuthEmailHook(request, authEmailHookConfig(process.env), resendAuthEmailSender(process.env.CUADRAO_AUTH_EMAIL_RESEND_API_KEY));
}
