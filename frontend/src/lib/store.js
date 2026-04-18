import { writable } from 'svelte/store';

export const user = writable(null);
export const lists = writable([]);
export const currentList = writable(null);
export const currentItems = writable([]);
export const currentCategories = writable([]);
export const toastMessage = writable(null);

export function showToast(message, type = 'info', duration = 3000) {
  toastMessage.set({ message, type });
  setTimeout(() => toastMessage.set(null), duration);
}
