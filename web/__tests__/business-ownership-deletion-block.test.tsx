import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import BusinessOwnershipDeletionBlock, { businessOwnershipCopyEs } from "@/components/business-app/BusinessOwnershipDeletionBlock";

test("each solely owned Business has its exact warning and separate transfer and close links", () => {
  const html = renderToStaticMarkup(<BusinessOwnershipDeletionBlock copy={businessOwnershipCopyEs} businesses={[
    { id: "one", name: "Taller Luna", transferHref: "/biz?transferSpace=one", closeHref: "/biz?closeSpace=one" },
    { id: "two", name: "Colmado Rosa", transferHref: "/biz?transferSpace=two", closeHref: "/biz?closeSpace=two" },
  ]} />);
  for (const name of ["Taller Luna", "Colmado Rosa"]) expect(html).toContain(`Eres el único dueño de ${name}. Transfiérelo o ciérralo antes de borrar tu cuenta.`);
  expect(html.match(/Transferir este negocio/g)).toHaveLength(2);
  expect(html.match(/Cerrar negocio/g)).toHaveLength(2);
  for (const id of ["one", "two"]) for (const action of ["transferSpace", "closeSpace"]) expect(html).toContain(`href="/biz?${action}=${id}"`);
  expect(businessOwnershipCopyEs.reopen).toBe("Reabrir negocio");
});
