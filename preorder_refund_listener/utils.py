"""
Helper functions for loading history, deduplication, and writing logs
"""
import csv, json, os
def load_preorder_history(path=None):
    """
    Load the preorder history JSON file, creating it with empty data if it doesn't exist.
    """
    if path is None:
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'preorders', 'preorder_history.json'))
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"reported_preorders": []}, f)

    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def append_refund_to_tracking(refund_record, tracking_path=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'preorders', 'NYT_preorder_tracking.csv'))):
    # refund_record: dict with ISBN, Title, Pub Date, Quantity (negative), Order ID, Line Item ID
    file_exists = os.path.exists(tracking_path)
    fieldnames = ['ISBN','Title','Pub Date','Quantity','Status','Order ID','Line Item ID']
    with open(tracking_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(refund_record)


def has_been_logged(order_id, line_item_id, log_path=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'preorders', 'preorder_refund_log.csv'))):
    """
    Check if a refund for this order_id and line_item_id has already been logged.
    """
    if not os.path.exists(log_path):
        return False
    with open(log_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('Order ID') == str(order_id) and row.get('Line Item ID') == str(line_item_id):
                return True
    return False

def process_refund_event(payload):
    """
    Process Shopify refund webhook payload:
    - Skip titles already released (based on preorder_history.json)
    - Deduplicate by order_id + line_item_id
    - Append a negative-quantity row to the preorder tracking CSV
    - Log the refund event to the audit log CSV
    """
    # Load released ISBNs
    history = load_preorder_history()
    released_isbns = {entry['isbn'] for entry in history.get('reported_preorders', [])}

    order_id = payload.get('id') or payload.get('order_id')
    refunds = payload.get('refunds' , [])
    processed_count = 0

    for refund in refunds:
        for line in refund.get('refund_line_items', []):
            line_item = line.get('line_item', {})
            isbn = (line_item.get('barcode') or '').strip()
            # Skip if no ISBN or title already released
            if not isbn or isbn in released_isbns:
                continue

            line_item_id = line.get('line_item_id')
            qty = line.get('quantity', 0)
            # Only process positive refund quantities
            if qty <= 0:
                continue

            record = {
                'ISBN': isbn,
                'Title': line_item.get('title', '').strip(),
                'Pub Date': '',
                'Quantity': -qty,
                'Status': 'Refund',
                'Order ID': order_id,
                'Line Item ID': line_item_id
            }

            # Deduplication
            if has_been_logged(order_id, line_item_id, log_path=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'preorders', 'preorder_refund_log.csv'))):
                continue

            # Append to tracking ledger and audit log
            append_refund_to_tracking(record, tracking_path=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'preorders', 'NYT_preorder_tracking.csv')))
            log_refund(record, log_path=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'preorders', 'preorder_refund_log.csv')))
            processed_count += 1

    return processed_count


# Audit log for refunds (same schema as append_refund_to_tracking)
def log_refund(refund_record, log_path=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'preorders', 'preorder_refund_log.csv'))):
    """
    Append a refund record to the refund audit log CSV.
    """
    file_exists = os.path.exists(log_path)
    fieldnames = ['ISBN', 'Title', 'Pub Date', 'Quantity', 'Status', 'Order ID', 'Line Item ID']
    with open(log_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(refund_record)

def run_mock_refund_test():
    """
    Run a mock test for refund processing with a test payload.
    This is used for local testing only and not called in production.
    """
    test_payload = {
        "id": 1234567890,
        "refunds": [
            {
                "refund_line_items": [
                    {
                        "line_item": {
                            "barcode": "9781234567890",
                            "title": "Test Book Title"
                        },
                        "line_item_id": 987654321,
                        "quantity": 1
                    }
                ]
            }
        ]
    }

    print("Running mock refund test...")
    result = process_refund_event(test_payload)
    print(f"Processed {result} refund(s)")
    
if __name__ == "__main__":
    run_mock_refund_test()