import json
import time

from google import genai

# Module-level client, set by configure_genai()
_client = None


def configure_genai(api_key):
    """Configure the Gemini API client."""
    global _client
    _client = genai.Client(api_key=api_key)


def _call_gemini_with_retry(model_name, prompt, max_retries=3):
    """Call Gemini API with exponential backoff on 429 (rate limit) errors.

    Retries after 10s, 30s, 60s before giving up.
    """
    delays = [10, 30, 60]
    for attempt in range(max_retries + 1):
        try:
            response = _client.models.generate_content(
                model=model_name, contents=prompt
            )
            return response.text
        except Exception as e:
            error_str = str(e)
            if "429" in error_str and attempt < max_retries:
                wait = delays[attempt]
                print(f"  Rate limited by Gemini API. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


def _strip_markdown_fences(text):
    """Strip markdown code fences from Gemini responses."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def parse_prompt(prompt, model_name="gemini-2.5-flash-lite"):
    """Parse a natural language outreach prompt into structured data.

    Returns:
        tuple: (search_criteria, email_intent) dicts
    """
    system_prompt = f"""You are a sales outreach assistant. Analyze the user's prompt and extract two JSON objects.

User prompt: "{prompt}"

Return ONLY valid JSON with this exact structure, no markdown fences, no explanation:
{{
  "search_criteria": {{
    "roles": ["list of target job titles/roles, e.g. CTO, VP Engineering"],
    "companies": ["specific company names if mentioned, otherwise empty list"],
    "company_type": "type of company if mentioned, e.g. startup, enterprise, or empty string",
    "industry": "industry if mentioned, e.g. AI, fintech, or empty string",
    "domains": ["specific domains if mentioned, e.g. example.com, otherwise empty list"],
    "location": "geographic location if mentioned, or empty string"
  }},
  "email_intent": {{
    "purpose": "brief description of the email's goal",
    "product_or_topic": "what is being pitched or discussed",
    "key_points": ["2-4 key selling points or talking points to include"],
    "tone": "professional, casual, friendly, urgent, etc."
  }}
}}

Rules:
- If roles are not explicitly stated, infer reasonable ones from context (e.g. "pitch our analytics tool" implies decision-makers like CTO, VP Engineering, Head of Data)
- If tone is not stated, default to "professional and friendly"
- Always provide at least one role and one key point
- Return ONLY the JSON object, nothing else"""

    raw = _call_gemini_with_retry(model_name, system_prompt)
    text = _strip_markdown_fences(raw)
    parsed = json.loads(text)
    return parsed["search_criteria"], parsed["email_intent"]


def generate_email(lead, email_intent, model_name="gemini-2.5-flash-lite"):
    """Generate a personalized outreach email for a single lead.

    Args:
        lead: dict with keys name, email, company, role
        email_intent: dict with purpose, product_or_topic, key_points, tone

    Returns:
        dict with 'subject' and 'body' keys
    """
    prompt = f"""Write a personalized cold outreach email.

Recipient details:
- Name: {lead.get('name', 'there')}
- Role: {lead.get('role', 'Professional')}
- Company: {lead.get('company', 'their company')}

Email intent:
- Purpose: {email_intent['purpose']}
- Product/Topic: {email_intent['product_or_topic']}
- Key points to mention: {json.dumps(email_intent['key_points'])}
- Tone: {email_intent['tone']}

Return ONLY valid JSON with this exact structure, no markdown fences, no explanation:
{{
  "subject": "the email subject line",
  "body": "the full email body"
}}

Rules:
- Subject line must be under 60 characters
- Body must be under 150 words
- Include a clear call-to-action (e.g. book a call, reply, check a link)
- Do NOT use placeholder brackets like [Name] or [Company] — use the actual values provided
- Personalize based on the recipient's role and company
- Sign off as "Best" with no sender name (the sender will add their own signature)
- Use plain text only, no HTML or markdown formatting"""

    raw = _call_gemini_with_retry(model_name, prompt)
    text = _strip_markdown_fences(raw)
    return json.loads(text)


def generate_emails_batch(leads, email_intent, model_name="gemini-2.5-flash-lite"):
    """Generate personalized outreach emails for ALL leads in a single API call.

    This dramatically reduces Gemini API usage: 1 call instead of N.

    Args:
        leads: list of dicts with keys name, email, company, role
        email_intent: dict with purpose, product_or_topic, key_points, tone

    Returns:
        list of dicts, each with 'subject' and 'body' keys (or None on failure).
        Length matches len(leads).
    """
    if not leads:
        return []

    # Build the recipient list for the prompt
    recipients_block = ""
    for i, lead in enumerate(leads, 1):
        recipients_block += (
            f"\nRecipient {i}:\n"
            f"  Name: {lead.get('name', 'there')}\n"
            f"  Role: {lead.get('role', 'Professional')}\n"
            f"  Company: {lead.get('company', 'their company')}\n"
            f"  Email: {lead.get('email', '')}\n"
        )

    prompt = f"""Write personalized cold outreach emails for each of the following {len(leads)} recipients.

{recipients_block}
Email intent (same for all):
- Purpose: {email_intent['purpose']}
- Product/Topic: {email_intent['product_or_topic']}
- Key points to mention: {json.dumps(email_intent['key_points'])}
- Tone: {email_intent['tone']}

Return ONLY a valid JSON array with exactly {len(leads)} objects, one per recipient in order. No markdown fences, no explanation:
[
  {{"subject": "email subject line for recipient 1", "body": "full email body for recipient 1"}},
  {{"subject": "email subject line for recipient 2", "body": "full email body for recipient 2"}}
]

Rules (apply to EVERY email):
- Subject line must be under 60 characters
- Body must be under 150 words
- Include a clear call-to-action (e.g. book a call, reply, check a link)
- Do NOT use placeholder brackets like [Name] or [Company] — use the actual values provided
- Personalize each email based on that recipient's role and company — each email should feel unique
- Sign off as "Best" with no sender name (the sender will add their own signature)
- Use plain text only, no HTML or markdown formatting
- Return EXACTLY {len(leads)} email objects in the array, in the same order as the recipients"""

    raw = _call_gemini_with_retry(model_name, prompt)
    text = _strip_markdown_fences(raw)

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list) and len(parsed) == len(leads):
            return parsed
        # If length mismatch, pad or truncate
        if isinstance(parsed, list):
            results = []
            for i in range(len(leads)):
                results.append(parsed[i] if i < len(parsed) else None)
            return results
    except (json.JSONDecodeError, KeyError):
        pass

    # Batch failed — fall back to individual calls
    print("  Batch generation failed, falling back to individual emails...")
    results = []
    for lead in leads:
        try:
            email_data = generate_email(lead, email_intent, model_name)
            results.append(email_data)
        except Exception:
            results.append(None)
    return results
