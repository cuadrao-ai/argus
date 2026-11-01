import type { InvoiceState, IslandStep } from "@/lib/scene-timeline";

export const landingCopy = {
  es: {
    useCases: [
      "Hasta el gasto en efectivo.",
      "Hasta la compra sin factura.",
      "Hasta lo que te deben.",
      "Hasta lo personal, aparte.",
      "Hasta lo que ve tu contable.",
    ],
    lead: "Envía tus facturas por WhatsApp o correo. Cuadrao las organiza y tu contable recibe todo en orden.",
    howLink: "Ver cómo funciona",
    scene: {
      label:
        "Una factura llega por WhatsApp a la Bandeja de Cuadrao, Ana la aprueba y el 606 y el 607 quedan listos para su contable.",
      time: "10:24 a. m.",
      lockTime: "10:24",
      island: {
        waiting: "Esperando facturas",
        incoming: "Factura por WhatsApp",
        reading: "Leyendo...",
        ready: "Listo para revisar",
        approved: "Aprobado por Ana",
        accountant: "Listo para tu contable",
      } satisfies Record<IslandStep, string>,
      nav: { business: "Mi negocio", home: "Inicio", inbox: "Bandeja", records: "Registros", billing: "Facturación", activity: "Actividad" },
      search: "Buscar",
      add: "Agregar",
      greeting: "Buen día, Ana",
      summary: "Resumen del negocio",
      attention: "Necesita atención",
      showing: (count: number) => `Mostrando ${count} de 5`,
      seeAll: "Ver todo",
      closeMonth: (month: string) => `Para cerrar ${month}`,
      missing: "faltan 4",
      stillReading: "1 todavía leyendo",
      seeWhich: "Ver cuáles",
      stats: [
        ["Ingresos", "RD$ 58.4 mil"],
        ["Gastos", "RD$ 9.6 mil"],
        ["Por cobrar", "RD$ 30,000.00"],
        ["ITBIS a pagar", "RD$ 7.9 mil"],
      ],
      attentionRows: [
        { name: "Ferretería La Esquina", icon: "whatsapp", tag: "Listo para revisar", tone: "new", when: "ahora", action: "Revisar" },
        { name: "IMG_2209.jpg", icon: "whatsapp", tag: "No se pudo leer", tone: "alert", when: "anteayer", action: "Resolver" },
        { name: "Papelería Central", icon: "upload", tag: "Listo para revisar", tone: "new", when: "ayer", action: "Revisar" },
        { name: "colmado-oct.jpg", icon: "envelope", tag: "Varias compras", tone: "alert", when: "hace 3 días", action: "Resolver" },
      ],
      note: { app: "Cuadrao", when: "ahora", body: "Tu factura ya está en la Bandeja." },
      flying: { tag: "Pendiente de revisión", amount: "RD$ 1,250", about: "Compra de materiales · WhatsApp" },
      inbox: {
        title: "Bandeja",
        tabs: { all: "Todos", review: "Por revisar", attention: "Necesitan atención" },
        columns: ["Contenido", "Canal", "Estado", "Monto"],
        invoice: { name: "Ferretería La Esquina", channel: "WhatsApp", amount: "RD$ 1,250.00" },
        states: { reading: "Leyendo...", ready: "Listo para revisar", approved: "Aprobado" } satisfies Record<InvoiceState, string>,
        approve: "Aprobar",
        view: "Ver",
        rows: [
          { name: "Factura de combustible", channel: "Correo", tag: "Listo para revisar", tone: "new", amount: "RD$ 2,300.00", action: "Revisar" },
          { name: "Papelería Central", channel: "Carga manual", tag: "Listo para revisar", tone: "new", amount: "RD$ 845.00", action: "Revisar" },
          { name: "Nube Hosting", channel: "Carga manual", tag: "Aprobado", tone: "done", amount: "US$ 25.00", action: "Ver" },
        ],
      },
      accountant: {
        title: "Tu contable",
        client: "Taller Rodríguez",
        checks: ["47 registros aprobados", "Cada línea con su documento", "606 listo", "607 listo"],
        exportLabel: "Exportar 606 y 607",
        exported: "Exportado",
      },
      cursor: "Ana",
      dock: { receive: "Recibir", square: "Cuadrar", how: "Cómo funciona", exportLabel: "Exportar", bill: "Facturar · En preparación" },
    },
  },
} as const;

export type LandingLocale = keyof typeof landingCopy;
