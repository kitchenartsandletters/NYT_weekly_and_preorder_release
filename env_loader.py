"""
Enhanced environment variable loading module for the Shopify reporting system
This module provides more robust environment variable handling with better fallbacks and validation
"""
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

def find_env_file(filename='.env.production', search_dirs=None):
    """
    Find the environment file by searching in multiple possible locations
    """
    if search_dirs is None:
        # Define search paths - start with current directory and work up
        search_dirs = [
            os.getcwd(),  # Current working directory
            os.path.dirname(os.path.abspath(__file__)),  # Script directory
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # Parent directory
            str(Path.home())  # User's home directory as a last resort
        ]
    
    for directory in search_dirs:
        env_path = os.path.join(directory, filename)
        if os.path.isfile(env_path):
            logging.info(f"Found environment file at: {env_path}")
            return env_path
    
    logging.warning(f"Could not find environment file {filename} in any of the search paths")
    return None

def load_environment_variables(env_file=None, required_vars=None):
    """
    Load environment variables from .env file with validation and fallbacks
    
    Args:
        env_file: Path to environment file (will search if None)
        required_vars: List of required environment variable names
        
    Returns:
        dict: Environment variables and their values
    """
    if required_vars is None:
        required_vars = [
            'SHOP_URL', 
            'SHOPIFY_ACCESS_TOKEN',
            'SENDGRID_API_KEY',
            'EMAIL_SENDER',
            'EMAIL_RECIPIENTS'
        ]
    
    # Dictionary to store environment variables
    env_vars = {}
    
    # Try to find and load the environment file
    if env_file is None:
        env_file = find_env_file()
    
    if env_file and os.path.exists(env_file):
        # Load variables from the .env file
        logging.info(f"Loading environment from: {env_file}")
        load_dotenv(env_file)
        
        # Display file contents for debugging (without sensitive values)
        try:
            with open(env_file, 'r') as f:
                file_contents = f.read()
                # Mask sensitive values
                masked_contents = []
                for line in file_contents.splitlines():
                    if '=' in line:
                        key, value = line.split('=', 1)
                        if any(sensitive in key.lower() for sensitive in ['token', 'key', 'secret', 'password']):
                            masked_contents.append(f"{key}=********")
                        else:
                            masked_contents.append(line)
                    else:
                        masked_contents.append(line)
                
                logging.debug(f"Environment file contents (sensitive values masked):\n{''.join(masked_contents)}")
        except Exception as e:
            logging.warning(f"Could not read environment file for debugging: {e}")
    else:
        logging.warning("No environment file found, using only existing environment variables")
    
    # Check for required variables
    all_ok = True
    for var in required_vars:
        value = os.environ.get(var)
        env_vars[var] = value
        
        if value:
            # Mask sensitive values in logs
            if any(sensitive in var.lower() for sensitive in ['token', 'key', 'secret', 'password']):
                logging.info(f"✓ {var} is set (value masked)")
            else:
                logging.info(f"✓ {var} = {value}")
        else:
            logging.error(f"✗ {var} is not set or is empty")
            all_ok = False
    
    # Check for test mode
    if os.environ.get('USE_TEST_DATA', '').lower() in ('true', '1', 't', 'yes'):
        env_vars['USE_TEST_DATA'] = True
        logging.info("🧪 Running in TEST DATA mode - no API connections will be made")
        # In test mode, we don't strictly need the API credentials
        all_ok = True
    else:
        env_vars['USE_TEST_DATA'] = False
    
    # Log summary
    if all_ok:
        logging.info("✅ All required environment variables are set")
    else:
        logging.error("❌ Some required environment variables are missing")
        if not env_vars.get('USE_TEST_DATA'):
            logging.info("💡 Set USE_TEST_DATA=true to run in test mode without API credentials")
    
    return env_vars

def initialize_api_credentials():
    """
    Initialize the Shopify API credentials and return properly formatted URL and headers
    """
    env_vars = load_environment_variables()
    
    if env_vars.get('USE_TEST_DATA'):
        # Return dummy values for test mode
        return {
            'GRAPHQL_URL': 'https://test-shop.myshopify.com/admin/api/2025-01/graphql.json',
            'HEADERS': {"Content-Type": "application/json", "X-Shopify-Access-Token": "test-token"},
            'TEST_MODE': True
        }
    
    shop_url = env_vars.get('SHOP_URL')
    access_token = env_vars.get('SHOPIFY_ACCESS_TOKEN')
    
    if not shop_url or not access_token:
        logging.error("Missing required API credentials. Cannot initialize API.")
        return None
    
    # Validate shop URL format
    if not shop_url.startswith(('http://', 'https://')):
        shop_url = f"https://{shop_url}"
    
    # Remove trailing slash if present
    if shop_url.endswith('/'):
        shop_url = shop_url[:-1]
    
    graphql_url = f"{shop_url}/admin/api/2025-01/graphql.json"
    headers = {"Content-Type": "application/json", "X-Shopify-Access-Token": access_token}
    
    logging.info(f"API initialized with URL: {graphql_url}")
    
    return {
        'GRAPHQL_URL': graphql_url,
        'HEADERS': headers,
        'TEST_MODE': False
    }

# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    api_config = initialize_api_credentials()
    if api_config and not api_config.get('TEST_MODE'):
        print(f"Ready to connect to: {api_config['GRAPHQL_URL']}")
    elif api_config and api_config.get('TEST_MODE'):
        print("Running in test mode with dummy API configuration")
    else:
        print("Failed to initialize API configuration")