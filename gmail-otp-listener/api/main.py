import base64
import json
import os
from email import policy
from email.parser import BytesParser

from bs4 import BeautifulSoup
from fastapi import FastAPI, Header, Request
from google.auth.transport.requests import Request as RefreshRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pydantic import BaseModel

from api.config import settings

app = FastAPI()

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class PubSubMessage(BaseModel):
    message: dict
    subscription: str


def get_credentials():
    creds = None

    if os.path.exists(settings.TOKEN_FILE):
        with open(settings.TOKEN_FILE) as f:
            creds_data = json.load(f)
            print("✅ Token file found.")
        try:
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
            print("✅ Credentials loaded from token file.")
        except ValueError:
            print("⚠️ Refresh token missing, need to re-authenticate")
            creds = None

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            settings.CLIENT_SECRET_FILE, SCOPES, redirect_uri=settings.REDIRECT_URI
        )
        print("✅ Flow created.")
        # Request offline access to get a refresh token
        creds = flow.run_local_server(port=settings.PORT, access_type="offline", prompt="consent")
        print("✅ Credentials created.")
        # Save the credentials
        with open(settings.TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())
        print("✅ New token created with refresh token.")

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(RefreshRequest())
        print("✅ Credentials refreshed.")
        with open(settings.TOKEN_FILE, "w") as token_file:
            print("✅ Token file updated.")
            token_file.write(creds.to_json())
        print("🔄 Access token refreshed.")

    return creds


def extract_email_body(msg):
    try:
        if msg.is_multipart():
            parts = []
            for part in msg.walk():
                content_type = part.get_content_type()
                if part.get_content_disposition() != "attachment":
                    if content_type == "text/plain":
                        parts.append(part.get_payload(decode=True).decode(errors="ignore"))
                    elif content_type == "text/html":
                        html = part.get_payload(decode=True).decode(errors="ignore")
                        soup = BeautifulSoup(html, "html.parser")
                        parts.append(soup.get_text())
            return "\n---\n".join(parts).strip()
        else:
            return msg.get_payload(decode=True).decode(errors="ignore")
    except Exception as e:
        print("⚠️ Failed to extract body:", e)
        return ""


def fetch_latest_email():
    print("📭 Fallback: Fetching latest email manually.")

    try:
        creds = get_credentials()
        gmail_service = build("gmail", "v1", credentials=creds)

        results = (
            gmail_service.users()
            .messages()
            .list(userId="me", labelIds=["INBOX"], maxResults=1)
            .execute()
        )

        messages = results.get("messages", [])
        print(f"📨 Messages found in inbox: {len(messages)}")

        if not messages:
            print("📭 No messages found.")
            return

        msg_id = messages[0]["id"]
        print(f"🔍 Fetching message ID: {msg_id}")

        full_msg = (
            gmail_service.users().messages().get(userId="me", id=msg_id, format="raw").execute()
        )

        raw_msg = base64.urlsafe_b64decode(full_msg["raw"].encode("ASCII"))
        parsed_email = BytesParser(policy=policy.default).parsebytes(raw_msg)

        from_header = parsed_email["From"]
        subject = parsed_email["Subject"]
        body = extract_email_body(parsed_email)

        print(f"\n📨 From: {from_header}\n📌 Subject: {subject}\n📝 Body:\n{body}\n")

    except Exception as e:
        print("❌ Error while fetching latest email:", e)


@app.post("/authenticate-user", response_model=None)
def authenticate_user():
    try:
        creds = get_credentials()

        if creds and creds.valid:
            return {"status": "Authenticated", "token_expiry": creds.expiry.isoformat()}
        else:
            return {"status": "Failed to authenticate"}

    except Exception as e:
        return {"error": str(e)}


@app.get("/oauth2callback", response_model=None)
def oauth2callback(request: Request):
    code = request.query_params.get("code")
    return {"status": "Received code", "code": code}


@app.post("/setup-watch")
def setup_gmail_watch():
    try:
        creds = get_credentials()
        service = build("gmail", "v1", credentials=creds)

        request_body = {
            "labelIds": ["INBOX"],
            "topicName": settings.GMAIL_TOPIC_NAME,
        }

        response = service.users().watch(userId="me", body=request_body).execute()

    except Exception as e:
        return {"error": str(e)}
    return {"status": "Watch set", "response": response}


@app.post("/gmail-webhook")
async def gmail_webhook(request: Request, x_cloud_trace_context: str = Header(None)):
    try:
        body = await request.json()
        print("📥 Webhook triggered. Raw body:", body)

        pubsub_message = PubSubMessage(**body)
        print("✅ PubSubMessage parsed")

        # Decode base64
        decoded_data = base64.b64decode(pubsub_message.message["data"]).decode("utf-8")
        print("🔍 Decoded data:", decoded_data)

        message_json = json.loads(decoded_data)
        history_id = message_json.get("historyId")
        email_address = message_json.get("emailAddress")

        print("📨 historyId:", history_id)
        print("📧 emailAddress:", email_address)

        if history_id:
            fetch_latest_email()
        else:
            print("⚠️ No historyId found in message")

    except Exception as e:
        print("❌ Error in webhook:", e)
        return {"error": str(e)}
    return {"status": "received"}
