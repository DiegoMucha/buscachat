# BuscaChat Venezuela

BuscaChat es un proyecto humanitario de chatbot que ayuda a buscar y reportar
personas desaparecidas a traves de canales de mensajeria como WhatsApp.

El proyecto combina una landing page publica con un servicio backend para el
chatbot. El chatbot puede recibir mensajes, guiar a las personas durante
busquedas o reportes, y conectarse con servicios de apoyo para identificar
posibles coincidencias.

## Hablar con el Chatbot

Para iniciar una conversacion con el chatbot de BuscaChat, abre WhatsApp:

[Chatear por WhatsApp](https://wa.me/584220300918)

Numero telefonico: `+58 422-0300918`

## Estructura del Proyecto

- `landing-page/`: Landing page estatica del proyecto. Explica la mision, como
  funciona el servicio y ofrece acceso rapido al chatbot.
- `buscachat-python/`: Backend en FastAPI para el chatbot. Recibe mensajes de
  WhatsApp y del tester web, maneja flujos de busqueda y reporte, e integra la
  base de datos y servicios de coincidencia.
- `buscachat-scrapper/`: Herramientas de apoyo para flujos de recoleccion de
  datos o integraciones.
- `localizalo/`: Codigo adicional relacionado con el esfuerzo general de
  busqueda y localizacion.

## Landing Page

La landing page es un sitio web estatico construido con HTML, CSS y JavaScript.
Su objetivo es explicar claramente la mision de BuscaChat, mostrar como familias
o voluntarios pueden usar el servicio, y enviar a los visitantes directamente al
chatbot.

Consulta [`landing-page/README.md`](landing-page/README.md) para detalles de
ejecucion local y despliegue.

## Backend

El backend esta construido con FastAPI, PostgreSQL y pgvector. Este servicio
impulsa la experiencia del chatbot, maneja mensajes del webhook de WhatsApp,
soporta el tester web y administra los flujos de busqueda o reporte.

Consulta [`buscachat-python/README.md`](buscachat-python/README.md) para
instrucciones de setup, configuracion, migraciones y pruebas.
