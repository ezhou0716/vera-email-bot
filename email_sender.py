import os
import base64
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def authenticate_gmail():
    """Authenticate with Gmail API using OAuth2.

    Reuses the same credentials.json and token.json as send_email.py.
    Returns a Gmail API service object.
    """
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"'{CREDENTIALS_FILE}' not found. "
                    "Download your OAuth2 credentials from Google Cloud Console. "
                    "See README.md for instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def create_message(email_data):
    """Create an encoded email message from a dict.

    Args:
        email_data: dict with keys 'to', 'subject', 'body'

    Returns:
        dict with 'raw' key containing the base64url-encoded message
    """
    message = EmailMessage()
    message.set_content(email_data["body"])
    message["To"] = email_data["to"]
    message["Subject"] = email_data["subject"]

    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"raw": encoded}


def send_single_email(service, message, recipient):
    """Send a single email via Gmail API.

    Returns True on success, False on failure. Does not exit the process,
    allowing batch sending to continue even if one email fails.
    """
    try:
        result = service.users().messages().send(
            userId="me",
            body=message
        ).execute()
        print(f"  Sent to {recipient} (Message ID: {result['id']})")
        return True
    except HttpError as error:
        print(f"  Failed to send to {recipient}: {error}")
        return False
