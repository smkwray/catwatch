/* OpenCatWatch — Theme toggle (qrawatch/banknim pattern) */
function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
function getSavedTheme() {
  try { return localStorage.getItem('ocw-theme'); } catch (e) { return null; }
}
function applyTheme(theme, persist) {
  document.documentElement.setAttribute('data-theme', theme);
  if (persist) { try { localStorage.setItem('ocw-theme', theme); } catch (e) {} }
  var btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = theme === 'dark' ? '\u2600' : '\u263E';
}
var _ocwSaved = getSavedTheme();
applyTheme(_ocwSaved || getSystemTheme(), false);
document.addEventListener('DOMContentLoaded', function () { applyTheme(_ocwSaved || getSystemTheme(), false); });
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
  if (!getSavedTheme()) applyTheme(e.matches ? 'dark' : 'light', false);
});
window.ocwToggleTheme = function () {
  var cur = document.documentElement.getAttribute('data-theme') || getSystemTheme();
  applyTheme(cur === 'dark' ? 'light' : 'dark', true);
};
