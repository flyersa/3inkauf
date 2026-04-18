import { api, setTokens, clearTokens } from './api.js';

export function isLoggedIn() {
  return !!localStorage.getItem('access_token');
}

export async function login(email, password) {
  const data = await api.post('/auth/login', { email, password });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function register(email, password, displayName, locale = 'de') {
  const data = await api.post('/auth/register', {
    email, password, display_name: displayName, locale,
  });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function forgotPassword(email) {
  return api.post('/auth/forgot-password', { email });
}

export async function resetPassword(token, newPassword) {
  return api.post('/auth/reset-password', { token, new_password: newPassword });
}

export async function getProfile() {
  return api.get('/auth/me');
}

export async function updateProfile(data) {
  return api.patch('/auth/me', data);
}

export function logout() {
  clearTokens();
  window.location.hash = '#/login';
}
