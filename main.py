import os
import json
import base64
import stripe
import requests
import threading
import smtplib
import time
import uuid # <-- Essential for generating unique cloud filenames
from datetime import datetime, timedelta
from functools import wraps 
from email.message import EmailMessage
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from werkzeug.exceptions import NotFound
from logic import analyze_weather_and_generate_alerts, update_firebase_alerts
# Flask & Extensions
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash, send_from_directory, abort
from flask_mail import Mail, Message
from flask_socketio import SocketIO, emit, join_room, leave_room

# Firebase Imports
import firebase_admin
from firebase_admin import credentials, auth, db as firebase_db, storage # <-- Essential: Added 'storage'

# Internal Project Imports
from models import db as sqlalchemy_db, User, MarketData, Transaction 
from ai_logic.ai_engine import generate_price_forecast
from mpesa import initiate_stk_push

# APScheduler Setup
from apscheduler.schedulers.background import BackgroundScheduler

# ==========================================
# 1. INITIALIZATION & APP CONFIGURATION
# ==========================================
load_dotenv()

app = Flask(__name__)
app.secret_key = 'delstarford_works_secret_key' 
app.config['PERMANENT_SESSION_LIFETIME'] = 86400 # 24 hours

# Flask-Mail Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = ('Farmerman Systems', os.environ.get('MAIL_USERNAME'))

mail = Mail(app)

# APScheduler Initialization
scheduler = BackgroundScheduler()
scheduler.start()

# Database Config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///farmerman.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
sqlalchemy_db.init_app(app)

# Initialize SocketIO for real-time chat
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Dictionary to track who is currently online { 'user_id': 'socket_id' }
online_users = {}

# Folder for legacy chat media (Fallback if cloud fails)
CHAT_MEDIA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'chat_media')
os.makedirs(CHAT_MEDIA_FOLDER, exist_ok=True)

# ==========================================
# CONSTANTS & UPLOAD CONFIGURATIONS
# ==========================================
FIREBASE_WEB_API_KEY = "AIzaSyDy41jUJ8h7zYE9Ocj7pPNGGXCq5RRbN-s"
ALLOWED_TRAINING_EXTENSIONS = {'mp4', 'pdf', 'png', 'jpg', 'jpeg', 'docx', 'mp3', 'wav', 'avi', 'webp'}
PREMIUM_CONTENT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'premium_content')
os.makedirs(PREMIUM_CONTENT_FOLDER, exist_ok=True) 

def allowed_training_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_TRAINING_EXTENSIONS

# ==========================================
# FIREBASE SECURE CONNECTION
# ==========================================
rtdb = None
try:
    render_path = '/etc/secrets/serviceAccountKey.json'
    local_path = 'serviceAccountKey.json'
    cert_path = render_path if os.path.exists(render_path) else local_path

    if not firebase_admin._apps:
        cred = credentials.Certificate(cert_path)
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://farmerman-systems-default-rtdb.firebaseio.com/',
            'storageBucket': 'farmerman-systems.firebasestorage.app'
        })
    
    rtdb = firebase_db 
    print(f"Firebase securely initialized using: {cert_path}")

    # CONNECTION TEST
    test_fetch = rtdb.reference('users').get()
    if test_fetch:
        print(f"Connection Verified: Found {len(test_fetch)} records in 'users' node.")
    else:
        print("Warning: Connection successful but 'users' node appears empty.")

except Exception as e:
    print(f"Firebase Initialization Error: {e}")

with app.app_context():
    sqlalchemy_db.create_all()


# ==========================================
# FIREBASE CLOUD STORAGE UPLOADER (NEW!)
# ==========================================
def upload_to_firebase_storage(file_obj, folder_name):
    """Uploads a file to Firebase Cloud Storage and returns an unguessable public URL."""
    try:
        bucket = storage.bucket()
        
        # 1. Generate a secure, unique filename (e.g., 123e4567-e89b.png)
        extension = file_obj.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{extension}"
        blob_path = f"{folder_name}/{unique_filename}"
        
        # 2. Upload to Firebase
        blob = bucket.blob(blob_path)
        file_obj.seek(0) # Ensure we read from the beginning of the file
        blob.upload_from_file(file_obj, content_type=file_obj.content_type)
        
        # 3. Make the file readable by the web browser
        blob.make_public()
        
        # 4. Return the permanent cloud URL
        return blob.public_url
        
    except Exception as e:
        print(f"Firebase Storage Error: {e}")
        return None


# ==========================================
# ASYNC EMAIL FUNCTIONS
# ==========================================
def send_async_emails(user_email, admin_email, user_msg_html, admin_msg_html, name, message_body, inquiry_subject):
    """Background worker for Contact Forms using smtplib."""
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server: 
            server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            
            user_msg = EmailMessage()
            user_msg['Subject'] = "We received your message - Farmerman Systems"
            user_msg['From'] = f"Farmerman Support <{app.config['MAIL_USERNAME']}>"
            user_msg['To'] = user_email
            user_msg.set_content("Thank you for contacting Farmerman Systems. We will get back to you shortly.")
            user_msg.add_alternative(user_msg_html, subtype='html')
            server.send_message(user_msg)
            
            admin_msg = EmailMessage()
            admin_msg['Subject'] = f"🚨 {inquiry_subject} Inquiry from {name}"
            admin_msg['From'] = f"Farmerman Server <{app.config['MAIL_USERNAME']}>"
            admin_msg['To'] = admin_email 
            admin_msg.set_content(f"New {inquiry_subject} message from {name}: {message_body}")
            admin_msg.add_alternative(admin_msg_html, subtype='html')
            server.send_message(admin_msg)
            
    except Exception as e:
        print(f"Failed to send background emails: {e}")

def send_drip_followup(user_email, name):
    """Background worker for the 3-Day Drip Campaign using Flask-Mail."""
    with app.app_context(): 
        try:
            user_data = rtdb.reference('users').order_by_child('email').equal_to(user_email).get()
            if user_data:
                uid = list(user_data.keys())[0]
                current_tier = user_data[uid].get('subscription_tier', 'free')

                if current_tier == 'free':
                    msg = Message("Still guessing market prices? 📈", recipients=[user_email])
                    msg.html = render_template('emails/drip_upgrade.html', name=name)
                    mail.send(msg)
                    print(f"Drip email successfully sent to {user_email}")
        except Exception as e:
            print(f"Failed to send Drip Campaign email: {e}")

# ==========================================
# CONTEXT PROCESSORS
# ==========================================
@app.context_processor
def inject_site_content():
    def get_site_content(page_id):
        try:
            return rtdb.reference(f'site_content/{page_id}').get()
        except Exception:
            return None
    return dict(get_site_content=get_site_content)

@app.context_processor
def inject_global_vars():
    """Injects secure .env variables globally into all Jinja templates (e.g., base.html)."""
    return dict(
        weather_api_key=os.environ.get('WEATHER_API_KEY')
    )

# ==========================================
# ENTERPRISE SECURITY DECORATORS
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash("Access Denied: Administrator privileges required.", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def tutor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_role = session.get('role', session.get('user_role'))
        if user_role not in ['tutor', 'admin']:
            flash("Access denied: This area is reserved for Tutors.", "danger")
            return redirect(url_for('insights')) # <-- New standard landing page
        return f(*args, **kwargs)
    return decorated_function

def premium_required(f):
    """The Gatekeeper for Premium Intelligence and Pro Academy content."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to access Premium content.", "warning")
            return redirect(url_for('login'))
        
        user_role = session.get('role', session.get('user_role'))
        user_tier = session.get('tier', session.get('subscription_tier', 'free'))
        
        # Admins and Tutors bypass billing
        if user_role in ['admin', 'tutor']:
            return f(*args, **kwargs)

        # Only Paid tiers get through
        if user_tier not in ['premium', 'pro', 'enterprise', 'bronze', 'silver', 'gold']:
            flash("Upgrade Required: This is Premium Content.", "warning")
            return redirect(url_for('pricing'))
        
        return f(*args, **kwargs)
    return decorated_function

def token_required(f):
    """API token verification for external endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token: return jsonify({"error": "Token missing"}), 401
        try:
            if token.startswith("Bearer "): token = token.split(" ")[1]
            request.user = auth.verify_id_token(token)
        except Exception: return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated_function

def token_admin_required(f):
    """Admin-only API token verification."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token: return jsonify({"error": "Token missing"}), 401
        try:
            if token.startswith("Bearer "): token = token.split(" ")[1]
            decoded_token = auth.verify_id_token(token)
            uid = decoded_token['uid']
            user_data = rtdb.reference(f'users/{uid}').get()
            if not user_data or user_data.get('role') != 'admin':
                return jsonify({"error": "Admin required"}), 403
            request.uid = uid
        except Exception: return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# BACKGROUND EMAIL WORKER
# ==========================================
def send_welcome_email(user_email, name, role):
    """Sends the welcome email in the background so the user doesn't wait."""
    with app.app_context():
        try:
            # Personalize subject based on the new roles
            if role == 'tutor':
                subject = "Welcome to the Faculty!"
            elif role == 'seller':
                subject = "Ready to scale your agribusiness? 🚀"
            else: # buyer or legacy client
                subject = "Your Market Intelligence is Ready!"
                
            msg = Message(subject, recipients=[user_email])
            
            template = 'emails/welcome_tutor.html' if role == 'tutor' else 'emails/welcome_client.html'
            msg.html = render_template(template, name=name)
            
            mail.send(msg)
            print(f"Welcome email successfully sent to {user_email}")
        except Exception as e:
            print(f"Failed to send welcome email: {e}")



# ==========================================
# ROBUST AUTHENTICATION ROUTES
# ==========================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email').strip()
        password = request.form.get('password')
        full_name = request.form.get('fullName').strip()
        organization = request.form.get('organization', '').strip()
        
        # 1. SECURITY: Capture and sanitize the role (UPDATED FOR BUYER/SELLER/TUTOR)
        selected_role = request.form.get('role', 'buyer').strip().lower()
        if selected_role not in ['buyer', 'seller', 'tutor']:
            selected_role = 'buyer'

        try:
            # 2. Create Auth User
            user = auth.create_user(email=email, password=password, display_name=full_name)
            
            # 3. Initialize profile in RTDB
            rtdb.reference(f'users/{user.uid}').set({
                'uid': user.uid,
                'full_name': full_name, 
                'email': email, 
                'organization': organization,
                'role': selected_role, 
                'subscription_tier': 'free', 
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            # 4. Fire off the Welcome Email
            threading.Thread(target=send_welcome_email, args=(email, full_name, selected_role)).start()
            
            # 5. Schedule the Drip Campaign
            run_time = datetime.now() + timedelta(days=3)
            scheduler.add_job(
                func=send_drip_followup,
                trigger='date',
                run_date=run_time,
                args=[email, full_name]
            )

            # 6. Redirect to Login
            flash("Account created successfully! Check your inbox for the welcome email.", "success")
            return redirect(url_for('login'))
            
        except Exception as e: 
            flash(f"Registration Error: {str(e)}", "danger")
            
    return render_template('register.html')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email').strip()
        password = request.form.get('password')
        
        try:
            # 1. Firebase Auth REST API
            request_ref = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
            data = {"email": email, "password": password, "returnSecureToken": True}
            req = requests.post(request_ref, json=data)
            req.raise_for_status() 
            
            user = req.json()
            uid = user['localId'] 
            
            # 2. Database Fetch & Auto-Heal
            user_ref = rtdb.reference(f'users/{uid}')
            user_data = user_ref.get()
            
            if user_data:
                # Fallback to 'buyer' if role is empty to match your new frontend
                raw_role = str(user_data.get('role', 'buyer')).strip().lower()
                raw_tier = str(user_data.get('subscription_tier', 'free')).strip().lower()
            else:
                raw_role = 'buyer'
                raw_tier = 'free'
                user_ref.set({'email': email, 'role': raw_role, 'subscription_tier': raw_tier, 'uid': uid})

            # 3. Secure the Session
            session.clear() 
            session.permanent = True 
            session['user_id'] = uid
            session['user_email'] = email
            session['role'] = raw_role
            session['tier'] = raw_tier 
            session['subscription_tier'] = raw_tier 

            # 4. Smart Redirects based on Role
            if raw_role == 'admin':
                flash("Welcome back, Administrator!", "success")
                return redirect(url_for('subscriber_management')) 
                
            elif raw_role == 'tutor':
                flash("Welcome to the Faculty Portal!", "success")
                # Usually tutors go to their dashboard, or keep it as market_intelligence if you prefer
                return redirect(url_for('tutor_dashboard')) 
                
            elif raw_role in ['buyer', 'seller', 'client']:
                # DIRECT BUYERS & SELLERS TO INSIGHTS & RESEARCH
                # (We keep 'client' in the list just in case you have older legacy users in the database)
                flash(f"Authentication successful. Welcome to your {raw_role.capitalize()} portal!", "success")
                return redirect(url_for('insights'))
                
            else:
                # Catch-all fallback
                flash("Authentication successful. Welcome to your portal!", "success")
                return redirect(url_for('insights'))
            
        except requests.exceptions.HTTPError:
            flash("Invalid email or password. Please try again.", "danger")
        except Exception as e:
            print(f"Login System Error: {e}")
            flash("System error during login. Check server console.", "danger")
            
    return render_template('login.html')



@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email').strip()
        try:
            request_ref = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={FIREBASE_WEB_API_KEY}"
            headers = {"content-type": "application/json; charset=UTF-8"}
            data = {"requestType": "PASSWORD_RESET", "email": email}
            req = requests.post(request_ref, headers=headers, json=data)
            req.raise_for_status() 
            flash(f"A password reset link has been sent to {email}. Please check your inbox.", "success")
            return redirect(url_for('login'))
        except requests.exceptions.HTTPError:
            error_data = req.json().get('error', {}).get('message', '')
            if error_data == "EMAIL_NOT_FOUND":
                flash("No account is registered with that email address.", "warning")
            else:
                flash("Failed to send reset email. Please try again.", "danger")
        except Exception as e:
            flash("System error. Please contact support.", "danger")
            
    return render_template('reset_password.html')

@app.route('/logout')
def logout():
    role = session.get('role')
    session.clear()
    
    if role == 'admin':
        flash("Admin session securely terminated.", "success")
    else:
        flash("You have been securely logged out.", "info")
        
    return redirect(url_for('login'))

# ==========================================
# CLIENT DASHBOARD & SETTINGS
# ==========================================
@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    try:
        profile = rtdb.reference(f'users/{uid}').get() or {}
        if 'full_name' not in profile: profile['full_name'] = 'Valued Farmer'
        return render_template('dashboard.html', profile=profile)
    except Exception as e:
        return render_template('dashboard.html', profile={'full_name': 'User'})

@app.route('/billing')
@login_required
def billing_history():
    user_id = session.get('user_id')
    profile = rtdb.reference(f'users/{user_id}').get() or {}
    current_plan = profile.get('subscription_tier', session.get('subscription_tier', 'free'))
    txns_ref = rtdb.reference(f'completed_transactions/{user_id}').get()
    transactions_list = sorted(txns_ref.values(), key=lambda x: x.get('date', ''), reverse=True) if txns_ref else []
        
    return render_template(
        'payments/billing_history.html', 
        profile=profile, 
        transactions=transactions_list, 
        current_plan=current_plan
    )

@app.route('/payment-failed')
@login_required
def payment_failed():
    error_message = request.args.get('msg', None)
    return render_template('payments/payment_failed.html', error_message=error_message)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def account_settings(): 
    uid = session['user_id']
    user_ref = rtdb.reference(f'users/{uid}')
    
    if request.method == 'POST':
        user_ref.update({
            'full_name': request.form.get('full_name'),
            'phone': request.form.get('phone'),
            'location': request.form.get('location')
        })
        flash("Settings updated successfully!", "success")
        return redirect(url_for('account_settings'))
        
    profile_data = user_ref.get() or {'full_name': 'User', 'email': session.get('user_email', '')}
    return render_template('accounts&subscription settings.html', profile=profile_data)
      
# ==========================================
# ADMIN HUB (Fully Protected)
# ==========================================
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard(): 
    users = rtdb.reference('users').get() or {}
    market = rtdb.reference('market_data').get() or {}
    txns = rtdb.reference('completed_transactions').get() or {}
    rev = 0.0; recent = []
    
    for uid, u_txns in txns.items():
        u_info = users.get(uid, {})
        for t in u_txns.values():
            rev += float(t.get('amount', 0))
            recent.append({'name': u_info.get('full_name', 'User'), 'date': t.get('date', ''), 'plan': t.get('plan', 'Pro')})
            
    recent.sort(key=lambda x: x['date'], reverse=True)
    return render_template('admin dashboard.html', total_subscribers=len(users), active_feeds=len(market), total_revenue=rev, recent_transactions=recent[:5])

@app.route('/admin/upload-training-media', methods=['GET', 'POST'])
@admin_required
def admin_upload_training():
    if request.method == 'POST':
        file = request.files.get('file')
        description = request.form.get('description', 'No description provided.')
        category = request.form.get('category', 'agripreneur') 
        
        if not file or file.filename == '':
            flash('No file selected.', 'warning')
            return redirect(request.url)
            
        if file and allowed_training_file(file.filename):
            filename = secure_filename(file.filename)
            save_path = os.path.join(PREMIUM_CONTENT_FOLDER, filename)
            file_extension = filename.rsplit('.', 1)[1].lower()
            
            try:
                file.save(save_path) 
                rtdb.reference('training_content').push({
                    'filename': filename, 'description': description, 'category': category,
                    'file_type': file_extension, 'upload_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                flash(f'Success! {filename} published to academy.', 'success')
            except Exception as e:
                flash(f'Error saving file: {e}', 'danger')
            return redirect(url_for('admin_upload_training'))
        else:
            flash(f'Invalid file type.', 'danger')

    files_metadata = list((rtdb.reference('training_content').get() or {}).values())
    return render_template('admin_training_upload.html', files_metadata=files_metadata)
@app.route('/admin/data-manager', methods=['GET', 'POST'])
@admin_required
def market_data_manager():
    if request.method == 'POST':
        # Safely convert price to float for graphing
        try:
            numeric_price = float(request.form.get('price', 0))
        except ValueError:
            numeric_price = 0.0

        rtdb.reference('market_data').push({
            "commodity": request.form.get('commodity').strip(),
            "category": request.form.get('category', 'Other'), # e.g. Vegetables, Grains
            "region": request.form.get('region'),
            "price": numeric_price,
            "unit": request.form.get('unit', 'kg'), # e.g. 'per bundle', 'per crate'
            "currency": request.form.get('currency', 'USD'),
            "trend": request.form.get('trend'),
            # Use actual datetime string for precise graphing
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
        })
        flash(f"Market data for {request.form.get('commodity')} published successfully!", "success")
        return redirect(url_for('market_data_manager'))
        
    items = rtdb.reference('market_data').get() or {}
    
    # Clean up the data for the frontend
    market_list = []
    for k, v in items.items():
        # Handle legacy data that might be missing the new fields
        v['id'] = k
        v['category'] = v.get('category', 'General')
        v['unit'] = v.get('unit', 'unit')
        # Convert Firebase '{".sv": "timestamp"}' to a string if it exists in legacy data
        if isinstance(v.get('updated_at'), dict):
            v['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        market_list.append(v)
        
    # Convert the iterator back into a proper list so JSON can read it!
    return render_template('market data manager.html', market_items=list(reversed(market_list)))


@app.route('/admin/delete-market-data/<item_id>', methods=['POST'])
@admin_required
def delete_market_data(item_id):
    try: 
        rtdb.reference(f'market_data/{item_id}').delete()
        flash("Removed.", "success")
    except Exception: 
        flash("Error.", "danger")
    return redirect(url_for('market_data_manager'))

@app.route('/admin/content', methods=['GET', 'POST'])
@admin_required
def content_manager():
    cms_ref = rtdb.reference('site_content')
    history_ref = rtdb.reference('content_history')
    if request.method == 'POST':
        page_id = request.form.get('page_selection')
        title = request.form.get('content_title')
        body = request.form.get('body_text')
        cms_ref.child(page_id).set({'title': title, 'body': body, 'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        history_ref.push({'page': page_id, 'summary': f"Updated {title[:20]}...", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        flash(f"Content for '{page_id}' successfully synchronized.", "success")
        return redirect(url_for('content_manager'))
    recent_edits = history_ref.order_by_key().limit_to_last(5).get()
    edits_list = list(recent_edits.values()) if recent_edits else []
    edits_list.reverse() 
    return render_template('content manager.html', recent_edits=edits_list)

@app.route('/admin/subscribers')
@admin_required
def subscriber_management():
    try:
        all_users = rtdb.reference('users').get()
        subscribers_list = [{'uid': uid, **data} for uid, data in all_users.items()] if all_users else []
        return render_template('subscriber management.html', subscribers=subscribers_list)
    except Exception as e:
        flash("Could not load the subscribers list.", "danger")
        return redirect(url_for('admin_dashboard'))
    
@app.route('/admin/update-role', methods=['POST'])
@admin_required
def update_user_role():
    """Updates a user's role (admin/tutor/client) and tier (free/premium)."""
    target_uid = request.form.get('user_id')
    new_role = request.form.get('role')
    new_tier = request.form.get('tier')

    if not target_uid:
        flash("User ID is missing.", "danger")
        return redirect(url_for('subscriber_management'))

    try:
        rtdb.reference(f'users/{target_uid}').update({
            'role': new_role,
            'subscription_tier': new_tier
        })
        flash(f"User updated successfully to {new_role} ({new_tier}).", "success")
    except Exception as e:
        flash(f"Error updating user: {e}", "danger")

    return redirect(url_for('subscriber_management'))

# ==========================================
# PROTECTED MARKET INTELLIGENCE & AI
# ==========================================
@app.route('/market-intelligence')
@login_required
def market_intelligence():
    try:
        featured_items = rtdb.reference('market_data').order_by_key().limit_to_last(3).get()
        preview_list = [{'id': k, **v} for k, v in featured_items.items()] if featured_items else []
        preview_list.reverse()
        return render_template('market intelligence.html', preview=preview_list)
    except Exception:
        return render_template('market intelligence.html', preview=[])

@app.route('/live-market-prices')
@login_required
@premium_required
def live_market_prices():
    items = MarketData.query.order_by(MarketData.commodity.asc()).all()
    return render_template('live market prices.html', market_items=items)

@app.route('/trends-forecasts')
@login_required
@premium_required 
def trends_forecasts():
    records = MarketData.query.filter_by(commodity="Maize (90kg)").all()
    hist = [{'date': r.updated_at, 'price': r.price} for r in records]
    labels = [r.updated_at.strftime('%b %d') for r in records]
    prices = [r.price for r in records]
    ai = generate_price_forecast(hist, 5) if len(hist) >= 5 else {}
    if ai and "error" not in ai:
        labels.extend(ai['future_dates']); prices.extend(ai['predicted_prices'])
    return render_template('trends&forecasts.html', labels=labels, prices=prices, ai_insight=ai)

@app.route('/api/market-prices', methods=['GET'])
def api_market_prices():
    if session.get('tier') not in ['premium', 'pro'] and session.get('user_role') not in ['admin', 'tutor']:
        return jsonify({"error": "Premium subscription required to access raw data"}), 403
        
    items = rtdb.reference('market_data').get() or {}
    return jsonify([{'id': k, **v} for k, v in items.items()]), 200

# ==========================================
# FARMERMAN ACADEMY (STUDENT ROUTES)
# ==========================================
@app.route('/academy')
@login_required 
def academy_home():
    user_tier = session.get('subscription_tier', 'free')
    if session.get('role') == 'admin':
        user_tier = 'admin' 
        
    try:
        courses_data = rtdb.reference('academy_courses').get() or {}
        courses = [{'id': k, **v} for k, v in courses_data.items()]
        courses.reverse() 
    except Exception as e:
        print(f"Error fetching courses: {e}")
        courses = []
        
    return render_template('academy/index.html', user_tier=user_tier, courses=courses)

@app.route('/academy/my-learning')
@login_required
def my_learning():
    user_id = session.get('user_id')
    user_tier = session.get('subscription_tier', 'free')
    
    all_courses_data = rtdb.reference('academy_courses').get() or {}
    user_progress_data = rtdb.reference(f'user_progress/{user_id}').get() or {}
    
    enrolled_courses = []
    completed_courses = []
    
    for cid, cdata in all_courses_data.items():
        cdata['id'] = cid
        
        if cid in user_progress_data:
            progress = int(user_progress_data[cid].get('progress', 0))
            cdata['progress'] = progress
            
            if progress >= 100:
                completed_courses.append(cdata)
            else:
                enrolled_courses.append(cdata)
        else:
            cdata['progress'] = 0 
            enrolled_courses.append(cdata)

    return render_template('academy/my_learning.html', 
                           enrolled_courses=enrolled_courses,
                           completed_courses=completed_courses,
                           user_tier=user_tier)

@app.route('/academy/course/<course_id>')
@premium_required 
def view_lesson(course_id):
    lesson_data = rtdb.reference(f'academy_courses/{course_id}').get()
    
    if not lesson_data:
        flash("This course could not be found.", "warning")
        return redirect(url_for('academy_home'))
        
    lesson_data['id'] = course_id 
    
    comments_data = rtdb.reference(f'course_comments/{course_id}').get() or {}
    comments = [{'id': k, **v} for k, v in comments_data.items()]
    comments.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    return render_template('academy/course_view.html', lesson=lesson_data, comments=comments)

@app.route('/academy/course/<course_id>/quiz')
@premium_required
def take_quiz(course_id):
    lesson_data = rtdb.reference(f'academy_courses/{course_id}').get()
    if not lesson_data:
        flash("Course not found.", "warning")
        return redirect(url_for('academy_home'))
        
    quiz_data = rtdb.reference(f'academy_courses/{course_id}/quiz').get()
    
    if not quiz_data:
        quiz_data = [
            {
                "question": "What is the optimal soil pH range for most agricultural crops?",
                "options": ["4.0 - 5.0 (Highly Acidic)", "6.0 - 7.0 (Slightly Acidic to Neutral)", "8.0 - 9.0 (Highly Alkaline)", "It does not matter"],
                "answer": 1 
            },
            {
                "question": "Which primary macronutrient is directly responsible for vigorous, leafy green growth?",
                "options": ["Phosphorus (P)", "Potassium (K)", "Nitrogen (N)", "Calcium (Ca)"],
                "answer": 2 
            },
            {
                "question": "When is the best time of day to apply foliar fertilizers or pesticides?",
                "options": ["Early morning or late afternoon", "High noon when the sun is brightest", "During a heavy rainstorm", "Midnight"],
                "answer": 0 
            }
        ]
        
    return render_template('academy/quiz_view.html', 
                           lesson=lesson_data, 
                           quiz=quiz_data, 
                           course_id=course_id)

@app.route('/academy/certificate')
@login_required
def generate_certificate():
    user_id = session.get('user_id')
    user_profile = rtdb.reference(f'users/{user_id}').get() or {}
    full_name = user_profile.get('full_name', 'Esteemed Farmer')
    
    user_progress_data = rtdb.reference(f'user_progress/{user_id}').get() or {}
    has_completed_course = any(int(data.get('progress', 0)) >= 100 for data in user_progress_data.values())
            
    if not has_completed_course and session.get('role') != 'admin':
        flash("You must complete at least one course to earn a certificate.", "warning")
        return redirect(url_for('my_learning'))
        
    today_date = datetime.now().strftime("%B %d, %Y")
    return render_template('academy/certificate.html', student_name=full_name, date=today_date)

@app.route('/academy/leaderboard')
@login_required
def academy_leaderboard():
    all_users = rtdb.reference('users').get() or {}
    all_progress = rtdb.reference('user_progress').get() or {}
    leaderboard = []
    
    for uid, user_data in all_users.items():
        # Allow legacy clients, new buyers, and new sellers to appear on the board
        user_role = user_data.get('role', 'buyer').lower()
        if user_role not in ['client', 'buyer', 'seller']:
            continue
            
        name = user_data.get('full_name', 'Anonymous Farmer')
        points = sum(100 for course_data in all_progress.get(uid, {}).values() if int(course_data.get('progress', 0)) >= 100)
                    
        if points > 0:
            leaderboard.append({'uid': uid, 'name': name, 'points': points})
            
    leaderboard.sort(key=lambda x: x['points'], reverse=True)
    
    current_user_id = session.get('user_id')
    current_user_rank = next(({'rank': i + 1, 'points': u['points']} for i, u in enumerate(leaderboard) if u['uid'] == current_user_id), None)

    return render_template('academy/academy_leaderboard.html', 
                           leaderboard=leaderboard, 
                           current_user_rank=current_user_rank) 

@app.route('/agripreneur_training')
@premium_required
def agripreneur_training():
    try:
        content_ref = rtdb.reference('training_content').get() or {}
        all_content = sorted(content_ref.values(), key=lambda x: x.get('order', 0))
    except Exception as e:
        print(f"Academy Data Error: {e}")
        all_content = []

    categories = ['agripreneur', 'aqua', 'econ']
    categorized_content = {cat: [c for c in all_content if c.get('category') == cat] for cat in categories}
    
    return render_template('agripreneur_training.html', content=categorized_content)

@app.route('/secure-media/<path:filename>')
@premium_required
def secure_media(filename):
    try:
        response = send_from_directory(PREMIUM_CONTENT_FOLDER, filename)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    except FileNotFoundError:
        abort(404, description="This training resource is currently unavailable.")
        
@app.route('/admin-delete-training/<content_id>')
@login_required
def delete_training(content_id):
    ref = rtdb.reference(f'training_content/{content_id}')
    item = ref.get()
    
    if item:
        try:
            os.remove(os.path.join(PREMIUM_CONTENT_FOLDER, item['filename']))
        except OSError:
            pass 
        
        ref.delete()
        flash("Content removed successfully.", "info")
    
    return redirect(url_for('training_manager'))

# ==========================================
# FARMERMAN ACADEMY (API ROUTES)
# ==========================================
@app.route('/api/academy/update-progress', methods=['POST'])
@login_required
def update_progress():
    data = request.json
    course_id = data.get('course_id')
    progress = data.get('progress', 0)
    user_id = session.get('user_id')
    
    if not course_id:
        return jsonify({"error": "Missing course ID"}), 400
        
    try:
        rtdb.reference(f'user_progress/{user_id}/{course_id}').update({
            'progress': progress,
            'last_accessed': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        return jsonify({"success": True, "message": "Progress updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/academy/submit-quiz', methods=['POST'])
@login_required
def submit_quiz():
    data = request.json
    course_id = data.get('course_id')
    score = data.get('score', 0)
    user_id = session.get('user_id')
    
    if not course_id:
        return jsonify({"error": "Missing course ID"}), 400
        
    try:
        rtdb.reference(f'user_progress/{user_id}/{course_id}').update({
            'quiz_score': score,
            'quiz_completed_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        return jsonify({"success": True, "message": "Score saved successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/academy/course/<course_id>/comment', methods=['POST'])
@premium_required
def post_course_comment(course_id):
    message = request.form.get('message')
    user_id = session.get('user_id')
    
    if message and message.strip():
        user_profile = rtdb.reference(f'users/{user_id}').get() or {}
        full_name = user_profile.get('full_name', 'FarmerMan Scholar')
        
        rtdb.reference(f'course_comments/{course_id}').push({
            'user_id': user_id,
            'user_name': full_name,
            'message': message.strip(),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        flash("Your question has been posted to the discussion!", "success")
    else:
        flash("Comment cannot be empty.", "warning")
        
    return redirect(url_for('view_lesson', course_id=course_id))

# ==========================================
# FARMERMAN ACADEMY (TUTOR ROUTES)
# ==========================================
@app.route('/academy/tutor/dashboard')
@tutor_required
def tutor_dashboard():
    tutor_id = session.get('user_id')
    
    all_courses = rtdb.reference('academy_courses').get() or {}
    my_courses = []
    
    for cid, cdata in all_courses.items():
        if cdata.get('tutor_id') == tutor_id or session.get('role') == 'admin':
            cdata['id'] = cid
            my_courses.append(cdata)
            
    all_progress = rtdb.reference('user_progress').get() or {}
    total_enrollments = 0
    total_completions = 0
    
    my_course_ids = [c['id'] for c in my_courses]
    
    for uid, progress_data in all_progress.items():
        for cid, data in progress_data.items():
            if cid in my_course_ids:
                total_enrollments += 1
                if int(data.get('progress', 0)) >= 100:
                    total_completions += 1

    return render_template('academy/tutor_dashboard.html', 
                           my_courses=my_courses,
                           total_enrollments=total_enrollments,
                           total_completions=total_completions)

@app.route('/academy/tutor/gradebook')
@tutor_required
def tutor_gradebook():
    all_users = rtdb.reference('users').get() or {}
    all_courses = rtdb.reference('academy_courses').get() or {}
    all_progress = rtdb.reference('user_progress').get() or {}
    
    student_records = []
    total_completions = 0
    
    for uid, progress_data in all_progress.items():
        user_info = all_users.get(uid, {})
        student_name = user_info.get('full_name', 'Unknown Farmer')
        student_email = user_info.get('email', 'N/A')
        
        for course_id, data in progress_data.items():
            course_info = all_courses.get(course_id, {})
            course_title = course_info.get('title', 'Deleted Course')
            progress_score = int(data.get('progress', 0))
            quiz_score = data.get('quiz_score')
            last_accessed = data.get('last_accessed', 'Unknown')
            
            if progress_score >= 100:
                total_completions += 1
                
            student_records.append({
                'student_name': student_name,
                'student_email': student_email,
                'course_title': course_title,
                'progress': progress_score,
                'quiz_score': quiz_score if quiz_score is not None else 'Not Taken',
                'last_accessed': last_accessed[:10] if last_accessed != 'Unknown' else 'N/A'
            })
            
    student_records.sort(key=lambda x: x['last_accessed'], reverse=True)
    active_learners = len(all_progress.keys())
    
    return render_template('academy/gradebook.html', 
                           student_records=student_records,
                           active_learners=active_learners,
                           total_completions=total_completions)

@app.route('/academy/tutor/sessions', methods=['GET', 'POST'])
@tutor_required
def tutor_sessions():
    tutor_id = session.get('user_id')
    
    if request.method == 'POST':
        course_id = request.form.get('course_id')
        topic = request.form.get('topic')
        session_date = request.form.get('session_date')
        session_time = request.form.get('session_time')
        meet_link = request.form.get('meet_link')
        
        try:
            rtdb.reference('tutor_sessions').push({
                'tutor_id': tutor_id,
                'course_id': course_id,
                'topic': topic,
                'date': session_date,
                'time': session_time,
                'meet_link': meet_link,
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            if course_id:
                rtdb.reference(f'academy_courses/{course_id}').update({'meet_link': meet_link})
                
            flash("Live session scheduled successfully! The course page has been updated.", "success")
            return redirect(url_for('tutor_sessions'))
            
        except Exception as e:
            flash(f"Error scheduling session: {e}", "danger")

    all_courses = rtdb.reference('academy_courses').get() or {}
    my_courses = [{'id': k, 'title': v.get('title')} for k, v in all_courses.items() 
                  if v.get('tutor_id') == tutor_id or session.get('role') == 'admin']
    
    all_sessions = rtdb.reference('tutor_sessions').get() or {}
    my_sessions = []
    
    for sid, sdata in all_sessions.items():
        if sdata.get('tutor_id') == tutor_id or session.get('role') == 'admin':
            course = all_courses.get(sdata.get('course_id'), {})
            sdata['course_title'] = course.get('title', 'Deleted Course')
            sdata['id'] = sid
            my_sessions.append(sdata)
            
    my_sessions.sort(key=lambda x: f"{x.get('date')} {x.get('time')}", reverse=True)
    
    return render_template('academy/tutor_sessions.html', 
                           my_courses=my_courses, 
                           my_sessions=my_sessions)
          
# ==========================================
# TUTOR SECURITY & UPLOAD LOGIC
# ==========================================
@app.route('/academy/tutor/builder', methods=['GET', 'POST'])
@tutor_required
def course_builder():
    if request.method == 'POST':
        # 1. Grab text data from the form
        title = request.form.get('course_title')
        description = request.form.get('course_description')
        category = request.form.get('category')
        meet_link = request.form.get('meet_link', '')       
        # 2. Handle File Uploads (Video & PDF)
        video_file = request.files.get('video_file')
        resource_file = request.files.get('resource_file')
        
        video_filename = ""
        resource_filename = ""
        
        # Save Video
        if video_file and allowed_training_file(video_file.filename):
            video_filename = secure_filename(video_file.filename)
            video_file.save(os.path.join(PREMIUM_CONTENT_FOLDER, video_filename))
            
        # Save PDF Resource
        if resource_file and allowed_training_file(resource_file.filename):
            resource_filename = secure_filename(resource_file.filename)
            resource_file.save(os.path.join(PREMIUM_CONTENT_FOLDER, resource_filename))
            
        # 3. Save everything to Firebase Realtime Database
        try:
            rtdb.reference('academy_courses').push({
                'title': title,
                'description': description,
                'category': category,
                'meet_link': meet_link,
                'video_file': video_filename,
                'resource_file': resource_filename,
                'tutor_id': session.get('user_id'),
                'tutor_name': session.get('user_email'), # Or fetch their full name
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            flash(f"Success! '{title}' has been published to the Academy.", "success")
            return redirect(url_for('course_builder'))
        except Exception as e:
            flash(f"Database Error: {str(e)}", "danger")

    return render_template('academy/course_builder.html')

# ==========================================
# PAYMENTS & CALLBACKS
# ==========================================
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID')
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY')

# --- MASTER PRICING DICTIONARY ---
# Single source of truth for all payment gateways
SYSTEM_PRICING = {
    'bronze': {"name": "Bronze Consulting Package", "kes": 75000, "usd": 500.00},
    'silver': {"name": "Silver Consulting Package", "kes": 180000, "usd": 1200.00},
    'gold': {"name": "Gold Consulting Package", "kes": 420000, "usd": 2800.00},
    'course_entrepreneurship': {"name": "Agribusiness Entrepreneurship", "kes": 3750, "usd": 25.00},
    'course_marketing': {"name": "Agricultural Marketing", "kes": 3000, "usd": 20.00},
    'course_finance': {"name": "Financial Management", "kes": 4500, "usd": 30.00},
    'course_value_chain': {"name": "Value Chain Development", "kes": 5250, "usd": 35.00},
    'course_post_harvest': {"name": "Post-Harvest Loss Strategies", "kes": 3000, "usd": 20.00},
    'course_bankable': {"name": "Bankable Agribusiness Projects", "kes": 6000, "usd": 40.00},
    'course_market_intel': {"name": "Market Intelligence & Research", "kes": 7500, "usd": 50.00},
    'course_consulting': {"name": "Agribusiness Consulting Skills", "kes": 9000, "usd": 60.00},
    'bundle_starter': {"name": "Agribusiness Starter Bundle", "kes": 9000, "usd": 60.00},
    'bundle_investor': {"name": "Agribusiness Investor Bundle", "kes": 18000, "usd": 120.00}
}

# --- Helper Function for Clean Code ---
def record_successful_transaction(user_id, plan_id, amount, gateway, receipt_number):
    """Updates the user tier and logs the transaction securely."""
    try:
        # 1. Upgrade the user's tier
        rtdb.reference(f'users/{user_id}').update({'subscription_tier': plan_id})
        
        # 2. Update their active session if they are currently logged in
        if session.get('user_id') == user_id:
            session['tier'] = plan_id
            session['subscription_tier'] = plan_id
            
        # 3. Log the financial transaction
        rtdb.reference(f'completed_transactions/{user_id}').push({
            'receipt_number': receipt_number, 
            'amount': amount,
            'gateway': gateway,
            'plan_purchased': plan_id,
            'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        return True
    except Exception as e:
        print(f"CRITICAL: Failed to record successful transaction for {user_id}. Error: {e}")
        return False

# --- 1. M-PESA LOGIC ---
@app.route('/process-mpesa', methods=['POST'])
@login_required
def process_mpesa():
    phone = request.form.get('phone_number')
    plan_id = request.form.get('plan_id', 'bronze') 
    raw_amount = request.form.get('amount') 
    
    # Validation & Fallbacks - Now uses SYSTEM_PRICING
    try:
        amount = int(float(raw_amount)) if raw_amount else SYSTEM_PRICING.get(plan_id, SYSTEM_PRICING['bronze'])['kes']
    except (ValueError, TypeError):
        amount = SYSTEM_PRICING.get(plan_id, SYSTEM_PRICING['bronze'])['kes']
        
    try:
        res = initiate_stk_push(phone, amount)
        if res and res.get('ResponseCode') == '0':
            checkout_id = res.get("CheckoutRequestID")
            # Store pending transaction for callback matching
            rtdb.reference(f'pending_transactions/{checkout_id}').set({
                'user_id': session.get('user_id'), 
                'amount': amount, 
                'plan_id': plan_id, 
                'status': 'awaiting_payment',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            return redirect(url_for('payment_processing', checkout_id=checkout_id))
            
        error_msg = res.get('errorMessage', 'Safaricom service is currently unavailable.')
        return redirect(url_for('payment_failed', msg=f"M-Pesa Error: {error_msg}"))
        
    except Exception as e:
        print(f"CRITICAL MPESA STK ERROR: {str(e)}")
        return redirect(url_for('payment_failed', msg="M-Pesa Gateway is currently unstable. Please try again later or use a Card."))

@app.route('/mpesa-callback', methods=['POST'])
def mpesa_callback():
    """Receives async confirmation from Safaricom."""
    try:
        data = request.json
        stk = data.get('Body', {}).get('stkCallback', {})
        checkout_id = stk.get("CheckoutRequestID")
        
        pending_ref = rtdb.reference(f'pending_transactions/{checkout_id}')
        pending_data = pending_ref.get()

        if pending_data:
            # 1. SUCCESS: Safaricom confirms the PIN was entered and funds captured
            if stk.get('ResultCode') == 0:
                meta = stk.get('CallbackMetadata', {}).get('Item', [])
                receipt = next((i['Value'] for i in meta if i['Name'] == 'MpesaReceiptNumber'), 'UNKNOWN')
                
                uid = pending_data.get('user_id')
                plan_bought = pending_data.get('plan_id', 'bronze')
                amount = pending_data.get('amount', 0)
                
                # Record the transaction securely
                record_successful_transaction(uid, plan_bought, amount, "M-Pesa", receipt)
                pending_ref.delete() # Cleanup deletes the pending record
            
            # 2. FAILED: User cancelled, typed wrong PIN, or had insufficient funds
            else:
                # Update status so the frontend polling knows to show the failed screen
                pending_ref.update({'status': 'failed'})
                
        # Always return 200 OK so Safaricom doesn't keep retrying
        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200
        
    except Exception as e:
        print(f"M-Pesa Callback Error: {e}")
        return jsonify({"ResultCode": 1, "ResultDesc": "Internal Server Error"}), 500

@app.route('/checkout')
@login_required 
def subscriber_checkout():
    # 1. Get the plan from the URL (e.g., /checkout?plan=silver or ?plan=course_marketing)
    # If no plan is specified, it safely defaults to 'bronze'
    plan_id = request.args.get('plan', 'bronze')
    
    # 2. Look up the exact pricing from our master dictionary (SYSTEM_PRICING)
    selected_plan = SYSTEM_PRICING.get(plan_id, SYSTEM_PRICING['bronze'])

    # 3. Send the dynamic prices to the HTML template
    return render_template(
        'payments/subscriber_checkout.html',
        plan_id=plan_id, 
        plan_name=selected_plan['name'], 
        amount_kes=selected_plan['kes'], 
        amount_usd=selected_plan['usd'],
        paystack_public_key=os.environ.get('PAYSTACK_PUBLIC_KEY', ''),
        stripe_public_key=os.environ.get('STRIPE_PUBLIC_KEY', ''),
        paypal_client_id=os.environ.get('PAYPAL_CLIENT_ID', '')
    )

@app.route('/payment-processing/<checkout_id>')
@login_required
def payment_processing(checkout_id):
    """Renders the waiting room while the user types their M-Pesa PIN."""
    return render_template('payments/payment_processing.html', checkout_id=checkout_id)

@app.route('/api/check-payment/<checkout_id>')
@login_required
def check_payment_status(checkout_id):
    """The frontend polls this endpoint every 3 seconds to check for the callback."""
    pending_txn = rtdb.reference(f'pending_transactions/{checkout_id}').get()
    
    if pending_txn:
        if pending_txn.get('status') == 'failed':
            return jsonify({'status': 'failed'})
        return jsonify({'status': 'pending'})
    
    # If the transaction is GONE, mpesa_callback successfully processed it!
    return jsonify({'status': 'completed'})

# --- 2. STRIPE LOGIC ---
@app.route('/create-stripe-session', methods=['POST'])
@login_required
def create_stripe_session():
    try:
        data = request.json
        plan_id = data.get('plan', 'bronze')
        
        # Look up the plan in our master dictionary
        selected_plan = SYSTEM_PRICING.get(plan_id, SYSTEM_PRICING['bronze'])
        # Stripe expects amounts in cents, so we multiply the USD amount by 100
        amount_in_cents = int(selected_plan['usd'] * 100)

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': amount_in_cents,
                    'product_data': {
                        'name': f"Farmerman Systems: {selected_plan['name']}",
                        'description': f"Payment for {selected_plan['name']}"
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            # Metadata is crucial for tracking who paid what in the Stripe Dashboard
            metadata={
                'user_id': session.get('user_id'), 
                'plan_id': plan_id
            }, 
            success_url=url_for('stripe_success', plan_id=plan_id, _external=True) + '&session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('pricing', _external=True),
        )
        return jsonify({'id': checkout_session.id})
    except Exception as e:
        print(f"Stripe Session Error: {e}")
        return jsonify(error="Unable to connect to Stripe."), 403

@app.route('/stripe-success')
@login_required
def stripe_success():
    """Validates the redirect back from Stripe."""
    plan_id = request.args.get('plan_id', 'bronze')
    session_id = request.args.get('session_id')
    user_id = session.get('user_id')
    
    # Grab the accurate USD price for the receipt
    amount_paid = SYSTEM_PRICING.get(plan_id, SYSTEM_PRICING['bronze'])['usd']
    
    if session_id and user_id:
        record_successful_transaction(user_id, plan_id, amount_paid, "Stripe", f"STR_{session_id[-8:]}")
        return redirect(url_for('payment_success'))
    
    return redirect(url_for('pricing'))

# --- 3. PAYPAL LOGIC ---
@app.route('/paypal-transaction-complete', methods=['POST'])
@login_required
def paypal_transaction_complete():
    try:
        data = request.json
        order_id = data.get('orderID')
        plan_id = data.get('plan', 'bronze')
        user_id = session.get('user_id')
        
        # Grab the accurate USD price for the receipt
        amount_paid = SYSTEM_PRICING.get(plan_id, SYSTEM_PRICING['bronze'])['usd']
        
        if user_id and order_id:
            record_successful_transaction(user_id, plan_id, amount_paid, "PayPal", f"PAY_{order_id}")
            return jsonify({"status": "success"}), 200
            
        return jsonify({"status": "failed", "error": "Missing data"}), 400
    except Exception as e:
        print(f"PayPal Recording Error: {e}")
        return jsonify({"status": "failed"}), 500

# --- 4. PAYSTACK LOGIC ---
@app.route('/verify-paystack')
@login_required
def verify_paystack():
    reference = request.args.get('reference')
    plan_id = request.args.get('plan', 'bronze')
    user_id = session.get('user_id')
    
    if not reference or not user_id: 
        flash("Invalid transaction reference.", "warning")
        return redirect(url_for('pricing'))
    
    secret_key = os.environ.get('PAYSTACK_SECRET_KEY')
    verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {secret_key}"}
    
    try:
        response = requests.get(verify_url, headers=headers)
        response_data = response.json()
        
        if response_data.get('status') is True and response_data.get('data', {}).get('status') == 'success':
            # Paystack sends amount in Kobo/Cents, so we divide by 100
            actual_amount = response_data['data']['amount'] / 100 
            
            record_successful_transaction(user_id, plan_id, actual_amount, "Paystack", reference)
            
            flash(f"Payment successful! Welcome to the {plan_id.capitalize()} plan.", "success")
            return redirect(url_for('payment_success'))
            
        flash("Payment verification failed. Please contact support.", "danger")
    except Exception as e:
        print(f"Paystack Verification Error: {e}")
        flash("Server error during verification.", "danger")
        
    return redirect(url_for('pricing'))

# --- SUCCESS PAGE ---
@app.route('/success')
@login_required
def payment_success(): 
    return render_template('payments/payment_success.html')

#==========================================
# STATIC PAGES & ERRORS
# ==========================================
@app.route('/')
def home(): 
    return render_template('home.html')

@app.route('/about')
def about_us(): 
    return render_template('about us.html')

@app.route('/impact')
def impact_initiatives(): 
    return render_template('impact&initiatives.html')

@app.route('/services')
def services(): 
    return render_template('our services.html')

@app.route('/privacy-policy')
def privacy_policy(): 
    return render_template('privacy policy.html')

# DEDUPLICATED PRICING ROUTE
@app.route('/pricing')
def pricing():
    # Notice the "payments/" folder prefix here
    return render_template('payments/pricing_subscription.html')

@app.route('/terms-of-service')
def terms_of_service(): 
    return render_template('terms of service.html')

@app.route('/refund-policy')
def refund_policy(): 
    return render_template('subscription&refund policy.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact_us(): 
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject') 
        message = request.form.get('message')
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        rtdb.reference('contact_inquiries').push({'name': name, 'email': email, 'subject': subject, 'message': message, 'timestamp': timestamp})
        
        current_year = datetime.now().year
        user_html = render_template('email_user_confirmation.html', name=name, message=message, year=current_year)
        admin_html = render_template('email_admin_notification.html', name=name, email=email, subject=subject, message=message, timestamp=timestamp)
        
        # BUG FIX: Use app.config['MAIL_USERNAME'] instead of undefined MAIL_USERNAME
        threading.Thread(target=send_async_emails, args=(email, app.config['MAIL_USERNAME'], user_html, admin_html, name, message, subject)).start()
        
        flash("Message sent! Check your email for a confirmation receipt.", "success")
        return redirect(url_for('contact_us'))
        
    return render_template('contact us.html')

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    user_id = session.get('user_id')
    try:
        # 1. Remove from Firebase
        rtdb.reference(f'users/{user_id}').delete()
        
        # 2. Clear local session
        session.clear()
        
        flash("Your account has been permanently deleted.", "info")
        # Change 'index' to whatever your landing page function is called
        # The logs suggest 'login' might be your intended landing page
        return redirect(url_for('login')) 
        
    except Exception as e:
        print(f"Error deleting account: {e}")
        flash("An error occurred.", "danger")
        # The logs explicitly said use 'account_settings'
        return redirect(url_for('account_settings'))
    
@app.route('/diagnostics', methods=['GET'])
def diagnostics():
    health_data = {
        "status": "Healthy",
        "system": "Farmerman Systems",
        "timestamp": datetime.now().strftime("%Y-%b-%d %H:%M:%S"),
        "version": "2.1.0",
        "uptime": "99.9%" 
    }
    return render_template('diagnostics.html', data=health_data)
# ==========================================
# REAL-TIME CHAT SYSTEM (Strict Privacy & Online-Only)
# ==========================================
@app.route('/chat/dashboard')
@login_required
@premium_required
# @premium_required # Uncomment if you want this protected
def chat_dashboard():
    """Chat dashboard showing all users and their current online status."""
    current_uid = session.get('user_id')
    all_users = rtdb.reference('users').get() or {}
    
    online_contacts = []
    for uid, data in all_users.items():
        # WE NO LONGER FILTER OUT OFFLINE USERS HERE!
        if uid != current_uid:
            online_contacts.append({
                'uid': uid,
                'name': data.get('full_name', 'Farmer'),
                'role': data.get('role', 'buyer'),
                # We pass the status to the frontend instead of filtering
                'is_online': uid in online_users 
            })
            
    # Pointing exactly to the file inside the chat folder
    return render_template('chat/dashboard.html', online_contacts=online_contacts)

@app.route('/chat')
@login_required
def chat_home():
    """Renders the main chat UI with smart sorting and unread badges."""
    current_uid = session.get('user_id')
    
    auto_open_uid = request.args.get('target_uid')
    auto_open_name = request.args.get('target_name')
    
    all_users = rtdb.reference('users').get() or {}
    all_chats = rtdb.reference('chats').get() or {}
    
    # FETCH UNREAD COUNTS FOR THE CURRENT USER
    my_unread_counts = rtdb.reference(f'unread_counts/{current_uid}').get() or {}
    
    current_user_profile = all_users.get(current_uid, {})
    my_location = current_user_profile.get('location', '').strip().lower()
    
    contacts = []
    for uid, data in all_users.items():
        if uid != current_uid:
            room_id = f"room_{min(str(current_uid), str(uid))}_{max(str(current_uid), str(uid))}"
            has_talked_before = 1 if room_id in all_chats else 0
            their_location = data.get('location', '').strip().lower()
            is_same_location = 1 if (my_location and their_location == my_location) else 0
            
            # Extract the specific unread count for this contact
            unread_count = my_unread_counts.get(uid, 0)

            contacts.append({
                'uid': uid,
                'name': data.get('full_name', 'Farmer'),
                'role': data.get('role', 'client'),
                'is_online': uid in online_users,
                'has_talked': has_talked_before,
                'same_location': is_same_location,
                'unread': unread_count # <-- NEW DATA POINT
            })
            
    # Sort logic: Unread messages float to the very top, then Talked, then Location, then Online
    contacts.sort(key=lambda x: (x['unread'] > 0, x['has_talked'], x['same_location'], x['is_online']), reverse=True)
            
    return render_template(
        'chat/index.html', 
        contacts=contacts, 
        current_uid=current_uid,
        auto_open_uid=auto_open_uid,   
        auto_open_name=auto_open_name  
    )
    
@app.route('/api/chat/upload', methods=['POST'])
@login_required
@premium_required
def upload_chat_media():
    """Handles image, video, and audio uploads to Cloud Storage."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty file'}), 400
        
    file_url = upload_to_firebase_storage(file, 'chat_media')
    
    if file_url:
        return jsonify({'url': file_url, 'type': file.content_type}), 200
    return jsonify({'error': 'Cloud upload failed'}), 500


# --- SOCKET.IO EVENTS ---

@socketio.on('connect')
def handle_connect():
    uid = session.get('user_id')
    if uid:
        online_users[uid] = request.sid
        
        # NEW: Join a personal room using the user's ID. 
        # This allows the server to send global notifications (like unread badges) 
        # directly to this user, regardless of what chat they are looking at.
        join_room(uid) 
        
        # 1. Update the green dots for everyone
        emit('user_status', {'uid': uid, 'status': 'online'}, broadcast=True)
        # 2. Tell everyone to refresh their sidebar
        emit('refresh_contacts', broadcast=True, include_self=False)

@socketio.on('disconnect')
def handle_disconnect():
    uid = session.get('user_id')
    if uid and uid in online_users:
        del online_users[uid]
        # 1. Turn the dot grey for everyone
        emit('user_status', {'uid': uid, 'status': 'offline'}, broadcast=True)
        # 2. Tell everyone to refresh sidebar
        emit('refresh_contacts', broadcast=True)

@socketio.on('join_chat')
def handle_join_chat(data):
    uid1 = session.get('user_id')
    uid2 = data.get('target_uid')
    if not uid2: return

    room = f"room_{min(str(uid1), str(uid2))}_{max(str(uid1), str(uid2))}"
    join_room(room)
    
    history = rtdb.reference(f'chats/{room}').get() or {}
    messages = []
    
    # SMART FETCH: Only send messages that the user hasn't deleted for themselves
    for msg in history.values():
        if uid1 not in msg.get('deleted_for', []):
            messages.append(msg)
            
    # NEW: RESET UNREAD COUNTER
    # Since the user just opened this chat, set their unread count from this sender to 0
    rtdb.reference(f'unread_counts/{uid1}/{uid2}').set(0)
            
    emit('chat_history', messages)

@socketio.on('clear_chat')
def handle_clear_chat(data):
    uid = session.get('user_id')
    target_uid = data.get('target_uid')
    mode = data.get('mode', 'me') # Can be 'me' or 'all'
    if not target_uid: return
    
    room = f"room_{min(str(uid), str(target_uid))}_{max(str(uid), str(target_uid))}"
    
    if mode == 'all':
        # Wipe it completely from the database
        rtdb.reference(f'chats/{room}').delete()
        emit('chat_cleared', {'mode': 'all'}, room=room)
    else:
        # CLEAR FOR ME ONLY
        messages_ref = rtdb.reference(f'chats/{room}')
        messages = messages_ref.get() or {}
        
        # Loop through existing messages and tag them as hidden for this specific user
        for msg_key, msg_data in messages.items():
            deleted_for = msg_data.get('deleted_for', [])
            if uid not in deleted_for:
                deleted_for.append(uid)
                messages_ref.child(msg_key).update({'deleted_for': deleted_for})
                
        # Emit the clear screen event ONLY to the person who clicked the button
        emit('chat_cleared', {'mode': 'me'}, to=request.sid)

@socketio.on('send_message')
def handle_send_message(data):
    sender_id = session.get('user_id')
    receiver_id = data.get('receiver_id')
    if not receiver_id: return

    room = f"room_{min(str(sender_id), str(receiver_id))}_{max(str(sender_id), str(receiver_id))}"
    
    message_data = {
        'sender_id': sender_id,
        'text': data.get('text', ''),
        'media_url': data.get('media_url'),
        'media_type': data.get('media_type'),
        'timestamp': datetime.now().strftime("%H:%M")
    }
    
    # 1. Save Message to Database
    rtdb.reference(f'chats/{room}').push(message_data)
    
    # 2. NEW: INCREMENT UNREAD COUNTER
    # Add +1 to the receiver's unread count from this sender
    unread_ref = rtdb.reference(f'unread_counts/{receiver_id}/{sender_id}')
    current_unread = unread_ref.get() or 0
    new_unread_count = current_unread + 1
    unread_ref.set(new_unread_count)
    
    # 3. Broadcast the message to the active chat room
    emit('receive_message', message_data, room=room)
    
    # 4. NEW: Global UI Notification
    # Ping the receiver's personal room so their sidebar badge updates instantly
    emit('update_unread_badge', {
        'sender_id': sender_id, 
        'count': new_unread_count
    }, room=receiver_id)

@socketio.on('typing')
def handle_typing(data):
    receiver_id = data.get('receiver_id')
    sender_id = session.get('user_id')
    room = f"room_{min(str(sender_id), str(receiver_id))}_{max(str(sender_id), str(receiver_id))}"
    emit('display_typing', {'sender_id': sender_id}, room=room, include_self=False)

@socketio.on('stop_typing')
def handle_stop_typing(data):
    receiver_id = data.get('receiver_id')
    sender_id = session.get('user_id')
    room = f"room_{min(str(sender_id), str(receiver_id))}_{max(str(sender_id), str(receiver_id))}"
    emit('hide_typing', {'sender_id': sender_id}, room=room, include_self=False)
# ==========================================
# ENTERPRISE EXPANSION HUBS (Live Database Integration)
# ==========================================

@app.route('/deal-room')
@login_required
@premium_required
def deal_room():
    """Exclusive portal for Gold/Investor tier to view bankable projects."""
    # Fetch live deals from Firebase
    deals_data = rtdb.reference('deals').get() or {}
    deals = [{'id': k, **v} for k, v in deals_data.items()]
    
    return render_template('deal_room.html', deals=deals)

@app.route('/api-docs')
@premium_required
def api_docs():
    """Developer documentation for Enterprise clients."""
    return render_template('api_docs.html')
# In main.py
@app.route('/climate')
@login_required
@premium_required
def climate_hub():
    """Weather and Climate Smart Agriculture dashboard."""
    user_id = session.get('user_id')
    
    # Fetch ONLY this user's personal alerts from Firebase
    climate_data = rtdb.reference(f'climate_alerts/{user_id}').get()
    
    # Format the data depending on how Firebase returned it
    alerts = []
    if isinstance(climate_data, dict):
        alerts = [{'id': k, **v} for k, v in climate_data.items()]
    elif isinstance(climate_data, list):
        # Firebase sometimes stores .set() lists as actual arrays
        alerts = [a for a in climate_data if a is not None]
        
    # Sort newest first
    alerts.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    return render_template('climate.html', alerts=alerts)

# Make sure you have these imports at the top of your main.py!
from flask import request, jsonify
from logic import analyze_weather_and_generate_alerts, update_firebase_alerts
# In main.py
@app.route('/api/climate/analyze', methods=['POST'])
@login_required
@premium_required
def analyze_climate():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400
    
    try:
        # Get the currently logged-in user's ID
        user_id = session.get('user_id')
        
        temp = float(data.get('temp', 0))
        humidity = float(data.get('humidity', 0))
        wind = float(data.get('wind', 0))
        condition = str(data.get('condition', ''))
        region = str(data.get('region', 'Unknown Region'))
        
        # Generate the alerts
        new_alerts = analyze_weather_and_generate_alerts(temp, humidity, wind, condition, region)
        
        # Save them ONLY to this user's profile!
        update_firebase_alerts(user_id, new_alerts)
        
        return jsonify({"status": "success", "message": "Updated personal alerts!"}), 200
        
    except Exception as e:
        print(f"Engine Error: {e}")
        return jsonify({"status": "error", "message": "Failed to analyze"}), 500
    
@app.route('/admin/add-climate-alert', methods=['POST'])
@admin_required
def add_climate_alert():
    """Admin route to publish new agronomic weather alerts."""
    try:
        rtdb.reference('climate_alerts').push({
            'region': request.form.get('region'),
            'temp': request.form.get('temp'),
            'condition': request.form.get('condition'),
            'humidity': request.form.get('humidity'),
            'wind': request.form.get('wind'),
            'alert_type': request.form.get('alert_type'), # 'warning' or 'success'
            'title': request.form.get('title'),
            'advice': request.form.get('advice'),
            'timestamp': datetime.now().strftime("%B %d, %Y - %H:%M")
        })
        flash("Climate alert published to the Hub!", "success")
    except Exception as e:
        flash(f"Error publishing climate alert: {e}", "danger")
        
    return redirect(url_for('admin_dashboard'))


@app.route('/insights')
@premium_required
def insights():
    """SEO-friendly thought leadership and market analysis blog."""
    # Fetch live articles from Firebase
    insights_data = rtdb.reference('insights').get() or {}
    articles = [{'id': k, **v} for k, v in insights_data.items()]
    
    return render_template('insights.html', articles=articles) 
@app.route('/insights/<article_id>')
def read_insight(article_id):
    """Fetches and displays a single full-length article."""
    # Fetch the specific article from Firebase
    article = rtdb.reference(f'insights/{article_id}').get()
    
    if not article:
        flash("Article not found.", "warning")
        return redirect(url_for('insights'))
        
    # Pass the data to the reader template
    return render_template('read_article.html', article=article)

# ==========================================
# ADMIN POSTING ROUTES FOR ENTERPRISE HUBS
# ==========================================
@app.route('/admin/add-deal', methods=['POST'])
@admin_required
def add_deal():
    """Admin route to publish new investment opportunities to the Deal Room."""
    try:
        rtdb.reference('deals').push({
            'title': request.form.get('title'),
            'ask': request.form.get('ask'),       # e.g., "$50,000"
            'roi': request.form.get('roi'),       # e.g., "14%"
            'sector': request.form.get('sector'), # e.g., "Agri-Tech"
            'risk': request.form.get('risk'),     # e.g., "Low"
            'status': request.form.get('status', 'Reviewing') # e.g., "Funding"
        })
        flash("New investment deal published to the Deal Room!", "success")
    except Exception as e:
        flash(f"Error posting deal: {e}", "danger")
        
    return redirect(url_for('admin_dashboard'))
@app.route('/admin/add-insight', methods=['POST'])
@admin_required
def add_insight():
    """Admin route to publish new Thought Leadership articles with Multimedia."""
    try:
        # 1. Grab files from the form
        image_file = request.files.get('image_file')
        video_file = request.files.get('video_file')
        audio_file = request.files.get('audio_file')
        
        # 2. Upload to Firebase Storage (if the file was provided)
        img_url = upload_to_firebase_storage(image_file, 'insights_media') if image_file and image_file.filename else "https://images.unsplash.com/photo-1592982537447-6f296cb31454?auto=format&fit=crop&w=600&q=80" # Fallback image
        video_url = upload_to_firebase_storage(video_file, 'insights_media') if video_file and video_file.filename else None
        audio_url = upload_to_firebase_storage(audio_file, 'insights_media') if audio_file and audio_file.filename else None

        # 3. Save to Realtime Database
        rtdb.reference('insights').push({
            'title': request.form.get('title'),
            'date': datetime.now().strftime("%B %d, %Y"),
            'category': request.form.get('category'),
            'read_time': request.form.get('read_time'), 
            'img': img_url,
            'video_url': video_url,
            'audio_url': audio_url,
            'summary': request.form.get('summary'),
            'content': request.form.get('content')
        })
        flash("Thought Leadership article with media published successfully!", "success")
    except Exception as e:
        flash(f"Error publishing insight: {e}", "danger")
        
    return redirect(url_for('admin_dashboard'))


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    
    # Add these two lines to create a clickable link in your terminal!
    print(f"\n Farmerman Systems is LIVE!")
    print(f" Click here to open: http://127.0.0.1:{port}\n")
    
    socketio.run(app, host='0.0.0.0', port=port, debug=True)