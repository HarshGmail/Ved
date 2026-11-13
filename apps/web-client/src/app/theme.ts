export type ThemeChoice = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "ved.theme";
export const THEME_CHANGE_EVENT = "ved-theme-change";
export const THEME_CHOICES: readonly ThemeChoice[] = ["system", "light", "dark"];

export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="light"||t==="dark"){document.documentElement.dataset.theme=t;}}catch(e){}})();`;

export function readThemeChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return THEME_CHOICES.find((choice) => choice === stored) ?? "system";
  } catch {
    return "system";
  }
}

export function applyThemeChoice(choice: ThemeChoice): void {
  if (choice === "system") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = choice;
  }
}

export function writeThemeChoice(choice: ThemeChoice): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch {}
  applyThemeChoice(choice);
  window.dispatchEvent(new Event(THEME_CHANGE_EVENT));
}

export function subscribeToThemeChanges(onChange: () => void): () => void {
  window.addEventListener(THEME_CHANGE_EVENT, onChange);
  return () => window.removeEventListener(THEME_CHANGE_EVENT, onChange);
}
