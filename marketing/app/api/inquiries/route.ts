import { handleInquiry } from "@/lib/forms/inquiry";
import { inquiryDeps } from "@/lib/forms/runtime";

export function POST(request: Request) {
  return handleInquiry(request, inquiryDeps());
}
