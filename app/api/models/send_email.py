import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

EMAIL_FROM = os.getenv("EMAIL_SENDER")
BREVO_API_KEY: str = os.getenv("BREVO_API_KEY")

# Email sending function
def send_email_notification(to_email: str, subject: str, text_content: str):
    url = "https://api.brevo.com/v3/smtp/email"
    payload = json.dumps(
        {
            "sender": {"name": "Sysnova", "email": EMAIL_FROM},
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": text_content,
        }
    )
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }
    response = requests.post(url, headers=headers, data=payload)
    return response


# send_email_notification("bikas.zaman@sysnova.com", "GNU Health Project", "This email is send from the Brevo.")
