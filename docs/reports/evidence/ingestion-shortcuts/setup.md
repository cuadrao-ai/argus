# Captura con Atajos de Apple / Apple Shortcuts capture setup

**Estado / Status:** experimental, desactivado por defecto / experimental,
default-off. **Nada de esta guía se ha probado en un iPhone físico** / **none
of this guide has been run on a physical iPhone yet**; see the
[device test protocol](device-test-protocol.md). Los nombres de acciones en
español no se pudieron verificar en la app y están marcados *(sin verificar)*;
English labels are the ones guides report and are marked *(unverified)* where
they changed across iOS versions. Capabilities and sources:
[capabilities.md](capabilities.md).

Lo que hace / What it does: cada vez que pagas con una tarjeta de Wallet en una
tienda, el atajo envía a Cuadrao el monto que muestra Wallet, el comercio y el
nombre de la tarjeta. Cuadrao lo guarda como **borrador para revisar**; no
cambia saldos ni presupuestos hasta que lo confirmes. / Each in-store Wallet
tap sends the amount text, merchant and card name to Cuadrao as a **draft to
review**; nothing changes balances or budgets until you confirm it.

Lo que no hace / What it does not do: no ve compras en línea, no ve todas las
tarjetas, puede no ejecutarse si Wallet recibe tarde los datos del banco, y
puede ejecutarse en un pago rechazado. / It misses online purchases and some
cards, may not run when the bank's data reaches Wallet late, and may run for a
declined tap. Tus estados de cuenta siguen siendo la fuente completa. / Your
statements remain the complete source.

## 1. Conectar el iPhone / Connect the iPhone

1. ES: En Cuadrao, abre Conexiones y elige "Atajos de Apple". Ponle un nombre
   al dispositivo (por ejemplo "iPhone de Ana").
   EN: In Cuadrao, open Connections and choose "Apple Shortcuts". Name the
   device (for example "Ana's iPhone").
   *(La pantalla nativa aún no existe; hoy es la llamada
   `POST /api/v1/financial-connections/shortcuts/devices`. / The native screen
   does not exist yet; today this is the API call above.)*
2. ES: Cuadrao muestra un **código del dispositivo** (empieza con `sct1.`) **una
   sola vez**. Cópialo. Si lo pierdes, desconecta el dispositivo y conéctalo de
   nuevo.
   EN: Cuadrao shows a **device token** (starts with `sct1.`) **once**. Copy
   it. If you lose it, disconnect the device and connect it again.

## 2. Crear la automatización / Build the automation

ES: Abre **Atajos** → pestaña **Automatización** → **Nueva automatización**
(o "+"). EN: Open **Shortcuts** → **Automation** tab → **New Automation**
(or "+").

1. Disparador / Trigger:
   - iOS 17-25: **Transacción** *(sin verificar)* / **Transaction**.
   - iOS 26 y 27: **Cartera** o **Wallet** → "Cuando toco" *(sin verificar)* /
     **Wallet** → "When I tap" *(unverified; reported renamed in iOS 26)*.
   - ES: Elige solo las tarjetas que quieres registrar. Deja todas las
     categorías y no filtres comercios. EN: Pick only the cards you want to
     track; keep all categories; no merchant filter.
2. ES: Elige **Ejecutar inmediatamente** *(sin verificar)* y desactiva
   "Preguntar antes de ejecutar". EN: Choose **Run Immediately** and turn off
   "Ask Before Running".
3. ES: Crea un atajo nuevo con estas acciones, en este orden. EN: Create a new
   shortcut with these actions, in order.

| # | ES | EN | Valor / Value |
| --- | --- | --- | --- |
| 1 | Texto *(sin verificar)* | Text | Pega el código `sct1.…` / paste the `sct1.…` token. Renómbralo "Código" / rename the variable "Token" |
| 2 | Fecha actual | Current Date | |
| 3 | Formatear fecha | Format Date | Formato / Format: **ISO 8601**, con hora / include time |
| 4 | Número aleatorio | Random Number | 1 a / to 999999999 |
| 5 | Texto | Text | `[Fecha formateada]-[Número aleatorio]` → variable "ID" |
| 6 | Obtener contenido de URL | Get Contents of URL | URL: `https://<api>/api/v1/ingestion/shortcuts/events`; Método / Method: **POST**; Encabezados / Headers: `Authorization` = `Bearer [Código]`; Cuerpo / Request Body: **JSON** with the fields below |
| 7 | Obtener valor de diccionario | Get Dictionary Value | Clave / Key: `receipt_id` from "Contenido de URL / Contents of URL" |
| 8 | Si | If | "Valor de diccionario" **no tiene ningún valor** / **does not have any value** |
| 9 | Mostrar notificación | Show Notification | "Cuadrao no guardó este pago / Cuadrao did not save this payment" |
| 10 | Fin si | End If | |

Campos JSON (todos de tipo **Texto**) / JSON fields (all of type **Text**):

| Clave / Key | Valor / Value |
| --- | --- |
| `event_id` | variable "ID" |
| `kind` | `transaction` |
| `source_app` | `wallet` |
| `captured_at` | Fecha formateada / Formatted Date |
| `amount` | Entrada del atajo → Importe / Shortcut Input → Amount |
| `merchant` | Entrada del atajo → Comercio / Shortcut Input → Merchant |
| `card` | Entrada del atajo → Tarjeta o pase / Shortcut Input → Card or Pass |
| `currency` *(opcional / optional)* | ES: solo si **esta tarjeta** siempre cobra en una moneda y Wallet muestra "$" sin decir cuál: escribe `DOP` o `USD`. EN: only if **this card** always charges one currency and Wallet shows a bare "$": type `DOP` or `USD`. Use one automation per card for this |
| `card_last4` *(opcional / optional)* | ES: los 4 últimos dígitos, escritos por ti. EN: the last four digits, typed by you |

ES: No envíes el monto como Número: Cuadrao lee el texto tal cual y, si "$"
puede ser pesos o dólares, te lo pregunta en la revisión. EN: Do not convert the
amount to a Number: Cuadrao reads the text as shown and asks you in review when
"$" could be pesos or dollars.

## 3. Sin conexión (opcional) / Offline fallback (optional)

ES: Atajos no reintenta. Si el pago ocurre sin señal, "Obtener contenido de URL"
falla y el atajo se detiene: **ese pago se pierde** salvo que uses esta
alternativa. Mientras Cuadrao no tenga activada la revisión, toda captura
responde "no guardado" y también se perdería. EN: Shortcuts never retries.
Without signal "Get Contents of URL" fails and the shortcut stops: **that
capture is lost** unless you use this fallback. Until Cuadrao's review queue is
on, every capture answers "not saved" and would also be lost.

Cambios al atajo del paso 2 / Changes to the step 2 shortcut:

1. ES: Antes de la acción 6, añade **Diccionario** con los mismos campos y
   luego **Texto** con `[Diccionario]` (debe producir JSON en una línea;
   *verificar en el dispositivo*). EN: Before action 6 add **Dictionary** with
   the same fields, then **Text** containing `[Dictionary]` (should yield
   one-line JSON; *verify on device*).
2. ES: **Añadir al archivo de texto** *(sin verificar)*: el Texto anterior, en
   `Atajos/Cuadrao/pendientes.txt`, "Crear nueva línea" activado. EN: **Append
   to Text File**: that Text, to `Shortcuts/Cuadrao/pending.txt`, "Make New
   Line" on.
3. ES: En la acción 6 cambia el cuerpo a **Archivo** con ese Texto y añade el
   encabezado `Content-Type: application/json`. EN: In action 6 set the body to
   **File** with that Text and add the header `Content-Type: application/json`.
4. ES: Si `receipt_id` tiene valor: **Obtener archivo** (pendientes.txt) →
   **Reemplazar texto** (busca el Texto exacto, expresión regular desactivada,
   reemplaza por nada) → **Guardar archivo** (sobrescribir). EN: If
   `receipt_id` has a value: **Get File** → **Replace Text** (the exact Text,
   regular expression off, replace with nothing) → **Save File** (overwrite).

Atajo manual "Enviar pendientes" / Manual "Send pending captures" shortcut.
ES: envía en tandas de **25 líneas** (cada tanda queda muy por debajo del
límite de 256 KiB aunque las capturas sean mensajes largos) y repite hasta 8
tandas, es decir hasta 200 capturas por ejecución. EN: it sends **25 lines** per
batch (well under the 256 KiB cap even for long message captures) and repeats
up to 8 batches, i.e. up to 200 captures per run.

1. **Repetir / Repeat** 8 veces / times:
   1. **Obtener archivo / Get File** `pendientes.txt` / `pending.txt`
      ("Error si no se encuentra" desactivado / "Error If Not Found" off).
   2. **Ajustar espacios / Trim Whitespace** *(sin verificar / unverified)* y
      luego / then **Dividir texto / Split Text** por nuevas líneas / by New
      Lines → variable "Lista" / "Lines".
   3. **Si / If** **Contar / Count** de "Lista" es 0: **Mostrar notificación /
      Show Notification** "Nada pendiente / Nothing pending" y **Detener este
      atajo / Stop This Shortcut**.
   4. **Obtener elementos de la lista / Get Items from List**: rango / range
      1-25 → **Combinar texto / Combine Text** con / with `,` →
      **Texto / Text** `{"events":[` `[Texto combinado / Combined Text]` `]}`.
   5. **Obtener contenido de URL / Get Contents of URL**:
      `https://<api>/api/v1/ingestion/shortcuts/events/batch`, POST,
      encabezados / headers `Authorization: Bearer [Código]` y / and
      `Content-Type: application/json`, cuerpo **Archivo** / body **File** = the
      Text above.
   6. ES: **Si** la respuesta **no** tiene `receipts`, **o** su texto contiene
      `not_saved`: muestra "No se enviaron; intenta más tarde" y **Detener este
      atajo** (el archivo queda igual; reenviar es seguro). EN: **If** the
      response has **no** `receipts`, **or** its text contains `not_saved`:
      show "Not sent; try later" and **Stop This Shortcut** (the file is kept;
      re-sending is safe).
   7. ES: Si no, quita esas 25 líneas: si "Lista" tiene más de 25, **Obtener
      elementos de la lista** 26 a "Contar", **Combinar texto** con nueva
      línea y **Guardar archivo** sobre `pendientes.txt` (sobrescribir); si
      no, guarda un archivo vacío. EN: Otherwise drop those 25 lines: if
      "Lines" has more than 25, **Get Items from List** 26 to Count, **Combine
      Text** with New Lines and **Save File** over `pending.txt` (overwrite);
      otherwise save an empty file.
2. ES: Si aún quedan pendientes después de 8 tandas, ejecútalo otra vez.
   EN: If captures remain after 8 batches, run it again.

ES: Reenviar es seguro: cada captura tiene su `event_id` y Cuadrao no la
duplica. Cada recibo dice qué pasó: `recorded`/`unchanged` (guardada),
`not_saved` (reenvíala), `out_of_window` (más de 30 días: no se puede guardar)
o `rejected` (no válida). Por eso el paso 6 conserva el archivo si hay algún
`not_saved`. EN: Re-sending is safe: each capture has its `event_id` and is
never duplicated. Each receipt says what happened: `recorded`/`unchanged`
(held), `not_saved` (send again), `out_of_window` (older than 30 days: cannot
be saved) or `rejected` (invalid). That is why step 6 keeps the file when any
receipt is `not_saved`.

## 4. Mensajes del banco (opcional) / Bank SMS (optional)

ES: Disparador **Mensaje** → "El remitente es" el número corto de tu banco
*(sin verificar)*, **Ejecutar inmediatamente**. Cuerpo JSON: `event_id`,
`kind` = `message_capture`, `source_app` = `messages`, `captured_at`,
`sender` (el nombre que tú elijas), `text` = Entrada del atajo (el mensaje).
Cuadrao guarda el texto para que lo revises; **no lee montos del mensaje** en
esta versión. EN: **Message** trigger → "Sender is" your bank's short code,
**Run Immediately**. JSON body as listed with `kind` = `message_capture`,
`source_app` = `messages`, `text` = Shortcut Input. Cuadrao keeps the text for
your review and **does not read amounts from it** in this version.

ES/EN: En iOS 27 existe, según reseñas, un disparador **Notificación** de una
app (por ejemplo la app del banco). Usa `source_app` = `notifications` con los
mismos campos. *Sin verificar en dispositivo.* / iOS 27 reportedly adds an app
**Notification** trigger; use `source_app` = `notifications`. *Unverified on a
device.*

## 5. Privacidad / Privacy

- ES: El código queda escrito dentro del atajo. **Cualquiera con tu iPhone
  desbloqueado puede verlo**, y **compartir el atajo comparte el código**. No
  compartas este atajo. EN: The token is written inside the shortcut.
  **Anyone with your unlocked iPhone can read it**, and **sharing the shortcut
  shares the token**. Do not share this shortcut.
- ES: El código solo sirve para añadir borradores a tu revisión; no permite
  leer nada de Cuadrao. EN: The token can only add drafts to your review; it
  cannot read anything from Cuadrao.
- ES: Si lo compartiste o perdiste el iPhone, **desconecta el dispositivo** en
  Cuadrao: el código deja de funcionar al instante y se borran los borradores
  sin revisar de ese dispositivo. EN: If you shared it or lost the phone,
  **disconnect the device** in Cuadrao: the token stops working immediately
  and unreviewed drafts from that device are removed.
- ES: Cuadrao no guarda el código, solo una huella (hash) para reconocerlo.
  EN: Cuadrao keeps only a hash of the token, never the token.

## 6. Desactivar / Turn it off

ES: Atajos → Automatización → tu automatización → desactiva "Activar esta
automatización" o bórrala; y en Cuadrao desconecta el dispositivo. EN:
Shortcuts → Automation → your automation → turn off "Enable This Automation" or
delete it; then disconnect the device in Cuadrao. Los borradores ya confirmados
se quedan; los no revisados se borran. / Confirmed entries stay; unreviewed
drafts are removed.
