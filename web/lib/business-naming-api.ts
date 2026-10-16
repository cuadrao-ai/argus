import { apiFetch } from "./argus-api-transport";

export type BusinessNamingState = {
  id: string;
  name: string;
  name_required: boolean;
  name_prompt_seen: boolean;
};
export type BusinessNamePrompt = BusinessNamingState & { show_prompt: boolean };
export const getBusinessName = () => apiFetch<BusinessNamingState>("/business/space/name");
export const claimBusinessNamePrompt = (spaceId: string) => apiFetch<BusinessNamePrompt>("/business/space/name-prompt", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ space_id: spaceId }),
});
export const saveBusinessName = (spaceId: string, name: string) => apiFetch<BusinessNamingState>("/business/space/name", {
  method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ space_id: spaceId, name }),
});
