import { confirmAuthGet } from "@/lib/auth-confirm";
import { createClient } from "@/lib/supabase-server";

export async function GET(request: Request) {
  const supabase = await createClient();
  return confirmAuthGet(request, (input) => supabase.auth.verifyOtp(input));
}
