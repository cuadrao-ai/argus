# Cuadrao: Política de privacidad / Privacy Policy

**Estado / Status:** BORRADOR, no publicado, sin revisión de abogado. / DRAFT, not published, not reviewed by a lawyer.

**Reglas de este borrador / Rules of this draft:** Todo dato desconocido es un marcador visible: `{{...}}` o `[A CONFIRMAR: ...]`. Cada uno está en [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md). Los flujos de datos están en [data-use-register.yaml](data-use-register.yaml). / Every unknown is a visible marker, each listed in OPEN_QUESTIONS.md. The data flows are in the register.

**Relación con el borrador retenido / Relation to the held draft:** La rama `docs/legal-cuadrao-deletion` (PR 781) tiene un borrador de Términos y Privacidad solo para Cuadrao Personal. Este documento conserva su estructura de controles, hogares y eliminación, y corrige los puntos que el [informe de privacidad del 5 de octubre](../reports/2026-10-05-cuadrao-privacy-preflight.md) marcó. / The held draft covers Personal only. This document keeps its controls, household and deletion structure and applies the preflight corrections.

---

## Español (es-419)

_Fecha de entrada en vigor: {{FECHA_DE_VIGENCIA}}_

<a id="es-who-we-are"></a>
### 1. Quiénes somos

Esta política cubre Cuadrao Personal (app para iPhone), Cuadrao Business (app web), el canal de WhatsApp, la recepción de recibos por correo y el sitio de marketing.

El responsable es {{OPERADOR_LEGAL}}, con domicilio en {{DIRECCION_LEGAL}}, país de constitución {{PAIS_DE_CONSTITUCION}}. Contacto de privacidad: {{CONTACTO_PRIVACIDAD}}.

En Cuadrao Business, el dueño del negocio es el responsable de los registros de su negocio. Cuadrao los trata por encargo suyo. Ver los [Términos de Business](terms-business.md).

<a id="es-data-collected"></a>
### 2. Datos que recopilamos, por producto

**Cuadrao Personal**
- Cuenta: correo, nombre si lo das, idioma, identificador del proveedor de inicio de sesión y datos de sesión.
- Lo que registras: cuentas, saldos, movimientos, planes, deudas y lo que compartes con un hogar.
- Chat con Cuadrao y los documentos o fotos que eliges subir.
- Ubicación del recibo, solo si la activas. [A CONFIRMAR: ruta y precisión finales]
- Cuadrao Full (nivel de pago): [A CONFIRMAR: datos de la compra y del agente, hoy no hay compra implementada en el repositorio].

**Cuadrao Business**
- Cuenta del dueño y de las personas con acceso, como el contador.
- Registros del negocio: cuentas, gastos, recibos originales, valores leídos, revisiones, aprobaciones y vínculos a la fuente.
- Datos fiscales que aparecen en un recibo, como RNC, NCF o e-CF e ITBIS, siempre marcados como no verificados hasta que una persona autorizada los revise.

**WhatsApp**
- Guardamos tu número solo como una huella con clave y los últimos 4 dígitos. No guardamos el número completo ni los identificadores de mensaje de Meta.
- Guardamos las fotos y los PDF que envías, el texto de pie de foto y tus respuestas al agente, según lo que hayas activado.

**Correo de recibos**
- La dirección de quien envía, el asunto, el cuerpo y los adjuntos del correo que llega a la dirección de recepción de tu negocio.

**Sitio de marketing**
- Si te anotas: correo, idioma y la versión del texto de consentimiento que viste.
- Si escribes una consulta: lo que escribes. Llega como correo a nuestra bandeja y no se guarda en una base de datos.

**Todos los productos**
- Eventos de uso con un identificador cifrado de la persona, sin perfiles ni grabación de sesión. Datos técnicos, registros y diagnósticos de errores.

<a id="es-why"></a>
### 3. Para qué los usamos

- Prestarte el servicio: iniciar sesión, guardar tus registros, leer tus recibos, preparar borradores y mostrártelos.
- Protegerlo: seguridad, prevención de abuso y de duplicados.
- Responder soporte y mejorar Cuadrao con eventos de uso medidos.

No vendemos tu información. No la usamos para publicidad dirigida. [A CONFIRMAR: el abogado debe validar esta frase frente a la configuración real de los proveedores]

<a id="es-ai-providers"></a>
### 4. Proveedores de IA y qué se envía

En Business pedimos tu permiso para cada función de IA, proveedor, propósito y tipo de dato, y puedes retirarlo. Para el chat, la memoria y la investigación de Personal todavía no existe un permiso guardado. [A CONFIRMAR #828: diseño del permiso antes del lanzamiento]. Cuando exista, retirarlo detendrá las solicitudes futuras. No puede recuperar datos ya enviados.

<a id="es-ai-receipts"></a>
**Lectura de recibos (Personal y Business).** La foto, el PDF o el documento que eliges se envía a un modelo de visión a través de OpenRouter. Se usa solo para leer comercio, monto, fecha y datos fiscales (RNC, NCF, e-CF, ITBIS). El texto actual del permiso de WhatsApp no menciona los datos fiscales y debe actualizarse (ver OPEN_QUESTIONS Q24). El resultado es un borrador. Registrar dinero siempre necesita tu aprobación. Para WhatsApp, el permiso es un interruptor guardado con el texto exacto que viste y el modelo. Si cambia el texto o el modelo, te pedimos permiso otra vez. El modelo exacto se muestra junto al permiso en los ajustes de WhatsApp. [A CONFIRMAR: lista de modelos permitidos y, para cada uno, retención y uso para entrenamiento, ver OPEN_QUESTIONS Q7]. Cada número vinculado tiene un solo permiso de IA activo a la vez: activar uno (lectura de recibos o agente) reemplaza al otro.

<a id="es-ai-business-agent"></a>
**Agente de Business.** Si lo activas para tu WhatsApp vinculado, el texto de tus mensajes y el contexto de borradores que necesita se envían, a través de OpenRouter, a los modelos autorizados para el agente. El agente prepara borradores. No registra gastos por sí solo.

<a id="es-ai-memory"></a>
**Agente de Cuadrao Full y memoria (Personal).** [A CONFIRMAR: el alcance del primer lanzamiento no está decidido]. Según el código actual: un clasificador de OpenRouter revisa el texto de un recuerdo candidato antes de guardarlo, y Perplexity recibe el texto de recuerdos confirmados y tus búsquedas para calcular embeddings. La investigación financiera usa Perplexity.

**Qué pasa con tus datos en esos proveedores.** [A CONFIRMAR: retención y uso para entrenamiento de cada proveedor y modelo]. OpenRouter dice que las políticas de los proveedores varían, así que pasar por OpenRouter no garantiza cero retención. No prometemos que los proveedores no entrenen con tus datos hasta confirmarlo.

<a id="es-whatsapp"></a>
### 5. WhatsApp

Vinculas tu número con un código de un solo uso que envías desde tu propio WhatsApp. Solo procesamos mensajes que tú envías o reenvías. No leemos tu historial, contactos ni perfil. Puedes desvincular el número y retirar el permiso de IA cuando quieras. Meta procesa los mensajes bajo sus propios términos. [A CONFIRMAR: texto del consentimiento para el número de teléfono y la visión de Meta sobre el agente]

<a id="es-email-intake"></a>
### 6. Correo de recibos

Cada negocio tiene una dirección de recepción propia. Los adjuntos se guardan como documentos. El correo pasa por Resend. Leerlos con IA espera tu permiso.

<a id="es-accountant-access"></a>
### 7. Contador y otras personas con acceso

Solo el dueño da acceso. Un permiso indica qué puede hacer la persona y puede vencer o revocarse. Hoy el contador puede ver y preparar; solo el dueño aprueba. Que otra persona apruebe está planeado, no disponible. El contador ve los registros de ese negocio y nada más. Puedes exportar un paquete CSV y Excel con los originales. Una vez descargado, el archivo ya no depende de Cuadrao.

<a id="es-subprocessors"></a>
### 8. Subencargados

| Proveedor | Para qué | Datos |
| --- | --- | --- |
| Supabase | Inicio de sesión y base de datos | Cuenta y registros |
| Render | Alojamiento del servidor | Datos técnicos, registros |
| OpenRouter y los proveedores de modelos detrás | Leer recibos, agentes | Ver sección 4 |
| Perplexity | Investigación financiera y embeddings de memoria | Consultas y texto de recuerdos |
| Meta (WhatsApp) | Mensajería | Mensajes y archivos |
| Resend | Correo de recibos, consultas y avisos | Correos |
| PostHog | Analítica sin perfiles | Eventos con identificador cifrado |
| Apple | Inicio de sesión con Apple, notificaciones, compra del nivel Full | [A CONFIRMAR] |
| Google | Inicio de sesión, si se activa | [A CONFIRMAR] |
| Cloudflare | Dominio y protección contra bots | Datos técnicos |

[A CONFIRMAR: lista final según lo que esté activo al publicar. Un proveedor que no está activo se quita.]

<a id="es-retention"></a>
### 9. Cuánto tiempo conservamos los datos y cómo eliminarlos

Conservamos tus datos mientras tu cuenta esté activa. Puedes eliminar tu cuenta desde la app. La eliminación es una operación que puede quedar pendiente hasta que cada proveedor confirme que terminó, y se reintenta si falla. Una solicitud de eliminación en un proveedor puede quedar pendiente hasta que él confirme.

Al eliminar tu cuenta borramos tu perfil, tus registros, documentos, conversaciones y fuentes conectadas, y revocamos esas conexiones. En un hogar, un saldo pendiente queda congelado fuera de los totales activos. Eliminar la cuenta no lo paga ni lo perdona. Los miembros anteriores conservan sus valores, fechas, categoría y origen, sin recibos, fotos ni texto que te identifique.

**Respaldos y registros.** [A CONFIRMAR: cuánto tardan los respaldos de Supabase, los registros de Render y la analítica de PostHog en borrar datos eliminados]. No prometemos borrado inmediato de respaldos.

**Business.** Los registros fiscales de un negocio pueden tener que conservarse por ley. El deber de conservar los registros fiscales es del dueño del negocio. [A CONFIRMAR con un contador: plazo exacto, el fundador menciona 10 años]. Antes de eliminar una cuenta de Business, el dueño debe exportar lo que necesite. [A CONFIRMAR: cómo se aplica la eliminación a los registros de Business, la regla de retención de Business sigue abierta en el repositorio]

<a id="es-rights"></a>
### 10. Tus derechos

Puedes pedir acceso, corrección, eliminación, oposición y portabilidad de tus datos. En la app puedes editar o borrar lo que registras, desconectar fuentes, retirar permisos de IA (hoy en Business por WhatsApp) y eliminar tu cuenta. Para otras solicitudes, escribe a {{CONTACTO_PRIVACIDAD}}. [A CONFIRMAR: leyes aplicables y plazo de respuesta, incluida la Ley 172-13 de República Dominicana]

<a id="es-transfers"></a>
### 11. Transferencias internacionales

Nuestros proveedores pueden procesar datos fuera de tu país. [A CONFIRMAR: dónde guardan los datos Supabase y Render, y base legal de la transferencia].

<a id="es-security"></a>
### 12. Seguridad

[A CONFIRMAR: cifrado de credenciales de fuentes conectadas, solo si esas fuentes se lanzan]. Los clientes no tienen acceso directo a las tablas de WhatsApp. Las claves de los proveedores solo viven en el servidor. Ningún sistema es perfectamente seguro. [A CONFIRMAR: deberes y plazo de aviso ante una brecha según la ley aplicable]

<a id="es-analytics"></a>
### 13. Analítica y cookies

Medimos eventos de uso con PostHog en nuestros servidores, sin perfiles de persona ni grabación de sesión. Un identificador cifrado no es anonimato legal. [A CONFIRMAR: cookies y consentimiento. La política web vigente de Argus dice que no se necesita un aviso de consentimiento, el abogado debe revisarlo para Cuadrao].

<a id="es-marketing-site"></a>
### 14. Sitio de marketing

Si te anotas, guardamos tu correo para enviarte un aviso de disponibilidad. Para quitarlo, escribe a {{CONTACTO_PRIVACIDAD}}. Al quitarlo, borramos tu correo y conservamos solo una huella para no volver a escribirte.

<a id="es-subscriptions"></a>
### 15. Compras

[A CONFIRMAR: el nivel Full de pago se cobra por compra dentro de la app de Apple. Los datos de pago los maneja Apple, no Cuadrao.]

<a id="es-children"></a>
### 16. Menores

Cuadrao no es para menores de {{EDAD_MINIMA}}. [A CONFIRMAR: edad mínima según la ley aplicable y las reglas de Apple]. Si sabemos que un menor nos dio datos, los eliminamos.

<a id="es-changes"></a>
### 17. Cambios

Si cambiamos esta política, publicamos la nueva versión con su fecha. Si el cambio afecta qué se envía a un proveedor de IA, te pedimos permiso otra vez donde existe un permiso guardado (hoy, Business por WhatsApp). [A CONFIRMAR #828]

<a id="es-contact"></a>
### 18. Contacto

{{OPERADOR_LEGAL}}, {{DIRECCION_LEGAL}}, {{CONTACTO_PRIVACIDAD}}.

---

## English

_Effective date: {{FECHA_DE_VIGENCIA}}_

<a id="en-who-we-are"></a>
### 1. Who we are

This policy covers Cuadrao Personal (iPhone app), Cuadrao Business (web app), the WhatsApp channel, receipt intake by email and the marketing site.

The controller is {{OPERADOR_LEGAL}}, located at {{DIRECCION_LEGAL}}, country of formation {{PAIS_DE_CONSTITUCION}}. Privacy contact: {{CONTACTO_PRIVACIDAD}}.

In Cuadrao Business, the business owner is the controller of the business records. Cuadrao processes them on the owner's behalf. See the [Business Terms](terms-business.md).

<a id="en-data-collected"></a>
### 2. Data we collect, by product

**Cuadrao Personal**
- Account: email, name if you give it, language, sign-in provider identifier and session data.
- What you record: accounts, balances, transactions, plans, debts and what you share with a household.
- Chat with Cuadrao and the documents or photos you choose to upload.
- Receipt location, only if you turn it on. [A CONFIRMAR: final route and precision]
- Cuadrao Full (paid tier): [A CONFIRMAR: purchase and agent data. No purchase implementation exists in the repository today].

**Cuadrao Business**
- The owner's account and the accounts of people with access, such as the accountant.
- Business records: accounts, expenses, original receipts, values read, revisions, approvals and source links.
- Tax data that appears on a receipt, such as RNC, NCF or e-CF and ITBIS, always marked not verified until an authorized person reviews it.

**WhatsApp**
- We store your number only as a keyed digest plus the last 4 digits. We do not store the full number or Meta's message identifiers.
- We store the photos and PDFs you send, caption text, and your replies to the agent, depending on what you turned on.

**Receipt email**
- The sender's address, subject, body and attachments of email that reaches your business's receiving address.

**Marketing site**
- If you sign up: email, language and the version of the consent text you saw.
- If you write an inquiry: what you write. It arrives as an email in our mailbox and is not stored in a database.

**All products**
- Usage events with a keyed identifier of the person, with no profiles or session recording. Technical data, logs and error diagnostics.

<a id="en-why"></a>
### 3. Why we use it

- To provide the service: sign you in, store your records, read your receipts, prepare drafts and show them to you.
- To protect it: security, abuse and duplicate prevention.
- To answer support and improve Cuadrao with measured usage events.

We do not sell your information. We do not use it for targeted advertising. [A CONFIRMAR: a lawyer must validate this sentence against the real provider configuration]

<a id="en-ai-providers"></a>
### 4. AI providers and what is sent

In Business we ask your permission for each AI feature, provider, purpose and kind of data, and you can withdraw it. For Personal chat, memory and research no stored permission exists yet. [A CONFIRMAR #828: permission design before launch]. When it exists, withdrawing it will stop later requests. It cannot recall data already sent.

<a id="en-ai-receipts"></a>
**Receipt reading (Personal and Business).** The photo, PDF or document you choose is sent to a vision model through OpenRouter. It is used only to read the merchant, amount, date and tax data (RNC, NCF, e-CF, ITBIS). The current WhatsApp permission text does not mention tax data and must be updated (see OPEN_QUESTIONS Q24). The result is a draft. Recording money always needs your approval. For WhatsApp, the permission is a switch stored with the exact text you saw and the model. If the text or the model changes, we ask again. The exact model is shown next to the permission in the WhatsApp settings. [A CONFIRMAR: list of allowed models and, for each, retention and training use, see OPEN_QUESTIONS Q7]. Each linked number has only one active AI permission at a time: turning on one (receipt reading or agent) replaces the other.

<a id="en-ai-business-agent"></a>
**Business agent.** If you turn it on for your linked WhatsApp, the text of your messages and the draft context it needs are sent through OpenRouter to the models authorized for the agent. The agent prepares drafts. It does not record expenses by itself.

<a id="en-ai-memory"></a>
**Cuadrao Full agent and memory (Personal).** [A CONFIRMAR: first-release scope is not decided]. Under the current code: an OpenRouter classifier checks the text of a candidate memory before it is stored, and Perplexity receives the text of confirmed memories and your searches to compute embeddings. Financial research uses Perplexity.

**What happens to your data at those providers.** [A CONFIRMAR: retention and training use for each provider and model]. OpenRouter says provider policies vary, so routing through OpenRouter does not guarantee zero retention. We do not promise that providers do not train on your data until that is confirmed.

<a id="en-whatsapp"></a>
### 5. WhatsApp

You link your number with a one-time code that you send from your own WhatsApp. We process only messages you send or forward. We do not read your history, contacts or profile. You can unlink the number and withdraw the AI permission at any time. Meta processes the messages under its own terms. [A CONFIRMAR: phone-number consent wording and Meta's view of the agent]

<a id="en-email-intake"></a>
### 6. Receipt email

Each business has its own receiving address. Attachments are saved as documents. The email passes through Resend. Reading them with AI waits for your permission.

<a id="en-accountant-access"></a>
### 7. Accountant and other people with access

Only the owner grants access. A grant says what the person can do and can expire or be revoked. Today an accountant can view and prepare; only the owner approves. Approval by someone else is planned, not available. The accountant sees that business's records and nothing else. You can export a CSV and Excel package with the originals. Once downloaded, the file no longer depends on Cuadrao.

<a id="en-subprocessors"></a>
### 8. Subprocessors

| Provider | Purpose | Data |
| --- | --- | --- |
| Supabase | Sign-in and database | Account and records |
| Render | Server hosting | Technical data, logs |
| OpenRouter and the model providers behind it | Receipt reading, agents | See section 4 |
| Perplexity | Financial research and memory embeddings | Queries and memory text |
| Meta (WhatsApp) | Messaging | Messages and files |
| Resend | Receipt email, inquiries and notices | Emails |
| PostHog | Analytics without profiles | Events with a keyed identifier |
| Apple | Sign in with Apple, notifications, Full tier purchase | [A CONFIRMAR] |
| Google | Sign-in, if enabled | [A CONFIRMAR] |
| Cloudflare | Domain and bot protection | Technical data |

[A CONFIRMAR: final list according to what is active at publication. A provider that is not active is removed.]

<a id="en-retention"></a>
### 9. How long we keep data and how to delete it

We keep your data while your account is active. You can delete your account in the app. Deletion is an operation that can stay pending until each provider confirms it finished, and it is retried if it fails. A deletion request at a provider can stay pending until that provider confirms.

When you delete your account we delete your profile, records, documents, conversations and connected sources, and revoke those connections. In a household, an unsettled balance is frozen outside active totals. Deleting the account does not pay or forgive it. Former members keep their values, dates, category and origin, without receipts, photos or text that identifies you.

**Backups and logs.** [A CONFIRMAR: how long Supabase backups, Render logs and PostHog analytics take to erase deleted data]. We do not promise immediate erasure from backups.

**Business.** A business's tax records may have to be kept by law. The duty to keep tax records belongs to the business owner. [A CONFIRMAR with an accountant: exact period, the founder mentions 10 years]. Before deleting a Business account, the owner should export what they need. [A CONFIRMAR: how deletion applies to Business records, the Business retention rule is still open in the repository]

<a id="en-rights"></a>
### 10. Your rights

You can ask for access, correction, deletion, objection and portability of your data. In the app you can edit or delete what you record, disconnect sources, withdraw AI permissions (today in Business by WhatsApp) and delete your account. For other requests write to {{CONTACTO_PRIVACIDAD}}. [A CONFIRMAR: applicable laws and response time, including Dominican Law 172-13]

<a id="en-transfers"></a>
### 11. International transfers

Our providers may process data outside your country. [A CONFIRMAR: where Supabase and Render store data, and the legal basis for the transfer].

<a id="en-security"></a>
### 12. Security

[A CONFIRMAR: encryption of connected-source credentials, only if those sources ship]. Clients have no direct access to the WhatsApp tables. Provider keys live only on the server. No system is perfectly secure. [A CONFIRMAR: breach duties and notice deadline under the applicable law]

<a id="en-analytics"></a>
### 13. Analytics and cookies

We measure usage events with PostHog on our servers, with no person profiles and no session recording. A keyed identifier is not legal anonymity. [A CONFIRMAR: cookies and consent. The current Argus web policy says no consent banner is needed, a lawyer must review that for Cuadrao].

<a id="en-marketing-site"></a>
### 14. Marketing site

If you sign up, we keep your email to send you one availability notice. To remove it, write to {{CONTACTO_PRIVACIDAD}}. On removal we erase your email and keep only a digest so we do not write to you again.

<a id="en-subscriptions"></a>
### 15. Purchases

[A CONFIRMAR: the paid Full tier is billed by in-app purchase through Apple. Apple handles payment data, not Cuadrao.]

<a id="en-children"></a>
### 16. Children

Cuadrao is not for people under {{EDAD_MINIMA}}. [A CONFIRMAR: minimum age under the applicable law and Apple rules]. If we learn a child gave us data, we delete it.

<a id="en-changes"></a>
### 17. Changes

If we change this policy, we publish the new version with its date. If the change affects what is sent to an AI provider, we ask for your permission again where a stored permission exists (today, Business by WhatsApp). [A CONFIRMAR #828]

<a id="en-contact"></a>
### 18. Contact

{{OPERADOR_LEGAL}}, {{DIRECCION_LEGAL}}, {{CONTACTO_PRIVACIDAD}}.

---

## Fuentes / Sources

Cada afirmación factual sale de estas rutas. / Each factual claim comes from these paths.

- Flujos y consentimientos: [data-use-register.yaml](data-use-register.yaml), [ai_consent.py](../../src/argus/domain/ingestion/whatsapp/ai_consent.py), [receipt_consent.py](../../src/argus/domain/ingestion/whatsapp/receipt_consent.py).
- WhatsApp (huella del número, últimos 4 dígitos, solo mensajes del dueño): [migración whatsapp_intake](../../supabase/migrations/20261008130000_whatsapp_intake.sql), [cuadrao-whatsapp-intake](../specs/lanes/cuadrao-whatsapp-intake.md), [API_CONTRACT](../API_CONTRACT.md).
- Correo de recibos y documentos con consentimiento falso hasta que el dueño elige: [API_CONTRACT](../API_CONTRACT.md).
- Modelos del agente de Business: [interpretation.py](../../src/argus/agent_runtime/business/interpretation.py), [runner.py](../../src/argus/agent_runtime/business/runner.py).
- Proveedores, memoria, embeddings, análisis, eliminación pendiente: [informe de privacidad](../reports/2026-10-05-cuadrao-privacy-preflight.md), [ARCHITECTURE](../ARCHITECTURE.md).
- Sitio de marketing: [contrato de formularios](../specs/cuadrao-marketing-forms-contract.md).
- Retención de Business abierta: [DATA_MODEL](../DATA_MODEL.md), [decision log](../specs/argus-decision-log.md).
- Borrador retenido (PR 781, rama `docs/legal-cuadrao-deletion`): hogares, controles, proveedores, eliminación.
