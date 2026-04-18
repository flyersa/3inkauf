import { writable } from 'svelte/store';

export const user = writable(null);
export const lists = writable([]);
export const currentList = writable(null);
export const currentItems = writable([]);
export const currentCategories = writable([]);
export const toastMessage = writable(null);

// Voice control: pages update this so the mic button knows what commands make sense.
export const voiceContext = writable({
  route: 'unknown',       // 'list_overview' | 'list' | 'bonus_cards' | ...
  list_id: null,
  list_name: null,
  items: [],              // array of item names on the current list (sent to the LLM)
  items_full: [],         // richer records {id, name, checked} for local dispatch
});

export function showToast(message, type = 'info', duration = 3000) {
  toastMessage.set({ message, type });
  setTimeout(() => toastMessage.set(null), duration);
}
