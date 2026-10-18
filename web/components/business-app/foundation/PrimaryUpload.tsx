"use client";

export function PrimaryUpload({ label, onClick, fullWidth = false }: { label: string; onClick: () => void; fullWidth?: boolean }) {
  return (
    <button
      type="button"
      data-testid="business-primary-upload"
      onClick={onClick}
      className={`inline-flex min-h-11 items-center justify-center rounded-full bg-[#2f5a49] px-5 text-[16px] font-medium text-[#fffefa] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] ${fullWidth ? "w-full" : ""}`}
    >
      {label}
    </button>
  );
}
