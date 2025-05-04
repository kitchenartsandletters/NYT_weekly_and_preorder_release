# DEPRECATED
#!/usr/bin/env python
"""
Test script to verify directory structure and file paths for preorder history
"""
import os
import sys
import json
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def verify_paths():
    """Verify all required paths and create if missing"""
    # Get base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    logging.info(f"Base directory: {base_dir}")
    
    # Expected directories
    directories = ['preorders', 'output', 'overrides']
    for directory in directories:
        dir_path = os.path.join(base_dir, directory)
        if not os.path.exists(dir_path):
            logging.info(f"Creating missing directory: {dir_path}")
            os.makedirs(dir_path, exist_ok=True)
        else:
            logging.info(f"Directory exists: {dir_path}")
    
    # Check for preorder history file
    history_file = os.path.join(base_dir, 'preorders', 'preorder_history.json')
    if os.path.exists(history_file):
        logging.info(f"History file exists: {history_file}")
        try:
            with open(history_file, 'r') as f:
                history_data = json.load(f)
                report_count = len(history_data.get('reported_preorders', []))
                logging.info(f"History file contains {report_count} reported preorders")
        except Exception as e:
            logging.error(f"Error reading history file: {e}")
    else:
        logging.warning(f"History file not found: {history_file}")
        
        # Create a simple template file if missing
        logging.info("Creating template history file")
        history_data = {
            "reported_preorders": [],
            "last_updated": "2025-03-17T00:00:00.000000"
        }
        try:
            with open(history_file, 'w') as f:
                json.dump(history_data, f, indent=2)
            logging.info(f"Created template history file at: {history_file}")
        except Exception as e:
            logging.error(f"Failed to create template history file: {e}")
    
    # Check for test approved_releases files
    output_dir = os.path.join(base_dir, 'output')
    approval_files = [f for f in os.listdir(output_dir) if f.startswith('approved_releases_') and f.endswith('.json')]
    logging.info(f"Found {len(approval_files)} approval files in output directory")
    for file in approval_files:
        logging.info(f"  - {file}")

if __name__ == "__main__":
    logging.info("Starting directory and file path verification")
    verify_paths()
    logging.info("Verification complete")