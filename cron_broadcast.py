import os
import sys
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime

# Import the generalized dispatch function
from zimbot import dispatch_scheduled_reports

def run_broadcast():
    # 1. Determine the Day of the Week
    today = datetime.now().strftime("%A").upper() # "MONDAY", "WEDNESDAY", "FRIDAY"
    
    # We only run on specific days
    if today not in ["MONDAY", "WEDNESDAY", "FRIDAY"]:
        print(f"Today is {today}. Broadcasts only run on Mon, Wed, Fri.")
        return
        
    # 2. Package Eligibility Rules
    # Seed ($3) -> Friday
    # Growth ($5) -> Monday, Friday
    # Harvest ($10) -> Monday, Wednesday, Friday
    
    allowed_packages = []
    if today == "MONDAY":
        allowed_packages = ["growth", "harvest"]
    elif today == "WEDNESDAY":
        allowed_packages = ["harvest"]
    elif today == "FRIDAY":
        allowed_packages = ["seed", "growth", "harvest"]
        
    print(f"Running {today} Broadcast for packages: {allowed_packages}")
    
    # 3. Initialize Firebase (Ensure env variables or path to cert is set)
    cred_path = os.environ.get("FIREBASE_CREDENTIALS", "firebase-adminsdk.json")
    if not firebase_admin._apps:
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {
                'databaseURL': os.environ.get('FIREBASE_DB_URL', 'https://your-database.firebaseio.com')
            })
        else:
            print("Warning: Firebase credentials not found. Proceeding with dummy data for demonstration.")
            
    # 4. Fetch Users
    active_users_to_message = []
    if firebase_admin._apps:
        all_users = db.reference('users').get() or {}
        for uid, user in all_users.items():
            if not isinstance(user, dict): continue
            
            sub_status = user.get('subscription_status', 'inactive')
            sub_tier = user.get('subscription_tier', 'free').lower()
            
            if sub_status == 'active' and sub_tier in allowed_packages:
                active_users_to_message.append({
                    "name": user.get('full_name', 'Farmer'),
                    "phone": user.get('phone', ''),
                    "preferred_channel": user.get('preferred_channel', 'sms'), # Default to sms
                    "email": user.get('email', '')
                })
    else:
        # Dummy fallback for testing
        active_users_to_message = [
            {"name": "Delstarford", "phone": "+263771234567", "preferred_channel": "whatsapp"},
            {"name": "Isaiah", "phone": "+263779876543", "preferred_channel": "sms"}
        ]
        
    if not active_users_to_message:
        print("No active users found for today's broadcast.")
        return

    # 5. Fetch/Generate the Intelligence Payload
    # In a full system, you would query the market trends here. We use the structured payload.
    scheduled_intelligence = {
        "asset": "Maize",
        "market": "Mbare",
        "price": "USD 24.80/bag",
        "bias": "Rising",
        "whatsapp_bias_symbol": "▲",
        "sms_insight": "Supply tightening. Sell in batches.",
        "whatsapp_insight": "Supply curves indicate rapid tightening across Harare hubs. It is highly recommended to sell your current stock in staged batches over the next 4 days to maximize yield returns.",
        "day": today
    }
    
    # 6. Dispatch
    dispatch_scheduled_reports(active_users_to_message, scheduled_intelligence)
    print(f"Successfully processed {len(active_users_to_message)} users.")

if __name__ == "__main__":
    run_broadcast()
