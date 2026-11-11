import { apiFetch } from "./argus-api-transport";

export type BusinessNamingState = {
  id: string;
  name: string | null;
  name_required: boolean;
};
export const getBusinessName = () => apiFetch<BusinessNamingState>("/business/space/name");
export const saveBusinessName = (spaceId: string, name: string) => apiFetch<BusinessNamingState>("/business/space/name", {
  method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ space_id: spaceId, name }),
});
