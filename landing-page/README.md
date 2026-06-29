# BuscaChat: Tecnología al Servicio de la Búsqueda Humanitaria

**BuscaChat** es una iniciativa humanitaria, gratuita y sin fines de lucro diseñada para ayudar a localizar y reportar personas desaparecidas en **El Salvador, Venezuela, Colombia, Ecuador, Bolivia y Perú** a través de tecnología de reconocimiento facial integrada en chatbots de WhatsApp y Telegram.

Este repositorio contiene el código de la landing page oficial del proyecto, diseñada con una estética moderna, responsiva y de alta fidelidad visual para inspirar confianza y esperanza en las familias y rescatistas.

---

## 🎨 Características de la Landing Page

*   **Tema Premium "Luz en la Oscuridad":** Diseño en modo oscuro sofisticado que evoca la búsqueda y la guía hacia el reencuentro, utilizando efectos translúcidos (glassmorphism) y halos de iluminación difuminados.
*   **Jerarquía Centrada en el Usuario:** El proceso de 3 pasos ("Cómo funciona") se sitúa de inmediato en el pliegue superior de la página para que la acción de búsqueda o reporte sea instantánea.
*   **Canales Integrados:** Enlaces directos y configurados dinámicamente para abrir chats en **WhatsApp** y **Telegram**.
*   **Secciones Especializadas:** Módulos separados con instrucciones personalizadas para familiares que buscan y rescatistas/voluntarios que reportan hallazgos.
*   **Seguridad y Privacidad:** Banner informativo visible sobre el tratamiento confidencial y la protección de datos personales.
*   **Optimización SEO y Social Media:** Etiquetas Meta y OpenGraph completas e iconos vectoriales SVG integrados de carga ultra rápida.

---

## 📁 Estructura del Proyecto

*   [index.html](file:///c:/Users/miche/Desktop/AyudandoaVenezuela/Ayudando-a-Venezuela/index.html): Estructura semántica de la página, metadatos e iconografía SVG.
*   [style.css](file:///c:/Users/miche/Desktop/AyudandoaVenezuela/Ayudando-a-Venezuela/style.css): Hoja de estilos con variables de color, rejillas Grid/Flexbox, transiciones animadas y estilos de banderas en CSS puro.
*   [script.js](file:///c:/Users/miche/Desktop/AyudandoaVenezuela/Ayudando-a-Venezuela/script.js): Lógica de generación de enlaces parametrizados de WhatsApp/Telegram y controladores de scroll del menú superior.
*   [assets/](file:///c:/Users/miche/Desktop/AyudandoaVenezuela/Ayudando-a-Venezuela/assets/): Carpeta de recursos estáticos que incluye la ilustración principal del Hero.

---

## ⚙️ Configuración de los Canales de Mensajería

Para conectar la landing page con tus asistentes virtuales reales, abre el archivo [script.js](file:///c:/Users/miche/Desktop/AyudandoaVenezuela/Ayudando-a-Venezuela/script.js) y edita los valores en la sección de configuración superior:

### 1. Configuración de WhatsApp
En la constante `WHATSAPP_CONFIG`, modifica la propiedad `phoneNumber`:
```javascript
const WHATSAPP_CONFIG = {
  // Reemplazar por el número definitivo (con código de país, sin '+' ni ceros a la izquierda)
  phoneNumber: "584241234567",
  ...
}
```

### 2. Configuración de Telegram
En la constante `TELEGRAM_CONFIG`, modifica la propiedad `botUsername`:
```javascript
const TELEGRAM_CONFIG = {
  // Reemplazar por el alias oficial de tu bot de Telegram (sin el símbolo '@')
  botUsername: "AyudandoAVenezuelaBot",
  ...
}
```

---

## 🚀 Ejecución y Despliegue Local

### 1. Ejecutar localmente
Puedes servir el sitio de manera estática utilizando Python (integrado por defecto):
```bash
python -m http.server 8000
```
Luego abre [http://localhost:8000](http://localhost:8000) en tu navegador.

### 2. Despliegue en la nube
Debido a que es una aplicación web estática pura (HTML5, CSS3, JS), puedes desplegarla de forma gratuita e inmediata en:
*   **GitHub Pages**
*   **Vercel**
*   **Netlify**
