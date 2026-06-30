import os
import requests
import json
from datetime import datetime, timedelta

PESAPAL_ENV = os.environ.get('PESAPAL_ENV', 'production')
CONSUMER_KEY = os.environ.get('PESAPAL_CONSUMER_KEY', 'your_consumer_key')
CONSUMER_SECRET = os.environ.get('PESAPAL_CONSUMER_SECRET', 'your_consumer_secret')

# Base URL for Pesapal V3
BASE_URL = "https://pay.pesapal.com/v3" if PESAPAL_ENV == 'production' else "https://cybqa.pesapal.com/pesapalv3"

# In-memory token cache to respect the 5-minute expiry without pinging DB
_token_cache = {
    'token': None,
    'expires_at': None
}

def get_pesapal_token():
    """Generates or retrieves a valid OAuth2 Bearer token."""
    now = datetime.now()
    
    # Return cached token if valid (buffer of 30 seconds)
    if _token_cache['token'] and _token_cache['expires_at'] and now < (_token_cache['expires_at'] - timedelta(seconds=30)):
        return _token_cache['token']
        
    url = f"{BASE_URL}/api/Auth/RequestToken"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "consumer_key": CONSUMER_KEY,
        "consumer_secret": CONSUMER_SECRET
    }
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        data = response.json()
        token = data.get('token')
        expiry_minutes = 5 # Pesapal default
        
        _token_cache['token'] = token
        _token_cache['expires_at'] = now + timedelta(minutes=expiry_minutes)
        return token
    else:
        raise Exception(f"Pesapal Auth Error: {response.text}")

def submit_order_request(amount, currency, email, phone, first_name, last_name, reference, description, callback_url, ipn_id):
    """Submits a transaction order to Pesapal and returns the redirect URL for the iframe."""
    token = get_pesapal_token()
    
    url = f"{BASE_URL}/api/Transactions/SubmitOrderRequest"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    payload = {
        "id": reference,
        "currency": currency,
        "amount": amount,
        "description": description,
        "callback_url": callback_url,
        "notification_id": ipn_id,
        "billing_address": {
            "email_address": email,
            "phone_number": phone,
            "country_code": "ZW", # Defaulting to Zimbabwe for ZIMBOT, adjust as needed
            "first_name": first_name,
            "middle_name": "",
            "last_name": last_name,
            "line_1": "",
            "line_2": "",
            "city": "",
            "state": "",
            "postal_code": "",
            "zip_code": ""
        }
    }
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if data.get('status') == '200' and 'redirect_url' in data:
            return data
        else:
            raise Exception(f"Pesapal Error Status: {data.get('error', data)}")
    else:
        raise Exception(f"Pesapal Order Submit Error: {response.text}")

def get_transaction_status(order_tracking_id):
    """Verifies the IPN ping by querying Pesapal for the actual transaction status."""
    token = get_pesapal_token()
    
    url = f"{BASE_URL}/api/Transactions/GetTransactionStatus?orderTrackingId={order_tracking_id}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Pesapal Status Check Error: {response.text}")
