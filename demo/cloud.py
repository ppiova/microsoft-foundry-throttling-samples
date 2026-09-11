"""Private Container Apps entry point. Requires platform-validated Entra headers."""
import os
import subprocess
from flask import Flask, jsonify, request, send_from_directory
import server

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024


@app.before_request
def authorize():
    if request.path == '/healthz':
        return None
    origin = os.environ.get('LAB_PUBLIC_ORIGIN', '')
    allowed = set(filter(None, os.environ.get('LAB_ALLOWED_USERS', '').split(',')))
    if not origin.startswith('https://') or not allowed:
        return jsonify(error='Access is not configured'), 503
    # These headers are stripped/replaced by Container Apps Easy Auth. This
    # entry point must only run behind that ingress, never an untrusted proxy.
    if (request.headers.get('X-MS-CLIENT-PRINCIPAL-IDP') != 'aad'
            or request.headers.get('X-MS-CLIENT-PRINCIPAL-ID') not in allowed):
        return jsonify(error='Your account has not been granted access to this lab.'), 403
    if request.host != origin.removeprefix('https://'):
        return jsonify(error='Invalid host'), 403
    if request.method == 'POST' and request.headers.get('Origin') != origin:
        return jsonify(error='Same-origin requests required'), 403


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response


@app.get('/healthz')
def health():
    return jsonify(status='ok')


@app.get('/')
def index():
    html = (server.ASSETS / 'index.html').read_text(encoding='utf-8')
    html = html.replace('Local demo', 'Private Azure demo').replace('Local workspace', 'Private workspace')
    html = html.replace('Runs on your local workstation', 'Hosted in Azure Container Apps')
    html = html.replace('<button id="presentation">', '<a href="/.auth/logout">Sign out</a><button id="presentation">')
    return html


@app.get('/<name>')
def asset(name):
    if name not in ('app.js', 'style.css', 'portal.css'):
        return jsonify(error='Not found'), 404
    return send_from_directory(server.ASSETS, name)


@app.get('/api/runs')
def evidence():
    return jsonify(server.runs())


@app.post('/api/run')
def simulate():
    if request.content_type != 'application/json':
        return jsonify(error='JSON required'), 400
    try:
        args = server.command(request.get_json())
    except (ValueError, TypeError, KeyError):
        return jsonify(error='Invalid simulation settings'), 400
    if not server.LOCK.acquire(blocking=False):
        return jsonify(error='A simulation is already running'), 409
    try:
        result = subprocess.run(args, cwd=server.ROOT, capture_output=True, text=True, timeout=180, shell=False)
        if result.returncode:
            return jsonify(error='Simulation failed. Contact the lab administrator.'), 500
        return jsonify(server.runs())
    except (OSError, subprocess.TimeoutExpired):
        return jsonify(error='Runtime unavailable or simulation timed out'), 500
    finally:
        server.LOCK.release()
