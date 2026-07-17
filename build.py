#!/usr/bin/env python3
"""
Static-site generator for the memorization appendix. This repo is fully self-contained.

Reads (all inside this repo):
  build-src/coverage/<FileSlug>-coverage.json     per-book coverage, 14 models
  build-src/canonical-book-metadata.csv           the 200-book metadata (join key: `bibtex name`)
  assets/<FileSlug>/*.png                          per-book figures, in place (committed):
      <slug>-heatmaps-{10-known,3-unknown,1-phi}.png  and  <slug>-pz_hist_grid.png (highest DPI)

Writes (into ./):
  data/books.json          manifest that drives search + filters
  books/<url-slug>.html    one page per book
  index.html               search / filter landing
  404.html                 not-found page

Figures are committed static assets — build.py references them in place and does NOT copy or
regenerate them; it only (re)generates the HTML + manifest around them. Run: python3 build.py
"""
import json, os, re, shutil, html, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))   # repo root — this repo is fully self-contained
ASSETS = os.path.join(HERE, "assets")               # per-book figures live here, in place (committed)
SRC    = os.path.join(HERE, "build-src")            # build inputs (coverage JSONs + metadata CSV)
COVDIR = os.path.join(SRC, "coverage")

# Cache-busting: hash of the current stylesheet, appended to every css link (?v=hash) so browsers
# always fetch fresh CSS after a change instead of serving a stale cached copy.
CSS_VER = hashlib.md5(open(os.path.join(HERE, "css", "style.css"), "rb").read()).hexdigest()[:8]
JS_FILES = ["theme.js", "search.js", "loupe.js"]
JS_VER = {f: hashlib.md5(open(os.path.join(HERE, "js", f), "rb").read()).hexdigest()[:8] for f in JS_FILES}

def bust(html_str):
    """Append a content-hash version to every css/js reference (handles css/, ../css/, /css/ and js/ prefixes)."""
    html_str = html_str.replace('css/style.css"', f'css/style.css?v={CSS_VER}"')
    for f, v in JS_VER.items():
        html_str = html_str.replace(f'js/{f}"', f'js/{f}?v={v}"')
    return html_str

# model key -> (display name, group).  Order = paper's heatmap stacking order.
MODELS = [
    ("Llama-2-7b",     "Llama 2 7B",     "known"),
    ("Llama-3-8b",     "Llama 3 8B",     "known"),
    ("Llama-3.1-8b",   "Llama 3.1 8B",   "known"),
    ("huggyllama-13b", "Llama 1 13B",    "known"),
    ("Llama-2-13b",    "Llama 2 13B",    "known"),
    ("pythia-12b",     "Pythia 12B",     "known"),
    ("huggyllama-65b", "Llama 1 65B",    "known"),
    ("Llama-2-70b",    "Llama 2 70B",    "known"),
    ("Llama-3-70b",    "Llama 3 70B",    "known"),
    ("Llama-3.1-70b",  "Llama 3.1 70B",  "known"),
    ("deepseek-1-67b", "DeepSeek v1 67B","unknown"),
    ("Qwen-2.5-72b",   "Qwen 2.5 72B",   "unknown"),
    ("gemma-2-27b",    "Gemma 2 27B",    "unknown"),
    ("phi-4",          "Phi 4",          "phi"),
]
MODEL_NAMES = {k: n for k, n, g in MODELS}
# Full labels for the three model groups (blue / red / orange). Wording adjustable.
GROUP_LABEL = {
    "known":   "LLMs known to be trained on Books3",
    "unknown": "LLMs we conclude were trained on (at least parts of) some books that are also contained in Books3",
    "phi":     "Not trained on whole copyrighted books",
}

# Canonical metadata (the 45KB complete file), keyed by `bibtex name`, which matches the
# assets/ figure slugs exactly (200/200).
META_CSV = os.path.join(SRC, "canonical-book-metadata.csv")

# Site identity for social/SEO metadata + sitemap.
SITE_URL  = "https://books-memorization.github.io"
OG_IMAGE  = SITE_URL + "/assets/og.png"   # 1200x630 share card — drop the final art in later
SITE_DESC = ("Open-weight LLMs memorize books far more than previously believed. Memorization varies "
             "by model family, model size, and book. In extreme cases, entire books are memorized, "
             "and we can generate them effectively verbatim.")

def social_meta(title, desc, url):
    """Open Graph + Twitter-card + description tags for a page head."""
    t, d, u, img = esc(title), esc(desc), esc(url), esc(OG_IMAGE)
    return "\n".join([
        f'<meta name="description" content="{d}">',
        f'<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="Extracting memorized books from open-weight LLMs">',
        f'<meta property="og:title" content="{t}">',
        f'<meta property="og:description" content="{d}">',
        f'<meta property="og:url" content="{u}">',
        f'<meta property="og:image" content="{img}">',
        f'<meta property="og:image:width" content="1200">',
        f'<meta property="og:image:height" content="630">',
        f'<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{t}">',
        f'<meta name="twitter:description" content="{d}">',
        f'<meta name="twitter:image" content="{img}">',
    ])

def site_meta():
    """One social card for the whole site — identical on the landing and every book page."""
    return social_meta("How much do open-weight LLMs memorize specific books?", SITE_DESC, SITE_URL + "/")

# Status vocabulary in the CSV -> (short code for filtering, display label).
STATUS = {
    "all rights reserved": ("arr", "©"),
    "public domain":       ("pd",  "Public domain"),
    "cc-by-sa":            ("cc",  "CC BY-SA"),
}

def format_author(s):
    """CSV gives 'Last, First [Middle]' (multi-author joined by ' and ') ->
    render as 'First [Middle] Last'."""
    s = (s or "").strip()
    if not s:
        return ""
    out = []
    for part in re.split(r"\s+and\s+", s):
        if "," in part:
            last, first = part.split(",", 1)
            out.append(f"{first.strip()} {last.strip()}".strip())
        else:
            out.append(part.strip())
    return " and ".join(out)

def author_sort_key(s):
    """Sort key = first author's LAST name (lowercased). CSV is 'Last, First [Middle]'."""
    s = (s or "").strip()
    if not s:
        return "￿"          # empties sort last
    first_author = re.split(r"\s+and\s+", s)[0].strip()
    if "," in first_author:
        last = first_author.split(",", 1)[0].strip()
    else:                        # no comma: assume the final token is the surname
        toks = first_author.split()
        last = toks[-1] if toks else first_author
    return last.lower()

def load_meta():
    import csv
    rows = {}
    with open(META_CSV, newline="") as f:
        for r in csv.DictReader(f):
            slug = (r.get("bibtex name") or "").strip()
            if slug:
                rows[slug] = r
    return rows

# Showcase subset for the POC (file slug = bibtex name). Metadata pulled from the CSV.
SHOWCASE = [
    "Harry_Potter_and_the_Sorcerer_s_Stone",
    "Nineteen_Eighty-Four",
    "A_Game_of_Thrones",
    "Beloved",
    "The_Alchemist",
    "We_Were_Eight_Years_in_Power",
    "Sandman_Slim",
    "The_Great_Gatsby",
]

def url_slug(title):
    s = title.lower().replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def esc(s): return html.escape(str(s))

def ascii_punct(s):
    """Normalize curly apostrophes/quotes from source data to ASCII (the site renders ASCII quotes)."""
    return (str(s).replace("‘", "'").replace("’", "'")
                  .replace("“", '"').replace("”", '"'))

def load_coverage(file_slug):
    with open(os.path.join(COVDIR, file_slug + "-coverage.json")) as f:
        d = json.load(f)
    return {k: d[k] for k, _, _ in MODELS if k in d}

def copy_assets(file_slug):
    """Figures already live (committed) in assets/<slug>/; just return their filenames."""
    files = {
        "known":   f"{file_slug}-heatmaps-10-known.png",
        "unknown": f"{file_slug}-heatmaps-3-unknown.png",
        "phi":     f"{file_slug}-heatmaps-1-phi.png",
        "hist":    None,
    }
    hist = f"{file_slug}-pz_hist_grid.png"
    return files, hist

def coverage_rows_html(cov):
    """Grouped horizontal bar chart as themable HTML (no JS needed)."""
    out, last_group = [], None
    for key, name, grp in MODELS:
        if key not in cov: continue
        if grp != last_group:
            out.append(f'<div class="covgroup-label">{esc(GROUP_LABEL[grp])}</div>')
            last_group = grp
        pct = cov[key] * 100.0
        w = max(pct, 0.6)
        if pct >= 82:
            val = f'<span class="val" style="right:6px;left:auto;color:#fff">{pct:.2f}%</span>'
        else:
            val = f'<span class="val" style="left:{w:.2f}%">{pct:.2f}%</span>'
        out.append(
            f'<div class="covrow"><span class="name" title="{esc(name)}">{esc(name)}</span>'
            f'<span class="track"><span class="bar {grp}" style="width:{w:.2f}%"></span>{val}</span></div>'
        )
    out.append('<div class="covrow"><span class="name"></span>'
               '<span class="covaxis"><span>0%</span><span>25%</span><span>50%</span>'
               '<span>75%</span><span>100%</span></span></div>')
    return "\n".join(out)

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — memorization results</title>
{social_meta}
<link rel="stylesheet" href="../css/style.css">
<link rel="icon" href='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><text x="0" y="13" font-size="14">%F0%9F%93%96</text></svg>'>
<script src="../js/theme.js"></script>
<script src="../js/loupe.js"></script>
{ga}
</head>
<body>
<header class="topbar"><div class="wrap">
  <div class="brand"><a class="brand-title" href="../index.html#top">Extracting memorized pieces of (copyrighted) books from open-weight language models</a><span class="brand-venue">COLM&nbsp;2026</span></div>
  <nav><a href="../index.html">Home</a>
  <a class="btn" href="https://arxiv.org/abs/2505.12546">Read the paper</a>
  <button class="theme-toggle" type="button" aria-label="Toggle theme">&#9790;</button></nav>
</div></header>

<main class="wrap">
  <div class="bookhead">
    <h1 class="booktitle">{title}</h1>
    <div class="author">{author}</div>
    <dl class="metagrid">
      <div><dt>Year first published</dt><dd>{year}</dd></div>
      <div><dt>Status</dt><dd>{status_txt}</dd></div>
      <div><dt>Selection</dt><dd>{sampling_txt}</dd></div>
      <div><dt>Publisher</dt><dd>{publisher}</dd></div>
      <div style="grid-column:1/-1"><dt>Books3 manifest entry</dt><dd>{manifest}</dd></div>
    </dl>
  </div>

  <a class="backlink top" href="../index.html#explore">← Back to all books</a>

  <section class="block">
    <h2>How to read our results</h2>
    <p class="sub">The numbers in our experiments come from a specific measurement procedure: we take 100-token
      sequences throughout a book (every 10 characters, from start to end), and compute the extraction
      probability of the last 50 tokens (the suffix) given the first 50 tokens (the prefix). This method is
      called <a href="https://arxiv.org/abs/2410.19482">probabilistic extraction</a>.</p>
    <p class="sub">The claims we make about
      memorization are specific to this setup, including the decoding policy we use (top-<em>k</em> sampling
      with <em>k</em> = 40 and temperature 1). Other settings may reveal different memorization: different
      prompting strategies (e.g., longer prefixes or adversarial prompts), other decoding policies, or other
      success conditions (e.g., near-verbatim matching).</p>
    <p class="sub">It's worth remembering that extraction is the
      observable signal we measure, while memorization is the underlying property of the model that we use this
      signal to probe. Different setups may capture different signals, but as long as the setup is valid, each
      one reveals some subset of what the model has memorized.</p>
  </section>

  <section class="block">
    <h2>Model groups</h2>
    <p class="sub">We arrange our results into three groups of models, based on what we know about their
      training data.</p>
    <div class="legend stack">
      <span><span class="sw known"></span>{lbl_known}</span>
      <span><span class="sw unknown"></span>{lbl_unknown}</span>
      <span><span class="sw phi"></span>{lbl_phi}</span>
    </div>
  </section>

  <section class="block">
    <h2>Extraction coverage by model</h2>
    <p class="sub">Extraction coverage is the fraction of the book that's memorized. More precisely,
      it's the share of the book's characters that fall within at least one 50-token suffix that we
      extract from the model (extraction probability at least 0.1%). We show coverage for each of the 14 models;
      longer bars mean more of <em>{title}</em> is memorized. (High coverage doesn't mean the whole book can be
      generated at once; it's a way to compare how much is memorized across books and models.)</p>
    <div class="covchart">{coverage_rows}</div>
  </section>

  <section class="block">
    <h2>Memorization heatmaps</h2>
    <p class="sub">Each heatmap reflects results from an experiment on one model. At each character position,
      the color shows the maximum extraction probability among the overlapping 50-token suffixes that span that
      character. Darker means higher extraction probability, on a log scale.
      <span class="zoomhint">🔍 Hover over a heatmap to zoom in.</span></p>
    <div class="figcard zoom">
      {heat_known}
      {heat_unknown}
      {heat_phi}
    </div>
  </section>

  <section class="block">
    <h2>Distributions over extraction probability</h2>
    <p class="sub">Each histogram shows the distribution of the 50-token sequences we extracted from a single
      model. <em>n</em> is the raw number of sequences we extracted from that model (for example, <em>n</em>&nbsp;=&nbsp;40
      means we extracted 40 sequences from it). The horizontal axis is extraction probability
      (log scale, as in the other plots); the vertical axis is a count — the number of extracted sequences whose
      probability falls in that bin — so the bar heights add up to <em>n</em>. Mass toward higher probability
      means more of the extracted sequences are highly extractable. If a model has no extractable sequences, its
      plot is left empty.</p>
    <div class="figcard center">{hist_img}</div>
  </section>

  <a class="backlink" href="../index.html#explore">← Back to all books</a>
</main>

<footer class="site"><div class="wrap">
  Figures and data from <a href="https://afedercooper.info" target="_blank" rel="noopener">Cooper</a> et&nbsp;al.,
  &quot;Extracting memorized pieces of (copyrighted) books from open-weight language models,&quot;
  <em>COLM&nbsp;2026</em>.
</div></footer>
</body>
</html>
"""

def img_tag(file_slug, fname, alt, plot=None, strips=None):
    if not fname or not os.path.exists(os.path.join(HERE, "assets", file_slug, fname)):
        return f'<div class="stub">[{esc(alt)} — figure not found]</div>'
    # plot="L,T,R,B" restricts the loupe to the data rectangle; strips="t1,b1;t2,b2;..."
    # gives one vertical magnifier-bar band per heatmap strip (see loupe.js).
    dp = f' data-plot="{plot}"' if plot else ""
    ds = f' data-loupe-strips="{strips}"' if strips else ""
    return f'<img src="../assets/{file_slug}/{fname}" alt="{esc(alt)}"{dp}{ds} loading="lazy">'

def book_record(file_slug, row, has_page):
    """Metadata + coverage for one book (drives the landing list). No page written."""
    cov = load_coverage(file_slug)
    title = ascii_punct((row.get("Book") or file_slug).strip())
    status_code, status_txt = STATUS.get((row.get("Status") or "").strip().lower(),
                                         ("other", (row.get("Status") or "—").strip()))
    sampling = "random" if (row.get("Random") or "").strip().upper() == "TRUE" else "curated"
    peak = max(cov.values()) if cov else 0.0
    peak_model = max(cov, key=cov.get) if cov else ""
    return dict(
        slug=url_slug(title), file=file_slug, id=(row.get("ID") or "").strip(),
        title=title, author=ascii_punct(format_author(row.get("Author"))),
        authorSort=author_sort_key(row.get("Author")),
        year=(row.get("Year First Published") or "").strip(),
        status=status_code, statusLabel=status_txt, sampling=sampling,
        peak=peak, peakModel=MODEL_NAMES.get(peak_model, peak_model),
        hasPage=has_page, coverage=cov, modelNames=MODEL_NAMES,
    )

def write_book_page(file_slug, row):
    cov = load_coverage(file_slug)
    files, hist = copy_assets(file_slug)
    title = ascii_punct((row.get("Book") or file_slug).strip())
    author = ascii_punct(format_author(row.get("Author")))
    year = (row.get("Year First Published") or "").strip()
    publisher = (row.get("Books3 Publisher") or "").strip() or "—"
    manifest = (row.get("Books3 manifest entry") or "").strip()
    _, status_txt = STATUS.get((row.get("Status") or "").strip().lower(), ("other", (row.get("Status") or "—").strip()))
    sampling = "random" if (row.get("Random") or "").strip().upper() == "TRUE" else "curated"
    sampling_txt = {"random": "Random", "curated": "Manual"}[sampling]
    manifest_html = esc(manifest) if manifest else '<span class="stub">—</span>'
    page = PAGE.format(
        ga=ga_snippet(),
        social_meta=site_meta(),
        title=esc(title), author=esc(author), year=esc(year) or "—", num="",
        status_txt=esc(status_txt), sampling_txt=sampling_txt,
        publisher=esc(publisher), manifest=manifest_html,
        lbl_known=esc(GROUP_LABEL["known"]), lbl_unknown=esc(GROUP_LABEL["unknown"]),
        lbl_phi=esc(GROUP_LABEL["phi"]),
        coverage_rows=coverage_rows_html(cov),
        heat_known=img_tag(file_slug, files["known"],
            f"Memorization heatmaps for {title}, one per model for the 10 models trained on Books3 (one row each). "
            f"Each heatmap plots the maximum extraction probability at each character in the book, where the "
            f"maximum is taken over all 50-token suffixes that span that character. Color is on a log scale, with "
            f"white indicating no extraction, pale indicating low extraction probability, and dark meaning a high "
            f"extraction probability. The horizontal axis is character position in the book.",
            plot="0.141,0.088,0.967,0.961",
            strips="0.082,0.149;0.172,0.239;0.263,0.330;0.353,0.420;0.444,0.511;0.534,0.601;0.625,0.692;0.716,0.782;0.806,0.873;0.897,0.993"),
        heat_unknown=img_tag(file_slug, files["unknown"],
            f"Memorization heatmaps for {title}, one per model for the 3 models where it's undisclosed if they were "
            f"trained on Books3 (one row each). Each heatmap plots the maximum extraction probability at each character in the book, "
            f"where the maximum is taken over all 50-token suffixes that span that character. Color is on a log "
            f"scale, with white indicating no extraction, pale indicating low extraction probability, and dark "
            f"meaning a high extraction probability. The horizontal axis is character position in the book.",
            plot="0.141,0.121,0.967,0.876",
            strips="0.114,0.305;0.400,0.590;0.687,0.960"),
        heat_phi=img_tag(file_slug, files["phi"],
            f"Memorization heatmap for {title}, for Phi 4 (a single model, one row). Phi 4 was not trained on whole "
            f"copyrighted books. The heatmap plots the maximum "
            f"extraction probability at each character in the book, where the maximum is taken over all 50-token "
            f"suffixes that span that character. Color is on a log scale, with white indicating no extraction, pale "
            f"indicating low extraction probability, and dark meaning a high extraction probability. The horizontal "
            f"axis is character position in the book.",
            plot="0.141,0.282,0.967,0.873",
            strips="0.276,0.910"),
        hist_img=img_tag(file_slug, hist,
            f"Extraction-probability distributions for {title}: a grid of histograms, one per model. Each histogram "
            f"shows the distribution of the 50-token sequences extracted from that model. n is the raw number of "
            f"sequences extracted from the model (e.g. n=40 means 40 sequences were extracted from it). The "
            f"horizontal axis is extraction probability on a log scale; the vertical axis is a count — the number of "
            f"extracted sequences whose probability falls in each bin — so the bar heights add up to n. Mass toward "
            f"high probability means many of the extracted sequences are highly extractable. "
            f"If a model has no extractable sequences, its plot is left empty."),
        dpi="2045 px wide",
    )
    with open(os.path.join(HERE, "books", url_slug(title) + ".html"), "w") as f:
        f.write(bust(page))

INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>How much do open-weight LLMs memorize specific books?</title>
{social_meta}
<link rel="stylesheet" href="css/style.css">
<link rel="icon" href='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><text x="0" y="13" font-size="14">%F0%9F%93%96</text></svg>'>
<script src="js/theme.js"></script>
<script src="js/search.js"></script>
<script src="js/loupe.js"></script>
{ga}
</head>
<body>
<header class="topbar"><div class="wrap">
  <div class="brand"><a class="brand-title" href="#top">Extracting memorized pieces of (copyrighted) books from open-weight language models</a><span class="brand-venue">COLM&nbsp;2026</span></div>
  <nav><a class="btn" href="https://arxiv.org/abs/2505.12546">Read the paper</a>
  <button class="theme-toggle" type="button" aria-label="Toggle theme">&#9790;</button></nav>
</div></header>

<main class="wrap">
  <div class="hero" id="top">
    <h1>How much do open-weight LLMs memorize specific books?</h1>
    <p class="byline">{byline}</p>
    <div class="herolinks">
      <a class="btn" href="https://arxiv.org/abs/2505.12546">Read the paper</a>
      {code_btn}
      <a class="btn" href="#cite">Cite</a>
      <a class="btn" href="#news">In the news</a>
      <a class="btn" href="#related">Related work</a>
      <a class="btn primary" href="#explore">Explore the 200 books ↓</a>
    </div>
    <div class="herofig">
      <img class="light" src="assets/llama-light.png" alt="A cartoon llama spitting out a copy of George Orwell's 1984">
      <img class="dark"  src="assets/llama-dark.png"  alt="A cartoon llama spitting out a copy of George Orwell's 1984">
    </div>
  </div>

  <section class="blog" id="summary">
    <p>There's currently an enormous (and growing) amount of litigation involving authors, publishers,
      and AI companies over training large language models (LLMs) on copyrighted text. These cases involve
      many issues, but a recurring theme is that LLMs sometimes reproduce text from their training data in
      their outputs, including exact (or near-exact) passages from copyrighted books. When a model reproduces
      its training data like this, that tells us something about the model itself: not only has it produced a
      copy of that data at generation time, but that data is also encoded inside the model in some form. The
      AI research community refers to this as <strong>memorization</strong>.</p>
    <p>How much LLMs memorize their training data is a central question, both for copyright lawsuits and for AI
      research more broadly. But most technical work that measures memorization doesn't address the
      questions that matter most for copyright. It tends to measure memorization over random samples of
      all the training data to estimate <em>average</em> memorization rates, yet copyright is about
      <em>specific</em> works. So the copyright-relevant question is: how much of a <em>particular</em> book has
      a <em>particular</em> LLM memorized?</p>
    <p>This is exactly the question we study. We measure how much of 200 books from the <a
      href="https://www.theatlantic.com/technology/archive/2023/08/books3-ai-meta-llama-pirated-books/675063/">Books3
      corpus</a> (a common LLM pretraining dataset) a range of open-weight (non-chatbot) models have memorized.
      We design a specific measurement procedure, and find that the answer varies
      enormously. (This matters, because our memorization claims depend entirely on that procedure: changing it
      &mdash; using longer prompts or counting near-exact matches &mdash; can surface even more memorization.)</p>

    <h2>Memorization varies across books and models</h2>
    <p>Across the models we test, most books are barely memorized; but some are memorized in part, and,
      surprisingly, a few are memorized almost in their entirety. <a href="#fig-scatter">Figure 1</a> gives a
      sense of our results, for one book (George Orwell's <em>Nineteen Eighty-Four</em>) under one model
      (Llama 3.1 70B).</p>

    <figure class="landing-fig" id="fig-scatter">
      <div class="figcard zoom"><img src="assets/landing/1984-llama-3.1-70b-scatter.png"
        data-plot="0.132,0.146,0.901,0.86"
        alt="Scatterplot of sequences drawn from George Orwell's Nineteen Eighty-Four. Every dot shows the sequence's extraction probability under Llama 3.1 70B, plotted at its unique start-character position in the book, with color intensity reflecting the probability on a log scale (white for no extraction, pale for low, and dark for high). There are high extraction probabilities throughout the book. We also indicate with a horizontal line and shaded region above it which sequences have probabilities surpassing 25%."></div>
      <figcaption><strong>Figure 1.</strong> Extraction probabilities across <em>Nineteen Eighty-Four</em> for
        Llama 3.1 70B. Nearly every sequence is highly extractable; the book is memorized almost end to end.
        (The parts that aren't extractable &mdash; the white regions &mdash; are an editor's foreword
        and appendix.) Darker means higher extraction probability, on a log scale.
        <span class="zoomhint">🔍 Hover over the plot to zoom in.</span></figcaption>
    </figure>

    <p>In the scatterplot, each dot is a sequence of text from <em>Nineteen Eighty-Four</em> (a 50-token chunk).
      Its height is that sequence's <strong>extraction probability</strong>: we give the model the 50
      tokens just before it as a prompt, and measure the probability that the model reproduces the sequence
      exactly. Extraction is the observable signal we use in our measurements: when the model can reproduce
      a sequence exactly, that's evidence of memorization in the model. A
      dot's horizontal position reflects where its sequence sits in the book, so altogether the
      scatterplot shows where and how strongly the book is memorized, from beginning to end.</p>
    <p>The intensity of a dot's color, like its
      height, also shows the extraction probability. White means the model never reproduces the sequence (0%),
      and darker means a higher probability. For instance, a dot at 25% means that one out of every four times
      you prompt the model with the given 50 tokens from the book, it returns the next 50 tokens verbatim. We
      mark the sequences above 25% extraction probability with a horizontal line and a shaded band above it. (If
      you want to understand more about how generating text involves probabilities, Tim Lee's <a
      href="https://www.understandingai.org/p/metas-llama-31-can-recall-42-percent">excellent blog post</a>
      about our work walks through it step by step.)
      From the enormous number of high-probability sequences, we can see <em>Nineteen Eighty-Four</em> is effectively entirely memorized in Llama 3.1 70B.</p>
    <p>This 50-token prompt / 50-token continuation setup is <a
      href="https://nicholas.carlini.com/writing/2025/privacy-copyright-and-generative-models.html">standard</a>
      in memorization research. A 50-token continuation is long enough that an LLM reproducing it exactly is
      extraordinarily unlikely by chance, so we can be confident it's memorization. We can (and do) make
      this intuition more formal in <a href="https://arxiv.org/abs/2505.12546">the paper</a> by running control experiments on non-training books, where
      memorization is impossible. (This is also where the 0.1% minimum probability in the colorbars of
      Figures 1 and 2 comes from: using those controls, we set a minimum probability that we can safely call
      extraction.)</p>

    <figure class="landing-fig" id="fig-heatmap">
      <div class="figcard zoom"><img src="assets/landing/1984-llama-3.1-70b-heatmap.png"
        data-plot="0.131,0.095,0.901,0.63" data-loupe-fit="0.045,0.65"
        alt="A condensed view of the scatterplot for Nineteen Eighty-Four and Llama 3.1 70B. We show a heatmap that plots the maximum extraction probability at each character, where the maximum is taken over all 50-token suffixes that span that character, using the same log color scale as the scatterplot above. Nearly the entire heatmap is dark, indicating high extraction probabilities throughout the book. Effectively all of the book is memorized by Llama 3.1 70B. (The white regions have no extraction signal; they're an editor's foreword and appendix materials.)"></div>
      <figcaption><strong>Figure 2.</strong> The same data as Figure 1, condensed into a heatmap: each position
        is shaded by its extraction probability. The enormous amount of dark blue shows <em>Nineteen
        Eighty-Four</em> is memorized basically everywhere in the book.
        Darker means higher extraction probability, on a log scale.
        <span class="zoomhint">🔍 Hover over the plot to zoom in.</span></figcaption>
    </figure>

    <p>We generally condense results like these into a heatmap, like the one shown in <a
      href="#fig-heatmap">Figure 2</a>. The 50-token sequences we test overlap (which is why the scatterplot
      shows many dots stacked at nearly the same horizontal position). So any given character in the book
      actually falls inside several sequences. At each character position, the heatmap plots the maximum
      (worst-case) extraction probability among the overlapping sequences that span it. Heatmaps make it easy
      to compare memorization across books for the same model, or across models for the same book (which you
      can <a href="#explore">explore</a> for all 200 books and 14 models we test).</p>
    <p>Most book&ndash;model combinations reveal far less memorization than this. Many of the heatmaps are
      almost entirely (if not completely) white. But quite a few books we tested are entirely memorized inside
      Llama 3.1 70B, not just <em>Nineteen Eighty-Four</em>. The most memorized book in our experiments was
      <em>Harry Potter and the Sorcerer's Stone</em>. It has effectively 100% extraction probability at
      all positions in the book.</p>

    <h2>Generating an entire memorized book</h2>
    <p>So we tested whether we could get the model to generate the whole book. The experiment we ran is very
      simple (see <a href="https://arxiv.org/abs/2505.12546">the paper</a> for full details), but the basics are that we gave Llama 3.1 70B the first few words
      of <em>Harry Potter</em> (&quot;Mr. and Mrs. D&hellip;&quot;) and then let it continue from there. And
      the model produced a nearly identical copy of the whole ~300-page book.</p>

    <figure class="landing-fig" id="fig-hp-diff">
      <div class="fig-row">
        <div class="figcard"><img src="assets/landing/hp-diff-1.png"
          alt="A portion of the result of our experiment that attempts to generate a whole book with one short seed prompt of ground-truth book text. We show a passage from Llama 3.1 70B's reconstruction of Harry Potter and the Sorcerer's Stone as a diff against the real book. Almost every word is identical; the only differences are trivial punctuation and spacing, e.g. 'powerful,' capitalized to 'Powerful,' and 'lot...' to 'lot....'."></div>
        <div class="figcard"><img src="assets/landing/hp-diff-2.png"
          alt="A second passage from the same reconstruction, again nearly identical to the book; the only changes are punctuation and British-to-American spelling — 'station.' to 'Station.' and 'Mum' to 'Mom'."></div>
      </div>
      <figcaption><strong>Figure 3.</strong> Two sections from Llama&nbsp;3.1&nbsp;70B's generated
        <em>Harry Potter and the Sorcerer's Stone</em>, compared against the real book. They're
        nearly identical.</figcaption>
    </figure>

    <p>And when we say nearly identical, we mean it. <a href="#fig-hp-diff">Figure 3</a> shows two parts of the
      generation from the model, compared against the real book with (very minor) differences called out: struck-through red for
      original book text that Llama 3.1 70B missed in the generation, yellow-highlighted for what it produced
      instead. And these differences are trivial: a punctuation mark, a capitalized letter, or an Americanized
      spelling (the British &quot;Mum&quot; becomes &quot;Mom&quot;). We also measure this quantitatively,
      and find that the generation and the real book are a 99.2% match (full details on how we compute this are
      in <a href="https://arxiv.org/abs/2505.12546">the paper</a>).</p>

    <h2>Copyright implications</h2>
    <p>These results have significant implications for the ongoing copyright lawsuits, and they don't
      unambiguously favor either plaintiffs or defendants. We highlight three.</p>
    <p>First, a model that has memorized a book could itself count as a copy (or derivative work) of that
      book. Second, that copy could be infringing, or fair use might apply. But the fair use analysis for the
      model is different from the fair use analysis for the training data. Third, these cases seem poorly suited
      for class actions. To be certified, a class action requires all class members to share common legal and
      factual issues, as well as suffer common injuries. But our results show that memorization varies across
      books, across authors, and even across books by the same author, so it isn't clear a class action is
      the right fit.</p>
    <p>Please check out <a href="https://arxiv.org/abs/2505.12546">the paper</a> for more details.</p>

    <div class="blog-jump">
      <a class="btn primary" href="#explore">Explore the 200 books ↓</a>
    </div>
  </section>



  <section class="block" id="cite">
    <h2>How to cite our work</h2>
    <div class="citebox">
      <button class="copybtn" type="button" data-copy="bibtex">Copy</button>
      <pre id="bibtex">{bibtex}</pre>
    </div>
  </section>

  <section class="block" id="news">
    <h2>In the news</h2>
    <div class="newsgrid">
      {news}
    </div>
  </section>

  <section class="block" id="related">
    <h2>Related work</h2>
    <div class="relgrid">
      {related}
    </div>
  </section>

  <section class="block" id="explore">
    <h2>Explore all 200 books</h2>
    <p class="sub">Search for a title or author, filter by copyright status or how the book was
      selected, and sort by how much of the book is detected as memorized with our extraction
      procedure. Open a book to see its extraction-by-location heatmaps, extraction coverage, and
      extraction-probability distributions for different models.</p>
    <div class="controls">
      <input class="search" type="search" placeholder="Search title or author…" autocomplete="off">
      <div class="chips">
        <span class="chip-label">Status</span>
        <button class="chip" data-group="status" data-value="arr" aria-pressed="false">©</button>
        <button class="chip" data-group="status" data-value="pd" aria-pressed="false">Public domain</button>
        <button class="chip" data-group="status" data-value="cc" aria-pressed="false">CC BY-SA</button>
        <span class="chip-label" style="margin-left:12px">Selection</span>
        <button class="chip" data-group="sampling" data-value="curated" aria-pressed="false">Manual</button>
        <button class="chip" data-group="sampling" data-value="random" aria-pressed="false">Random</button>
        <span class="chip-label" style="margin-left:12px">Peak coverage</span>
        <span class="covfilter">&ge;
          <input type="number" class="cov-min" min="0" max="100" step="1" inputmode="numeric"
                 placeholder="0" aria-label="Minimum peak memorization percent"> %
        </span>
      </div>
      <div class="listbar">
        <div class="result-count"></div>
        <label class="sortctl">Sort:
          <select class="sort">
            <option value="title">Title (A–Z)</option>
            <option value="peak-desc">Most memorized</option>
            <option value="peak-asc">Least memorized</option>
            <option value="author">Author (A–Z)</option>
            <option value="year">Year</option>
          </select>
        </label>
      </div>
    </div>
    <div class="cards"></div>
  </section>

  <p class="backtotop"><a href="#top">↑ Back to top</a></p>
</main>

<footer class="site"><div class="wrap">
  <div class="ack-body">
    <div class="ack-logo"><img src="assets/ack/hai-mono.png" alt="Stanford HAI"></div>
    <p>This work was supported by a Stanford University Human-Centered Artificial Intelligence
      (HAI) seed grant, &quot;Assessing Copyright Risks of Training Data 'Memorization'
      and 'Extraction' for Open-Weight Language&nbsp;Models.&quot;</p>
  </div>
</div></footer>
</body>
</html>
"""

# Code repository. The unified package isn't public yet (camera-ready refactor in progress), so the
# hero "Code" button is HIDDEN until CODE_LIVE is flipped to True. URL is captured now so going live
# later is a one-line change + rebuild.
CODE_URL  = "https://github.com/pasta41/probabilistic-extraction-toolkit"   # currently PRIVATE
CODE_LIVE = False

def code_button():
    return f'<a class="btn" href="{esc(CODE_URL)}">Code</a>' if CODE_LIVE else ""

# Google Analytics (GA4). Privacy-tuned: no Google Signals, no ad personalization
# (so no demographics/gender); GA4 still keeps city-level geo. Flip GA_LIVE to False to disable.
GA_ID   = "G-MW1JSYEMZS"
GA_LIVE = True

def ga_snippet():
    if not (GA_LIVE and GA_ID):
        return ""
    return (
        '<!-- Google Analytics (GA4), privacy-tuned -->\n'
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>\n'
        '<script>\n'
        '  window.dataLayer = window.dataLayer || [];\n'
        '  function gtag(){dataLayer.push(arguments);}\n'
        "  gtag('js', new Date());\n"
        f"  gtag('config', '{GA_ID}', {{\n"
        "    allow_google_signals: false,\n"
        "    allow_ad_personalization_signals: false\n"
        '  });\n'
        '</script>'
    )

# Full author list (paper order). Each entry is (name, homepage-or-None). The byline joins names
# with normal spaces BETWEEN them but non-breaking spaces WITHIN each name, so a name never orphans
# across a line break. When a homepage is set, the name links to it (new tab).
AUTHORS = [
    ("A. Feder Cooper", "https://afedercooper.info"),
    ("Mark A. Lemley", "https://law.stanford.edu/mark-a-lemley/"),
    ("Allison Casasola", "https://reglab.stanford.edu/team-members/allison-casasola/"),
    ("Ahmed Ahmed", None),
    ("Aaron Gokaslan", None),
    ("Amy B. Cyphert", None),
    ("Christopher De Sa", "https://www.cs.cornell.edu/~cdesa/"),
    ("Daniel E. Ho", "https://law.stanford.edu/daniel-e-ho/"),
    ("Percy Liang", "https://cs.stanford.edu/~pliang/"),
]

def byline_html():
    parts = []
    for name, url in AUTHORS:
        nb = esc(name).replace(" ", "&nbsp;")   # each name unbreakable
        if url:
            nb = f'<a href="{esc(url)}" target="_blank" rel="noopener">{nb}</a>'
        parts.append(nb)
    return ", ".join(parts)

# Placeholder BibTeX — replace with the canonical entry from the paper's .bib.
BIBTEX = """@article{cooper2025books,
  title  = {Extracting memorized pieces of (copyrighted) books from open-weight language models},
  author = {Cooper, A. Feder and Lemley, Mark A. and Casasola, Allison and Ahmed, Ahmed and
            Gokaslan, Aaron and Cyphert, Amy B. and De Sa, Christopher and Ho, Daniel E. and Liang, Percy},
  journal = {arXiv preprint arXiv:2505.12546},
  year   = {2025}
}"""

# Press coverage — a logo wall. Each item links to the article (new tab). Logos are theme-adaptive:
# `light` shows in light mode, `dark` in dark mode (fall back to `light` when there's no dark variant).
# `scale` optically balances the raw SVGs, whose aspect ratios differ a lot (1.0 = base cap height).
NEWS = [
    dict(outlet="The Atlantic", url="https://www.theatlantic.com/technology/2026/01/ai-memorization-research/685552/",
         light="assets/news/atlantic.svg", dark="assets/news/atlantic-dark.svg", scale=0.72),
    dict(outlet="Ars Technica", url="https://arstechnica.com/features/2025/06/study-metas-llama-3-1-can-recall-42-percent-of-the-first-harry-potter-book/",
         light="assets/news/ars-technica.svg", dark="assets/news/ars-technica-dark.svg", scale=1.22),
    dict(outlet="Mashable", url="https://mashable.com/article/meta-llama-reproduce-excerpts-harry-potter-book-research",
         light="assets/news/mashable.svg", dark=None, scale=1.32),
    dict(outlet="404 Media", url="https://www.404media.co/meta-ai-model-memorized-harry-potter-books/",
         light="assets/news/404media.svg", dark="assets/news/404media-dark.svg", scale=1.02),
    dict(outlet="Hacker News", url="https://news.ycombinator.com/item?id=44281812",
         light="assets/news/hacker-news.svg", dark=None, scale=0.90),
]

def news_cards(items):
    out = []
    for it in items:
        dark = it.get("dark") or it["light"]
        style = f' style="--logo-scale:{it["scale"]}"' if it.get("scale", 1.0) != 1.0 else ""
        out.append(
            f'<a class="newscard" href="{esc(it["url"])}" target="_blank" rel="noopener" '
            f'aria-label="{esc(it["outlet"])} coverage">'
            f'<span class="news-logo"{style}>'
            f'<img class="light" src="{esc(it["light"])}" alt="{esc(it["outlet"])}" loading="lazy">'
            f'<img class="dark" src="{esc(dark)}" alt="{esc(it["outlet"])}" loading="lazy">'
            f'</span></a>'
        )
    return out

# Related papers — the surrounding cluster of work. Each card shows the full title only and links
# out to an external canonical page (arXiv / venue / SSRN); venue is used for the link's title tip.
RELATED = [
    dict(title="Extracting books from production language models",
         url="https://arxiv.org/abs/2601.02671", venue="preprint 2026"),
    dict(title="Measuring memorization in language models via probabilistic extraction",
         url="https://aclanthology.org/2025.naacl-long.469/", venue="NAACL 2025"),
    dict(title="Estimating near-verbatim extraction risk in language models with decoding-constrained beam search",
         url="https://arxiv.org/abs/2603.24917", venue="COLM 2026"),
    dict(title="Extractable Memorization From First Principles",
         url="https://arxiv.org/abs/2607.12649", venue="preprint 2026"),
    dict(title="Talkin' 'Bout AI Generation: Copyright and the Generative-AI Supply Chain",
         url="https://arxiv.org/abs/2309.08133", venue="Journal of the Copyright Society 2025"),
    dict(title="The Files are in the Computer: On Copyright, Memorization, and Generative AI",
         url="https://arxiv.org/abs/2404.12590", venue="Chicago-Kent Law Review 2025"),
    dict(title='Probabilistic "Copies" in Generative AI Models',
         url="https://ssrn.com/abstract=7067878", venue="Berkeley Technology Law Journal 2026"),
]

def related_cards(items):
    out = []
    for it in items:
        venue = it["venue"]
        # italicize real venues; leave "preprint …" upright
        venue_html = esc(venue) if venue.lower().startswith("preprint") else f'<em>{esc(venue)}</em>'
        out.append(
            f'<a class="relcard" href="{esc(it["url"])}" target="_blank" rel="noopener">'
            f'<span class="rel-title">{esc(it["title"])}</span>'
            f'<span class="rel-venue">{venue_html}</span></a>'
        )
    return out

NOT_FOUND = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>404 — Page not found</title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="/css/style.css">
<link rel="icon" href='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><text x="0" y="13" font-size="14">%F0%9F%93%96</text></svg>'>
<script src="/js/theme.js"></script>
{ga}
</head>
<body>
<header class="topbar"><div class="wrap">
  <div class="brand"><a class="brand-title" href="/">Extracting memorized pieces of (copyrighted) books from open-weight language models</a><span class="brand-venue">COLM&nbsp;2026</span></div>
  <nav><a href="/">Home</a>
  <a class="btn" href="https://arxiv.org/abs/2505.12546">Read the paper</a>
  <button class="theme-toggle" type="button" aria-label="Toggle theme">&#9790;</button></nav>
</div></header>

<main class="wrap">
  <section class="notfound">
    <div class="bignum">404</div>
    <p class="nf-tag">Nothing memorized here.</p>
    <a class="btn primary" href="/">← Back home</a>
  </section>
</main>

<footer class="site"><div class="wrap">
  Figures and data from <a href="https://afedercooper.info" target="_blank" rel="noopener">Cooper</a> et&nbsp;al.,
  &quot;Extracting memorized pieces of (copyrighted) books from open-weight language models,&quot;
  <em>COLM&nbsp;2026</em>.
</div></footer>
</body>
</html>
"""

def main():
    meta = load_meta()
    manifest, built = [], 0
    for file_slug, row in meta.items():
        if not os.path.exists(os.path.join(COVDIR, file_slug + "-coverage.json")):
            continue
        has_page = os.path.exists(os.path.join(ASSETS, file_slug, f"{file_slug}-heatmaps-10-known.png"))
        manifest.append(book_record(file_slug, row, has_page=has_page))
        if has_page:
            write_book_page(file_slug, row)
            built += 1
    print(f"  {len(manifest)} landing records · {built} full pages")
    with open(os.path.join(HERE, "data", "books.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    with open(os.path.join(HERE, "index.html"), "w") as f:
        f.write(bust(INDEX.format(bibtex=esc(BIBTEX), news="\n".join(news_cards(NEWS)),
                             related="\n".join(related_cards(RELATED)), code_btn=code_button(),
                             social_meta=site_meta(), byline=byline_html(), ga=ga_snippet())))
    with open(os.path.join(HERE, "404.html"), "w") as f:
        f.write(bust(NOT_FOUND.format(ga=ga_snippet())))

    # sitemap.xml (landing + every built book page) + robots.txt
    urls = [SITE_URL + "/"] + [f"{SITE_URL}/books/{r['slug']}.html" for r in manifest if r["hasPage"]]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"  <url><loc>{u}</loc></url>" for u in urls]
    sm.append("</urlset>")
    with open(os.path.join(HERE, "sitemap.xml"), "w") as f:
        f.write("\n".join(sm) + "\n")
    with open(os.path.join(HERE, "robots.txt"), "w") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    print(f"  sitemap.xml ({len(urls)} urls) + robots.txt")

if __name__ == "__main__":
    main()
