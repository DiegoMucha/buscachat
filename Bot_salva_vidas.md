# Bot Salva Vidas — Documentación técnica

Asistente conversacional para **consulta y registro de personas desaparecidas tras un terremoto**. Corre sobre **n8n** + **Redis**, funciona en **Telegram** y **WhatsApp**, y por ahora es un **prototipo determinístico** (sin IA): guía al usuario por opciones y recolecta datos. Las búsquedas reales (reconocimiento facial / por nombre) son funciones que se conectarán en la siguiente iteración.

> **Estado actual:** la conversación funciona de punta a punta (menús, pasos, recolección de datos, fotos, memoria). Lo que todavía **no** ocurre es la ejecución real contra una base de datos o un servicio. Los mensajes de cierre son placeholders honestos del tipo *"aquí aparecerán los resultados cuando conectemos la base de datos"*.

---

## 1. Idea en una frase

Un motor determinístico que **guía y recolecta** datos por opciones, y al cerrar cada flujo emite una **acción** (una etiqueta) que mañana dispara la API correspondiente. El motor nunca "razona": solo sigue reglas y una máquina de estados.

---

## 2. Arquitectura

```
Telegram Trigger ─┐
                  ├─► Extraer Mensaje ─► ¿Procesar? ─► Obtener Historial ─► Obtener Estado
Webhook (WhatsApp)┘   (normaliza)        (filtro)          (Redis get)        (Redis get)
                                                                                    │
                                                                                    ▼
                                                                          Motor Conversacional
                                                                            (toda la lógica)
                                                                                    │
                                                                                    ▼
                                                          Guardar Historial ─► Guardar Estado ─► Send (Telegram)
                                                              (Redis set)         (Redis set)
```

Tres piezas conceptuales:

1. **Entrada multicanal normalizada** — un solo nodo entiende Telegram y WhatsApp, texto e imagen, y lo deja todo en un formato común.
2. **Motor conversacional determinístico** — un único nodo de código con la máquina de estados y todas las reglas.
3. **Persistencia en Redis** — el "paso actual" (estado) y la memoria de la conversación viven en Redis, no en n8n.

---

## 3. Recorrido nodo por nodo

| Nodo | Tipo | Qué hace |
|------|------|----------|
| **Telegram Trigger** | telegramTrigger | Recibe mensajes de Telegram (updates: `message`). |
| **Webhook** | webhook (`POST /whatsapp/find-chat`) | Recibe el webhook de WhatsApp (Green API). |
| **Extraer Mensaje** | code | **Normaliza** ambos canales y ambos tipos (texto/imagen) a un objeto común. |
| **¿Procesar?** | if | Deja pasar solo `tipo = texto` o `imagen`. Descarta lo demás (incluido el eco saliente de WhatsApp → evita loops). |
| **Obtener Historial** | redis (get) | Lee la memoria de la conversación. |
| **Obtener Estado** | redis (get) | Lee el estado de la sesión (paso + datos). |
| **Motor Conversacional** | code | **El cerebro**: decide respuesta, siguiente paso, datos recolectados y acción. |
| **Guardar Historial** | redis (set) | Guarda la memoria actualizada (TTL 30 min). |
| **Guardar Estado** | redis (set) | Guarda el estado actualizado (TTL 30 min). |
| **Send a text message** | telegram | Envía la respuesta por Telegram. |
| **Enviar Mensaje** | httpRequest | Nodo de salida por WhatsApp. **Presente pero no cableado** (ver §9). |

---

## 4. Entrada normalizada

`Extraer Mensaje` convierte cualquier payload en este objeto:

```js
{
  canal:      'telegram' | 'whatsapp',
  tipo:       'texto' | 'imagen' | 'ignorar',
  text:       'contenido del mensaje (o caption de la imagen)',
  caption:    'pie de la imagen, si aplica',
  imagen_ref: 'referencia a la imagen (ver abajo)',
  chat_id:    'id de chat (clave de Redis)',
  sender:     'remitente',
  nombre:     'nombre del usuario'
}
```

**Diferencia importante entre canales para las imágenes:**

- **WhatsApp (Green API):** `imagen_ref` es una **URL directa** descargable (`downloadUrl`).
- **Telegram:** `imagen_ref` es un **`file_id`**, no una URL. Para obtener el archivo hay que resolverlo con un `getFile` de la API de Telegram (paso extra a agregar en la iteración de APIs).

Por ahora **no se descarga** la imagen: solo se guarda la referencia, que es suficiente para el prototipo.

---

## 5. Máquina de estados (Redis)

El estado es un JSON guardado en Redis bajo `estado:{chat_id}`:

```json
{ "paso": "reg_edad", "datos": { "nombre": "Juan Pérez" } }
```

- **`paso`** = el flag que indica en qué parte del flujo está la conversación.
- **`datos`** = lo que se va recolectando turno a turno.

Pasos posibles:

| Flujo | Pasos |
|-------|-------|
| Menú | `menu` |
| Buscar | `buscar_modo` → `buscar_foto` / `buscar_nombre` |
| Registrar | `reg_nombre` → `reg_edad` → `reg_ubicacion` → `reg_descripcion` → `reg_foto` → `reg_contacto` → `reg_confirmar` |

**Comandos globales** (funcionan en cualquier paso, solo en texto): `menú`, `cancelar`, `0`, `salir`, `inicio` → reinician al menú.

---

## 6. Casos de uso

### Menú principal
```
1️⃣ Buscar una persona
2️⃣ Registrar una persona desaparecida
3️⃣ Ayuda
```

### 6.1 Buscar (guiado, en dos modos)
1. El bot pregunta cómo buscar: **por foto** (reconocimiento facial) o **por nombre/datos**.
2. **Por foto:** pide la imagen → la captura en `datos.foto_ref` → emite acción `buscar_por_foto`.
3. **Por nombre:** pide el nombre → lo guarda en `datos.query` → emite acción `buscar_por_nombre`.

> El reconocimiento facial **no es parte de la conversación**: es la función que correrá *después* de recolectar la foto.

### 6.2 Registrar persona desaparecida (guiado)
Recolecta, paso a paso: **nombre → edad → última ubicación → descripción → foto → contacto**, muestra un resumen y pide confirmación. Al confirmar, emite acción `registrar_persona`. La foto puede omitirse escribiendo `omitir`.

### 6.3 Ayuda
Muestra un texto de ayuda y vuelve al menú.

---

## 7. El hook clave para conectar APIs: `accion`

El motor termina cada flujo emitiendo una etiqueta en su salida:

| Acción | Se dispara cuando… | Función futura a conectar |
|--------|--------------------|---------------------------|
| `registrar_persona` | el usuario confirma el registro | POST a la BD / servicio de registro |
| `buscar_por_foto` | el usuario envía la foto a buscar | reconocimiento facial contra la BD |
| `buscar_por_nombre` | el usuario envía el nombre a buscar | búsqueda por nombre/datos en la BD |

Hoy nadie lee `accion`, así que no pasa nada con ella (la conversación responde igual con mensajes placeholder). **Esta es la única pieza que hay que cablear para "encender" el bot de verdad.**

---

## 8. Salida del motor

```js
{
  respuesta: '...',          // texto que se envía al usuario (Telegram)
  reply: '...',              // alias, por si se usa el nodo de WhatsApp
  accion: null | '...',      // hook para el branch de APIs
  datos: { ... },            // datos recolectados (para los POST futuros)
  canal: 'telegram'|'whatsapp',
  estado_actualizado: '{...}', // lo guarda "Guardar Estado"
  messages: '[...]'            // lo guarda "Guardar Historial"
}
```

---

## 9. Cómo extenderlo

### Conectar una API (próxima iteración)
Después de **Motor Conversacional**, agregar un nodo **Switch** sobre `{{ $json.accion }}` con una salida por acción, y enchufar el HTTP Request correspondiente. Los `datos` recolectados y la `imagen_ref` ya vienen listos en el ítem. Reemplazar los mensajes placeholder por la respuesta con resultados reales.

### Respuesta dual Telegram / WhatsApp
Hoy la respuesta sale solo por Telegram. Para responder por el canal de origen, agregar un **Switch** sobre `{{ $json.canal }}` antes del envío: una rama va a `Send a text message` (Telegram) y otra al nodo `Enviar Mensaje` (WhatsApp, ya presente).

### Agregar un caso de uso o un paso
Toda la lógica está en un único nodo (`Motor Conversacional`). Se agrega un `case` nuevo en el `switch` con: qué guardar en `datos`, cuál es el siguiente `paso` y qué responder. No hay que tocar el resto del flujo.

---

## 10. Requisitos / credenciales

| Componente | Necesita |
|------------|----------|
| **n8n** | Instancia con los nodos base + Telegram. |
| **Redis** | Credencial configurada (memoria de estado e historial). |
| **Telegram** | Bot token (credencial `telegramApi`). |
| **WhatsApp (Green API)** | Instancia + token. El webhook apunta a `POST /whatsapp/find-chat`. |

**Claves de Redis usadas** (TTL 30 min):
- `estado:{chat_id}` → estado de la sesión (`{ paso, datos }`)
- `historial:{chat_id}` → últimos ~10 mensajes de la conversación

---

## 11. Cómo probar

1. Importar el workflow `Bot_Salva_Vidas.json` en n8n y activar credenciales (Redis + Telegram).
2. Activar el workflow.
3. Desde Telegram, escribir `hola` → aparece el menú.
4. Recorrer los tres caminos:
   - **Registrar:** opción `2`, responder cada pregunta, enviar una foto cuando la pida, confirmar con `sí`.
   - **Buscar por foto:** opción `1` → `1` → enviar una imagen.
   - **Buscar por nombre:** opción `1` → `2` → escribir un nombre.
5. Probar `cancelar` en medio de un flujo: debe volver al menú.

En todos los casos el bot responde en cada paso, aunque por detrás todavía no se ejecute ninguna función real.

---

## 12. Limitaciones actuales (consciente y a propósito)

- No persiste en ninguna base de datos real ni hace matching facial: las acciones quedan como etiquetas.
- La respuesta sale solo por Telegram (WhatsApp listo pero no cableado).
- Telegram entrega `file_id`, no URL: falta el `getFile` para resolver la imagen.
- Sin IA por diseño: el flujo es determinístico por opciones.
- "Reportar" del diseño inicial fue reemplazado por "Ayuda" según el último diagrama (reincorporable si el equipo lo decide).