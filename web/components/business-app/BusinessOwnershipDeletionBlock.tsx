export const businessOwnershipCopyEs = {
  warning: "Eres el único dueño de {Negocio}. Transfiérelo o ciérralo antes de borrar tu cuenta.",
  transfer: "Transferir este negocio",
  close: "Cerrar negocio",
  reopen: "Reabrir negocio",
};

type Copy = { [Key in keyof typeof businessOwnershipCopyEs]: string };
export type SolelyOwnedBusiness = { id: string; name: string; transferHref: string; closeHref: string };

export default function BusinessOwnershipDeletionBlock({ businesses, copy }: { businesses: SolelyOwnedBusiness[]; copy: Copy }) {
  return <ul className="space-y-3">
    {businesses.map(business => <li key={business.id}>
      <p className="text-[14px] leading-relaxed">{copy.warning.replace("{Negocio}", () => business.name)}</p>
      <div className="flex flex-wrap gap-x-4">
        <a className="inline-flex min-h-11 items-center text-[14px] underline" href={business.transferHref}>{copy.transfer}</a>
        <a className="inline-flex min-h-11 items-center text-[14px] underline" href={business.closeHref}>{copy.close}</a>
      </div>
    </li>)}
  </ul>;
}
