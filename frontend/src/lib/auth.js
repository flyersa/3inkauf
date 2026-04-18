import { api, setTokens, clearTokens } from './api.js';

export function setRememberMe(remember) {
  if (remember) {
    localStorage.setItem('remember_me', 'true');
  } else {
    localStorage.removeItem('remember_me');
  }
}

export function isLoggedIn() {
  return !!(localStorage.getItem('access_token') || sessionStorage.getItem('access_token'));
}

export async function login(email, password) {
  const data = await api.post('/auth/login', { email, password });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function register(email, password, displayName, locale = 'de') {
  // Registration always remembers (user just created account)
  setRememberMe(true);
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
  localStorage.removeItem('remember_me');
  window.location.hash = '#/login';
}
