#!/usr/bin/env python3
"""Download the Fomantic-UI, jQuery and CodeMirror assets to package them 100% offline."""
import os
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
CSS_DIR = os.path.join(FRONTEND_DIR, "css")
JS_DIR = os.path.join(FRONTEND_DIR, "js")
FONTS_DIR = os.path.join(FRONTEND_DIR, "css", "themes", "default", "assets", "fonts")

for d in (CSS_DIR, JS_DIR, FONTS_DIR):
    os.makedirs(d, exist_ok=True)

FILES_TO_DOWNLOAD = [
    (
        "https://cdnjs.cloudflare.com/ajax/libs/jquery/3.7.1/jquery.min.js",
        os.path.join(JS_DIR, "jquery.min.js"),
    ),
    (
        "https://cdnjs.cloudflare.com/ajax/libs/fomantic-ui/2.9.3/semantic.min.js",
        os.path.join(JS_DIR, "semantic.min.js"),
    ),
    (
        "https://cdnjs.cloudflare.com/ajax/libs/fomantic-ui/2.9.3/semantic.min.css",
        os.path.join(CSS_DIR, "semantic.min.css"),
    ),
    (
        "https://cdnjs.cloudflare.com/ajax/libs/fomantic-ui/2.9.3/themes/default/assets/fonts/icons.woff2",
        os.path.join(FONTS_DIR, "icons.woff2"),
    ),
    (
        "https://cdnjs.cloudflare.com/ajax/libs/fomantic-ui/2.9.3/themes/default/assets/fonts/icons.woff",
        os.path.join(FONTS_DIR, "icons.woff"),
    ),
    (
        "https://cdnjs.cloudflare.com/ajax/libs/fomantic-ui/2.9.3/themes/default/assets/fonts/brand-icons.woff2",
        os.path.join(FONTS_DIR, "brand-icons.woff2"),
    ),
    (
        "https://cdnjs.cloudflare.com/ajax/libs/fomantic-ui/2.9.3/themes/default/assets/fonts/outline-icons.woff2",
        os.path.join(FONTS_DIR, "outline-icons.woff2"),
    ),
    # CodeMirror 5: terminal-style SQL console (editor + SQL syntax mode +
    # Dracula dark theme + placeholder addon).
    (
        "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css",
        os.path.join(CSS_DIR, "codemirror.min.css"),
    ),
    (
        "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/dracula.min.css",
        os.path.join(CSS_DIR, "codemirror-theme-dracula.min.css"),
    ),
    (
        "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js",
        os.path.join(JS_DIR, "codemirror.min.js"),
    ),
    (
        "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/sql/sql.min.js",
        os.path.join(JS_DIR, "codemirror-mode-sql.min.js"),
    ),
    (
        "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/display/placeholder.min.js",
        os.path.join(JS_DIR, "codemirror-addon-placeholder.min.js"),
    ),
]

def main():
    headers = {"User-Agent": "Mozilla/5.0"}
    for url, target_path in FILES_TO_DOWNLOAD:
        if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
            print(f"Already exists: {os.path.basename(target_path)}")
            continue
        print(f"Downloading {os.path.basename(target_path)}...")
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp, open(target_path, "wb") as out:
            out.write(resp.read())
        print(f"Saved: {target_path} ({os.path.getsize(target_path)} bytes)")
    print("All assets downloaded successfully.")

if __name__ == "__main__":
    main()
