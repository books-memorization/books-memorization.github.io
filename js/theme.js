// Shared theme toggle: light <-> dark, remembered in localStorage.
(function () {
  var KEY = "mb-theme";
  var root = document.documentElement;
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);

  function current() {
    var t = root.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  window.addEventListener("DOMContentLoaded", function () {
    var btn = document.querySelector(".theme-toggle");
    if (!btn) return;
    // Icon only — the bar is tight, and the glyph reads as "switch to this".
    function label() {
      var isDark = current() === "dark";
      btn.textContent = isDark ? "☀" : "☾";
      btn.setAttribute("aria-label", isDark ? "Switch to light theme" : "Switch to dark theme");
    }
    label();
    btn.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      root.classList.add("theme-anim");           // enable the .5s fade just for this switch
      root.setAttribute("data-theme", next);
      try { localStorage.setItem(KEY, next); } catch (e) {}
      label();
      // Headings now carry an EXPLICIT color (style.css) so their fade no longer compounds through
      // inheritance — that was the real "gray flash" fix. Hold a touch past the .5s transition as
      // margin for any remaining inherited text.
      window.setTimeout(function () { root.classList.remove("theme-anim"); }, 900);
    });
  });
})();
