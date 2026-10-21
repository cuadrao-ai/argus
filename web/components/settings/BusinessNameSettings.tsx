"use client";

import { useEffect, useState } from "react";
import { getBusinessName, type BusinessNamingState } from "@/lib/business-naming-api";
import BusinessNameDialog from "@/components/business-app/BusinessNameDialog";
import { useBusiness } from "@/components/business-app/BusinessWorkspace";

export default function BusinessNameSettings({ onClose }: { onClose: () => void }) {
  const { chosen, reload } = useBusiness();
  const [business, setBusiness] = useState<BusinessNamingState | null>(null);
  useEffect(() => {
    let active = true;
    void getBusinessName().then(value => { if (active && value.id === chosen?.space_id) setBusiness(value); }).catch(() => { if (active) onClose(); });
    return () => { active = false; };
  }, [chosen?.space_id, onClose]);
  if (!business || chosen?.role !== "owner" || chosen.space_id !== business.id) return null;
  return <BusinessNameDialog business={business} required={false} onClose={onClose} onSaved={() => { reload(); onClose(); }} />;
}
