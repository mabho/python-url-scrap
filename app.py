# app.py
from flask import Flask, request, render_template_string
import requests
from bs4 import BeautifulSoup
import html
from urllib.parse import urlparse

app = Flask(__name__)

# ========================
# --- CONFIGURATION ------
# ========================

BASE_SELECTOR = ".ResponsivePage-content"

# Only block-level tags; inline tags will be kept automatically
ALLOWED_TAGS = {"p", "blockquote", "ul", "ol", "li", "h2", "h3", "h4", "h5", "h6"}

# Special sequences to handle separately
SPECIAL_SEQUENCE = [("iframe", "script")]

# ========================
# --- TEMPLATE ----------
# ========================

TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>HTML Scraper</title>
  <style>
    body { font-family: system-ui, -apple-system, "Segoe UI", Roboto; padding: 20px; max-width: 1000px; margin:auto;}
    form { margin-bottom: 1rem; display:flex; gap:8px; align-items:center; }
    input[type="text"] { flex:1; padding:8px; font-size:1rem; }
    button { padding:8px 12px; font-size:1rem; }
    pre { background:#f6f8fa; border:1px solid #e1e4e8; padding:12px; overflow:auto; white-space:pre-wrap; }
    .summary { margin-bottom:1rem; color:#333; }
    .error { color:#a00; }
  </style>
</head>
<body>
  <h1>HTML Scraper</h1>
  <form method="post" action="{{ url_for('index') }}">
    <input id="url" name="url" type="text" placeholder="https://example.com" value="{{ url_value|default('') }}" required />
    <button type="submit">Fetch</button>
  </form>

  {% if error %}
    <p class="error"><strong>Error:</strong> {{ error }}</p>
  {% endif %}

  {% if summary %}
    <div class="summary">
      <strong>Summary:</strong> {{ summary.content_blocks }} content blocks, {{ summary.iframe_blocks }} iframe+script blocks
    </div>
  {% endif %}

  {% if extracted_blocks %}
    <h2>Extracted content blocks</h2>
    {% for block in extracted_blocks %}
      <pre>{{ block }}</pre>
    {% endfor %}
  {% endif %}

  {% if html_source %}
    <h2>Full HTML source</h2>
    <pre>{{ html_source|safe }}</pre>
  {% endif %}
</body>
</html>
"""

# ========================
# --- HELPERS -----------
# ========================

def normalize_url(u: str) -> str:
    u = u.strip()
    if not u:
        return ""
    parsed = urlparse(u)
    if not parsed.scheme:
        u = "https://" + u
        parsed = urlparse(u)
    if not parsed.netloc:
        return ""
    return u


def extract_blocks_recursive(element):
    """
    Recursively traverse element's children to extract allowed tags
    and iframe+script sequences.
    Returns a list of HTML strings, each to be wrapped in <pre>.
    """
    blocks = []
    current_group = []

    def traverse(el):
        nonlocal current_group

        if not getattr(el, "name", None):
            return

        # --- Special sequences (iframe + script) ---
        for seq in SPECIAL_SEQUENCE:
            if el.name == seq[0] and el.next_sibling and getattr(el.next_sibling, "name", None) == seq[1]:
                # Finish current group if it exists
                if current_group:
                    blocks.append("".join(current_group))
                    current_group.clear()
                # Add special sequence as its own block
                blocks.append(str(el) + "\n" + str(el.next_sibling))
                return  # Do not descend further

        # --- Allowed block tags ---
        if el.name in ALLOWED_TAGS:
            current_group.append(str(el))
            return  # Do not descend further

        # --- Otherwise, traverse children recursively ---
        for child in el.children:
            traverse(child)

    # Traverse all direct children of base element
    for child in element.children:
        traverse(child)

    # Append any remaining content group at the end
    if current_group:
        blocks.append("".join(current_group))

    return blocks

# ========================
# --- ROUTES ------------
# ========================

@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    html_source = None
    url_value = ""
    displayed_url = ""
    extracted_blocks = []
    summary = {"content_blocks": 0, "iframe_blocks": 0}

    if request.method == "POST":
        url_value = request.form.get("url", "")
        normalized = normalize_url(url_value)
        if not normalized:
            error = "The URL looks invalid. Include hostname and scheme."
        else:
            try:
                headers = {"User-Agent": "HTML-Scraper/1.0"}
                resp = requests.get(normalized, headers=headers, timeout=10)
                resp.raise_for_status()
                html_source = resp.text
                displayed_url = normalized
                url_value = normalized

                soup = BeautifulSoup(html_source, "html.parser")
                content = soup.select_one(BASE_SELECTOR)

                if not content:
                    error = f"Could not find {BASE_SELECTOR} in the page."
                else:
                    extracted_blocks = extract_blocks_recursive(content)

                    # Compute summary
                    for block_html in extracted_blocks:
                        if "<iframe" in block_html and "<script" in block_html:
                            summary["iframe_blocks"] += 1
                        else:
                            summary["content_blocks"] += 1

            except requests.exceptions.RequestException as e:
                error = f"Request failed: {e}"

    escaped_full_html = html.escape(html_source) if html_source else None

    return render_template_string(
        TEMPLATE,
        error=error,
        html_source=escaped_full_html,
        url_value=url_value,
        displayed_url=displayed_url,
        extracted_blocks=extracted_blocks,
        summary=summary
    )

# ========================
# --- RUN ---------------
# ========================

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5555, debug=True)
