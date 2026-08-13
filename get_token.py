import os
from google_auth_oauthlib.flow import Flow

# Localhost callback is used only for this interactive OAuth flow.
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
CLIENT_FILE = "client_secret.json"
TOKEN_FILE = "token.json"

flow = Flow.from_client_secrets_file(
    CLIENT_FILE,
    scopes=SCOPES,
    redirect_uri="http://localhost",
)

auth_url, state = flow.authorization_url(
    access_type="offline",
    prompt="consent",
    include_granted_scopes="true",
)

print("\nافتح الرابط التالي في المتصفح وسجّل الدخول ووافق على YouTube:\n")
print(auth_url)
print("\nبعد الموافقة سيظهر عنوان يبدأ بـ http://localhost/?code=...")
print("انسخ عنوان الصفحة كاملًا والصقه هنا ثم اضغط Enter.\n")

redirect_response = input("Redirect URL: ").strip()

if not redirect_response.startswith("http://localhost/"):
    raise ValueError("يجب لصق رابط localhost الكامل الذي أعادته Google.")

# fetch_token validates the OAuth state and exchanges the authorization code.
flow.fetch_token(authorization_response=redirect_response)

with open(TOKEN_FILE, "w", encoding="utf-8") as f:
    f.write(flow.credentials.to_json())

if not os.path.isfile(TOKEN_FILE):
    raise RuntimeError("فشل إنشاء token.json")

print("\nتم إنشاء token.json بنجاح.")
