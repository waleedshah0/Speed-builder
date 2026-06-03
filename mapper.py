"""
services/mapper.py
──────────────────
Uses OpenAI to:
  1. Semantically map client field names → our valid schema fields.
  2. Reject fields whose meaning is genuinely different.
  3. Normalise the Date_of_Birth value to "DD Mon YYYY" format.
"""

import os
import json
import re
from typing import Dict, Tuple
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Our canonical schema ────────────────────────────────────────────────────
VALID_SCHEMA = {
    "Name":          "Full name of the person",
    "Email":         "Email address of the person",
    "Phone_Number":  "Phone or mobile number of the person",
    "Address":       "Residential or mailing address of the person",
    "National_ID":   "National identification number, passport number, or government-issued ID",
    "Date_of_Birth": "Date of birth of the person",
}

SYSTEM_PROMPT = """
You are a data-mapping assistant. Your job is to map client-supplied JSON fields
to our canonical schema fields based on SEMANTIC MEANING — not just name similarity.

Our canonical schema (field → description):
{schema}

Rules:
1. For each client field, decide if it semantically matches one of our canonical fields.
2. A match means the client field carries the SAME real-world meaning as our field.
   - "Full_Name", "full name", "Name" → matches "Name"         ✓
   - "Passport_No", "National_Number"  → matches "National_ID"  ✓
   - "Current_Date", "Today"           → does NOT match "Date_of_Birth" ✗
3. Each canonical field may be matched AT MOST ONCE (no duplicates).
4. If a client field's meaning is different or ambiguous, put it in "unmatched"
   with a short reason.
5. Also normalise the value of any matched "Date_of_Birth" field to the format
   "DD Mon YYYY" (e.g. "28 Dec 2002"). If the date cannot be parsed, keep the
   original value and note the issue in "unmatched".

Respond ONLY with a valid JSON object in exactly this structure (no markdown):
{{
  "mapped": {{
    "<canonical_field>": "<client_value>"
  }},
  "unmatched": {{
    "<client_field>": "<reason>"
  }}
}}
"""


def _build_schema_text() -> str:
    lines = []
    for field, desc in VALID_SCHEMA.items():
        lines.append(f'  "{field}": "{desc}"')
    return "{\n" + ",\n".join(lines) + "\n}"


def map_fields_with_ai(payload: Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Sends the client payload to OpenAI and returns:
      (mapped_dict, unmatched_dict)
    """
    schema_text = _build_schema_text()
    system = SYSTEM_PROMPT.format(schema=schema_text)

    user_message = (
        "Map these client fields to our schema:\n"
        + json.dumps(payload, indent=2)
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",           # cheap & capable for structured tasks
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user_message},
        ],
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    result = json.loads(raw)

    mapped    = result.get("mapped", {})
    unmatched = result.get("unmatched", {})

    # ── Validate that every key in mapped is actually a valid canonical field ──
    cleaned_mapped: Dict[str, str] = {}
    for key, value in mapped.items():
        if key in VALID_SCHEMA:
            cleaned_mapped[key] = value
        else:
            unmatched[key] = f"AI returned an unknown canonical key '{key}'"

    return cleaned_mapped, unmatched


def validate_mapped_payload(mapped: Dict[str, str]) -> Tuple[bool, list]:
    """
    Checks that all required canonical fields are present in the mapped dict.
    Returns (is_valid, list_of_missing_fields).
    """
    missing = [field for field in VALID_SCHEMA if field not in mapped]
    return (len(missing) == 0), missing
