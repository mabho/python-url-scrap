# 🕸️ Python URL Scraper

A simple Flask web application that scrapes web pages and extracts content blocks with special handling for embedded iframe+script combinations. Perfect for extracting and analyzing content from blogs, articles, and pages with embedded interactive elements (like Datawrapper charts).

## ✨ Features

- **Smart Content Extraction**: Extracts content from configurable CSS selectors (`.ResponsivePage-content`, `.BlogPost`)
- **Iframe+Script Detection**: Automatically detects and isolates `<iframe>` + `<script>` pairs in two scenarios:
  - Nested within content blocks (paragraphs, lists, etc.)
  - As siblings to content blocks
- **Dynamic Title Fetching**: Retrieves titles (h2-h6) from iframe destination pages for better context
- **Copy-to-Clipboard**: One-click copying of any extracted content block

---

## 🚀 Quick Start

### 1. Clone this repository
```bash
git clone https://github.com/<yourname>/python_url_scrap.git
cd python_url_scrap
```

### 2. Create and activate a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```


### 3. Install dependencies
```bash
pip install flask requests beautifulsoup4
```

### 4. Run the application
```bash
python app.py
```

You should see something like:
```bash
 * Running on http://127.0.0.1:5555 (Press CTRL+C to quit)
```

Then open your browser and visit http://127.0.0.1:5555.

---

## 🔧 Configuration

The application can be configured by modifying the constants in `app.py`:

```python
# Target CSS selectors for content extraction
BASE_SELECTOR = ".ResponsivePage-content, .BlogPost"

# HTML tags considered for content blocks
ALLOWED_TAGS = {"p", "blockquote", "ul", "ol", "li", "h2", "h3", "h4", "h5", "h6"}

# Server configuration
HOST = "127.0.0.1"
PORT = 5555
```

## 📖 How It Works

### Content Extraction Process

1. **Page Fetching**: Downloads the target webpage with appropriate headers
2. **Content Selection**: Finds content using the configured CSS selectors
3. **Block Processing**: Analyzes HTML structure to identify:
   - Regular content blocks (paragraphs, lists, headings)
   - Iframe+script combinations (both nested and sibling patterns)
4. **Title Extraction**: For each iframe, fetches the destination page and extracts the first heading (h2-h6)
5. **Template Rendering**: Displays extracted blocks with copy functionality

### Iframe+Script Detection

The scraper handles two scenarios:

#### Nested Pattern
```html
<p>
  Some text content
  <iframe src="https://example.com/chart"></iframe>
  <script>/* chart script */</script>
  More text content
</p>
```

#### Sibling Pattern
```html
<p>Introduction text</p>
<iframe src="https://example.com/chart"></iframe>
<script>/* chart script */</script>
<p>Conclusion text</p>
```

## 🖥️ Web Interface

- **URL Input**: Enter any webpage URL to scrape
- **Summary Stats**: View count of content blocks vs iframe+script blocks
- **Content Blocks**: Each block is displayed in a syntax-highlighted container
- **Iframe Titles**: Automatically fetched titles appear as headers (e.g., "[Datawrapper] Chart Title")
- **Copy Buttons**: One-click copying with visual feedback
- **Error Handling**: Clear error messages for invalid URLs or network issues

## 🛠️ Technical Details

### Dependencies

- **Flask**: Web framework for the user interface
- **Requests**: HTTP client for fetching web pages and iframe content
- **BeautifulSoup4**: HTML parsing and manipulation
- **urllib.parse**: URL handling and validation

### Key Functions

- `fetch_iframe_title()`: Extracts titles from iframe destination pages
- `extract_blocks_recursive()`: Main content extraction with sibling detection
- `_process_allowed_element()`: Handles iframe+script pairs within content blocks
- `clean_orphaned_tags()`: Removes fragmented HTML tags
- `normalize_url()`: URL validation and normalization

## 🚨 Limitations

- **Rate Limiting**: No built-in rate limiting for iframe title fetching
- **JavaScript**: Cannot execute JavaScript, only extracts static HTML
- **Authentication**: No support for pages requiring login
- **Large Pages**: May be slow on pages with many iframes due to title fetching
- **Timeout**: 10-second timeout for all HTTP requests

## 🔒 Security Considerations

- Uses appropriate User-Agent headers to avoid blocking
- No storage of scraped content (memory only)
- Input validation for URLs
- Safe HTML parsing with BeautifulSoup
