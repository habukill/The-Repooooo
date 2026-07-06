"""
Run this script to get a new OAuth token.
It will print an auth URL. Open it in browser, approve, then paste the redirect URL back here.
"""
import json, urllib.parse, urllib.request, sys

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
REDIRECT_URI = "http://localhost"

SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
]

with open(CREDENTIALS_FILE) as f:
    creds_data = json.load(f)["installed"]

client_id = creds_data["client_id"]
client_secret = creds_data["client_secret"]

# Build auth URL
params = {
    "client_id": client_id,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": " ".join(SCOPES),
    "access_type": "offline",
    "prompt": "consent",
}
auth_url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)

print("\n=== STEP 1: Open this URL in your browser ===")
print(auth_url)
print("\n=== STEP 2: After approving, paste the FULL redirect URL here ===")
print("(The URL will start with http://localhost/?code=...)")

redirect_url = input("\nPaste URL: ").strip()

# Extract code
parsed = urllib.parse.urlparse(redirect_url)
qs = urllib.parse.parse_qs(parsed.query)
code = qs.get("code", [None])[0]

if not code:
    print("ERROR: Could not find code in URL")
    sys.exit(1)

print(f"\nExchanging code for token...")

data = urllib.parse.urlencode({
    "code": code,
    "client_id": client_id,
    "client_secret": client_secret,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code",
}).encode()

req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
req.add_header("Content-Type", "application/x-www-form-urlencoded")

with urllib.request.urlopen(req) as resp:
    token = json.loads(resp.read())

# Format as google-auth compatible token file
token_data = {
    "token": token["access_token"],
    "refresh_token": token.get("refresh_token"),
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": client_id,
    "client_secret": client_secret,
    "scopes": SCOPES,
}

with open(TOKEN_FILE, "w") as f:
    json.dump(token_data, f, indent=2)

print(f"\n✓ Token saved to {TOKEN_FILE}")
print("\n=== token.json content (copy for GitHub Secret) ===")
print(json.dumps(token_data, indent=2))
