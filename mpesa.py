import requests
from datetime import datetime
import base64

# --- CONFIGURATION ---
CONSUMER_KEY = 'mjpi9dRnBx6ZgredXiDbOK8U1gSnCds5TdJr7A3VrAdEg5a0'
CONSUMER_SECRET = 'CPiCSfv7qWx5faY0tfHElspd1OMA9IBIlJo86snqBMtGhtglvBKPwzP2mG3d33hD'
PASSKEY = 'bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919'
BUSINESS_SHORT_CODE = '174379'
CALLBACK_URL = 'https://your-ngrok-url.ngrok-free.app/mpesa-callback'

def get_access_token():
    api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    try:
        r = requests.get(api_url, auth=(CONSUMER_KEY, CONSUMER_SECRET))
        r.raise_for_status()
        return r.json()['access_token']
    except Exception as e:
        print(f"Error getting token: {e}")
        return None

def initiate_stk_push(phone_number, amount):
    access_token = get_access_token()
    if not access_token:
        return {"error": "Authentication failed"}

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    data_to_encode = BUSINESS_SHORT_CODE + PASSKEY + timestamp
    password = base64.b64encode(data_to_encode.encode()).decode('utf-8')

    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    payload = {
        "BusinessShortCode": BUSINESS_SHORT_CODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone_number,
        "PartyB": BUSINESS_SHORT_CODE,
        "PhoneNumber": phone_number,
        "CallBackURL": CALLBACK_URL,
        "AccountReference": "Farmerman Systems",
        "TransactionDesc": "Subscription Payment"
    }

    stk_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    response = requests.post(stk_url, json=payload, headers=headers)
    return response.json()