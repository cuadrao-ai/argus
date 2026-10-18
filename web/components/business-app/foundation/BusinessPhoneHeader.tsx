"use client";

import { Search } from "lucide-react";

export function PhoneSearchButton({ label, onSearch }: { label: string; onSearch: () => void }) {
  return (
    <button
      type="button"
      data-testid="business-phone-search"
      aria-label={label}
      onClick={onSearch}
      className="flex h-11 w-11 items-center justify-center rounded-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49]"
    >
      <Search className="h-5 w-5" strokeWidth={2} aria-hidden="true" />
    </button>
  );
}
