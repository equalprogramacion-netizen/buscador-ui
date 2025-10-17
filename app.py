# =========================================================
# app/main.py — Biotico Unificado (dev/prod)
# Seguridad + sesión (idle + absolute) + UI básica
# =========================================================

from __future__ import annotations

# ---------- Stdlib ----------
import os
import re
import hashlib
import secrets
import time
import json
import hmac
import base64
from collections import defaultdict
import uuid
from pathlib import Path
from urllib.parse import urlencode

# ---------- FastAPI / Starlette ----------
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.types import Message

# Proxy headers es opcional
try:
    from starlette.middleware.proxy_headers import ProxyHeadersMiddleware  # type: ignore
except Exception:  # pragma: no cover
    ProxyHeadersMiddleware = None

# Swagger UI privado (solo tras login)
from fastapi.openapi.docs import get_swagger_ui_html


# =========================================================
# 1) CONFIGURACIÓN
# =========================================================

ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "equalambiental.com")

JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
JWT_SECRET_PREV = os.getenv("JWT_SECRET_PREV", "")

_signers = [TimestampSigner(JWT_SECRET)]
if JWT_SECRET_PREV:
    _signers.append(TimestampSigner(JWT_SECRET_PREV))
_signer = _signers[0]

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "biotico_session")
ISSUED_COOKIE_NAME  = SESSION_COOKIE_NAME + "_iat"

IS_PROD = os.getenv("ENV", "development").lower() == "production"

SESSION_MAX_IDLE = int(os.getenv("SESSION_MAX_IDLE", "1800"))           # 30 min
SESSION_MAX_ABSOLUTE = int(os.getenv("SESSION_MAX_ABSOLUTE", "43200"))  # 12 h
SESSION_PERSISTENT = os.getenv("SESSION_PERSISTENT", "true").lower() == "true"

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")]
CORS_ORIGINS  = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000").split(",")]

# Enlaces (las UIs de servicios se abren vía /gate)
RECONCILIAR_UI  = os.getenv("RECONCILIAR_UI", "/ui/buscador")
BUSCADOR_EXTERN = os.getenv("BUSCADOR_EXTERN", "")
DOCS_URL        = os.getenv("DOCS_URL", "/docs")

# Branding
APP_NAME  = os.getenv("APP_NAME", "Biotico – Centro de herramientas")
LOGO_URL  = os.getenv("LOGO_URL", "")
LOGO_FILE = os.getenv("LOGO_FILE", "logo.png")

PRIMARY   = os.getenv("PRIMARY", "#22c55e")
ACCENT    = os.getenv("ACCENT",  "#7c9bff")
INK       = os.getenv("INK",     "#e6ebff")
MUTED     = os.getenv("MUTED",   "#9aa3c7")
BG        = os.getenv("BG",      "#0b1020")
CARD      = os.getenv("CARD",    "#0f162b")
BORDER    = os.getenv("BORDER",  "rgba(255,255,255,.08)")

LOGO_SIZE      = int(os.getenv("LOGO_SIZE", "28"))
LOGO_SIZE_BIG  = int(os.getenv("LOGO_SIZE_BIG", "44"))
LOGO_RADIUS    = os.getenv("LOGO_RADIUS", "12px")

# CSRF
CSRF_COOKIE = "csrf_token"
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@" + re.escape(ALLOWED_DOMAIN) + r"$")

# --- SSO Gate config ---
GATEWAY_SHARED_SECRET = os.getenv("GATEWAY_SHARED_SECRET", "")
RECONCILIADOR_BASE = os.getenv("RECONCILIADOR_BASE", "https://reconciliador-api.onrender.com")
BUSCADOR_BASE       = os.getenv("BUSCADOR_BASE",       "https://buscador-api.onrender.com")
HUB_ISS = os.getenv("HUB_ISS", "biotico-hub")
if not GATEWAY_SHARED_SECRET:
    raise RuntimeError("Falta GATEWAY_SHARED_SECRET en el Hub")


# =========================================================
# 2) ESTADO EN MEMORIA
# =========================================================
REVOKED_TOKENS: set[str] = set()


# =========================================================
# 3) MIDDLEWARES
# =========================================================

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        resp = await call_next(request)
        resp.headers["X-Request-ID"] = rid
        if getattr(resp, "media_type", "") in ("text/html", "application/xhtml+xml"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

class CSPNonceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.csp_nonce = secrets.token_urlsafe(16)
        return await call_next(request)

class SessionRefreshMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        email = current_user_email(request)
        if email:
            _set_session(resp, email, request=request, sliding_refresh=True)
        return resp

ANON_ALLOW_PATHS = {
    "/", "/login", "/logout", "/static", "/static/", "/favicon.ico",
    "/_openapi.json", "/_docs", "/healthz", "/robots.txt"
}
class AuthGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/static/") or path in ANON_ALLOW_PATHS:
            return await call_next(request)
        if not current_user_email(request):
            return RedirectResponse("/login")
        return await call_next(request)

MAX_BODY = int(os.getenv("MAX_BODY_BYTES", "1048576"))  # 1 MiB
class BodyLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        orig_receive = request._receive
        async def receive() -> Message:
            message = await orig_receive()
            body = message.get("body", b"")
            if body and len(body) > MAX_BODY:
                return {"type": "http.disconnect"}
            return message
        request._receive = receive  # type: ignore[attr-defined]
        return await call_next(request)

class StaticCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        if request.url.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


# =========================================================
# 4) APP + /static
# =========================================================

middleware: list[Middleware] = []

if ProxyHeadersMiddleware is not None:
    try:
        middleware.append(Middleware(ProxyHeadersMiddleware, trusted_hosts=ALLOWED_HOSTS))
    except TypeError:
        middleware.append(Middleware(ProxyHeadersMiddleware))

middleware += [
    Middleware(RequestIDMiddleware),
    Middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS),
    Middleware(CORSMiddleware,
               allow_origins=CORS_ORIGINS,
               allow_credentials=True,
               allow_methods=["GET", "POST", "OPTIONS"],
               allow_headers=["*"]),
    Middleware(CSPNonceMiddleware),
    Middleware(SessionRefreshMiddleware),
    Middleware(AuthGuardMiddleware),
    Middleware(BodyLimitMiddleware),
    Middleware(StaticCacheMiddleware),
]

if IS_PROD:
    middleware.insert(2, Middleware(HTTPSRedirectMiddleware))

docs_kwargs = {}
if IS_PROD:
    docs_kwargs = dict(docs_url=None, redoc_url=None, openapi_url=None)

app = FastAPI(title="Biotico Unificado", middleware=middleware, **docs_kwargs)

static_dir = os.path.join(os.path.dirname(__file__), "static")
Path(static_dir).mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# =========================================================
# 5) LOGO / BRAND
# =========================================================

def _resolve_logo_src() -> str:
    if LOGO_URL:
        return LOGO_URL
    for name in [LOGO_FILE, "logo.png", "logo.jpg", "logo.jpeg", "logo.svg", "logo"]:
        if os.path.exists(os.path.join(static_dir, name)):
            return f"/static/{name}"
    return ""

_LOGO_SRC = _resolve_logo_src()


# =========================================================
# 6) SESIÓN / SEGURIDAD
# =========================================================

def _cookie_name() -> str:
    return SESSION_COOKIE_NAME if not IS_PROD else f"__Host-{SESSION_COOKIE_NAME}"

def _unsign_any(token: str, max_age: int) -> bytes | None:
    for s in _signers:
        try:
            return s.unsign(token, max_age=max_age)
        except (BadSignature, SignatureExpired, Exception):
            continue
    return None

def _get_cookie(request: Request) -> str | None:
    return request.cookies.get(_cookie_name())

def _absolute_issued_at(request: Request) -> int | None:
    try:
        return int(request.cookies.get(ISSUED_COOKIE_NAME) or "0") or None
    except Exception:
        return None

def _set_session(resp: Response, email: str, *, request: Request | None = None, sliding_refresh: bool = False):
    token = _signer.sign(email.encode("utf-8")).decode("utf-8")
    name = _cookie_name()
    kwargs = dict(httponly=True, samesite="strict" if IS_PROD else "lax", secure=IS_PROD, path="/")
    if SESSION_PERSISTENT:
        kwargs["max_age"] = SESSION_MAX_IDLE
    resp.set_cookie(name, token, **kwargs)
    if not sliding_refresh:
        issued_at = int(time.time())
        resp.set_cookie(
            ISSUED_COOKIE_NAME, str(issued_at),
            httponly=True, samesite="strict" if IS_PROD else "lax",
            secure=IS_PROD, path="/", max_age=SESSION_MAX_ABSOLUTE
        )

def _clear_session(resp: Response, token_to_revoke: str | None = None):
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/")
    resp.delete_cookie(_cookie_name(), path="/")
    resp.delete_cookie(ISSUED_COOKIE_NAME, path="/")
    if token_to_revoke:
        REVOKED_TOKENS.add(token_to_revoke)

def _get_email_from_cookie(token: str | None) -> str | None:
    if not token or token in REVOKED_TOKENS:
        return None
    raw = _unsign_any(token, max_age=SESSION_MAX_IDLE)
    return raw.decode("utf-8") if raw else None

def current_user_email(request: Request) -> str | None:
    token = _get_cookie(request)
    email = _get_email_from_cookie(token)
    if not email:
        return None
    iat = _absolute_issued_at(request)
    if iat is None:
        return None
    if time.time() - iat > SESSION_MAX_ABSOLUTE:
        return None
    return email

def _make_csrf() -> str:
    return _signer.sign(secrets.token_urlsafe(16).encode()).decode()

def _check_csrf(value: str | None) -> bool:
    if not value:
        return False
    return _unsign_any(value, max_age=600) is not None


# =========================================================
# 7) RATE LIMIT PARA /login
# =========================================================

_login_attempts = defaultdict(list)

def _too_many_attempts(ip: str, window=300, limit=10) -> bool:
    now = time.time()
    L = _login_attempts[ip]
    while L and now - L[0] > window:
        L.pop(0)
    L.append(now)
    return len(L) > limit

def _backoff_seconds(ip: str) -> int:
    excess = max(0, len(_login_attempts[ip]) - 10)
    return min(60, 2 ** excess)

def _hash(email: str) -> str:
    return hashlib.sha256((email + JWT_SECRET[:16]).encode()).hexdigest()[:16]


# =========================================================
# 8) CABECERAS DE SEGURIDAD
# =========================================================

@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    if IS_PROD:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Referrer-Policy"] = "no-referrer"
    nonce = getattr(request.state, "csp_nonce", "")
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        f"style-src 'self' 'nonce-{nonce}'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        "base-uri 'self'; form-action 'self'"
    )
    resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"
    resp.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    resp.headers["X-Download-Options"] = "noopen"
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resp.headers["Cross-Origin-Resource-Policy"] = "same-site"
    resp.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    return resp


# =========================================================
# 9) HTML HELPERS
# =========================================================

def _base_styles(request: Request) -> str:
    small = LOGO_SIZE
    big = LOGO_SIZE_BIG
    nonce = getattr(request.state, "csp_nonce", "")
    return f"""
    <style nonce="{nonce}">
      :root {{
        --bg:{BG}; --card:{CARD}; --ink:{INK}; --muted:{MUTED};
        --primary:{PRIMARY}; --accent:{ACCENT}; --border:{BORDER};
        --logo-radius:{LOGO_RADIUS};
      }}
      *{{box-sizing:border-box}}
      html,body{{height:100%}}
      body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,-apple-system,Segoe UI,Roboto}}
      a{{color:{ACCENT};text-decoration:none;}}
      a:hover{{text-decoration:underline}}
      a[target="_blank"]::after{{content:"\u2197"; margin-left:6px; font-size:90%; opacity:.9}}
      .wrap-center{{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}}
      .wrap{{max-width:1120px;margin:36px auto;padding:0 16px}}
      .card{{background:{CARD};border:1px solid {BORDER};border-radius:{LOGO_RADIUS};box-shadow:0 12px 40px rgba(0,0,0,.30);padding:28px}}
      .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:22px}}
      .tile{{background:{CARD}; border:1px solid {BORDER};border-radius:{LOGO_RADIUS}; padding:20px;box-shadow:0 6px 18px rgba(0,0,0,.25)}}
      .btn{{appearance:none;display:inline-flex;align-items:center;justify-content:center;background:{PRIMARY};color:#07120a;font-weight:800;border:0;border-radius:{LOGO_RADIUS}; padding:12px 20px; min-height:48px;cursor:pointer}}
      .muted{{color:{MUTED}}}
      .header{{display:flex;gap:12px;align-items:center;margin-bottom:12px}}
      .footer{{margin-top:16px;color:{MUTED};font-size:13px;border-top:1px solid {BORDER}; padding-top:12px}}
      .logo-small{{width:{small}px;height:{small}px;object-fit:contain;border-radius:{LOGO_RADIUS}}}
      .logo-big{{width:{big}px;height:{big}px;object-fit:contain;border-radius:{LOGO_RADIUS};display:block;margin:0 auto 16px}}
    </style>
    """

def _logo_img_html(big: bool = False) -> str:
    src = _LOGO_SRC
    cls = "logo-big" if big else "logo-small"
    size = LOGO_SIZE_BIG if big else LOGO_SIZE
    fallback = (
        f"<div class='{cls}' style='width:{size}px;height:{size}px;border-radius:{LOGO_RADIUS};background:{PRIMARY};opacity:.9'></div>"
    )
    if not src:
        return fallback
    return f'<img class="{cls}" src="{src}" alt="logo" onerror="this.outerHTML=`{fallback}`">'


# =========================================================
# 10) RUTAS
# =========================================================

@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    if current_user_email(request):
        return RedirectResponse("/choose")
    return HTMLResponse(
        _base_styles(request) +
        f"""
        <div class="wrap-center">
          <div class="card" style="max-width:720px;width:100%">
            <div class="center">
              {_logo_img_html(big=True)}
              <h1>Biotico — Inicio</h1>
              <p class="muted">Accede con tu correo corporativo <strong>@{ALLOWED_DOMAIN}</strong>.</p>
              <div style="display:flex;gap:16px;justify-content:center;flex-wrap:wrap;margin-top:16px">
                <a class="btn" href="/login">Entrar</a>
              </div>
            </div>
          </div>
        </div>
        """
    )

@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")

@app.get("/robots.txt")
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /", media_type="text/plain")

@app.get("/favicon.ico")
def favicon():
    for name in ("favicon.ico", "favicon.png"):
        if os.path.exists(os.path.join(static_dir, name)):
            return RedirectResponse(url=f"/static/{name}")
    return Response(status_code=204)

@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    csrf = _make_csrf()
    html = _base_styles(request) + f"""
        <div class="wrap-center">
          <div class="card" style="max-width:720px;width:100%">
            <div class="header" style="justify-content:center">
              {_logo_img_html()} <h2>Iniciar sesión</h2>
            </div>
            <form method="post" style="display:flex;flex-direction:column;gap:12px">
              <div style="width:100%">
                <label for="email">Correo corporativo</label>
                <input id="email" name="email" type="email" required placeholder="tu@{ALLOWED_DOMAIN}">
              </div>
              <input type="hidden" name="csrf" value="{csrf}">
              <div><button class="btn" type="submit">Entrar</button></div>
            </form>
            <p class="muted" style="margin-top:12px">Por ahora solo validamos el dominio; el inicio de sesión corporativo (OIDC) llegará después.</p>
          </div>
        </div>
    """
    resp = HTMLResponse(html)
    resp.set_cookie(CSRF_COOKIE, csrf, max_age=600, samesite="lax", secure=IS_PROD, path="/")
    return resp

@app.post("/login")
def login_post(request: Request, email: str = Form(...), csrf: str = Form(None)):
    ip = request.client.host if request and request.client else "unknown"
    if _too_many_attempts(ip):
        wait = _backoff_seconds(ip)
        html = _base_styles(request) + f"<div class='wrap-center'><div class='card center'><h3>Demasiados intentos. Espera {wait}s.</h3></div></div>"
        return HTMLResponse(html, status_code=429, headers={"Retry-After": str(wait)})

    if not _check_csrf(csrf):
        return HTMLResponse(_base_styles(request) + "<div class='wrap-center'><div class='card center'><h3>CSRF inválido</h3></div></div>", status_code=400)

    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        return HTMLResponse(
            _base_styles(request) +
            f"""
            <div class="wrap-center">
              <div class="card center" style="max-width:520px">
                <h3>Solo correos @{ALLOWED_DOMAIN}</h3>
                <div style="margin-top:12px"><a class="btn" href="/login">Volver</a></div>
              </div>
            </div>
            """,
            status_code=403
        )

    resp = RedirectResponse("/choose", status_code=302)
    _set_session(resp, email, sliding_refresh=False)
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp

@app.get("/_docs", response_class=HTMLResponse)
def private_docs(request: Request):
    if not current_user_email(request):
        return RedirectResponse("/login")
    return get_swagger_ui_html(openapi_url="/_openapi.json", title="Docs privadas")

@app.get("/_openapi.json")
def private_openapi(request: Request):
    if not current_user_email(request):
        return RedirectResponse("/login")
    return app.openapi()

@app.get("/choose", response_class=HTMLResponse)
def choose(request: Request):
    email = current_user_email(request)
    if not email:
        return RedirectResponse("/login")

    # Tarjeta Reconciliador → por gate
    card_reconciliar = f"""
      <div class="tile">
        <h3>Reconciliar un nombre</h3>
        <p class="muted">Interfaz para usuarios (UI del reconciliador).</p>
        <div style="margin-top:12px">
          <a class="btn" href="/gate/reconciliador?dest=/ui/buscador">Abrir</a>
        </div>
      </div>
    """

    # Tarjeta Consulta Avanzada de la Base de Datos Biótica → por gate
    card_buscador = f"""
      <div class="tile">
        <h3>Consulta Avanzada de la Base de Datos Biótica</h3>
        <p class="muted">Búsqueda avanzada sobre la base de datos Biótica (protegida por el Hub).</p>
        <div style="margin-top:12px">
          <a class="btn" href="/gate/buscador?dest=/">Abrir Consulta Avanzada</a>
        </div>
      </div>
    """

    # Docs (por gate, nueva pestaña)
    card_docs = f"""
      <div class="tile">
        <h3>Ver detalles</h3>
        <p class="muted">Documentación de la API (Swagger UI).</p>
        <div style="margin-top:12px">
          <a class="btn" href="/gate/reconciliador?dest=/docs" target="_blank">Abrir docs</a>
        </div>
      </div>
    """

    return HTMLResponse(
        _base_styles(request) +
        f"""
        <div class="wrap">
          <div class="header">
            {_logo_img_html()}
            <h2 style="margin:0">{APP_NAME}</h2>
          </div>
          <div class="grid">
            {card_reconciliar}
            {card_buscador}
            {card_docs}
            <div class="tile" style="opacity:.6; cursor:not-allowed">
              <h3>Reconciliar por archivo (lote)</h3>
              <p class="muted">Próximamente · En desarrollo</p>
              <span class="pill">Roadmap</span>
            </div>
            <div class="tile" style="opacity:.6; cursor:not-allowed">
              <h3>Diagnóstico de conectores</h3>
              <p class="muted">Próximamente · En desarrollo</p>
              <span class="pill">Roadmap</span>
            </div>
          </div>
          <div class="footer">
            Sesión: {email} · <a href="/logout">Cerrar sesión</a>
          </div>
        </div>
        """
    )

@app.get("/logout")
def logout(request: Request):
    token = _get_cookie(request)
    resp = RedirectResponse("/login")
    _clear_session(resp, token_to_revoke=token)
    resp.headers["Clear-Site-Data"] = '"cache","cookies","storage"'
    return resp


# =========================================================
# 11) GATE SSO → firma y redirige a servicios con ?st=...
# =========================================================

def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

def _sign_payload(payload_b64: str, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), digestmod="sha256").digest()
    return _b64url(sig)

@app.get("/gate/{rid}")
def gate_sso(request: Request, rid: str, dest: str = "/"):
    email = current_user_email(request)
    if not email:
        return RedirectResponse("/login")

    services = {
        "reconciliador": {"aud": "reconciliador", "base": RECONCILIADOR_BASE},
        "buscador":      {"aud": "buscador",      "base": BUSCADOR_BASE},
    }
    svc = services.get(rid)
    if not svc:
        raise HTTPException(status_code=404, detail="Tool not found")

    now = int(time.time())
    payload = {
        "sub": email,          # correo del usuario
        "aud": svc["aud"],
        "iat": now,
        "exp": now + 300,      # 5 min
        "rid": rid,
        "iss": HUB_ISS,
    }
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig_b64 = _sign_payload(payload_b64, GATEWAY_SHARED_SECRET)
    st = f"{payload_b64}.{sig_b64}"

    joiner = "&" if "?" in dest else "?"
    return RedirectResponse(f"{svc['base']}{dest}{joiner}st={st}", status_code=302)


