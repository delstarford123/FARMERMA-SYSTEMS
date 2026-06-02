import os
import requests
from dotenv import load_dotenv

# Ensure environment variables are loaded if a .env file exists
load_dotenv()

def get_pesapal_token():
    """Authenticates with PesaPal v3 and returns a Bearer Token."""
    consumer_key = os.environ.get('PESAPAL_CONSUMER_KEY')
    consumer_secret = os.environ.get('PESAPAL_CONSUMER_SECRET')
    env = os.environ.get('PESAPAL_ENV', 'sandbox').lower()
    
    if not consumer_key or not consumer_secret:
        print("[ERROR] PesaPal credentials missing from environment variables (PESAPAL_CONSUMER_KEY/SECRET)")
        return None

    base_url = "https://pay.pesapal.com/v3" if env == 'production' else "https://cybqa.pesapal.com/pesapalv3"
    api_url = f"{base_url}/api/Auth/RequestToken"
    
    payload = {
        "consumer_key": consumer_key,
        "consumer_secret": consumer_secret
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    try:
        r = requests.post(api_url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        res_data = r.json()
        if res_data.get('status') == '200' or 'token' in res_data:
            return res_data.get('token')
        print(f"[ERROR] PesaPal Auth Failed: {res_data}")
        return None
    except Exception as e:
        print(f"[ERROR] Error authenticating with PesaPal: {e}")
        return None

def register_pesapal_ipn(token, ipn_url):
    """Registers the Instant Payment Notification (IPN) webhook URL with PesaPal."""
    env = os.environ.get('PESAPAL_ENV', 'sandbox').lower()
    base_url = "https://pay.pesapal.com/v3" if env == 'production' else "https://cybqa.pesapal.com/pesapalv3"
    
    api_url = f"{base_url}/api/URLSetup/RegisterIPN"
    payload = {
        "url": ipn_url,
        "ipn_notification_type": "GET"
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    try:
        r = requests.post(api_url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[ERROR] Error registering PesaPal IPN: {e}")
        return None

def submit_pesapal_order(token, order_reference, amount, currency, description, callback_url, ipn_id, email, phone, first_name, last_name):
    """Submits a checkout order to PesaPal and returns the redirection details."""
    env = os.environ.get('PESAPAL_ENV', 'sandbox').lower()
    base_url = "https://pay.pesapal.com/v3" if env == 'production' else "https://cybqa.pesapal.com/pesapalv3"
    
    api_url = f"{base_url}/api/Transactions/SubmitOrderRequest"
    
    # Sanitize phone numbers - PesaPal prefers digits or local format
    phone_sanitized = str(phone).strip().replace('+', '')
    
    payload = {
        "id": str(order_reference),
        "currency": str(currency),
        "amount": float(amount),
        "description": str(description)[:100], # Keep description reasonably concise
        "callback_url": str(callback_url),
        "notification_id": str(ipn_id),
        "billing_address": {
            "email_address": email,
            "phone_number": phone_sanitized,
            "country_code": "KE",
            "first_name": first_name or "Valued",
            "last_name": last_name or "Farmer"
        }
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    try:
        r = requests.post(api_url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[ERROR] Error submitting PesaPal Order: {e}")
        # Try to print response body for debugging
        try:
            print(f"[ERROR] Response Text: {r.text}")
        except NameError:
            pass
        return None

def get_pesapal_transaction_status(token, order_tracking_id):
    """Queries PesaPal to obtain the final status of a transaction."""
    env = os.environ.get('PESAPAL_ENV', 'sandbox').lower()
    base_url = "https://pay.pesapal.com/v3" if env == 'production' else "https://cybqa.pesapal.com/pesapalv3"
    
    api_url = f"{base_url}/api/Transactions/GetTransactionStatus?orderTrackingId={order_tracking_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    try:
        print(f"[INFO] Checking PesaPal status for Tracking ID: {order_tracking_id}")
        r = requests.get(api_url, headers=headers, timeout=15)
        r.raise_for_status()
        res_data = r.json()
        print(f"[INFO] PesaPal Status Response: {res_data.get('payment_status_description')} for {order_tracking_id}")
        return res_data
    except Exception as e:
        print(f"[ERROR] Error checking PesaPal transaction status ({order_tracking_id}): {e}")
        return None
