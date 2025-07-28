import os
import logging
import base64
import requests
from dotenv import load_dotenv

MAILTRAP_API_TOKEN = os.getenv("MAILTRAP_API_TOKEN")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECIPIENTS = os.getenv("EMAIL_RECIPIENTS")
FORCE_TEST_EMAIL = os.getenv("FORCE_TEST_EMAIL", "false").lower() == "true"


def validate_env_for_mailtrap():
    if not MAILTRAP_API_TOKEN or not EMAIL_SENDER or not EMAIL_RECIPIENTS:
        raise EnvironmentError("Missing required Mailtrap environment variables.")


def prepare_attachments(filepaths):
    attachments = []
    for filepath in filepaths:
        with open(filepath, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        filename = os.path.basename(filepath)
        attachments.append({
            "content": encoded,
            "filename": filename,
            "type": "text/csv",  # Adjust MIME type as needed
            "disposition": "attachment"
        })
    return attachments


def send_mailtrap_email(subject, body_html, attachments=None):
    validate_env_for_mailtrap()
    url = "https://send.api.mailtrap.io/api/send"
    headers = {
        "Authorization": f"Bearer {MAILTRAP_API_TOKEN}",
        "Content-Type": "application/json"
    }

    to_addresses = [{"email": email.strip()} for email in EMAIL_RECIPIENTS.split(";") if email.strip()]
    data = {
        "from": {"email": EMAIL_SENDER, "name": "Preorder Manager"},
        "to": to_addresses,
        "subject": subject,
        "html": body_html,
    }

    if attachments:
        data["attachments"] = attachments

    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        logging.error(f"Mailtrap error: {response.status_code} {response.text}")
        raise RuntimeError("Mailtrap email failed to send.")

    logging.info("✅ Mailtrap email sent successfully.")


def send_test_email_if_requested():
    if FORCE_TEST_EMAIL:
        logging.warning("⚠️  FORCE_TEST_EMAIL is set — sending test email now.")
        test_subject = "Test Email from NYT Preorder System"
        test_html = "<p>This is a test email sent via Mailtrap API.</p>"
        send_mailtrap_email(test_subject, test_html)
    else:
        logging.warning("Skipping forced test email — FORCE_TEST_EMAIL not enabled.")
