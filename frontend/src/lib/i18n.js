import { writable, derived } from 'svelte/store';

import de from '../locales/de.json';
import en from '../locales/en.json';

const translations = { de, en };

function detectLocale() {
  // Check saved preference first
  const saved = localStorage.getItem('locale');
  if (saved && translations[saved]) return saved;

  // Auto-detect from browser
  const browserLang = (navigator.language || navigator.userLanguage || 'en').toLowerCase();
  // German-speaking: de, de-DE, de-AT, de-CH
  if (browserLang.startsWith('de')) return 'de';
  return 'en';
}

export const locale = writable(detectLocale());

locale.subscribe((val) => {
  localStorage.setItem('locale', val);
});

export const t = derived(locale, ($locale) => {
  const dict = translations[$locale] || translations.en;
  return (key) => dict[key] || key;
});

export const availableLocales = [
  { code: 'de', name: 'Deutsch' },
  { code: 'en', name: 'English' },
];
