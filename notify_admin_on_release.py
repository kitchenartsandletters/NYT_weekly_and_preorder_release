import os
import sys
import json
import logging
import sendgrid
from sendgrid.helpers.mail import Mail
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.production')

SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
FROM_EMAIL = os.getenv('FROM_EMAIL', 'admin@kitchenartsandletters.com')
TO_EMAIL = os.getenv('TO_EMAIL', 'admin@kitchenartsandletters.com')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DRY_RUN = False  # Toggle to False when ready

def load_approved_releases():
    output_dir = os.path.join(BASE_DIR, 'output')
    releases = []
    for filename in os.listdir(output_dir):
        if filename.startswith('approved_releases_') and filename.endswith('.json'):
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                releases.extend(data.get('approved', []))
    return releases

def format_release_table(releases):
    header = "| # | Title | ISBN | Pub Date | Quantity Released |\n|---|-------|------|----------|-------------------|\n"
    rows = ""
    for i, book in enumerate(releases, 1):
        rows += f"| {i} | {book.get('title', '')} | {book.get('isbn', '')} | {book.get('pub_date', '')} | {book.get('quantity', '')} |\n"
    return header + rows

def send_email(subject, body):
    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=TO_EMAIL,
        subject=subject,
        html_content=body.replace('\n', '<br>')  # Simple line-break formatting
    )
    response = sg.send(message)
    return response.status_code, response.body

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    releases = load_approved_releases()
    if not releases:
        logging.info("No approved releases found. Exiting.")
        return

    with open(os.path.join(BASE_DIR, 'controls', 'release_email_template.md'), 'r', encoding='utf-8') as f:
        template = f.read()

    release_table = format_release_table(releases)
    today = datetime.today().strftime('%B %d, %Y')
    subject = f"📚 Weekly Preorder Releases - {today}"
    body = template.replace('{{release_table}}', release_table)

    if DRY_RUN:
        logging.info("[Dry Run] Would send the following email:")
        logging.info(f"Subject: {subject}")
        logging.info(f"Body:\n{body}")
    else:
        status, response = send_email(subject, body)
        logging.info(f"Email sent with status: {status}")
        if status >= 400:
            logging.error(f"SendGrid error: {response}")

if __name__ == "__main__":
    main()
