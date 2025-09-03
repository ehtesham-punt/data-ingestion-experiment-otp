import base64
import json
import os
import re
from datetime import datetime, timedelta
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime

import httpx
import restate
from bs4 import BeautifulSoup
from fastapi import FastAPI, Header, Request
from google.auth.transport.requests import Request as RefreshRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pydantic import BaseModel

# from restate import client as restate_client
from api.config import settings
from api.login_workflow import login_wf

restate_app = restate.app(
    services=[
        login_wf,
    ],
    # we need hypercorn to run this
    protocol="bidi",
)


app = FastAPI()
app.mount("/restate", restate_app)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class PubSubMessage(BaseModel):
    message: dict
    subscription: str


class ParsedEmail(BaseModel):
    from_email: str
    to_email: str
    otp: str | None = None
    platform: str | None = None


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
            print("⚠️ Failed to load credentials from file.")
            creds = None

    # 🔄 Refresh token if available and token is expired
    if creds and creds.expired and creds.refresh_token:
        print("🔄 Token expired, refreshing...")
        creds.refresh(RefreshRequest())
        with open(settings.TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())
        print("✅ Token refreshed and saved.")
        return creds

    # ❌ If no creds or no refresh_token, re-authenticate
    if not creds or not creds.valid:
        print("⚠️ No valid credentials, initiating flow...")
        flow = InstalledAppFlow.from_client_secrets_file(
            settings.CLIENT_SECRET_FILE, SCOPES, redirect_uri=settings.REDIRECT_URI
        )
        creds = flow.run_local_server(port=settings.PORT, access_type="offline", prompt="consent")
        print("✅ New token obtained.")
        with open(settings.TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())
        return creds

    return creds


def parse_email(raw_email: bytes) -> ParsedEmail | None:
    """Parse email and extract OTP using BeautifulSoup + regex."""
    msg = BytesParser(policy=policy.default).parsebytes(raw_email)

    # Check email freshness
    date_header = msg["Date"]
    email_datetime = parsedate_to_datetime(date_header)
    if datetime.now(email_datetime.tzinfo) - email_datetime > timedelta(minutes=5):
        return None

    # Extract body (prefer HTML)
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                body = part.get_content()
                break
    else:
        if msg.get_content_type() == "text/html":
            body = msg.get_content()

    soup = BeautifulSoup(body, "html.parser")
    text = soup.get_text()

    # === STEP 1: Try extracting From/To from body first if it is an textual forward ===
    from_match = re.search(r"From:\s.*<(\S+@\S+)>", text)
    to_match = re.search(r"To:\s.*<(\S+@\S+)>", text)
    real_from = from_match.group(1) if from_match else None
    real_to = to_match.group(1) if to_match else None

    # === STEP 2: If missing, fall back to headers ===
    if not real_from:
        email_from_header = msg.get_all("From", [])
        parsed_from = getaddresses(email_from_header)
        real_from = parsed_from[0][1] if parsed_from else None

    if not real_to:
        email_to_header = msg.get_all("To", [])
        parsed_to = getaddresses(email_to_header)
        real_to = parsed_to[0][1] if parsed_to else None

    # Extract OTP (4-digit number)
    match = re.search(r"Your otp code is (\d{4})", text, re.IGNORECASE)
    otp = match.group(1) if match else None

    platform = "zepto"

    return ParsedEmail(from_email=real_from, to_email=real_to, otp=otp, platform=platform)


def fetch_latest_email() -> ParsedEmail | None:
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
            return None

        msg_id = messages[0]["id"]
        print(f"🔍 Fetching message ID: {msg_id}")

        full_msg = (
            gmail_service.users().messages().get(userId="me", id=msg_id, format="raw").execute()
        )

        raw_msg = base64.urlsafe_b64decode(full_msg["raw"].encode("ASCII"))
        parsed_result = parse_email(raw_msg)
        if parsed_result is None:
            print("📭 Email is older than 5 minutes or not from a valid platform.")
            return None
        print("📨 Parsed Email:", parsed_result.dict())
        return parsed_result

    except Exception as e:
        print("❌ Error while fetching latest email:", e)
        return None


async def signal_workflow_with_otp(platform: str, username: str, otp: str):
    """Signal the workflow with the received OTP"""
    key = f"{platform}_{username}"
    print("🔑 Key:", key)

    print("✅ Signaling workflow with OTP...")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://localhost:8080/login_workflow/{key}/receive_otp",
            json={"otp": otp},
            headers={"Content-Type": "application/json"},
        )
        print("✅ Workflow signaled with OTP.")
        return response


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
            "labelIds": ["UNREAD"],
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
        decoded_data = base64.b64decode(pubsub_message.message["data"]).decode("utf-8")
        message_json = json.loads(decoded_data)

        history_id = message_json.get("historyId")
        email_address = message_json.get("emailAddress")

        print("📨 historyId:", history_id)
        print("📧 emailAddress:", email_address)

        if not history_id:
            return {"status": "no-history-id"}

        creds = get_credentials()
        gmail_service = build("gmail", "v1", credentials=creds)

        # Load last known history ID from file
        last_id_file = "last_history_id.txt"
        if not os.path.exists(last_id_file):
            with open(last_id_file, "w") as f:
                f.write(str(history_id))
            print("🔐 First-time setup, saving initial history ID.")
            return {"status": "initialized-history"}

        with open(last_id_file) as f:
            last_history_id = f.read().strip()

        # 🚫 Skip if incoming historyId is older or same
        if int(history_id) <= int(last_history_id):
            print(
                f"⏭️ Incoming historyId ({history_id}) is not newer than last saved ({last_history_id}) — skipping."
            )
            return {"status": "stale-history-id"}

        print("🔄 Checking Gmail history from", last_history_id, "to", history_id)

        # Fetch messageAdded events
        history_response = (
            gmail_service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=last_history_id,
                historyTypes=["messageAdded"],
            )
            .execute()
        )

        with open(last_id_file, "w") as f:
            f.write(str(history_id))  # 🔄 Always update history

        messages_added = []
        for h in history_response.get("history", []):
            messages_added.extend(h.get("messagesAdded", []))

        if not messages_added:
            print("⏩ No new messages added — skipping.")
            return {"status": "no_new_email"}

        print("✅ New message detected — fetching latest inbox message")
        parsed_email = fetch_latest_email()
        if parsed_email and parsed_email.otp:
            username = parsed_email.to_email.split("@")[0]
            print("✅ Parsed email has OTP. Signaling workflow...")
            await signal_workflow_with_otp(
                platform=parsed_email.platform, username=username, otp=parsed_email.otp
            )
        else:
            print("⚠️ Parsed email had no OTP or was not recent.")

    except Exception as e:
        print("❌ Error in webhook:", e)
        return {"error": str(e)}

    return {"status": "received"}
