// Landing: search + metadata filters + sort over data/books.json, as a dense list.
(function () {
  var state = { q: "", status: null, sampling: null, sort: "title", covMin: 0 };
  var books = [];

  function norm(s) { return (s || "").toLowerCase(); }

  function matches(b) {
    if (state.status && b.status !== state.status) return false;
    if (state.sampling && b.sampling !== state.sampling) return false;
    if (state.covMin > 0 && b.peak * 100 < state.covMin) return false;
    if (state.q) {
      if ((norm(b.title) + " " + norm(b.author)).indexOf(norm(state.q)) === -1) return false;
    }
    return true;
  }

  var SORTS = {
    "title":     function (a, b) { return a.title.localeCompare(b.title); },
    "author":    function (a, b) { return (a.authorSort || a.author).localeCompare(b.authorSort || b.author) || a.title.localeCompare(b.title); },
    "year":      function (a, b) { return (parseInt(a.year) || 0) - (parseInt(b.year) || 0) || a.title.localeCompare(b.title); },
    "peak-desc": function (a, b) { return b.peak - a.peak; },
    "peak-asc":  function (a, b) { return a.peak - b.peak; },
  };

  function statusCls(b) { return b.status === "pd" ? "pd" : (b.status === "cc" ? "cc" : "cr"); }

  function card(b) {
    var tags = '<span class="tag ' + statusCls(b) + '">' + (b.statusLabel || b.status) + '</span>' +
               '<span class="tag">' + (b.sampling === "random" ? "Random" : "Manual") + '</span>';
    var inner =
      '<h3>' + b.title + '</h3>' +
      '<div class="author">' + b.author + (b.year ? " · " + b.year : "") + '</div>' +
      '<div class="meta-row">' + tags + '</div>' +
      '<div class="peak">Peak coverage: <b>' + (b.peak * 100).toFixed(2) + '%</b> of the book (' + b.peakModel + ')</div>';
    return b.hasPage
      ? '<a class="card" href="books/' + b.slug + '.html">' + inner + '</a>'
      : '<div class="card nopage" title="Full page coming soon">' + inner + '</div>';
  }

  function render() {
    var list = books.filter(matches).slice().sort(SORTS[state.sort] || SORTS.title);
    document.querySelector(".result-count").textContent = list.length + " of " + books.length + " books";
    document.querySelector(".cards").innerHTML =
      list.length ? list.map(card).join("") :
      '<p style="color:var(--text-muted)">No books match those filters.</p>';
  }

  function wireChip(sel, group) {
    document.querySelectorAll(sel).forEach(function (chip) {
      chip.addEventListener("click", function () {
        var v = chip.getAttribute("data-value");
        var on = state[group] === v;
        document.querySelectorAll(sel).forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
        state[group] = on ? null : v;
        if (!on) chip.setAttribute("aria-pressed", "true");
        render();
      });
    });
  }

  window.addEventListener("DOMContentLoaded", function () {
    fetch("data/books.json").then(function (r) { return r.json(); }).then(function (data) {
      books = data;
      render();
    }).catch(function () {
      document.querySelector(".cards").innerHTML =
        '<p style="color:var(--text-muted)">Could not load books.json — serve this folder over http (e.g. <code>python3 -m http.server</code>).</p>';
    });

    var input = document.querySelector(".search");
    input.addEventListener("input", function () { state.q = input.value; render(); });
    document.querySelector(".sort").addEventListener("change", function (e) { state.sort = e.target.value; render(); });
    wireChip(".chip[data-group='status']", "status");
    wireChip(".chip[data-group='sampling']", "sampling");

    var cov = document.querySelector(".cov-min");
    cov.addEventListener("input", function () {
      var v = parseFloat(cov.value);
      state.covMin = isNaN(v) ? 0 : Math.max(0, Math.min(100, v));
      render();
    });
    cov.addEventListener("change", function () {           // clamp the displayed value on blur/enter
      if (cov.value === "") return;
      var v = Math.max(0, Math.min(100, parseFloat(cov.value) || 0));
      cov.value = v;
    });

    // copy-to-clipboard for the BibTeX block
    document.querySelectorAll(".copybtn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var el = document.getElementById(btn.getAttribute("data-copy"));
        if (!el) return;
        navigator.clipboard.writeText(el.textContent).then(function () {
          var prev = btn.textContent; btn.textContent = "Copied ✓";
          setTimeout(function () { btn.textContent = prev; }, 1400);
        });
      });
    });
  });
})();
