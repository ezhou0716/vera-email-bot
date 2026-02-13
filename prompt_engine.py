import json
import time

import google.generativeai as genai


def configure_genai(api_key):
    """Configure the Gemini API key."""
    genai.configure(api_key=api_key)



def _call_gemini_with_retry(model, prompt, max_retries=3):
    """Call Gemini API with exponential backoff on 429 (rate limit) errors.

    Retries after 5s, 10s, 20s before giving up.
    """
    delays = [10, 30, 60]
    for attempt in range(max_retries + 1):
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_str = str(e)
            if "429" in error_str and attempt < max_retries:
                wait = delays[attempt]
                print(f"  Rate limited by Gemini API. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


def parse_prompt(prompt, model_name="gemini-2.0-flash"):
    """Parse a natural language outreach prompt into structured data.

    Returns:
        tuple: (search_criteria, email_intent) dicts
    """
    model = genai.GenerativeModel(model_name)
    model = genai.GenerativeModel(model_name)

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

    raw = _call_gemini_with_retry(model, system_prompt)

    # Strip markdown fences if Gemini wraps the response
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    parsed = json.loads(text)
    return parsed["search_criteria"], parsed["email_intent"]


def generate_email(lead, email_intent, model_name="gemini-2.0-flash"):
    """Generate a personalized outreach email for a specific lead.

    Args:
        lead: dict with keys name, email, company, role
        email_intent: dict with purpose, product_or_topic, key_points, tone

    Returns:
        dict with 'subject' and 'body' keys
    """
    model = genai.GenerativeModel(model_name)
    model = genai.GenerativeModel(model_name)

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

    raw = _call_gemini_with_retry(model, prompt)

    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    return json.loads(text)
