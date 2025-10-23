# app.py
from flask import Flask, request, render_template_string
import requests
from bs4 import BeautifulSoup, Tag
from urllib.parse import urlparse
import re

app = Flask(__name__)

# ========================
# --- CONFIGURATION ------
# ========================

BASE_SELECTOR = ".ResponsivePage-content"
ALLOWED_TAGS = {"p", "blockquote", "ul", "ol", "li", "h2", "h3", "h4", "h5", "h6"}
# We look for iframe followed (in document order) by a script within the same allowed element.
SPECIAL_SEQUENCE = ("iframe", "script")

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
    <pre>{{ html_source }}</pre>
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

def _find_script_after(tag: Tag, boundary: Tag):
    """
    Given a Tag `tag` (an iframe) return the first <script> Tag that occurs
    after `tag` in document order but still within `boundary` (the allowed element).
    Return None if not found.
    """
    for node in tag.next_elements:
        if isinstance(node, Tag) and node.name == "script":
            # ensure node is inside boundary
            if boundary in node.parents:
                return node
            else:
                return None
    return None

def _process_allowed_element(el: Tag):
    """
    Given an allowed block Tag el, find any iframe+script pairs inside it,
    extract them, and split el's HTML into a sequence of parts:
     - content segments (strings) and
     - iframe blocks (strings)
    Returns list of parts in order. iframe-block parts are exact HTML strings containing the iframe+script.
    """
    # Collect pairs in document order
    pairs = []
    for iframe in el.find_all("iframe"):
        script = _find_script_after(iframe, el)
        if script is not None:
            pairs.append((iframe, script))

    if not pairs:
        # no special sequences: single content piece = the whole element HTML
        return [str(el)]

    # Build replacement tokens and mapping
    token_map = {}
    html_str = str(el)
    for idx, (iframe, script) in enumerate(pairs):
        pair_html = str(iframe) + str(script)
        token = f"@@IFRAME_SEQ_{idx}@@"
        # Replace only the first occurrence of this exact sequence
        html_str, n = re.subn(re.escape(pair_html), token, html_str, count=1, flags=re.DOTALL)
        if n == 1:
            token_map[token] = pair_html
        else:
            # fallback: if exact concatenation didn't match (rare), try replacing iframe alone then script alone
            # replace iframe first
            iframe_token = f"@@IFRAME_ONLY_{idx}@@"
            html_str, n1 = re.subn(re.escape(str(iframe)), iframe_token, html_str, count=1, flags=re.DOTALL)
            script_token = f"@@SCRIPT_ONLY_{idx}@@"
            html_str, n2 = re.subn(re.escape(str(script)), script_token, html_str, count=1, flags=re.DOTALL)
            # assemble pair if both replaced
            if n1 == 1 and n2 == 1:
                # join tokens so splitting keeps them together
                combined_token = f"@@IFRAME_SEQ_{idx}@@"
                html_str = html_str.replace(iframe_token + ".*?" + script_token, combined_token)  # not ideal, but fallback
                token_map[combined_token] = str(iframe) + str(script)
            else:
                # give up for this pair (leave as-is)
                pass

    # Split by tokens while keeping them
    parts = re.split(r'(@@IFRAME_SEQ_\d+@@)', html_str)

    result = []
    for part in parts:
        if not part:
            continue
        m = re.match(r'@@IFRAME_SEQ_(\d+)@@', part)
        if m:
            token = part
            if token in token_map:
                result.append(token_map[token])
            # else skip unknown token
        else:
            # keep content segment if not purely whitespace
            if part.strip():
                result.append(part)
    return result

def extract_blocks_recursive(element: Tag):
    """
    Traverse element recursively and collect blocks.
    Allowed elements produce content parts (which may be split by iframe/script).
    iframe+script blocks extracted from allowed elements are emitted as separate blocks.
    Consecutive content segments are grouped into current_group and flushed to blocks when a special block is emitted.
    """
    blocks = []
    current_group = []

    def traverse(el):
        nonlocal current_group

        if not isinstance(el, Tag):
            return

        # If this is an allowed block, process it (do NOT descend further for this el)
        if el.name in ALLOWED_TAGS:
            parts = _process_allowed_element(el)
            for part in parts:
                # part is either a content HTML (string) or an iframe+script HTML (string containing '<iframe' and '<script')
                if "<iframe" in part and "<script" in part:
                    # flush current_group first
                    if current_group:
                        blocks.append("".join(current_group))
                        current_group = []
                    # append the iframe block as its own block
                    blocks.append(part)
                else:
                    # a content segment; append to grouping
                    current_group.append(part)
            return  # stop descending into this allowed block

        # Not an allowed block: descend children
        for child in el.children:
            traverse(child)

    # Start traversal from direct children of base element (preserve order)
    for child in element.children:
        traverse(child)

    # flush final group
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

                    # compute summary
                    for block_html in extracted_blocks:
                        if "<iframe" in block_html and "<script" in block_html:
                            summary["iframe_blocks"] += 1
                        else:
                            summary["content_blocks"] += 1

            except requests.exceptions.RequestException as e:
                error = f"Request failed: {e}"

    # pass raw html_source (Jinja will escape in the template)
    return render_template_string(
        TEMPLATE,
        error=error,
        html_source=html_source,
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
