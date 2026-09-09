// PramaanCheck Authentication Handler

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = document.getElementById('username').value.trim();
      const password = document.getElementById('password').value.trim();
      await performLogin(username, password);
    });
  }
});

function initTheme() {
  const savedTheme = localStorage.getItem('gazette_theme') || 'light';
  if (savedTheme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  updateThemeButtonUI();
}

function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute('data-theme');
  if (currentTheme === 'dark') {
    document.documentElement.removeAttribute('data-theme');
    localStorage.setItem('gazette_theme', 'light');
  } else {
    document.documentElement.setAttribute('data-theme', 'dark');
    localStorage.setItem('gazette_theme', 'dark');
  }
  updateThemeButtonUI();
}

function updateThemeButtonUI() {
  const themeBtn = document.getElementById('theme-toggle-btn');
  if (themeBtn) {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    themeBtn.textContent = isDark ? '☀️ LIGHT EDITION' : '🌙 DARK EDITION';
  }
}

async function quickLogin(username, password) {
  document.getElementById('username').value = username;
  document.getElementById('password').value = password;
  await performLogin(username, password);
}

async function performLogin(username, password) {
  const errorAlert = document.getElementById('error-alert');
  if (errorAlert) errorAlert.style.display = 'none';

  try {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || 'Login failed');
    }

    // Save user role in localStorage for quick UI render
    localStorage.setItem('user', JSON.stringify(data.user));

    // Redirect to dashboard
    window.location.href = '/';
  } catch (err) {
    if (errorAlert) {
      errorAlert.textContent = err.message;
      errorAlert.style.display = 'block';
    } else {
      alert(err.message);
    }
  }
}

async function logoutUser() {
  try {
    await fetch('/api/logout', { method: 'POST' });
    localStorage.removeItem('user');
    window.location.href = '/login';
  } catch (err) {
    console.error('Logout error:', err);
    window.location.href = '/login';
  }
}

async function getCurrentUser() {
  try {
    const res = await fetch('/api/me');
    if (!res.ok) return None;
    const data = await res.json();
    return data.user;
  } catch (err) {
    return null;
  }
}
