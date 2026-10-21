import type { BusinessLocale } from "./content";

const es = {
  useCases: [
    "Hasta el gasto en efectivo.",
    "Hasta la compra sin factura.",
    "Hasta lo que te deben.",
    "Hasta lo personal, aparte.",
    "Hasta lo que ve tu contador.",
  ],
  eyebrow: "PARA NEGOCIOS EN REPÚBLICA DOMINICANA",
  description:
    "Estamos construyendo Cuadrao para reunir los gastos y documentos de tu negocio. Desde el recibo que llega hasta el registro que revisas y apruebas.",
  storyLabel: "DEL DOCUMENTO AL REGISTRO",
  storyTitle: "Lo que pasa en tu negocio, sin perder el hilo.",
  storyBody:
    "Una foto, un archivo o un gasto que anotas. Queremos que cada entrada conserve su origen, puedas corregirla y sepas quién la aprobó.",
  steps: [
    {
      title: "Recibir",
      body: "Guarda el documento o anota el gasto. El original acompaña al registro para que puedas volver a él.",
      label: "Recibo recibido",
      detail: "Compra de materiales",
      amount: "RD$ 1,250",
      status: "Pendiente de revisión",
    },
    {
      title: "Revisar",
      body: "Revisa el monto y el detalle junto al documento. Corrige lo que haga falta antes de guardar el gasto.",
      label: "Revisión del gasto",
      detail: "Materiales para el taller",
      amount: "RD$ 1,250",
      status: "Detalle revisado",
    },
    {
      title: "Aprobar",
      body: "La persona responsable confirma el registro revisado. El gasto y su documento quedan relacionados.",
      label: "Registro aprobado",
      detail: "Materiales para el taller",
      amount: "RD$ 1,250",
      status: "Aprobado por la persona responsable",
    },
  ],
  truth:
    "Recorrido ilustrativo con datos de ejemplo.",
  principlesLabel: "MENOS TRABAJO REPETIDO. MÁS CLARIDAD.",
  principlesTitle: "Cada dato, con su respaldo.",
  principlesBody:
    "Estamos enfocando el primer piloto en recibir, revisar y aprobar gastos. La idea es pedirte atención donde hace falta y mantener el control en tus manos.",
  principles: [
    { title: "El original", body: "Vuelve al documento que explica el monto." },
    { title: "La revisión", body: "Corrige los detalles antes de confirmar." },
    {
      title: "La aprobación",
      body: "La persona responsable tiene la última palabra.",
    },
    { title: "El registro", body: "Encuentra el gasto y su respaldo juntos." },
  ],
  limitsQuestion: "¿Qué se puede probar hoy?",
  limitsAnswer:
    "Estamos preparando un piloto de recepción de archivos, revisión y aprobación de gastos. Las conexiones de WhatsApp y correo, la preparación automática con IA y el trabajo entre firmas y sus clientes aún necesitan validación. No las anunciamos como disponibles. El alcance y el acceso se acuerdan antes de cada piloto.",
  fitQuestion: "¿Para quién lo estamos construyendo?",
  fitAnswer:
    "Para negocios en República Dominicana que necesitan mantener sus gastos y documentos al día, y para las personas que los ayudan a revisar sus cuentas. Estamos aprendiendo de sus procesos antes de ampliar el producto.",
};
const en: typeof es = {
  useCases: [
    "Even the cash expenses.",
    "Even purchases with no invoice.",
    "Even what you are owed.",
    "Even personal costs, set apart.",
    "Even what your accountant sees.",
  ],
  eyebrow: "FOR BUSINESSES IN THE DOMINICAN REPUBLIC",
  description:
    "We’re building Cuadrao to bring your business expenses and documents together. From the receipt that arrives to the record you review and approve.",
  storyLabel: "FROM DOCUMENT TO RECORD",
  storyTitle: "Keep track of what happens in your business.",
  storyBody:
    "A photo, a file or an expense you enter. We want each entry to keep its source, let you correct it and show who approved it.",
  steps: [
    {
      title: "Receive",
      body: "Save the document or enter the expense. The original stays with the record so you can return to it.",
      label: "Receipt received",
      detail: "Materials purchase",
      amount: "RD$ 1,250",
      status: "Awaiting review",
    },
    {
      title: "Review",
      body: "Check the amount and details against the document. Correct what is needed before saving the expense.",
      label: "Expense review",
      detail: "Workshop materials",
      amount: "RD$ 1,250",
      status: "Details reviewed",
    },
    {
      title: "Approve",
      body: "The person responsible confirms the reviewed record. The expense and its document stay linked.",
      label: "Approved record",
      detail: "Workshop materials",
      amount: "RD$ 1,250",
      status: "Approved by the person responsible",
    },
  ],
  truth:
    "Illustrative journey with sample data.",
  principlesLabel: "LESS REPEATED WORK. MORE CLARITY.",
  principlesTitle: "Every detail, with its source.",
  principlesBody:
    "Our first pilot focuses on receiving, reviewing and approving expenses. The goal is to ask for attention where it is needed and keep you in control.",
  principles: [
    {
      title: "The original",
      body: "Return to the document behind the amount.",
    },
    { title: "The review", body: "Correct the details before confirming." },
    {
      title: "The approval",
      body: "The person responsible has the final say.",
    },
    { title: "The record", body: "Find the expense and its source together." },
  ],
  limitsQuestion: "What can be tested today?",
  limitsAnswer:
    "We’re preparing a pilot for receiving files, reviewing expenses and approving them. WhatsApp and email connections, automatic AI preparation and collaboration between firms and their clients still need validation. We do not advertise them as available. Scope and access are agreed before each pilot.",
  fitQuestion: "Who are we building it for?",
  fitAnswer:
    "Businesses in the Dominican Republic that need to keep their expenses and documents up to date, and the people who help review their accounts. We’re learning from their processes before expanding the product.",
};
export const touchupCopy: Record<BusinessLocale, typeof es> = { es, en };
