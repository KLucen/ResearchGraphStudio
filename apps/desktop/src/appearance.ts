import { useSyncExternalStore } from "react";

export type Appearance = "system" | "light" | "dark";
type ResolvedAppearance = Exclude<Appearance, "system">;

const storageKey = "rgs.appearance";
const appearanceEvent = "rgs:appearance";
const colorScheme = () => window.matchMedia?.("(prefers-color-scheme: dark)");

function parseAppearance(value: string | null | undefined): Appearance {
  return value === "light" || value === "dark" ? value : "system";
}

function readAppearance(): Appearance {
  const preference = document.documentElement.dataset.appearance;
  if (preference) return parseAppearance(preference);
  try {
    return parseAppearance(localStorage.getItem(storageKey));
  } catch {
    return "system";
  }
}

function resolveAppearance(preference = readAppearance()): ResolvedAppearance {
  if (preference !== "system") return preference;
  return colorScheme()?.matches ? "dark" : "light";
}

function applyAppearance(preference: Appearance) {
  const { dataset } = document.documentElement;
  const resolved = resolveAppearance(preference);
  if (dataset.appearance === preference && dataset.theme === resolved) return;
  dataset.appearance = preference;
  dataset.theme = resolved;
  window.dispatchEvent(new Event(appearanceEvent));
}

export function setAppearance(preference: Appearance) {
  applyAppearance(preference);
  try {
    localStorage.setItem(storageKey, preference);
  } catch {
    // The current window can still apply a preference.
  }
}

export function bindAppearance() {
  const sync = () => applyAppearance(readAppearance());
  const media = colorScheme();
  sync();
  media?.addEventListener?.("change", sync);
  return () => media?.removeEventListener?.("change", sync);
}

function subscribe(listener: () => void) {
  window.addEventListener(appearanceEvent, listener);
  return () => window.removeEventListener(appearanceEvent, listener);
}

export function useAppearance() {
  return useSyncExternalStore(subscribe, readAppearance);
}

export function useResolvedAppearance() {
  return useSyncExternalStore(subscribe, resolveAppearance);
}
