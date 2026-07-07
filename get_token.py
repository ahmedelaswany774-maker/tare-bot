from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
credentials = flow.run_local_server(port=8080, open_browser=False)

with open("token.json", "w") as f:
    f.write(credentials.to_json())

print("تم! token.json اتعمل بنجاح")

