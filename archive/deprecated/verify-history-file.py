# DEPRECATED
#!/usr/bin/env python
"""
Quick script to verify preorder history file and fix if needed
"""
import os
import sys
import json
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def verify_history_file():
    """Verify preorder history file and fix if needed"""
    # Get base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    history_file = os.path.join(base_dir, 'preorders', 'preorder_history.json')
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    
    # Check if file exists and is valid
    is_valid = False
    history_data = None
    
    if os.path.exists(history_file):
        logging.info(f"History file exists: {history_file}")
        try:
            with open(history_file, 'r') as f:
                history_data = json.load(f)
            
            # Validate expected structure
            if 'reported_preorders' in history_data and isinstance(history_data['reported_preorders'], list):
                report_count = len(history_data['reported_preorders'])
                logging.info(f"History file contains {report_count} reported preorders")
                is_valid = True
            else:
                logging.warning("History file is missing expected structure")
        except json.JSONDecodeError:
            logging.error("History file contains invalid JSON")
        except Exception as e:
            logging.error(f"Error reading history file: {e}")
    else:
        logging.warning(f"History file not found: {history_file}")
    
    # Fix or create the file if needed
    if not is_valid:
        # Create a valid template file
        logging.info("Creating/fixing history file")
        history_data = {
            "reported_preorders": [],
            "last_updated": datetime.now().isoformat()
        }
        
        # If we had an existing file with some data, try to preserve it
        if history_data and 'reported_preorders' in history_data and history_data['reported_preorders']:
            try:
                valid_preorders = []
                for preorder in history_data['reported_preorders']:
                    if isinstance(preorder, dict) and 'isbn' in preorder and 'quantity' in preorder:
                        valid_preorders.append(preorder)
                
                if valid_preorders:
                    logging.info(f"Preserving {len(valid_preorders)} valid preorder entries")
                    history_data['reported_preorders'] = valid_preorders
            except Exception as e:
                logging.error(f"Error preserving preorder data: {e}")
        
        # Write the fixed file
        try:
            with open(history_file, 'w') as f:
                json.dump(history_data, f, indent=2)
            logging.info(f"Created/fixed history file at: {history_file}")
        except Exception as e:
            logging.error(f"Failed to create/fix history file: {e}")
    
    return is_valid

if __name__ == "__main__":
    logging.info("Verifying preorder history file")
    verify_history_file()
    logging.info("Verification complete")