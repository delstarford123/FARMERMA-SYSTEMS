import firebase_admin
from firebase_admin import credentials, auth, db
from firebase_admin._auth_utils import EmailAlreadyExistsError

# 1. Initialize Firebase Admin
cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://farmerman-systems-default-rtdb.firebaseio.com/'
})

email = "delstarfordisaiah@gmail.com"
password = "Delstarford123"
full_name = "Delstarford Isaiah"

try:
    print(f"Attempting to create user {email}...")
    # Try to create a brand new user
    user = auth.create_user(
        email=email,
        password=password,
        display_name=full_name
    )
    uid = user.uid
    print(f"Success! Created new user in Auth with UID: {uid}")

except EmailAlreadyExistsError:
    # If you already registered this email, just grab the existing account
    print(f"User {email} already exists in Auth. Fetching UID...")
    user = auth.get_user_by_email(email)
    uid = user.uid
    
    # Optionally update the password to ensure it is Delstarford123
    auth.update_user(uid, password=password)
    print(f"Password reset to the requested password. UID: {uid}")

# 2. Force the Admin profile into the Realtime Database
print("Writing Admin profile to Realtime Database...")
admin_ref = db.reference(f'users/{uid}')
admin_ref.set({
    'email': email,
    'full_name': full_name,
    'role': 'admin',
    'subscription_tier': 'pro',
    'created_at': 'System Initialized Admin'
})

print("\n==================================================")
print("✅ ADMIN SETUP COMPLETE!")
print(f"Email: {email}")
print(f"Role: admin")
print("You can now start your Flask server and log in.")
print("==================================================\n")