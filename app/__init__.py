"""Clean Air Assistant: application factory and security headers."""
from flask import Flask, Response
from werkzeug.middleware.proxy_fix import ProxyFix

from .routes import bp
from .validation import MAX_UPLOAD_BYTES

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data: https://tile.openstreetmap.org; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


def create_app() -> Flask:
    """Create and configure the Flask application instance."""
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES  # per-route limits in routes._guard
    app.register_blueprint(bp)

    @app.after_request
    def set_security_headers(resp: Response) -> Response:
        """Attach defensive security headers to every HTTP response."""
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
        return resp

    return app
