import os
import requests
import base64
from datetime import datetime
from dotenv import load_dotenv

# Load secret variables from .env
load_dotenv()

# --- SECURE CONFIGURATION ---
# Pulling credentials from environment variables instead of hardcoding them
CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY')
CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET')
PASSKEY = os.environ.get('MPESA_PASSKEY')
BUSINESS_SHORT_CODE = os.environ.get('MPESA_BUSINESS_SHORT_CODE', '174379')

# FIX 1: Strip whitespace to prevent "Invalid CallBackURL" errors from hidden spaces in .env
CALLBACK_URL = os.environ.get('MPESA_CALLBACK_URL', 'https://farmerman-systems.onrender.com/mpesa-callback').strip()

def get_access_token():
    api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    try:
        # FIX 2: Added timeout=15 to prevent Render workers from hanging
        r = requests.get(api_url, auth=(CONSUMER_KEY, CONSUMER_SECRET), timeout=15)
        r.raise_for_status()
        return r.json()['access_token']
    except Exception as e:
        print(f"❌ Error getting M-Pesa access token: {e}")
        return None

def initiate_stk_push(phone_number, amount):
    access_token = get_access_token()
    if not access_token:
        return {"error": "Authentication failed", "ResponseCode": "Error"}

    # 1. PHONE NUMBER SANITIZER
    # Safaricom strictly requires the 2547XXXXXXXX format. This fixes user typos.
    phone_str = str(phone_number).strip().replace('+', '')
    if phone_str.startswith('0'):
        phone_str = '254' + phone_str[1:]
    elif phone_str.startswith('7') or phone_str.startswith('1'):
        phone_str = '254' + phone_str

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    data_to_encode = BUSINESS_SHORT_CODE + PASSKEY + timestamp
    password = base64.b64encode(data_to_encode.encode()).decode('utf-8')

    headers = {
        'Authorization': f'Bearer {access_token}', 
        'Content-Type': 'application/json'
    }

    payload = {
        "BusinessShortCode": BUSINESS_SHORT_CODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount), # Ensure amount is a strict integer
        "PartyA": phone_str,
        "PartyB": BUSINESS_SHORT_CODE,
        "PhoneNumber": phone_str,
        "CallBackURL": CALLBACK_URL,
        "AccountReference": "FarmermanSys", # FIX 3: Shortened to 12 chars to prevent Safaricom rejection
        "TransactionDesc": "Pro Subscription"
    }

    stk_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    
    try:
        # FIX 4: Added timeout=30 to prevent the 503 gateway timeouts on Render
        response = requests.post(stk_url, json=payload, headers=headers, timeout=30)
        
        # 2. JSON DECODE ERROR HANDLER
        # Prevents the Flask app from crashing if Safaricom returns an HTML error page
        try:
            return response.json()
        except requests.exceptions.JSONDecodeError:
            print(f"❌ Safaricom API Error [{response.status_code}]: {response.text}")
            return {"error": "Safaricom API is down or rejected the request.", "ResponseCode": "Error"}
            
    except requests.exceptions.Timeout:
        # Clean fallback if Safaricom's sandbox takes too long
        print("❌ Safaricom STK Push Timed Out")
        return {"error": "Safaricom is taking too long to respond. Please try again.", "ResponseCode": "Error"}
    except Exception as e:
        print(f"❌ Request Failed: {e}")
        return {"error": str(e), "ResponseCode": "Error"}