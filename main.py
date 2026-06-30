import gspread
from google.oauth2.service_account import Credentials
from collections import Counter
import random
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
# ==========================================================
# CONFIG
# ==========================================================

SPREADSHEET_ID = "152D6n5c8dVDr7cdWBYESI7VrEaNr5CCT-eCTeuT6qvE"
SHEET_NAME = "VUP"


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]

# ==========================================================
# GOOGLE SHEETS
# ==========================================================

import os
import json
from google.oauth2.service_account import Credentials

google_credentials = json.loads(os.environ["GOOGLE_CREDENTIALS"])

creds = Credentials.from_service_account_info(
    google_credentials,
    scopes=SCOPES
)

client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)


# ==========================================================
# READ RANGE
# ==========================================================

def read_symbols(range_name):
    values = sheet.get(range_name)

    symbols = []

    for row in values:
        for cell in row:
            cell = cell.strip().upper()

            if cell != "" and cell != "SYMBOL":
                symbols.append(cell)

    return symbols


# ==========================================================
# FREQUENCY FILTER
# ==========================================================

def frequency_filter(symbols):

    counter = Counter(symbols)

    ranked = sorted(
        counter.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return ranked


# ==========================================================
# GEMINI FILTER (Dummy)
# ==========================================================

def gemini_filter(freq_list):

    shortlisted = []

    for symbol, count in freq_list:

        if count >= 1:
            shortlisted.append(symbol)

    return shortlisted

from openai import OpenAI
import json


groq_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

def groq_validate(symbols):

    prompt = f"""
You are an institutional equity analyst specializing in the Indian stock market.

Analyze these stocks:

{", ".join(symbols)}

For each stock consider:

- Latest news
- Corporate announcements
- Quarterly results
- Technical trend
- Market sentiment
- Sector momentum
- Relative strength
- Institutional activity
- Risk

Assign:

1. score (0-100)

100 = Extremely Bullish
80 = Bullish
60 = Neutral
40 = Bearish
20 = Extremely Bearish

2. sentiment

Bullish
Neutral
Bearish

Return ONLY JSON.

Format:

{{
  "stocks": [
    {{
      "symbol": "...",
      "score": 90,
      "sentiment": "Bullish"
    }}
  ]
}}
"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You are an institutional quantitative equity analyst."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )
    text = response.choices[0].message.content.strip()

    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(text)
        return data["stocks"]
    except Exception as e:
        print("Gemini Response:")
        print(text)
        raise e
from google import genai
import json


gemini_client = genai.Client(api_key=GEMINI_API_KEY)
import time
from google.genai.errors import ServerError

def gemini_probability(stocks):

    prompt = f"""
You are an institutional quantitative equity analyst.

The following stocks have already passed an initial screening.

{json.dumps(stocks, indent=2)}

Estimate the probability that each stock will CLOSE HIGHER than today's close on the NEXT TRADING DAY.

Consider:
- Technical trend
- Price action
- Sector momentum
- News
- Relative strength
- Market sentiment
- Institutional activity
- Fundamentals

Return ONLY valid JSON.

Format:

{{
  "stocks": [
    {{
      "symbol": "BHEL",
      "probability": 0.8234,
      "confidence": 0.91
    }}
  ]
}}

Sort from highest probability to lowest.
"""

    response = None

    for attempt in range(5):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            break

        except ServerError:
            print(f"Gemini busy... Retry {attempt + 1}/5")
            time.sleep(10)

    if response is None:
        raise Exception("Gemini unavailable after 5 retries")

    text = response.text.strip()

    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    print("========== GEMINI ==========")
    print(text)
    print("============================")

    data = json.loads(text)

    return data["stocks"]
# ==========================================================
# WRITE RESULT
# ==========================================================

def write_result(start_cell, result):

    rows = []

    rank = 1

    for r in result:

        # Skip probabilities below 75%
        if r["probability"] < 0.75:
            continue

        rows.append([
            f"{rank}. {r['symbol']} {r['probability']*100:.2f}% (Conf {r['confidence']*100:.1f}%)"
        ])

        rank += 1

    # Append IST timestamp
    ist_time = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d-%m-%Y %I:%M:%S %p IST")

    rows.append([""])
    rows.append([f"Last Updated: {ist_time}"])

    sheet.update(values=rows, range_name=start_cell)
# ==========================================================
# PIPELINE
# ==========================================================

def process(input_range,output_cell):

    print(f"\nProcessing {input_range}")

    symbols=read_symbols(input_range)

    print("Stocks Read :",len(symbols))

    freq=frequency_filter(symbols)

    print("Frequency")

    for s,c in freq:
        print(s,c)

    shortlisted=gemini_filter(freq)

    print("\nAfter Gemini Filter")

    print(shortlisted)

    validated = groq_validate(shortlisted)

    validated = [
        s for s in validated
        if s["score"] >= 75
    ]

    final_result = gemini_probability(validated)

    write_result(output_cell,final_result)


# ==========================================================
# MAIN
# ==========================================================

def main():

    process("A4:AC10","AF4")

    process("A14:AC20","AI4")

    print("\nCompleted Successfully")


if __name__=="__main__":
    main()
