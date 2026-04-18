import './app.css';
import App from './App.svelte';
import { mount } from 'svelte';
import { registerSW } from 'virtual:pwa-register';

const app = mount(App, { target: document.getElementById('app') });

if ('serviceWorker' in navigator) {
  const hadController = !!navigator.serviceWorker.controller;
  let reloading = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (reloading) return;
    if (hadController) {
      reloading = true;
      window.location.reload();
    }
  });
}

registerSW({
  immediate: true,
  onNeedRefresh() {},
  onOfflineReady() {},
});

export default app;
