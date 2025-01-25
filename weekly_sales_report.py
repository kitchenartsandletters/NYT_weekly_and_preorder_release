import os
import requests
import csv
import logging
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv
import sendgrid
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import time
import random
import sys
import base64

# -----------------------------#
#         Configuration        #
# -----------------------------#

# Base directory for the script (use current working directory)
BASE_DIR = os.getcwd()

# Initialize global variables
GRAPHQL_URL = None
HEADERS = None

# ... (other unchanged functions) ...

def export_skipped_line_items(skipped_line_items, filename):
    """
    Exports skipped line items to a CSV file.
    """
    abs_path = os.path.join(os.getcwd(), filename)  # Use the current working directory
    print(f"Exporting skipped items to CSV at path: {abs_path}")  # Debug statement
    with open(abs_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Order ID', 'Product Name', 'Quantity', 'Reason'])
        for item in skipped_line_items:
            writer.writerow([item['order_id'], item['product_name'], item['quantity'], item['reason']])

def export_to_csv(sales_data, filename):
    """
    Exports the sales data to a CSV file.
    """
    abs_path = os.path.join(os.getcwd(), filename)  # Use the current working directory
    print(f"Exporting to CSV at path: {abs_path}")  # Debug statement
    with open(abs_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ISBN', 'QTY'])
        for barcode, qty in sales_data.items():
            writer.writerow([barcode, qty])

def send_email(report_path):
    """
    Sends the report as an email attachment using SendGrid.
    """
    api_key = os.getenv('SENDGRID_API_KEY')
    sender_email = os.getenv('EMAIL_SENDER')
    recipient_emails = os.getenv('EMAIL_RECIPIENTS').split(',')

    if not api_key or not sender_email or not recipient_emails:
        print("Error: Missing email configuration.")
        return

    abs_report_path = os.path.join(BASE_DIR, report_path)

    sg = sendgrid.SendGridAPIClient(api_key)
    subject = "Weekly Shopify Sales Report"
    content = "Attached is the weekly Shopify sales report."

    message = Mail(
        from_email=sender_email,
        to_emails=recipient_emails,
        subject=subject,
        plain_text_content=content
    )

    try:
        with open(abs_report_path, 'rb') as f:
            report_data = f.read()
            encoded_file = base64.b64encode(report_data).decode()
            attachment = Attachment(
                FileContent(encoded_file),
                FileName(os.path.basename(abs_report_path)),
                FileType('text/csv'),
                Disposition('attachment')
            )
            message.add_attachment(attachment)
    except Exception as e:
        print(f"Error attaching report: {e}")
        logging.error(f"Error attaching report: {e}")
        return

    try:
        response = sg.send(message)
        print(f"Email sent! Status: {response.status_code}")
        logging.info(f"Email sent! Status: {response.status_code}")
    except Exception as e:
        print(f"Failed to send email: {e}")
        logging.error(f"Failed to send email: {e}")

# ... (rest of the script unchanged) ...

# -----------------------------#
#             Main             #
# -----------------------------#

def get_last_week_date_range():
    today = datetime.now()
    last_sunday = today - timedelta(days=today.weekday() + 1)  # Last Sunday
    last_monday = last_sunday - timedelta(days=6)  # Previous Monday
    return last_monday.strftime('%Y-%m-%d'), last_sunday.strftime('%Y-%m-%d')


def main():
    parser = argparse.ArgumentParser(description='Generate and email a Shopify weekly sales report.')
    args = parser.parse_args()  # No need for '--env' argument anymore

    # Automatically determine last week's date range
    start_date, end_date = get_last_week_date_range()
    print(f"Generating report for: {start_date} to {end_date}")

    load_environment()

    global SHOP_URL, GRAPHQL_URL, HEADERS
    SHOP_URL = os.getenv('SHOP_URL')
    ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')

    if not SHOP_URL or not ACCESS_TOKEN:
        print("Error: Missing SHOP_URL or SHOPIFY_ACCESS_TOKEN.")
        return

    GRAPHQL_URL = f"https://{SHOP_URL}/admin/api/2025-01/graphql.json"
    HEADERS = {"Content-Type": "application/json", "X-Shopify-Access-Token": ACCESS_TOKEN}

    orders = fetch_orders(start_date, end_date)
    if not orders:
        print("No orders found.")
        return

    sales_data, skipped_items = aggregate_sales(orders)
    if not sales_data:
        print("No sales data.")
        return

    report_filename = f"shopify_sales_report_{datetime.now().strftime('%Y-%m-%d')}.csv"
    skipped_filename = "skipped_line_items.csv"

    export_to_csv(sales_data, report_filename)
    export_skipped_line_items(skipped_items, filename=skipped_filename)

    print(f"Report generated: {os.path.join(BASE_DIR, report_filename)}")
    print(f"Skipped items logged: {os.path.join(BASE_DIR, skipped_filename)}")
    # Debug: Print the current BASE_DIR value
    print(f"Current working directory (BASE_DIR): {BASE_DIR}")

    send_email(report_filename)

if __name__ == "__main__":
    main()