from google_auth_oauthlib.flow import Flow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_FILE = "client_secret.json"
TOKEN_FILE = "token.json"

flow = Flow.from_client_secrets_file(
    CLIENT_FILE,
    scopes=SCOPES,
    redirect_uri="http://localhost"
)

auth_url, state = flow.authorization_url(
    access_type="offline",
    prompt="consent",
    include_granted_scopes="true"
)

print("\nافتح الرابط التالي في المتصفح وسجّل الدخول ووافق على YouTube Upload:\n")
print(auth_url)
print("\nبعد الموافقة سيظهر لك عنوان يبدأ بـ http://localhost/?code=...")
print("انسخ عنوان الصفحة كاملًا والصقه هنا ثم اضغط Enter. لا ترسله في المحادثة.\n")
redirect_response = input("Redirect URL: ").strip()

flow.fetch_token(authorization_response=redirect_response)

with open(TOKEN_FILE, "w", encoding="utf-8") as f:
    f.write(flow.credentials.to_json())

print("\nتم إنشاء token.json بنجاح.")
