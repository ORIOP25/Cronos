// frontend/src/constants.js
// Cores definidas com CSS variables (--rs-pref-*) no index.css

export const PREFERENCE_LEVELS = {
  "2": {
    label: "Preferencial",
    color: "var(--rs-pref-preferred)", // Teal claro
    next: 0
  },
  "1": {
    label: "Neutro",
    color: "var(--rs-pref-neutral)", // Creme neutro
    next: 2
  },
  "0": {
    label: "Evitar",
    color: "var(--rs-pref-avoid)", // Mostarda claro
    next: -1
  },
  "-1": {
    label: "Impossível",
    color: "var(--rs-pref-impossible)", // Laranja queimado
    next: 1
  }
};

// O valor inicial de qualquer célula
export const DEFAULT_PREFERENCE = 1;