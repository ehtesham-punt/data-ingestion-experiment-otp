from fastapi import FastAPI
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
# from google.auth.transport.requests import Request
from fastapi import FastAPI, Request
from googleapiclient.discovery import build
from email import policy
from email.parser import BytesParser
from bs4 import BeautifulSoup
import base64
import json
import os
import re

app = FastAPI()

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CLIENT_SECRET_FILE = 'client_secret.json'
TOKEN_FILE = 'token.json'

def get_credentials():
    creds = None

    # If token file exists, load it
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            creds_data = json.load(f)
        try:
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
        except ValueError:
            # If refresh_token is missing, force re-auth
            print("⚠️ Refresh token missing, need to re-authenticate")
            creds = None

    # If no valid credentials, do first-time login
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRET_FILE,
            SCOPES,
            redirect_uri="http://localhost:8001/oauth2callback"
        )
        # Request offline access to get a refresh token
        creds = flow.run_local_server(port=8001, access_type='offline', prompt='consent')
        # Save the credentials
        with open(TOKEN_FILE, 'w') as token_file:
            token_file.write(creds.to_json())
        print("✅ New token created with refresh token.")

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, 'w') as token_file:
            token_file.write(creds.to_json())
        print("🔄 Access token refreshed.")

    return creds



def fetch_latest_email_raw():
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)

    # Get latest email from inbox
    results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()
    messages = results.get('messages', [])
    if not messages:
        return None

    msg_id = messages[0]['id']
    msg = service.users().messages().get(userId='me', id=msg_id, format='raw').execute()

    raw_data = base64.urlsafe_b64decode(msg['raw'])
    return raw_data

def parse_email_and_extract_otp(raw_bytes: bytes) -> str | None:
    msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain':
                body += part.get_payload(decode=True).decode(errors='ignore')
            elif content_type == 'text/html':
                html = part.get_payload(decode=True).decode(errors='ignore')
                body += BeautifulSoup(html, "html.parser").get_text()
    else:
        body = msg.get_payload(decode=True).decode(errors='ignore')

    # Find 6-digit OTP
    match = re.search(r'\b\d{6}\b', body)
    return match.group(0) if match else None

@app.post("/get-otp", response_model=None)
def get_otp():
    try:
        raw_email = fetch_latest_email_raw()
        if not raw_email:
            return {"status": "No email found"}

        otp = parse_email_and_extract_otp(raw_email)
        if otp:
            return {"otp": otp}
        return {"status": "OTP not found in latest email"}

    except Exception as e:
        return {"error": str(e)}

@app.get("/oauth2callback", response_model=None)
def oauth2callback(request: Request):
    # Here you can capture the "code" from query params
    code = request.query_params.get("code")
    return {"status": "Received code", "code": code}
