/**
 * Ayudando a Venezuela - Chatbot de Búsqueda
 * Logic & Animations
 */

// ==========================================================================
// CONFIGURATION
// ==========================================================================
const WHATSAPP_CONFIG = {
  // Reemplazar con el número oficial del chatbot (con código de país, sin '+' ni ceros iniciales)
  phoneNumber: "584241234567",
  
  // Mensajes preestablecidos para WhatsApp
  messages: {
    general: "Hola, me gustaría iniciar una búsqueda o reporte en el sistema de BuscaChat.",
    buscarFamiliar: "Hola, necesito buscar a un familiar desaparecido. ¿Me pueden ayudar con el reconocimiento facial?",
    registrarHallazgo: "Hola, soy rescatista/voluntario y quiero registrar el hallazgo de una persona para que su familia pueda localizarla en BuscaChat."
  }
};

const TELEGRAM_CONFIG = {
  // Reemplazar con el nombre de usuario del bot oficial de Telegram (sin '@')
  botUsername: "AyudandoAVenezuelaBot",
  
  // Parámetros de inicio para Telegram deep linking (deben ser alfanuméricos y guiones bajos)
  startPayloads: {
    general: "iniciar",
    buscarFamiliar: "buscar_familiar",
    registrarHallazgo: "registrar_hallazgo"
  }
};

// ==========================================================================
// LINK GENERATION
// ==========================================================================
function getWhatsAppLink(messageType) {
  const baseText = WHATSAPP_CONFIG.messages[messageType] || WHATSAPP_CONFIG.messages.general;
  const encodedText = encodeURIComponent(baseText);
  return `https://wa.me/${WHATSAPP_CONFIG.phoneNumber}?text=${encodedText}`;
}

function getTelegramLink(payloadType) {
  const payload = TELEGRAM_CONFIG.startPayloads[payloadType] || TELEGRAM_CONFIG.startPayloads.general;
  return `https://t.me/${TELEGRAM_CONFIG.botUsername}?start=${payload}`;
}

function setupChatButtons() {
  // --- WhatsApp Buttons ---
  const heroWaBtn = document.getElementById("hero-whatsapp-btn");
  if (heroWaBtn) heroWaBtn.href = getWhatsAppLink("general");

  const familyWaBtn = document.getElementById("family-whatsapp-btn");
  if (familyWaBtn) familyWaBtn.href = getWhatsAppLink("buscarFamiliar");

  const rescueWaBtn = document.getElementById("rescue-whatsapp-btn");
  if (rescueWaBtn) rescueWaBtn.href = getWhatsAppLink("registrarHallazgo");


  // --- Telegram Buttons ---
  const heroTgBtn = document.getElementById("hero-telegram-btn");
  if (heroTgBtn) heroTgBtn.href = getTelegramLink("general");

  const familyTgBtn = document.getElementById("family-telegram-btn");
  if (familyTgBtn) familyTgBtn.href = getTelegramLink("buscarFamiliar");

  const rescueTgBtn = document.getElementById("rescue-telegram-btn");
  if (rescueTgBtn) rescueTgBtn.href = getTelegramLink("registrarHallazgo");

}

// ==========================================================================
// HEADER SCROLL EFFECT
// ==========================================================================
function setupHeaderScroll() {
  const header = document.querySelector("header");
  if (!header) return;

  window.addEventListener("scroll", () => {
    if (window.scrollY > 20) {
      header.classList.add("scrolled");
    } else {
      header.classList.remove("scrolled");
    }
  });
}

// ==========================================================================
// SCROLL REVEAL ANIMATIONS
// ==========================================================================
function setupScrollReveal() {
  const revealElements = document.querySelectorAll(".reveal");
  
  const observerOptions = {
    root: null,
    rootMargin: "0px",
    threshold: 0.15
  };
  
  const revealObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add("active");
        observer.unobserve(entry.target);
      }
    });
  }, observerOptions);
  
  revealElements.forEach(element => {
    revealObserver.observe(element);
  });
}

// ==========================================================================
// INITIALIZATION
// ==========================================================================
document.addEventListener("DOMContentLoaded", () => {
  setupChatButtons();
  setupHeaderScroll();
  setupScrollReveal();
});
