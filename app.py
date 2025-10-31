# app.py
from flask import Flask, request, render_template_string
import requests
from bs4 import BeautifulSoup, Tag
from urllib.parse import urlparse, urljoin
import re

app = Flask(__name__)

# ========================
# --- CONFIGURATION ------
# ========================

BASE_SELECTOR = ".ResponsivePage-content, .BlogPost"
DEFAULT_SELECTOR = BASE_SELECTOR  # Keep original as default
ALLOWED_TAGS = {"p", "blockquote", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
# Tags to search for titles in iframe destinations (in priority order)
IFRAME_TITLE_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
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
    form { margin-bottom: 1rem; }
    .form-row { display:flex; gap:8px; align-items:center; margin-bottom: 8px; }
    .form-row label { min-width: 80px; font-size: 0.9rem; color: #656d76; }
    input[type="text"] { flex:1; padding:8px; font-size:1rem; }
    button { padding:8px 12px; font-size:1rem; }
    pre { background:#f6f8fa; border:1px solid #e1e4e8; padding:12px; overflow:auto; white-space:pre-wrap; position: relative; }
    .summary { margin-bottom:1rem; color:#333; }
    .error { color:#a00; }
    h3 { color:#0969da; margin-top: 1.5rem; margin-bottom: 0.5rem; font-size: 1.1rem; }
    .code-block { position: relative; margin-bottom: 1rem; }
    .copy-btn { 
      position: absolute;
      top: 8px; 
      right: 8px; 
      background: #f6f8fa; 
      border: 1px solid #d1d9e0; 
      border-radius: 4px; 
      padding: 4px 8px; 
      font-size: 0.8rem; 
      cursor: pointer; 
      color: #656d76;
      transition: all 0.2s;
      z-index: 10;
    }
    .copy-btn:hover { 
      background: #e1e4e8; 
      border-color: #afb8c1; 
    }
    .copy-btn.copied { 
      background: #d1f7d1; 
      border-color: #74c574; 
      color: #0f5132; 
    }
  </style>
</head>
<body>
  <h1>HTML Scraper</h1>
  <form method="post" action="{{ url_for('index') }}">
    <div class="form-row">
      <label for="url">URL:</label>
      <input id="url" name="url" type="text" placeholder="https://example.com" value="{{ url_value|default('') }}" required />
    </div>
    <div class="form-row">
      <label for="selector">Selector:</label>
      <input id="selector" name="selector" type="text" placeholder="CSS selector" value="{{ selector_value|default('') }}" />
    </div>
    <div class="form-row">
      <label></label>
      <button type="submit">Fetch</button>
    </div>
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
      {% if block.is_iframe and block.title %}
        <h3>[Datawrapper] {{ block.title }}</h3>
      {% endif %}
      <div class="code-block">
        <button class="copy-btn" onclick="copyToClipboard(this)">Copy</button>
        <pre>{{ block.html }}</pre>
      </div>
    {% endfor %}
  {% endif %}

  {% if html_source %}
    <h2>Full HTML source</h2>
    <div class="code-block">
      <button class="copy-btn" onclick="copyToClipboard(this)">Copy</button>
      <pre>{{ html_source }}</pre>
    </div>
  {% endif %}

  <script>
    function copyToClipboard(button) {
      // Find the pre element that's a sibling of the button
      const preElement = button.parentElement.querySelector('pre');
      const textToCopy = preElement.textContent;
      
      // Use the modern clipboard API
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(textToCopy).then(() => {
          showCopySuccess(button);
        }).catch(err => {
          // Fallback to the older method
          fallbackCopyToClipboard(textToCopy, button);
        });
      } else {
        // Fallback for older browsers or non-secure contexts
        fallbackCopyToClipboard(textToCopy, button);
      }
    }
    
    function fallbackCopyToClipboard(text, button) {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.opacity = '0';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      
      try {
        document.execCommand('copy');
        showCopySuccess(button);
      } catch (err) {
        console.error('Failed to copy text: ', err);
        button.textContent = 'Failed';
        setTimeout(() => {
          button.textContent = 'Copy';
          button.classList.remove('copied');
        }, 2000);
      }
      
      document.body.removeChild(textArea);
    }
    
    function showCopySuccess(button) {
      button.textContent = 'Copied!';
      button.classList.add('copied');
      setTimeout(() => {
        button.textContent = 'Copy';
        button.classList.remove('copied');
      }, 2000);
    }
  </script>
</body>
</html>
"""

# ========================
# --- HELPERS -----------
# ========================

def fetch_iframe_title(iframe_url: str, base_url: str = "") -> str:
    """
    Fetch the content of an iframe URL and extract the first title tag.
    Uses IFRAME_TITLE_TAGS configuration for which tags to search.
    Returns the raw text content of the title, or empty string if not found or error.
    """
    try:
        # Handle relative URLs
        if base_url and not urlparse(iframe_url).netloc:
            iframe_url = urljoin(base_url, iframe_url)
        
        # Normalize URL
        normalized = normalize_url(iframe_url)
        if not normalized:
            return ""
        
        headers = {"User-Agent": "HTML-Scraper/1.0"}
        resp = requests.get(normalized, headers=headers, timeout=10)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Look for first title tag using configured tags (in priority order)
        for tag_name in IFRAME_TITLE_TAGS:
            title_element = soup.find(tag_name)
            if title_element:
                # Extract raw text, stripping all HTML tags
                return title_element.get_text(strip=True)
        
        return ""
    except Exception:
        # If any error occurs, return empty string
        return ""

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

def clean_orphaned_tags(html_fragment: str) -> str:
    """
    Clean up orphaned opening and closing tags from HTML fragments.
    Removes standalone opening/closing tags that don't have their counterpart.
    """
    if not html_fragment or not html_fragment.strip():
        return ""
    
    # Parse the fragment
    try:
        soup = BeautifulSoup(html_fragment, "html.parser")
        
        # If the fragment only contains orphaned tags (like just "<p>" or "</p>"), 
        # it will be mostly empty after parsing
        text_content = soup.get_text(strip=True)
        
        # Check if we have meaningful content vs just whitespace/orphaned tags
        if not text_content:
            # Check if we have any complete tags with content
            has_complete_tags = False
            for tag in soup.find_all():
                if tag.get_text(strip=True):
                    has_complete_tags = True
                    break
            
            if not has_complete_tags:
                return ""  # This fragment is just orphaned tags, discard it
        
        # Return the cleaned HTML
        return str(soup)
    
    except Exception:
        # If parsing fails, return the original fragment
        return html_fragment

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

def _process_allowed_element(el: Tag, base_url: str = ""):
    """
    Given an allowed block Tag el, find any iframe+script pairs inside it,
    extract them, and split el's HTML into a sequence of parts:
     - content segments (strings) and
     - iframe blocks (tuples of (html_string, title_string))
    Returns list of parts in order. iframe-block parts are tuples containing (iframe+script HTML, title).
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
        # Extract iframe src and fetch title
        iframe_src = iframe.get('src', '')
        title = ""
        if iframe_src:
            title = fetch_iframe_title(iframe_src, base_url)
        
        pair_html = str(iframe) + str(script)
        
        # Store the title separately, don't embed it in HTML
        token = f"@@IFRAME_SEQ_{idx}@@"
        # Replace only the first occurrence of this exact sequence
        html_str, n = re.subn(re.escape(pair_html), token, html_str, count=1, flags=re.DOTALL)
        if n == 1:
            token_map[token] = (pair_html, title)  # Store as tuple: (html, title)
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
                token_map[combined_token] = (pair_html, title)  # Store as tuple: (html, title)
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
                result.append(token_map[token])  # This is now a tuple (html, title)
            # else skip unknown token
        else:
            # keep content segment if not purely whitespace
            cleaned_part = clean_orphaned_tags(part)
            if cleaned_part.strip():
                result.append(cleaned_part)
    return result

def extract_blocks_recursive(element: Tag, base_url: str = ""):
    """
    Traverse element recursively and collect blocks.
    Allowed elements produce content parts (which may be split by iframe/script).
    iframe+script blocks extracted from allowed elements are emitted as separate blocks.
    Also detects iframe+script pairs that are siblings to allowed elements.
    Consecutive content segments are grouped into current_group and flushed to blocks when a special block is emitted.
    """
    blocks = []
    current_group = []

    def flush_current_group():
        nonlocal current_group
        if current_group:
            blocks.append("".join(current_group))
            current_group = []

    # Collect all direct children as tags
    tag_children = [child for child in element.children if isinstance(child, Tag)]
    
    # Process children in order, detecting iframe+script sibling pairs
    i = 0
    while i < len(tag_children):
        child = tag_children[i]
        
        # Check if current child is iframe and next child is script (sibling pair)
        if (child.name == "iframe" and 
            i + 1 < len(tag_children) and 
            tag_children[i + 1].name == "script"):
            
            # Found iframe+script sibling pair
            iframe = child
            script = tag_children[i + 1]
            
            # Extract iframe src and fetch title
            iframe_src = iframe.get('src', '')
            title = ""
            if iframe_src:
                title = fetch_iframe_title(iframe_src, base_url)
            
            pair_html = str(iframe) + str(script)
            
            # Flush any accumulated content to maintain order
            flush_current_group()
            
            # Add iframe block at current position
            blocks.append((pair_html, title))
            
            # Skip the script tag since we processed it with iframe
            i += 2
            continue
        
        # Process single child normally
        if child.name in ALLOWED_TAGS:
            # This is an allowed block, process it
            parts = _process_allowed_element(child, base_url)
            for part in parts:
                if isinstance(part, tuple):
                    # This is an iframe block tuple (html, title) from within allowed tag
                    flush_current_group()
                    blocks.append(part)
                else:
                    # a content segment; append to grouping
                    current_group.append(part)
        else:
            # Not an allowed tag, recursively process its children
            child_blocks = extract_blocks_recursive(child, base_url)
            for block in child_blocks:
                if isinstance(block, tuple):
                    # iframe block from deeper level
                    flush_current_group()
                    blocks.append(block)
                else:
                    # content block from deeper level
                    current_group.append(block)
        
        i += 1

    # flush final group
    flush_current_group()

    return blocks

# ========================
# --- ROUTES ------------
# ========================

@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    html_source = None
    url_value = ""
    selector_value = DEFAULT_SELECTOR
    displayed_url = ""
    extracted_blocks = []
    summary = {"content_blocks": 0, "iframe_blocks": 0}

    if request.method == "POST":
        url_value = request.form.get("url", "")
        selector_value = request.form.get("selector", DEFAULT_SELECTOR).strip()
        
        # Use default selector if user left it empty
        if not selector_value:
            selector_value = DEFAULT_SELECTOR
            
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
                content = soup.select_one(selector_value)
                if not content:
                    error = f"Could not find '{selector_value}' in the page."
                else:
                    extracted_blocks = extract_blocks_recursive(content, normalized)

                    # Prepare blocks for template with metadata
                    template_blocks = []
                    for block in extracted_blocks:
                        if isinstance(block, tuple):
                            # iframe block: (html, title)
                            html, title = block
                            template_blocks.append({
                                'html': html,
                                'is_iframe': True,
                                'title': title
                            })
                            summary["iframe_blocks"] += 1
                        else:
                            # content block: just html string
                            template_blocks.append({
                                'html': block,
                                'is_iframe': False,
                                'title': ''
                            })
                            summary["content_blocks"] += 1
                    
                    extracted_blocks = template_blocks

            except requests.exceptions.RequestException as e:
                error = f"Request failed: {e}"

    # pass raw html_source (Jinja will escape in the template)
    return render_template_string(
        TEMPLATE,
        error=error,
        html_source=html_source,
        url_value=url_value,
        selector_value=selector_value,
        displayed_url=displayed_url,
        extracted_blocks=extracted_blocks,
        summary=summary
    )

# ========================
# --- RUN ---------------
# ========================

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5555, debug=True)
