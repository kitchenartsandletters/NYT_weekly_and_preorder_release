import os
import requests
import csv
import logging
import argparse
from datetime import datetime, timedelta
import sendgrid
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import time
import sys
import base64
from dotenv import load_dotenv

# -----------------------------#
#         Configuration       #
# -----------------------------#

# Base directory for the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Initialize global variables
GRAPHQL_URL = None
HEADERS = None

def load_environment():
    """
    Loads environment variables from .env.production file
    Used for local development/testing
    """
    try:
        load_dotenv('.env.production')  # Specifically load .env.production
        logging.info("Environment variables successfully loaded.")
        logging.info(f"SHOP_URL present: {bool(os.getenv('SHOP_URL'))}")
        logging.info(f"SHOPIFY_ACCESS_TOKEN present: {bool(os.getenv('SHOPIFY_ACCESS_TOKEN'))}")
        logging.info(f"SENDGRID_API_KEY present: {bool(os.getenv('SENDGRID_API_KEY'))}")
        logging.info(f"EMAIL_SENDER present: {bool(os.getenv('EMAIL_SENDER'))}")
        logging.info(f"EMAIL_RECIPIENTS present: {bool(os.getenv('EMAIL_RECIPIENTS'))}")
    except Exception as e:
        logging.error(f"Error loading environment variables: {e}")

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def run_query_with_retries(query, variables, max_retries=3, delay=1):
    """
    Runs a GraphQL query with retry logic
    """
    attempt = 0
    while attempt < max_retries:
        try:
            response = requests.post(
                GRAPHQL_URL,
                json={'query': query, 'variables': variables},
                headers=HEADERS
            )
            
            if response.status_code != 200:
                logging.error(f"Error: Received status code {response.status_code}")
                logging.error(f"Response: {response.text}")
                attempt += 1
                time.sleep(delay)
                continue
                
            data = response.json()
            
            if 'errors' in data:
                logging.error(f"GraphQL Errors: {data['errors']}")
                attempt += 1
                time.sleep(delay)
                continue
                
            return data['data']
            
        except Exception as e:
            logging.error(f"Attempt {attempt + 1} failed: {e}")
            attempt += 1
            time.sleep(delay)
            
    raise Exception(f"Failed to execute query after {max_retries} attempts")

def fetch_orders(start_date, end_date):
    """
    Fetches basic order data without collections or metafields
    """
    orders = []
    has_next_page = True
    cursor = None

    # Update log file path to use output directory
    output_dir = os.path.join(BASE_DIR, 'output')
    os.makedirs(output_dir, exist_ok=True)
    log_file_path = os.path.join(output_dir, 'fetched_order_ids.log')

    try:
        with open(log_file_path, 'w') as log_file:
            logging.info(f"Opened {log_file_path} for writing.")

            query = """
            query($first: Int!, $query: String!, $after: String) {
                orders(first: $first, query: $query, after: $after, reverse: false) {
                    edges {
                        cursor
                        node {
                            id
                            name
                            createdAt
                            cancelledAt
                            
                            lineItems(first: 25) {
                                edges {
                                    node {
                                        id
                                        name
                                        quantity
                                        variant {
                                            id
                                            barcode
                                            product {
                                                id
                                                title
                                            }
                                        }
                                    }
                                }
                            }
                            
                            refunds {
                                id
                                createdAt
                                refundLineItems(first: 25) {
                                    edges {
                                        node {
                                            quantity
                                            lineItem {
                                                id
                                                name
                                                variant {
                                                    id
                                                    barcode
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    pageInfo {
                        hasNextPage
                    }
                }
            }
            """

            variables = {
                "first": 250,
                "query": f'created_at:>="{start_date}" AND created_at:<="{end_date}"',
                "after": cursor
            }

            while has_next_page:
                try:
                    data = run_query_with_retries(query, variables)
                    fetched_orders = data['orders']['edges']
                    for edge in fetched_orders:
                        order = edge['node']
                        orders.append(order)

                        # Log each order's ID & creation date
                        order_id = order['id']
                        order_created_at = order['createdAt']
                        try:
                            log_file.write(f"{order_id}\t{order_created_at}\n")
                            logging.debug(f"Logged Order ID: {order_id}, Created At: {order_created_at}")
                        except Exception as e:
                            logging.error(f"Failed to write Order ID {order_id} to log: {e}")

                    has_next_page = data['orders']['pageInfo']['hasNextPage']
                    logging.info(f"Fetched {len(fetched_orders)} orders. Has next page: {has_next_page}")

                    if has_next_page:
                        cursor = fetched_orders[-1]['cursor']
                        variables['after'] = cursor
                    else:
                        break

                except Exception as e:
                    logging.error(f"Failed to fetch orders after retries: {e}", exc_info=True)
                    break

    except Exception as e:
        logging.error(f"Failed to open {log_file_path} for writing: {e}")
        exit(1)

    logging.info(f"Total orders fetched: {len(orders)}")
    return orders

def fetch_product_details(product_ids):
    """
    Fetches both collections and pub dates for products
    """
    if not product_ids:
        return {}

    query = """
    query($ids: [ID!]!) {
        nodes(ids: $ids) {
            ... on Product {
                id
                title
                collections(first: 4) {
                    edges {
                        node {
                            title
                        }
                    }
                }
                metafields(first: 10, namespace: "custom") {
                    edges {
                        node {
                            key
                            value
                        }
                    }
                }
            }
        }
    }
    """
    
    try:
        # Split into chunks of 10 products to manage query cost
        chunk_size = 10
        all_product_details = {}
        
        for i in range(0, len(product_ids), chunk_size):
            chunk = product_ids[i:i + chunk_size]
            variables = {"ids": chunk}
            
            data = run_query_with_retries(query, variables)
            
            for node in data.get('nodes', []):
                if node:
                    product_id = node['id']
                    all_product_details[product_id] = {
                        'title': node['title'],
                        'collections': [edge['node']['title'] for edge in node.get('collections', {}).get('edges', [])],
                        'pub_date': None
                    }
                    
                    # Extract pub_date if it exists
                    metafields = node.get('metafields', {}).get('edges', [])
                    for metafield in metafields:
                        if metafield['node']['key'] == 'pub_date':
                            all_product_details[product_id]['pub_date'] = metafield['node']['value']
                            break
            
            # Add a small delay between chunks
            if i + chunk_size < len(product_ids):
                time.sleep(1)
        
        return all_product_details
        
    except Exception as e:
        logging.error(f"Error fetching product details: {e}")
        return {}

def is_valid_isbn(barcode):
    """
    Checks if a barcode is a valid ISBN (starts with 978 or 979)
    """
    return barcode and (str(barcode).startswith('978') or str(barcode).startswith('979'))

def track_preorder_sales(preorder_items, tracking_file='preorder_tracking.csv'):
    """
    Maintains a running log of preorder sales
    Reads existing file, merges new preorder items, logs changes
    """
    logging.info("Starting preorder tracking process")
    logging.info(f"New preorder items to track: {len(preorder_items)}")

    # Path to the tracking file in the repository
    tracking_path = os.path.join(BASE_DIR, 'preorders', tracking_file)
    log_path = os.path.join(BASE_DIR, 'output', 'preorder_tracking_log.txt')

    # Ensure output directory exists
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    # Read existing tracking data
    existing_preorders = {}
    if os.path.exists(tracking_path):
        with open(tracking_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row['ISBN'], row['Pub Date'])
                existing_preorders[key] = {
                    'Title': row['Title'],
                    'Quantity': int(row['Quantity']),
                    'Status': row['Status']
                }

    # Prepare logging of changes
    preorder_log_entries = []
    preorder_log_entries.append("=== Preorder Tracking Log ===")
    preorder_log_entries.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    preorder_log_entries.append("\nExisting Preorders (Before Update):")
    for (isbn, pub_date), data in existing_preorders.items():
        preorder_log_entries.append(f"ISBN: {isbn}, Title: {data['Title']}, Pub Date: {pub_date}, Quantity: {data['Quantity']}, Status: {data['Status']}")

    # Process current preorder items
    current_date = datetime.now().date()
    new_preorder_count = 0
    updated_preorder_count = 0

    preorder_log_entries.append("\nNew Preorder Items:")
    for item in preorder_items:
        pub_date = item.get('pub_date') or ''
        key = (item['barcode'], pub_date)
        
        if key in existing_preorders:
            # Update existing preorder
            old_qty = existing_preorders[key]['Quantity']
            existing_preorders[key]['Quantity'] += item['quantity']
            updated_preorder_count += 1
            preorder_log_entries.append(
                f"Updated: ISBN {item['barcode']}, Title: {item['title']}, "
                f"Quantity: {old_qty} → {existing_preorders[key]['Quantity']}"
            )
        else:
            # Add new preorder
            existing_preorders[key] = {
                'Title': item['title'],
                'Quantity': item['quantity'],
                'Status': 'Preorder'
            }
            new_preorder_count += 1
            preorder_log_entries.append(
                f"New Preorder: ISBN {item['barcode']}, Title: {item['title']}, Quantity: {item['quantity']}"
            )

    # Remove released items
    released_items = {}
    existing_preorders = {
        key: data for (key, data) in existing_preorders.items() 
        if not (key[1] and  # has a pub date
                datetime.strptime(key[1], '%Y-%m-%d').date() <= current_date and 
                data['Status'] == 'Preorder')
    }

    # Log released items
    preorder_log_entries.append("\nReleased Preorder Items:")
    for (isbn, pub_date), data in list(existing_preorders.items()):
        if pub_date:
            try:
                pub_date_obj = datetime.strptime(pub_date, '%Y-%m-%d').date()
                if pub_date_obj <= current_date and data['Status'] == 'Preorder':
                    released_items[isbn] = data['Quantity']
                    preorder_log_entries.append(f"Released: ISBN {isbn}, Title: {data['Title']}, Quantity: {data['Quantity']}")
            except ValueError:
                logging.error(f"Invalid pub date format: {pub_date}")

    # Write updated tracking file
    with open(tracking_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['ISBN', 'Title', 'Pub Date', 'Quantity', 'Status'])
        writer.writeheader()
        for (isbn, pub_date), data in existing_preorders.items():
            writer.writerow({
                'ISBN': isbn,
                'Title': data['Title'],
                'Pub Date': pub_date,
                'Quantity': data['Quantity'],
                'Status': data['Status']
            })

    # Write log file
    preorder_log_entries.append(f"\nSummary:")
    preorder_log_entries.append(f"Total Existing Preorders: {len(existing_preorders)}")
    preorder_log_entries.append(f"New Preorder Items: {new_preorder_count}")
    preorder_log_entries.append(f"Updated Preorder Items: {updated_preorder_count}")
    preorder_log_entries.append(f"Released Preorder Items: {len(released_items)}")

    with open(log_path, 'w', encoding='utf-8') as log_file:
        log_file.write('\n'.join(preorder_log_entries))

    return released_items

def is_preorder_or_future_pub(product_details):
    """
    Checks if a product is preorder or has future pub date
    """
    if not product_details:
        return False, None
        
    # Check if in Preorder collection
    is_preorder = 'Preorder' in product_details.get('collections', [])
    
    # Check pub date
    pub_date_str = product_details.get('pub_date')
    if pub_date_str:
        try:
            pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d').date()
            is_future = pub_date > datetime.now().date()
            if is_future:
                return True, f'Future Pub Date: {pub_date_str}'
        except ValueError:
            logging.error(f"Invalid pub date format: {pub_date_str}")
    
    if is_preorder:
        return True, 'Preorder Collection'
        
    return False, None

def process_refunds(order):
    """
    Process refunds for an order
    """
    refunded_quantities = {}
    refunds = order.get('refunds', [])
    for refund in refunds:
        refund_line_items = refund.get('refundLineItems', {}).get('edges', [])
        for refund_item in refund_line_items:
            refund_node = refund_item['node']
            quantity = refund_node['quantity']
            line_item = refund_node.get('lineItem', {})
            variant = line_item.get('variant')
            
            if variant and variant.get('barcode'):
                barcode = variant['barcode']
                if barcode not in refunded_quantities:
                    refunded_quantities[barcode] = 0
                refunded_quantities[barcode] += quantity
                
    return refunded_quantities

def aggregate_sales(orders):
    """
    Aggregates sales data using two-phase approach
    Now includes tracking of preorder items
    """
    sales_data = {}
    skipped_line_items = []
    preorder_items = []  # New list to track preorder items
    
    # First collect all unique product IDs
    product_ids = set()
    for order in orders:
        if order.get('cancelledAt'):
            continue
            
        for line_item in order.get('lineItems', {}).get('edges', []):
            variant = line_item['node'].get('variant')
            if variant and variant.get('product', {}).get('id'):
                product_ids.add(variant['product']['id'])
    
    # Fetch product details
    logging.info(f"Fetching details for {len(product_ids)} products")
    product_details = fetch_product_details(list(product_ids))
    
    # Process orders with product details
    for order in orders:
        if order.get('cancelledAt'):
            continue
            
        order_id = order['id']
        refunded_quantities = process_refunds(order)
        
        for line_item in order.get('lineItems', {}).get('edges', []):
            line_item_node = line_item['node']
            quantity = line_item_node['quantity']
            variant = line_item_node.get('variant')
            
            if not variant:
                skipped_line_items.append({
                    'order_id': order_id,
                    'product_name': line_item_node.get('name', 'Unknown'),
                    'quantity': quantity,
                    'reason': 'No variant information'
                })
                continue
            
            barcode = variant.get('barcode')
            if not barcode:
                skipped_line_items.append({
                    'order_id': order_id,
                    'product_name': line_item_node.get('name', 'Unknown'),
                    'barcode': 'N/A',
                    'quantity': quantity,
                    'reason': 'No barcode'
                })
                continue
            
            if not is_valid_isbn(barcode):
                skipped_line_items.append({
                    'order_id': order_id,
                    'product_name': line_item_node.get('name', 'Unknown'),
                    'barcode': barcode,
                    'quantity': quantity,
                    'reason': 'Not an ISBN (does not start with 978 or 979)'
                })
                continue
            
            # Check preorder status using product details
            product = variant.get('product', {})
            product_id = product.get('id')
            details = product_details.get(product_id, {})
            
            is_excluded, reason = is_preorder_or_future_pub(details)
            if is_excluded:
                # If it's a preorder or future pub, track it
                if reason == 'Preorder Collection' or reason.startswith('Future Pub Date'):
                    preorder_items.append({
                        'barcode': barcode,
                        'title': product.get('title', 'Unknown'),
                        'quantity': quantity,
                        'pub_date': details.get('pub_date')  # This might be None, which is okay
                    })
                
                skipped_line_items.append({
                    'order_id': order_id,
                    'product_name': product.get('title', 'Unknown'),
                    'barcode': barcode,
                    'quantity': quantity,
                    'reason': reason
                })
                continue
            
            # Calculate final quantity after refunds
            refunded_qty = refunded_quantities.get(barcode, 0)
            final_qty = quantity - refunded_qty
            
            if final_qty > 0:
                sales_data[barcode] = sales_data.get(barcode, 0) + final_qty
    
    return sales_data, skipped_line_items, preorder_items

def export_skipped_line_items(skipped_line_items, filename):
    """
    Exports skipped line items to a CSV file with additional details.
    """
    output_dir = os.path.join(BASE_DIR, 'output')
    os.makedirs(output_dir, exist_ok=True)
    abs_path = os.path.join(output_dir, filename)
    
    logging.info(f"Exporting skipped items to CSV at path: {abs_path}")
    
    with open(abs_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Order ID', 'Product Name', 'Barcode/ISBN', 'Quantity', 'Reason'])
        for item in skipped_line_items:
            writer.writerow([
                item['order_id'],
                item['product_name'],
                item.get('barcode', 'N/A'),  # Add barcode if available
                item['quantity'],
                item['reason']
            ])

def export_to_csv(sales_data, filename):
    """
    Exports the sales data to a CSV file.
    """
    output_dir = os.path.join(BASE_DIR, 'output')
    os.makedirs(output_dir, exist_ok=True)
    abs_path = os.path.join(output_dir, filename)
    
    logging.info(f"Exporting to CSV at path: {abs_path}")
    
    with open(abs_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ISBN', 'QTY'])
        for barcode, qty in sales_data.items():
            writer.writerow([barcode, qty])

def send_email(report_filename, skipped_filename, preorder_filename, start_date, end_date, skipped_items):
    """
    Sends the report as an email attachment using SendGrid.
    Now includes preorder tracking report
    """
    api_key = os.getenv('SENDGRID_API_KEY')
    sender_email = os.getenv('EMAIL_SENDER')
    recipient_emails = os.getenv('EMAIL_RECIPIENTS').split(',')

    if not api_key or not sender_email or not recipient_emails:
        logging.error("Error: Missing email configuration.")
        return

    output_dir = os.path.join(BASE_DIR, 'output')
    abs_report_path = os.path.join(output_dir, report_filename)
    abs_skipped_path = os.path.join(output_dir, skipped_filename)
    abs_preorder_path = os.path.join(output_dir, preorder_filename)

    # Create summary of skipped items
    skipped_summary = {}
    for item in skipped_items:
        reason = item['reason']
        if reason not in skipped_summary:
            skipped_summary[reason] = 0
        skipped_summary[reason] += item['quantity']

    email_content = f"""NYT Bestseller Weekly Report
Report Period: Sunday {start_date} through Saturday {end_date}

REPORT DEFINITIONS:
- This report includes all completed sales of ISBN products (barcodes starting with '978' or '979')
- Quantities reflect final sales after any refunds or cancellations
- Each line includes the ISBN and the total quantity sold

ITEMS NOT INCLUDED IN REPORT:
"""
    for reason, quantity in skipped_summary.items():
        email_content += f"- {quantity} items: {reason}\n"

    email_content += "\nAttached files:\n"
    email_content += f"1. {report_filename} - NYT Bestseller sales report\n"
    email_content += f"2. {skipped_filename} - Detailed list of excluded items\n"
    email_content += f"3. {preorder_filename} - Preorder tracking log\n"

    sg = sendgrid.SendGridAPIClient(api_key)
    subject = f"NYT Bestseller Weekly Report ({start_date} to {end_date})"

    message = Mail(
        from_email=sender_email,
        to_emails=recipient_emails,
        subject=subject,
        plain_text_content=email_content
    )

    # Attach main report
    try:
        with open(abs_report_path, 'rb') as f:
            report_data = f.read()
            encoded_file = base64.b64encode(report_data).decode()
            attachment = Attachment(
                FileContent(encoded_file),
                FileName(report_filename),
                FileType('text/csv'),
                Disposition('attachment')
            )
            message.add_attachment(attachment)
    except Exception as e:
        logging.error(f"Error attaching main report: {e}")
        return

    # Attach excluded items report
    try:
        with open(abs_skipped_path, 'rb') as f:
            skipped_data = f.read()
            encoded_file = base64.b64encode(skipped_data).decode()
            attachment = Attachment(
                FileContent(encoded_file),
                FileName(skipped_filename),
                FileType('text/csv'),
                Disposition('attachment')
            )
            message.add_attachment(attachment)
    except Exception as e:
        logging.error(f"Error attaching excluded items report: {e}")
        return

    # Attach preorder tracking report
    try:
        with open(abs_preorder_path, 'rb') as f:
            preorder_data = f.read()
            encoded_file = base64.b64encode(preorder_data).decode()
            attachment = Attachment(
                FileContent(encoded_file),
                FileName(preorder_filename),
                FileType('text/csv'),
                Disposition('attachment')
            )
            message.add_attachment(attachment)
    except Exception as e:
        logging.error(f"Error attaching preorder tracking report: {e}")
        return

    try:
        response = sg.send(message)
        logging.info(f"Email sent! Status: {response.status_code}")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

def get_last_week_date_range():
    """
    Returns the date range for last week (Sunday through Saturday)
    For a report run on Monday Feb 3rd, 2025, this should return:
    Sunday Jan 26th through Saturday Feb 1st
    """
    today = datetime.now()
    
    # First, find the most recent Saturday (Feb 1st in our example)
    days_after_saturday = today.weekday() + 2  # Adding 2 because Sunday is 6 and we want to include the previous Saturday
    last_saturday = today - timedelta(days=days_after_saturday)
    
    # Then get the Sunday before that Saturday (Jan 26th in our example)
    last_sunday = last_saturday - timedelta(days=6)
    
    # Set times to ensure full day coverage
    last_sunday = last_sunday.replace(hour=0, minute=0, second=0, microsecond=0)
    last_saturday = last_saturday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return last_sunday.strftime('%Y-%m-%d'), last_saturday.strftime('%Y-%m-%d')

def validate_sales_data(sales_data, skipped_items):
    """
    Performs basic validation checks on sales data
    Returns a list of warnings if any issues are found
    """
    warnings = []
    
    # Basic volume checks
    total_quantity = sum(sales_data.values())
    if total_quantity == 0:
        warnings.append("WARNING: No sales recorded for this period")
    
    # ISBN format check
    invalid_isbns = [isbn for isbn in sales_data.keys() 
                    if not (str(isbn).startswith('978') or str(isbn).startswith('979'))]
    if invalid_isbns:
        warnings.append(f"WARNING: Found {len(invalid_isbns)} invalid ISBNs in sales data")
    
    # Unusual quantities check (more than 1000 of any single ISBN)
    large_quantities = [(isbn, qty) for isbn, qty in sales_data.items() if qty > 1000]
    if large_quantities:
        warnings.append(f"WARNING: Unusually large quantities found for {len(large_quantities)} ISBNs")
        for isbn, qty in large_quantities:
            warnings.append(f"         ISBN: {isbn}, Quantity: {qty}")
    
    # Check for negative quantities
    negative_quantities = [(isbn, qty) for isbn, qty in sales_data.items() if qty < 0]
    if negative_quantities:
        warnings.append(f"WARNING: Found {len(negative_quantities)} ISBNs with negative quantities")
    
    # Basic skipped items analysis
    if len(skipped_items) > 100:  # Arbitrary threshold
        warnings.append(f"WARNING: Large number of skipped items: {len(skipped_items)}")
    
    return warnings

def main():
    print(f"Script running from directory: {os.getcwd()}")
    print(f"BASE_DIR set to: {BASE_DIR}")
    print(f"Python version: {sys.version}")

    load_environment()

    # Automatically determine last week's date range
    start_date, end_date = get_last_week_date_range()
    print(f"Generating report for: {start_date} to {end_date}")

    global SHOP_URL, GRAPHQL_URL, HEADERS
    SHOP_URL = os.getenv('SHOP_URL')
    ACCESS_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')

    if not SHOP_URL or not ACCESS_TOKEN:
        logging.error("Error: Missing SHOP_URL or SHOPIFY_ACCESS_TOKEN.")
        return

    GRAPHQL_URL = f"https://{SHOP_URL}/admin/api/2025-01/graphql.json"
    HEADERS = {"Content-Type": "application/json", "X-Shopify-Access-Token": ACCESS_TOKEN}

    orders = fetch_orders(start_date, end_date)
    if not orders:
        logging.error("No orders found.")
        return

    sales_data, skipped_items, preorder_items = aggregate_sales(orders)
    if not sales_data:
        logging.error("No sales data.")
        return

    # Track preorder sales
    released_items = track_preorder_sales(preorder_items)

    logging.info(f"Tracking {len(preorder_items)} new preorder items")
    logging.info(f"Released items this week: {len(released_items)}")
    
    # Add released items to sales_data
    for isbn, quantity in released_items.items():
        sales_data[isbn] = sales_data.get(isbn, 0) + quantity

    # Run validations
    warnings = validate_sales_data(sales_data, skipped_items)

    # Create email content
    email_content = f"""Weekly Shopify Sales Report
Report Period: {start_date} to {end_date}

REPORT DEFINITIONS:
- This report includes all completed sales of ISBN products (barcodes starting with '978')
- Quantities reflect final sales after any refunds or cancellations
- Each line includes the ISBN and the total quantity sold

"""

    # Add warnings if any exist
    if warnings:
        email_content += "\nVALIDATION WARNINGS:\n"
        for warning in warnings:
            email_content += f"{warning}\n"
            logging.warning(warning)  # Also log the warnings

    # Add preorder tracking details to email
    email_content += "\nPREORDER TRACKING:\n"
    if preorder_items:
        email_content += f"Total Preorder Items Tracked: {len(preorder_items)}\n"
        preorder_summary = {}
        for item in preorder_items:
            title = item['title']
            if title not in preorder_summary:
                preorder_summary[title] = 0
            preorder_summary[title] += item['quantity']
        
        for title, qty in preorder_summary.items():
            email_content += f"- {title}: {qty} preorder copies\n"
    else:
        email_content += "No preorder items tracked this week.\n"

    # If there are any released items
    if released_items:
        email_content += "\nRELEASED PREORDER ITEMS:\n"
        for isbn, qty in released_items.items():
            email_content += f"- ISBN {isbn}: {qty} copies now included in sales report\n"

    report_filename = f"NYT_weekly_sales_report_{datetime.now().strftime('%Y-%m-%d')}.csv"
    skipped_filename = f"NYT_excluded_items_{datetime.now().strftime('%Y-%m-%d')}.csv"
    preorder_filename = f"NYT_preorder_tracking_{datetime.now().strftime('%Y-%m-%d')}.csv"


    export_to_csv(sales_data, report_filename)
    export_skipped_line_items(skipped_items, skipped_filename)

    output_dir = os.path.join(BASE_DIR, 'output')
    report_path = os.path.join(output_dir, report_filename)
    skipped_path = os.path.join(output_dir, skipped_filename)

    # Verify environment
    logging.info("=== Environment Verification ===")
    logging.info(f"Python Version: {sys.version}")
    logging.info(f"Current Directory: {os.getcwd()}")
    logging.info(f"Output Directory: {os.path.join(BASE_DIR, 'output')}")
    
    # Verify date calculations
    start_date, end_date = get_last_week_date_range()
    logging.info("=== Date Range Verification ===")
    logging.info(f"Report Period: {start_date} to {end_date}")
    logging.info(f"Current time: {datetime.now()}")

    logging.info(f"Report generated: {report_path}")
    logging.info(f"Skipped items logged: {skipped_path}")
    logging.info(f"Current working directory (BASE_DIR): {BASE_DIR}")

     # Verify files exist before sending
    for filename in [report_filename, skipped_filename, preorder_filename]:
        file_path = os.path.join(output_dir, filename)
        if os.path.exists(file_path):
            logging.info(f"Verified file exists: {filename}")
        else:
            logging.error(f"Missing file: {filename}")

    send_email(
        report_filename,
        skipped_filename,
        preorder_filename,
        start_date,
        end_date,
        skipped_items
    )

if __name__ == "__main__":
    main()