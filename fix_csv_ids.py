# DEPRECATED: This script is deprecated. Use the new script instead.

import csv

input_file = 'preorders/NYT_preorder_tracking.csv'
output_file = 'preorders/NYT_preorder_tracking.csv'

# Read the existing data
rows = []
with open(input_file, 'r', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        rows.append(row)

# Replace line item IDs for rows where Order ID starts with 'manual-'
counter = 1
for row in rows:
    if row['Order ID'].startswith('manual-'):
        row['Line Item ID'] = f'line-manual-{counter:03d}'
        counter += 1

# Write back to the same file
with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
    fieldnames = rows[0].keys()
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print("✅ Successfully updated Line Item IDs for manual orders.")