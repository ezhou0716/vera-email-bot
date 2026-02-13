# Vera Email Bot

A Python bot that sends emails through Gmail using the Google Gmail API and OAuth2 authentication. Includes an **AI-powered outreach mode** that automatically discovers leads, generates personalized emails, and sends them — all from a single natural language prompt.

## AI-Powered Outreach Mode

Give Vera a plain English prompt and it handles the rest:

```bash
python vera.py "Find CTOs at AI startups and pitch our analytics tool"
```

**What happens:**
1. **Gemini AI** parses your prompt into structured search criteria and email intent
2. **Hunter.io** (+ optional Google Custom Search) discovers relevant leads
3. **Gemini AI** generates a personalized email for each lead
4. You **review** all emails before anything is sent
5. **Gmail API** sends the approved emails with rate limiting

See [AI Outreach Setup](#7-ai-outreach-setup) below for configuration.

## Prerequisites

- Python 3.10 or later
- A Google account (Gmail)
- A Google Cloud project (free to create)

**Additional prerequisites for AI outreach mode:**
- A [Google Gemini API key](https://ai.google.dev/) (free tier available)
- A [Hunter.io API key](https://hunter.io/) (free tier: 25 searches/month)
- (Optional) A [Google Custom Search API key + Engine ID](https://developers.google.com/custom-search/v1/introduction) for fallback lead discovery

## 1. Google Cloud Setup

Follow these steps to enable the Gmail API and create credentials.

### 1.1 Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** at the top of the page, then click **New Project**
3. Name it something like `vera-email-bot` and click **Create**
4. Make sure the new project is selected in the project dropdown

### 1.2 Enable the Gmail API

1. In the Cloud Console sidebar, go to **APIs & Services** > **Library**
2. Search for **Gmail API**
3. Click on **Gmail API** in the results
4. Click **Enable**

### 1.3 Configure the OAuth Consent Screen

1. Go to **APIs & Services** > **OAuth consent screen**
2. Select **External** as the user type and click **Create**
3. Fill in the required fields:
   - **App name**: `vera-email-bot` (or any name)
   - **User support email**: your email address
   - **Developer contact email**: your email address
4. Click **Save and Continue**
5. On the **Scopes** page, click **Add or Remove Scopes**
   - Search for `https://www.googleapis.com/auth/gmail.send`
   - Check the box next to it and click **Update**
   - Click **Save and Continue**
6. On the **Test users** page, click **Add Users**
   - Enter the Gmail address you will use to send emails
   - Click **Add**, then **Save and Continue**
7. Click **Back to Dashboard**

> **Note:** While your app is in "Testing" mode, only the test users you added can authenticate. This is fine for personal use. You do not need to publish the app.

### 1.4 Create OAuth2 Credentials

1. Go to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth client ID**
3. For **Application type**, select **Desktop app**
4. Name it `vera-email-bot-desktop` (or any name)
5. Click **Create**
6. On the confirmation dialog, click **Download JSON**
7. Rename the downloaded file to `credentials.json`
8. Move `credentials.json` into the project root directory (same folder as `send_email.py`)

## 2. Installation

It's recommended to use a virtual environment:

```bash
# Create a virtual environment
python -m venv venv

# Activate it (Windows)
venv\Scripts\activate

# Activate it (macOS/Linux)
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## 3. Configuration

Open `email_config.json` in any text editor and fill in your email details:

```json
{
  "to": "recipient@example.com",
  "cc": "",
  "bcc": "",
  "subject": "Hello from Vera Email Bot",
  "body": "This is a test email sent via the Gmail API."
}
```

### Field reference

| Field | Required | Description |
|-------|----------|-------------|
| `to` | Yes | Recipient email address(es). Comma-separated for multiple: `"a@example.com, b@example.com"` |
| `cc` | No | CC recipients. Leave as `""` to skip. Comma-separated for multiple. |
| `bcc` | No | BCC recipients. Leave as `""` to skip. Comma-separated for multiple. |
| `subject` | Yes | The email subject line. |
| `body` | Yes | Plain text email body. Use `\n` for newlines. |

### Example with all fields

```json
{
  "to": "alice@example.com, bob@example.com",
  "cc": "manager@example.com",
  "bcc": "archive@example.com",
  "subject": "Weekly Status Update",
  "body": "Hi team,\n\nHere is the weekly status update.\n\nBest regards,\nVera Bot"
}
```

## 4. Running the Bot

```bash
python send_email.py
```

### First run

A browser window will open asking you to:
1. Sign in to your Google account
2. Grant the bot permission to send emails on your behalf

After you approve, a `token.json` file is created in the project directory. This stores your authentication token so you don't have to approve again.

### Subsequent runs

The saved token is reused automatically. No browser interaction is needed unless the token expires and cannot be refreshed (rare).

### Expected output

```
Loading email configuration...
Sending email to: recipient@example.com
  Subject: Hello from Vera Email Bot
Authenticating with Gmail API...
Composing message...
Sending...
Email sent successfully! Message ID: 18d1234abcd5678
```

## 5. Security Notes

- **Never commit `credentials.json` or `token.json`** to version control. The included `.gitignore` already excludes them.
- The bot only requests the `gmail.send` permission. It **cannot** read, list, or modify your existing emails.
- To revoke the bot's access to your Gmail account:
  - Delete `token.json` from the project directory, **or**
  - Go to [Google Account Permissions](https://myaccount.google.com/permissions) and remove `vera-email-bot`

## 6. Troubleshooting

| Error | Solution |
|-------|----------|
| `'credentials.json' not found` | Download your OAuth2 credentials from Google Cloud Console (see Section 1.4) and place the file in the project root. |
| `Access blocked: This app's request is invalid` or `403: access_denied` | Make sure you added your Gmail address as a **test user** in the OAuth consent screen (see Section 1.3, step 6). |
| `Token has been expired or revoked` | Delete `token.json` and run the bot again. You'll be prompted to re-authenticate in the browser. |
| `Insufficient Permission` | Delete `token.json` and re-authenticate. This can happen if the required scope changed. |
| `RefreshError` or `invalid_grant` | Delete `token.json` and re-authenticate. This can happen if you changed your Google password or revoked access. |

## 7. AI Outreach Setup

### 7.1 Get API Keys

1. **Gemini API** (required): Go to [ai.google.dev](https://ai.google.dev/), sign in, and create an API key.
2. **Hunter.io** (required): Sign up at [hunter.io](https://hunter.io/) and copy your API key from the dashboard.
3. **Google Custom Search** (optional): Follow the [Custom Search JSON API guide](https://developers.google.com/custom-search/v1/introduction) to create an API key and a Custom Search Engine ID (cx).

### 7.2 Configure config.json

Create `config.json` in the project root:

```json
{
  "gemini_api_key": "YOUR_GEMINI_API_KEY",
  "hunter_api_key": "YOUR_HUNTER_IO_API_KEY",
  "google_search_api_key": "YOUR_GOOGLE_CUSTOM_SEARCH_API_KEY",
  "google_search_cx": "YOUR_CUSTOM_SEARCH_ENGINE_ID",
  "settings": {
    "max_leads": 10,
    "gmail_send_delay_seconds": 2,
    "hunter_results_limit": 10,
    "google_search_results_limit": 5,
    "gemini_model": "gemini-2.0-flash"
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `gemini_api_key` | Yes | Your Google Gemini API key for prompt parsing and email generation. |
| `hunter_api_key` | Yes | Your Hunter.io API key for lead discovery. |
| `google_search_api_key` | No | Google Custom Search API key. Enables fallback lead discovery when Hunter.io has no results. |
| `google_search_cx` | No | Google Custom Search Engine ID. Required if `google_search_api_key` is set. |
| `settings.max_leads` | No | Maximum number of leads to process (default: 10). |
| `settings.gmail_send_delay_seconds` | No | Delay between sending each email in seconds (default: 2). |
| `settings.hunter_results_limit` | No | Max results per Hunter.io domain search (default: 10). |
| `settings.google_search_results_limit` | No | Max results per Google Custom Search query (default: 5). |
| `settings.gemini_model` | No | Gemini model to use (default: `gemini-2.0-flash`). |

> **Security:** `config.json` is listed in `.gitignore` and will not be committed.

### 7.3 Usage

```bash
python vera.py "<your outreach prompt>"
```

**Example prompts:**

```bash
python vera.py "Find CTOs at AI startups and pitch our analytics tool"
python vera.py "Reach out to marketing managers at Shopify and HubSpot about our SEO product"
python vera.py "Contact engineering leads at fintech companies in San Francisco about our API platform"
python vera.py "Email HR directors at companies with 500+ employees about our recruiting software"
```

The bot will show you all discovered leads and generated emails for review. Type `y` to send or `n` to abort.

### 7.4 How It Works

```
Your prompt
    |
    v
[Gemini AI] -- Parses prompt into search criteria + email intent
    |
    v
[Hunter.io] -- Discovers leads (name, email, company, role)
  (+ optional Google Custom Search fallback)
    |
    v
[Gemini AI] -- Generates personalized email per lead
    |
    v
[You review] -- Preview all emails, confirm y/n
    |
    v
[Gmail API] -- Sends emails with rate limiting
    |
    v
Summary: sent/failed counts
```

### 7.5 Rate Limits

| Service | Free Tier Limit | Notes |
|---------|----------------|-------|
| Gemini API | 15 requests/minute | Bot retries automatically on 429 errors |
| Hunter.io | 25 searches/month | Each domain search counts as 1 request |
| Google Custom Search | 100 queries/day | Only used as fallback; optional |
| Gmail API | 500 emails/day | Standard Gmail sending limit |

### 7.6 AI Outreach Troubleshooting

| Error | Solution |
|-------|----------|
| `Set a valid 'gemini_api_key' in config.json` | Get a key from [ai.google.dev](https://ai.google.dev/) and update `config.json`. |
| `Set a valid 'hunter_api_key' in config.json` | Get a key from [hunter.io](https://hunter.io/) and update `config.json`. |
| `Rate limited by Gemini API` | The bot retries automatically. If it persists, wait a minute and try again. |
| `Hunter.io error` | Check your API key and remaining monthly quota at [hunter.io/api-keys](https://hunter.io/api-keys). |
| `No leads found` | Try a more specific prompt, provide company names or domains, or set up Google Custom Search for broader discovery. |
| `Error parsing prompt` | Rephrase your prompt to be clearer about who to contact and what to pitch. |
