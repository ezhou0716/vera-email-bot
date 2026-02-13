import os
import sys
import json
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
CONFIG_FILE = "email_config.json"


def authenticate():
    """Authenticate with Gmail API using OAuth2.

    On first run, opens a browser for Google consent.
    On subsequent runs, uses the saved token.
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
                print(f"Error: '{CREDENTIALS_FILE}' not found.")
                print("Download your OAuth2 credentials from Google Cloud Console.")
                print("See README.md for instructions.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def load_config():
    """Load email configuration from email_config.json."""
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: '{CONFIG_FILE}' not found.")
        print("Create it with to, cc, bcc, subject, and body fields.")
        print("See README.md for the expected format.")
        sys.exit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    required_fields = ["to", "subject", "body"]
    for field in required_fields:
        if field not in config or not config[field].strip():
            print(f"Error: '{field}' is required and cannot be empty in {CONFIG_FILE}.")
            sys.exit(1)

    return config


def create_message(config):
    """Create an encoded email message from the config.

    Returns a dict with 'raw' key containing the base64url-encoded message.
    """
    message = EmailMessage()
    message.set_content(config["body"])
    message["To"] = config["to"]
    message["Subject"] = config["subject"]

    if config.get("cc", "").strip():
        message["Cc"] = config["cc"]

    if config.get("bcc", "").strip():
        message["Bcc"] = config["bcc"]

    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"raw": encoded}


def send_email(service, message):
    """Send the email via Gmail API."""
    try:
        result = service.users().messages().send(
            userId="me",
            body=message
        ).execute()
        print(f"Email sent successfully! Message ID: {result['id']}")
        return result
    except HttpError as error:
        print(f"Failed to send email: {error}")
        sys.exit(1)


def main():
    print("Loading email configuration...")
    config = load_config()

    print(f"Sending email to: {config['to']}")
    if config.get("cc", "").strip():
        print(f"  CC: {config['cc']}")
    if config.get("bcc", "").strip():
        print(f"  BCC: {config['bcc']}")
    print(f"  Subject: {config['subject']}")

    print("Authenticating with Gmail API...")
    service = authenticate()

    print("Composing message...")
    message = create_message(config)

    print("Sending...")
    send_email(service, message)


if __name__ == "__main__":
    main()
