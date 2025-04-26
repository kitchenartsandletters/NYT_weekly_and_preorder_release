import os
import csv
import logging
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
preorder_dir = os.path.join(BASE_DIR, 'preorders')
output_dir = os.path.join(BASE_DIR, 'output')

current_file = os.path.join(preorder_dir, 'NYT_preorder_tracking.csv')
backup_file = os.path.join(preorder_dir, 'NYT_preorder_tracking.csv.bak')
delta_output = os.path.join(output_dir, f'delta_log_{datetime.today().strftime("%Y-%m-%d")}.csv')

def load_csv_as_dict(filepath):
    entries = {}
    if not os.path.exists(filepath):
        logging.warning(f"File not found: {filepath}")
        return entries

    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            isbn = row.get('ISBN')
            if isbn:
                quantity = int(row.get('Quantity', 0))
                if isbn in entries:
                    entries[isbn]['Quantity'] += quantity
                else:
                    entries[isbn] = {
                        'Title': row.get('Title', ''),
                        'Pub Date': row.get('Pub Date', ''),
                        'Quantity': quantity
                    }
    return entries

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    current = load_csv_as_dict(current_file)
    previous = load_csv_as_dict(backup_file)

    if not current:
        logging.error("Current tracking file missing or empty. Aborting.")
        return

    changes = []

    # Check for additions and updates
    for isbn, row in current.items():
        if isbn not in previous:
            changes.append(["Added", isbn, row.get('Title', ''), row.get('Pub Date', ''), "0", str(row.get('Quantity', 0))])
        else:
            prev_qty = int(previous[isbn].get('Quantity', 0))
            curr_qty = int(row.get('Quantity', 0))
            if prev_qty != curr_qty:
                changes.append(["Updated", isbn, row.get('Title', ''), row.get('Pub Date', ''), str(prev_qty), str(curr_qty)])

    # Check for removals
    for isbn, row in previous.items():
        if isbn not in current:
            changes.append(["Removed", isbn, row.get('Title', ''), row.get('Pub Date', ''), str(row.get('Quantity', 0)), "0"])

    if not changes:
        logging.info("No changes detected between backup and current preorder tracking.")
        return

    # Write the delta log
    os.makedirs(output_dir, exist_ok=True)
    with open(delta_output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Change Type", "ISBN", "Title", "Pub Date", "Previous Quantity", "Current Quantity"])
        writer.writerows(changes)

    logging.info(f"Delta log written to {delta_output}")

if __name__ == "__main__":
    main()