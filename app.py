import os

from flask import Flask, send_from_directory

# Directory containing index.html and other static assets (CSS, JS, images).
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    """Serve the main website page."""
    return send_from_directory(ROOT_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    """Serve any other static files (CSS, JS, images, etc.) from the repo root."""
    return send_from_directory(ROOT_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
