import os
import json
import base64
import requests
from flask import Flask, redirect, url_for, session, render_template, request

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "authshield-ultra-secure-key-999")

# Network endpoints
KC_INTERNAL = os.getenv("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080")
KC_BROWSER = os.getenv("KEYCLOAK_BROWSER_URL", "http://localhost:8080")
REALM = os.getenv("REALM_NAME", "authshield")
CLIENT_ID = os.getenv("CLIENT_ID", "school-portal")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "OPZkebb4uIXsrXK9dMudFXRLW6psuowD")

def parse_jwt_payload(token_str):
    """Safely decodes JWT payload without external dependencies."""
    try:
        parts = token_str.split(".")
        if len(parts) >= 2:
            payload = parts[1]
            padded = payload + "=" * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(padded)
            return json.loads(decoded)
    except Exception as e:
        app.logger.error(f"Error parsing token: {e}")
    return {}

@app.route("/")
def home():
    user = session.get("user")
    return render_template("index.html", user=user)

@app.route("/login")
def login():
    redirect_uri = url_for("auth_callback", _external=True)
    # prompt=login ensures Keycloak presents credential fields even if a session lingered
    auth_url = (
        f"{KC_BROWSER}/realms/{REALM}/protocol/openid-connect/auth"
        f"?client_id={CLIENT_ID}&response_type=code&scope=openid%20profile%20email%20roles"
        f"&redirect_uri={redirect_uri}&prompt=login"
    )
    return redirect(auth_url)

@app.route("/callback")
def auth_callback():
    code = request.args.get("code")
    if not code:
        return "Authentication error: Missing authorization code", 400

    redirect_uri = url_for("auth_callback", _external=True)
    token_url = f"{KC_INTERNAL}/realms/{REALM}/protocol/openid-connect/token"
    
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    
    res = requests.post(token_url, data=data, auth=(CLIENT_ID, CLIENT_SECRET))
    if res.status_code != 200:
        return f"Token exchange failed: {res.text}", res.status_code

    token_data = res.json()
    access_token = token_data.get("access_token")
    id_token = token_data.get("id_token")

    # Decode claims directly from the cryptographically verified JWT payload
    parsed_claims = parse_jwt_payload(access_token)
    if not parsed_claims and id_token:
        parsed_claims = parse_jwt_payload(id_token)

    # Save user details and token for OIDC end-session logout
    session["user"] = parsed_claims
    session["id_token"] = id_token
    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    id_token = session.get("id_token")
    session.clear()
    
    post_logout = url_for("home", _external=True)
    # Terminate the IdP session at Keycloak so another user can sign in
    if id_token:
        keycloak_logout = (
            f"{KC_BROWSER}/realms/{REALM}/protocol/openid-connect/logout"
            f"?id_token_hint={id_token}&post_logout_redirect_uri={post_logout}"
        )
    else:
        keycloak_logout = (
            f"{KC_BROWSER}/realms/{REALM}/protocol/openid-connect/logout"
            f"?client_id={CLIENT_ID}&post_logout_redirect_uri={post_logout}"
        )
    return redirect(keycloak_logout)

@app.route("/records")
def records():
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))
    return render_template("records.html", user=user)

@app.route("/grades")
def grades():
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))
    roles = user.get("resource_access", {}).get("school-portal", {}).get("roles", [])
    if "Teacher" not in roles and "Administrator" not in roles:
        return "403 Forbidden: Teacher or Administrator role required", 403
    return render_template("grades.html", user=user)

@app.route("/admin-console")
def admin_console():
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))
    roles = user.get("resource_access", {}).get("school-portal", {}).get("roles", [])
    if "Administrator" not in roles:
        return "403 Forbidden: Administrator role required", 403
    return render_template("admin.html", user=user)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
