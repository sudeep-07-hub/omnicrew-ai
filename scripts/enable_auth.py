import google.auth
from google.auth.transport.requests import AuthorizedSession
import json

credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
authed_session = AuthorizedSession(credentials)

url = 'https://identitytoolkit.googleapis.com/admin/v2/projects/omnicrew-ai-2026/config?updateMask=signIn.email.enabled,signIn.email.passwordRequired'
payload = {
    "signIn": {
        "email": {
            "enabled": True,
            "passwordRequired": True
        }
    }
}

response = authed_session.patch(url, json=payload)
print(response.status_code)
print(response.text)
