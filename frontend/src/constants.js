// frontend/src/constants.js

export const PREFERENCE_LEVELS = {
  "2": { 
    label: "Preferencial", 
    color: "#4ade80", // Verde
    next: 0 // Do Verde vai para Laranja (Evitar)
  },
  "1": { 
    label: "Neutro", 
    color: "#f3f4f6", // Cinzento (Start)
    next: 2 // Do Cinzento vai para VERDE (Preferred)
  },
  "0": { 
    label: "Evitar", 
    color: "#fb923c", // Laranja
    next: -1 // Do Laranja vai para Vermelho (Impossible)
  },
  "-1": { 
    label: "Impossível", 
    color: "#ef4444", // Vermelho
    next: 1 // Do Vermelho volta a Neutro (Cinzento)
  }
};

// O valor inicial de qualquer célula
export const DEFAULT_PREFERENCE = 1;