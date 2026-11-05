# Cuadrao Business: Términos y acuerdo de tratamiento de datos / Terms and Data Processing Agreement

**Estado / Status:** BORRADOR, no publicado, sin revisión de abogado. / DRAFT, not published, not reviewed by a lawyer.

Los marcadores `{{...}}` y `[A CONFIRMAR: ...]` están en [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md). Business es por invitación. [A CONFIRMAR: si Business es solo para empresas (B2B), eso cambia las reglas de consumidores]. / Business is invite-only. Whether it is B2B only is open.

---

## Español (es-419)

_Fecha de entrada en vigor: {{FECHA_DE_VIGENCIA}}_

### Parte A. Términos de uso

**A1. Quiénes somos.** Cuadrao Business lo ofrece {{OPERADOR_LEGAL}}, con domicilio en {{DIRECCION_LEGAL}}. Es una app web por invitación para llevar los gastos de un negocio, con recibos por WhatsApp, por correo o por la web.

**A2. Quién puede usarla.** Una persona con autoridad para actuar por el negocio (el dueño). El dueño puede dar acceso a otras personas, por ejemplo a su contador. Cada persona usa su propia cuenta.

**A3. Cuadrao prepara, tú apruebas.** Cuadrao lee recibos y prepara borradores. Un gasto se registra solo cuando una persona autorizada lo aprueba. Cada aprobación queda con su fuente y su historial de revisiones.

**A4. No es asesoría fiscal ni contable.** Cuadrao no hace declaraciones, no presenta nada a la DGII y no da una opinión fiscal. El contador del negocio decide el tratamiento fiscal.

**A5. Revisiones de facturas y comprobantes (DGII, e-CF).** Cuadrao lee RNC, NCF o e-CF e ITBIS de un recibo. Cada valor aparece como no verificado hasta que una persona autorizada lo revise. Una revisión que hace Cuadrao es evidencia para una persona, nunca una opinión fiscal ni una prueba de validez ante la DGII. La validez se comprueba en el portal de la DGII. [A CONFIRMAR: si existe una delegación de DGII solo de consulta que permita comprobar automáticamente]

**A6. Factura de consumo (tipo 32).** Un comprobante de consumo, como el B02 en papel, no respalda por sí solo un crédito de ITBIS ni una deducción de ISR. Cuadrao puede leer uno y mostrarlo, pero no lo trata como respaldo fiscal. [A CONFIRMAR con un contador: cómo se aplica al e-CF tipo 32 y su monto límite]

**A7. Faltan recibos.** Que falte un recibo no prueba que un proveedor no esté registrado. Cuadrao lo registra y deja el estado del proveedor como desconocido para el contador.

**A8. Gastos del dueño.** Un gasto pagado con dinero propio se registra contra una fuente "fondos del dueño". El contador decide si es un aporte de capital o una deuda con el dueño.

**A9. Uso aceptable.** No uses Cuadrao para romper la ley, subir datos que no puedes subir, acceder a negocios que no son tuyos ni presentar sus resultados como asesoría profesional.

**A10. Precio.** [A CONFIRMAR: Business es por invitación, el precio y la facturación no están definidos].

**A11. Garantías, responsabilidad, ley aplicable.** [A CONFIRMAR: el abogado los redacta. Dependen de {{PAIS_DE_CONSTITUCION}}].

**A12. Terminación y exportación.** Puedes dejar de usar Cuadrao cuando quieras. Antes de cerrar, exporta lo que necesites (sección B8).

**A13. Contacto.** {{OPERADOR_LEGAL}}, {{CONTACTO_SOPORTE}}.

### Parte B. Acuerdo de tratamiento de datos

**B1. Roles.** El dueño del negocio es el responsable de los registros del negocio: los recibos, los gastos, las aprobaciones y los datos de sus clientes y proveedores que aparezcan. Cuadrao ({{OPERADOR_LEGAL}}) los trata por encargo y según las instrucciones del dueño. Para los datos de la cuenta de cada persona y para la seguridad y mejora del servicio, Cuadrao es responsable. [A CONFIRMAR: el abogado valida este reparto según la ley aplicable]

**B2. Qué tratamos y para qué.** Los datos del [registro de uso de datos](data-use-register.yaml), en los flujos de producto Business: registros del negocio, lectura de recibos, agente de WhatsApp, recepción por correo, acceso del contador y exportación. El propósito es prestar el servicio al dueño.

**B3. Subencargados.** Supabase (base de datos), Render (alojamiento), OpenRouter y los proveedores de modelos detrás (lectura de recibos y agente), Meta (WhatsApp), Resend (correo) y PostHog (analítica sin perfiles). La [Política de privacidad](privacy-policy.md#es-subprocessors) tiene la lista vigente. [A CONFIRMAR: cómo se avisa al dueño de un cambio y si puede oponerse]

**B4. IA.** La lectura de recibos y el agente envían datos a OpenRouter solo con el permiso del dueño. El permiso de WhatsApp se guarda con el texto exacto y el modelo, y pide permiso otra vez si cambian. Se puede revocar. El agente no registra gastos por sí solo. [A CONFIRMAR: uso para entrenamiento por modelo]

**B5. Acceso del contador.** Solo el dueño da acceso. Cada permiso dice qué puede hacer la persona, puede vencer y se puede revocar. Hoy el contador puede ver y preparar; solo el dueño aprueba. Que un contador o una firma apruebe está planeado, no disponible. [A CONFIRMAR: la firma de contadores y la delegación de una firma contable, que es una fase posterior]. Cada acción de una persona con permiso queda registrada con quién la hizo.

**B6. WhatsApp.** El dueño vincula su propio número con un código de un solo uso. Cuadrao guarda una huella del número y sus últimos 4 dígitos. Solo se procesan mensajes que el dueño envía o reenvía. Dar de baja (opt-out): el dueño puede desvincular el número y retirar el permiso de IA en cualquier momento. Después, Cuadrao deja de aceptar mensajes de ese número y deja de enviarlos a IA. [A CONFIRMAR: texto del consentimiento para el número de teléfono, reglas de plantillas y opt-in de Meta, y si Meta permite el agente]

**B7. Seguridad.** Acceso limitado por negocio y por permiso, sin acceso directo de clientes a las tablas de WhatsApp, y claves de proveedores solo en el servidor. [A CONFIRMAR: medidas técnicas finales y plazo de aviso de brechas según la ley aplicable]

**B8. Exportación y devolución.** El dueño puede exportar un paquete CSV y Excel con los recibos originales. Al terminar el servicio, el dueño exporta sus registros antes de eliminar la cuenta. [A CONFIRMAR: tiempo de gracia y cómo se aplica la eliminación a los registros de Business, la regla de retención de Business sigue abierta]

**B9. Conservación fiscal.** El deber de conservar los registros fiscales es del dueño. [A CONFIRMAR con un contador: el plazo, el fundador menciona 10 años]. Cuadrao no promete guardar los registros para siempre.

**B10. Derechos de las personas.** Si una persona pide acceso, corrección o eliminación de datos de un negocio, Cuadrao ayuda al dueño a responder. [A CONFIRMAR: plazo y procedimiento, incluida la Ley 172-13]

**B11. Brechas.** Cuadrao avisa al dueño sin demora injustificada si detecta una brecha que afecte sus registros. [A CONFIRMAR: plazo exacto]

**B12. Transferencias internacionales.** [A CONFIRMAR: dónde guardan los datos Supabase y Render].

---

## English

_Effective date: {{FECHA_DE_VIGENCIA}}_

### Part A. Terms of Use

**A1. Who we are.** Cuadrao Business is offered by {{OPERADOR_LEGAL}}, located at {{DIRECCION_LEGAL}}. It is an invite-only web app to keep a business's expenses, with receipts by WhatsApp, email or the web.

**A2. Who can use it.** A person with authority to act for the business (the owner). The owner can give access to others, for example the accountant. Each person uses their own account.

**A3. Cuadrao prepares, you approve.** Cuadrao reads receipts and prepares drafts. An expense is recorded only when an authorized person approves it. Each approval keeps its source and revision history.

**A4. Not tax or accounting advice.** Cuadrao does not file returns, does not submit anything to the DGII and does not give a tax opinion. The business's accountant decides the tax treatment.

**A5. Invoice and receipt checks (DGII, e-CF).** Cuadrao reads RNC, NCF or e-CF and ITBIS from a receipt. Each value shows as not verified until an authorized person reviews it. A check Cuadrao makes is evidence for a person. It is never a tax opinion or proof of validity before the DGII. Validity is checked in the DGII portal. [A CONFIRMAR: whether a query-only DGII delegation exists that would allow automatic checks]

**A6. Consumer invoice (type 32).** A consumer receipt, like the paper B02, does not by itself support an ITBIS credit or an ISR deduction. Cuadrao may read one and show it, but does not treat it as tax support. [A CONFIRMAR with an accountant: how this applies to e-CF type 32 and its amount limit]

**A7. Missing receipts.** A missing receipt does not prove a supplier is unregistered. Cuadrao records it and leaves the supplier status unknown for the accountant.

**A8. Owner spending.** An expense paid with the owner's own money is recorded against an "owner funds" source. The accountant decides whether it is a capital contribution or a debt to the owner.

**A9. Acceptable use.** Do not use Cuadrao to break the law, upload data you may not upload, access businesses that are not yours or present its results as professional advice.

**A10. Price.** [A CONFIRMAR: Business is invite-only, price and billing are not defined].

**A11. Warranties, liability, governing law.** [A CONFIRMAR: a lawyer drafts them. They depend on {{PAIS_DE_CONSTITUCION}}].

**A12. Termination and export.** You can stop using Cuadrao at any time. Before closing, export what you need (section B8).

**A13. Contact.** {{OPERADOR_LEGAL}}, {{CONTACTO_SOPORTE}}.

### Part B. Data Processing Agreement

**B1. Roles.** The business owner is the controller of the business records: receipts, expenses, approvals and any customer or supplier data they contain. Cuadrao ({{OPERADOR_LEGAL}}) processes them on the owner's behalf and under the owner's instructions. For each person's account data and for the security and improvement of the service, Cuadrao is the controller. [A CONFIRMAR: a lawyer validates this split under the applicable law]

**B2. What we process and why.** The data in the [data-use register](data-use-register.yaml), for the Business product flows: business records, receipt reading, WhatsApp agent, email intake, accountant access and export. The purpose is to provide the service to the owner.

**B3. Subprocessors.** Supabase (database), Render (hosting), OpenRouter and the model providers behind it (receipt reading and agent), Meta (WhatsApp), Resend (email) and PostHog (analytics without profiles). The [Privacy Policy](privacy-policy.md#en-subprocessors) has the current list. [A CONFIRMAR: how the owner is told of a change and whether they can object]

**B4. AI.** Receipt reading and the agent send data to OpenRouter only with the owner's permission. The WhatsApp permission is stored with the exact text and the model, and asks again if either changes. It can be revoked. The agent does not record expenses by itself. [A CONFIRMAR: training use per model]

**B5. Accountant access.** Only the owner grants access. Each grant says what the person can do, can expire and can be revoked. Today an accountant can view and prepare; only the owner approves. Approval by an accountant or a firm is planned, not available. [A CONFIRMAR: firm-level delegation, which is a later phase]. Every action by a granted person is recorded with who did it.

**B6. WhatsApp.** The owner links their own number with a one-time code. Cuadrao stores a digest of the number and its last 4 digits. Only messages the owner sends or forwards are processed. Opt-out: the owner can unlink the number and withdraw the AI permission at any time. After that, Cuadrao stops accepting messages from that number and stops sending them to AI. [A CONFIRMAR: phone-number consent wording, Meta's template and opt-in rules, and whether Meta allows the agent]

**B7. Security.** Access limited by business and by grant, no direct client access to the WhatsApp tables, and provider keys only on the server. [A CONFIRMAR: final technical measures and breach notice deadline under the applicable law]

**B8. Export and return.** The owner can export a CSV and Excel package with the original receipts. When the service ends, the owner exports their records before deleting the account. [A CONFIRMAR: grace period and how deletion applies to Business records, the Business retention rule is still open]

**B9. Tax record retention.** The duty to keep tax records belongs to the owner. [A CONFIRMAR with an accountant: the period, the founder mentions 10 years]. Cuadrao does not promise to keep records forever.

**B10. People's rights.** If a person asks for access, correction or deletion of data in a business's records, Cuadrao helps the owner respond. [A CONFIRMAR: deadline and procedure, including Law 172-13]

**B11. Breaches.** Cuadrao tells the owner without undue delay if it detects a breach that affects their records. [A CONFIRMAR: exact deadline]

**B12. International transfers.** [A CONFIRMAR: where Supabase and Render store data].

---

## Fuentes / Sources

- Aprobación humana, fuente y revisiones; agente sin registro automático: [especificación de ejecución de Business](../specs/lanes/cuadrao-business-agent-execution-spec.md) (D4 valores no verificados, L10 fondos del dueño, B02, recibos faltantes).
- Permisos de WhatsApp con texto y modelo, revocación: [ai_consent.py](../../src/argus/domain/ingestion/whatsapp/ai_consent.py), [migración de consentimiento](../../supabase/migrations/20261011100000_business_whatsapp_ai_consent.sql).
- Número como huella y últimos 4 dígitos; solo mensajes del dueño: [migración whatsapp_intake](../../supabase/migrations/20261008130000_whatsapp_intake.sql), [cuadrao-whatsapp-intake](../specs/lanes/cuadrao-whatsapp-intake.md), [API_CONTRACT](../API_CONTRACT.md).
- Permisos de acceso (leer, preparar, aprobar, vencimiento, revocación): [migración de base de Business](../../supabase/migrations/20261010223000_business_contract_foundation.sql).
- Retención de Business abierta: [DATA_MODEL](../DATA_MODEL.md), [decision log](../specs/argus-decision-log.md).
- Exportación CSV y Excel con originales: [especificación de ejecución de Business](../specs/lanes/cuadrao-business-agent-execution-spec.md) (D1).
