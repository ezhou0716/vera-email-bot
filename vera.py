import sys
import json
import time

from prompt_engine import parse_prompt, generate_email
from lead_finder import find_leads
from email_sender import authenticate_gmail, create_message, send_single_email

CONFIG_FILE = "config.json"


def load_config():
    """Load and validate config.json."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: '{CONFIG_FILE}' not found.")
        print("Create it with your API keys. See README.md for the expected format.")
        sys.exit(1)

    if not config.get("gemini_api_key") or config["gemini_api_key"].startswith("YOUR_"):
        print("Error: Set a valid 'gemini_api_key' in config.json")
        sys.exit(1)
    if not config.get("hunter_api_key") or config["hunter_api_key"].startswith("YOUR_"):
        print("Warning: No valid 'hunter_api_key' in config.json — will use free web scraping instead.")

    return config


def display_leads(leads):
    """Print a formatted summary of discovered leads."""
    print(f"\n{'='*60}")
    print(f"  Found {len(leads)} lead(s)")
    print(f"{'='*60}")
    for i, lead in enumerate(leads, 1):
        name = lead.get("name") or "(unknown)"
        role = lead.get("role") or "(no role)"
        print(f"  {i}. {name} — {role}")
        print(f"     {lead['email']} @ {lead.get('company', '(unknown)')}")
    print()


def display_email_preview(lead, email_data, index):
    """Print a formatted email preview."""
    print(f"--- Email #{index} ---")
    print(f"  To:      {lead['email']}")
    print(f"  Subject: {email_data['subject']}")
    print(f"  Body:")
    for line in email_data["body"].split("\n"):
        print(f"    {line}")
    print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python vera.py \"<your outreach prompt>\"")
        print()
        print("Examples:")
        print('  python vera.py "Find CTOs at AI startups and pitch our analytics tool"')
        print('  python vera.py "Reach out to marketing managers at Shopify about our SEO product"')
        sys.exit(1)

    prompt = sys.argv[1]
    print(f"\nVera Email Bot — AI-Powered Outreach")
    print(f"{'='*60}\n")

    # Load config
    config = load_config()
    settings = config.get("settings", {})
    gemini_key = config["gemini_api_key"]
    hunter_key = config["hunter_api_key"]
    google_key = config.get("google_search_api_key", "")
    google_cx = config.get("google_search_cx", "")
    model_name = settings.get("gemini_model", "gemini-2.0-flash")
    max_leads = settings.get("max_leads", 10)
    send_delay = settings.get("gmail_send_delay_seconds", 2)
    hunter_limit = settings.get("hunter_results_limit", 10)
    google_limit = settings.get("google_search_results_limit", 5)
    scraping_timeout = settings.get("scraping_timeout_seconds", 10)
    scraping_max_pages = settings.get("scraping_max_pages_per_domain", 5)

    # Step 1: Parse prompt
    print(f"[1/4] Parsing prompt with Gemini...")
    try:
        search_criteria, email_intent = parse_prompt(prompt, gemini_key, model_name)
    except Exception as e:
        print(f"Error parsing prompt: {e}")
        sys.exit(1)

    print(f"  Search criteria: {json.dumps(search_criteria, indent=2)}")
    print(f"  Email intent: {json.dumps(email_intent, indent=2)}")

    # Step 2: Find leads
    print(f"\n[2/4] Discovering leads...")
    google_key_valid = google_key and not google_key.startswith("YOUR_")
    google_cx_valid = google_cx and not google_cx.startswith("YOUR_")
    leads = find_leads(
        search_criteria,
        hunter_api_key=hunter_key,
        google_search_api_key=google_key if google_key_valid else None,
        google_search_cx=google_cx if google_cx_valid else None,
        hunter_limit=hunter_limit,
        google_search_limit=google_limit,
        max_leads=max_leads,
        scraping_timeout=scraping_timeout,
        scraping_max_pages=scraping_max_pages,
    )

    if not leads:
        print("\nNo leads found. Try a different prompt or check your API keys.")
        sys.exit(0)

    display_leads(leads)

    # Step 3: Generate emails
    print(f"[3/4] Generating personalized emails...")
    emails = []
    for i, lead in enumerate(leads, 1):
        print(f"  Generating email {i}/{len(leads)} for {lead.get('name') or lead['email']}...")
        try:
            email_data = generate_email(lead, email_intent, gemini_key, model_name)
            emails.append(email_data)
        except Exception as e:
            print(f"  Error generating email for {lead['email']}: {e}")
            emails.append(None)

    # Step 4: Display previews
    print(f"\n{'='*60}")
    print(f"  Email Previews")
    print(f"{'='*60}\n")
    for i, (lead, email_data) in enumerate(zip(leads, emails), 1):
        if email_data:
            display_email_preview(lead, email_data, i)
        else:
            print(f"--- Email #{i} --- SKIPPED (generation failed)")
            print()

    # Count valid emails
    valid_pairs = [(lead, email) for lead, email in zip(leads, emails) if email]
    if not valid_pairs:
        print("No emails were generated successfully. Exiting.")
        sys.exit(1)

    # Confirm
    print(f"{'='*60}")
    print(f"  Ready to send {len(valid_pairs)} email(s)")
    print(f"{'='*60}")
    response = input("\nSend all emails? (y/n): ").strip().lower()
    if response != "y":
        print("Aborted. No emails were sent.")
        sys.exit(0)

    # Send
    print("\nAuthenticating with Gmail...")
    service = authenticate_gmail()

    sent = 0
    failed = 0
    for i, (lead, email_data) in enumerate(valid_pairs):
        message = create_message({
            "to": lead["email"],
            "subject": email_data["subject"],
            "body": email_data["body"],
        })
        success = send_single_email(service, message, lead["email"])
        if success:
            sent += 1
        else:
            failed += 1

        # Rate-limiting delay between sends (skip after last)
        if i < len(valid_pairs) - 1:
            time.sleep(send_delay)

    # Summary
    print(f"\n{'='*60}")
    print(f"  Done! Sent: {sent} | Failed: {failed}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
