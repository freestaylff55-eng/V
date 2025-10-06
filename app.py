# app.py
import os
import base64
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import requests
import logging

# Optional rate limiter
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter_available = True
except Exception:
    limiter_available = False

load_dotenv()
FLASK_PORT = int(os.getenv("PORT", "3000"))
ENCRYPTION_KEY_HEX = os.getenv("ENCRYPTION_KEY")
TARGET_API_URL = os.getenv("TARGET_API_URL")  # if not set -> mock mode
DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")

# Basic checks
if not ENCRYPTION_KEY_HEX:
    raise RuntimeError("ENCRYPTION_KEY not set in .env (run: python -c \"import os; print(os.urandom(32).hex())\")")
try:
    ENC_KEY = bytes.fromhex(ENCRYPTION_KEY_HEX)
except Exception:
    raise RuntimeError("ENCRYPTION_KEY must be valid hex")

if len(ENC_KEY) != 32:
    raise RuntimeError("ENCRYPTION_KEY must be 32 bytes (64 hex chars)")

# Flask app
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.logger.setLevel(logging.INFO)

# Optional limiter
if limiter_available:
    limiter = Limiter(app, key_func=get_remote_address, default_limits=["30 per minute"])
    app.logger.info("flask-limiter enabled")
else:
    limiter = None
    app.logger.info("flask-limiter NOT installed — install flask_limiter for rate limiting")

# --- DB init ---
DB_PATH = "tokens.db"
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT,
            token_enc TEXT,
            created_at TEXT
        );
    """)
    conn.commit()
    conn.close()

init_db()

# --- Encryption helpers (AES-GCM) ---
def encrypt_token(plain_text: str) -> str:
    aesgcm = AESGCM(ENC_KEY)
    iv = os.urandom(12)
    ct = aesgcm.encrypt(iv, plain_text.encode("utf-8"), None)
    combined = iv + ct
    return base64.b64encode(combined).decode("utf-8")

def decrypt_token(b64: str) -> str:
    aesgcm = AESGCM(ENC_KEY)
    raw = base64.b64decode(b64)
    iv = raw[:12]
    ct = raw[12:]
    plain = aesgcm.decrypt(iv, ct, None)
    return plain.decode("utf-8")

# Helper: DB operations
def insert_token(label: str, token_enc: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO user_tokens (label, token_enc, created_at) VALUES (?, ?, ?)",
                (label, token_enc, datetime.utcnow().isoformat()))
    conn.commit()
    last = cur.lastrowid
    conn.close()
    return last

def get_token_row(token_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, label, token_enc, created_at FROM user_tokens WHERE id = ?", (token_id,))
    row = cur.fetchone()
    conn.close()
    return row

def delete_token_row(token_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM user_tokens WHERE id = ?", (token_id,))
    conn.commit()
    changes = cur.rowcount
    conn.close()
    return changes

# --- Routes ---

@app.route("/")
def index():
    # serve main static index.html
    return send_from_directory("static", "index.html")

# Save token
@app.route("/api/save-token", methods=["POST"])
def save_token():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    label = data.get("label", "default")
    if not token or not isinstance(token, str):
        return jsonify({"error": "token required"}), 400
    try:
        enc = encrypt_token(token)
        tid = insert_token(label, enc)
        return jsonify({"ok": True, "id": tid})
    except Exception as e:
        app.logger.exception("save-token failed")
        return jsonify({"error": "server_error"}), 500

# Update bio
@app.route("/api/update-bio", methods=["POST"])
def update_bio():
    data = request.get_json(silent=True) or {}
    tid = data.get("id")
    new_bio = data.get("newBio")
    if not tid or not isinstance(new_bio, str):
        return jsonify({"error": "id and newBio required"}), 400

    row = get_token_row(int(tid))
    if not row:
        return jsonify({"error": "token not found"}), 404

    try:
        token_enc = row[2]
        access_token = decrypt_token(token_enc)
    except Exception:
        app.logger.exception("decrypt failed")
        return jsonify({"error": "decrypt_failed"}), 500

    # If TARGET_API_URL is not configured, run in mock mode (simulate success) for testing
    if not TARGET_API_URL:
        app.logger.info("TARGET_API_URL not set -> running in MOCK mode (no external request)")
        mock = {"status": "ok", "bio": new_bio, "updated_at": datetime.utcnow().isoformat()}
        access_token = None
        return jsonify({"ok": True, "upstream": mock})

    # Make real request to upstream endpoint
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "XMODZ-BioPortal/1.0"
        }
        payload = {"bio": new_bio}
        r = requests.post(TARGET_API_URL, json=payload, headers=headers, timeout=10)
        try:
            upstream_json = r.json()
        except Exception:
            upstream_json = {"status_code": r.status_code, "text": r.text[:400]}
        access_token = None
        if r.status_code >= 200 and r.status_code < 300:
            return jsonify({"ok": True, "upstream": upstream_json})
        else:
            app.logger.warning("upstream returned error: %s", r.status_code)
            return jsonify({"error": "upstream_failed", "detail": upstream_json}), 502
    except requests.RequestException as ex:
        app.logger.exception("upstream request failed")
        access_token = None
        return jsonify({"error": "upstream_error", "detail": str(ex)}), 502

# Delete token
@app.route("/api/delete-token", methods=["POST"])
def delete_token():
    data = request.get_json(silent=True) or {}
    tid = data.get("id")
    if not tid:
        return jsonify({"error": "id required"}), 400
    try:
        changes = delete_token_row(int(tid))
        return jsonify({"ok": True, "deleted": changes})
    except Exception:
        app.logger.exception("delete failed")
        return jsonify({"error": "server_error"}), 500

# Serve static files fallback
@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory("static", path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=DEBUG)
