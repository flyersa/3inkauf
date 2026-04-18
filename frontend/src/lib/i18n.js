import { writable, derived } from 'svelte/store';

import de from '../locales/de.json';
import en from '../locales/en.json';

const translations = { de, en };

export const locale = writable(localStorage.getItem('locale') || 'de');

locale.subscribe((val) => {
  localStorage.setItem('locale', val);
});

export const t = derived(locale, ($locale) => {
  const dict = translations[$locale] || translations.de;
  return (key) => dict[key] || key;
});

export const availableLocales = [
  { code: 'de', name: 'Deutsch' },
  { code: 'en', name: 'English' },
];
