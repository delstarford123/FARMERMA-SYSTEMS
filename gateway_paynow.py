import os
import time
from paynow import Paynow

# Load from environment variables to keep credentials secure
PAYNOW_INTEGRATION_ID = os.environ.get('PAYNOW_INTEGRATION_ID', 'YOUR_INTEGRATION_ID')
PAYNOW_INTEGRATION_KEY = os.environ.get('PAYNOW_INTEGRATION_KEY', 'YOUR_INTEGRATION_KEY')
WEBHOOK_URL = os.environ.get('PAYNOW_WEBHOOK_URL', 'https://your-domain.com/webhook/paynow/status')

paynow = Paynow(
    PAYNOW_INTEGRATION_ID,
    PAYNOW_INTEGRATION_KEY,
    WEBHOOK_URL,
    "http://google.com" # Return URL (not used for USSD push, but required by SDK)
)

def trigger_mobile_push(user_phone, amount, user_uid, package_name):
    """
    Triggers an EcoCash or OneMoney USSD push to the user's phone.
    Returns a dictionary with success status and instructions.
    """
    # Clean phone number
    clean_phone = user_phone.replace('+', '').strip()
    
    # Determine the mobile wallet provider based on prefix
    if clean_phone.startswith('26371') or clean_phone.startswith('071'):
        method = 'onemoney'
    else:
        # Default to EcoCash for 077/078
        method = 'ecocash'

    # Create a unique reference for the transaction
    reference = f"ZIMBOT_{user_uid[-6:]}_{int(time.time())}"
    
    # Create the payment object
    payment = paynow.create_payment(reference, 'farmer@zimbot.local')
    payment.add(f'{package_name.title()} Package Subscription', float(amount))

    try:
        # Initiate the mobile push
        response = paynow.send_mobile(payment, clean_phone, method)
        
        if response.success:
            poll_url = response.poll_url
            instructions = response.instructions
            return {
                "success": True,
                "reference": reference,
                "poll_url": poll_url,
                "instructions": instructions,
                "method": method
            }
        else:
            return {
                "success": False,
                "error": "Failed to initiate push with the gateway."
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def verify_manual_reference(reference_code):
    """
    Validates a manual reference code.
    True offline validation (e.g., dialing *151# to a merchant code directly)
    cannot be instantly verified against Paynow without a prior transaction link.
    If you use a direct EcoCash Biller API or Android SMS scraper, implement that check here.
    """
    # Mock validation: assumes the reference is valid for structural purposes
    # In production, query your Biller API: is_paid = my_biller_api.check(reference_code)
    return True
