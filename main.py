import os
import json
import base64
import stripe
import requests
import threading
import smtplib
from datetime import datetime, timedelta
from functools import wraps 
from email.message import EmailMessage

from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from werkzeug.exceptions import NotFound

# Flask & Extensions
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash, send_from_directory, abort
from flask_mail import Mail, Message

# Firebase Imports
import firebase_admin
from firebase_admin import credentials, auth, db as firebase_db

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
            'databaseURL': 'https://farmerman-systems-default-rtdb.firebaseio.com/'
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
# ASYNC EMAIL FUNCTIONS
# ==========================================
def send_async_emails(user_email, admin_email, user_msg_html, admin_msg_html, name, message_body, inquiry_subject):
    """Background worker for Contact Forms using smtplib."""
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server: # Changed to port 465 for SSL
            server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            
            # Send to User
            user_msg = EmailMessage()
            user_msg['Subject'] = "We received your message - Farmerman Systems"
            user_msg['From'] = f"Farmerman Support <{app.config['MAIL_USERNAME']}>"
            user_msg['To'] = user_email
            user_msg.set_content("Thank you for contacting Farmerman Systems. We will get back to you shortly.")
            user_msg.add_alternative(user_msg_html, subtype='html')
            server.send_message(user_msg)
            
            # Send to Admin
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

# ==========================================
# ENTERPRISE SECURITY DECORATORS
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login')) # Updated to standard 'login' route
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
        user_role = session.get('role', session.get('user_role')) # Safely checks both 
        if user_role not in ['tutor', 'admin']:
            flash("Access denied: This area is reserved for Tutors.", "danger")
            return redirect(url_for('market_intelligence')) # Redirects to safe dashboard
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
        if user_tier not in ['premium', 'pro', 'enterprise']:
            flash("Upgrade Required: This is Premium Market Intelligence.", "warning")
            return redirect(url_for('pricing')) # Redirects to pricing page
        
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

import threading
from flask_mail import Message

# ==========================================
# BACKGROUND EMAIL WORKER
# ==========================================
def send_welcome_email(user_email, name, role):
    """Sends the welcome email in the background so the user doesn't wait."""
    with app.app_context():
        try:
            subject = "Welcome to the Faculty!" if role == 'tutor' else "Your Market Intelligence is Ready!"
            msg = Message(subject, recipients=[user_email])
            
            # Use the templates we designed earlier
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
        
        # 1. SECURITY: Capture and sanitize the role (Force 'client' if tampered)
        selected_role = request.form.get('role', 'client').strip().lower()
        if selected_role not in ['client', 'tutor']:
            selected_role = 'client'

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
            
            # 4. Fire off the Welcome Email (Using threading so the page loads instantly)
            threading.Thread(target=send_welcome_email, args=(email, full_name, selected_role)).start()
            
            # 5. Schedule the Drip Campaign (Fires 3 days from exactly right now)
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
                raw_role = str(user_data.get('role', 'client')).strip().lower()
                raw_tier = str(user_data.get('subscription_tier', 'free')).strip().lower()
            else:
                # Auto-heal missing profile data
                raw_role = 'client'
                raw_tier = 'free'
                user_ref.set({'email': email, 'role': raw_role, 'subscription_tier': raw_tier, 'uid': uid})

            # 3. Secure the Session
            session.clear() # Clear any old rogue data
            session.permanent = True 
            session['user_id'] = uid
            session['user_email'] = email
            session['role'] = raw_role
            session['tier'] = raw_tier # Using 'tier' matches our @premium_required decorator
            session['subscription_tier'] = raw_tier 

            # 4. Smart Redirects based on Role
            if raw_role == 'admin':
                flash("Welcome back, Administrator!", "success")
                return redirect(url_for('subscriber_management')) # Send admins to the new management table
            elif raw_role == 'tutor':
                flash("Welcome to the Faculty Portal!", "success")
                return redirect(url_for('market_intelligence')) # Or point to 'academy_home'
            else:
                flash("Authentication successful. Welcome to your portal!", "success")
                return redirect(url_for('market_intelligence'))
            
        except requests.exceptions.HTTPError:
            flash("Invalid email or password. Please try again.", "danger")
        except Exception as e:
            print(f"Login System Error: {e}")
            flash("System error during login. Check server console.", "danger")
            
    # Assuming you named your new login template 'login.html'
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
            return redirect(url_for('client_login'))
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
        
    # THE FIX: Changed 'client_login' to 'login' to match our new routing
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
# --- BILLING & INVOICE HISTORY PAGE ---
@app.route('/billing')
@login_required
def billing_history():
    user_id = session.get('user_id')
    
    # 1. Fetch user profile (Useful if you want to print their Name/Organization on the invoice)
    profile = rtdb.reference(f'users/{user_id}').get() or {}
    
    # Securely grab the current plan (checks database first, falls back to session)
    current_plan = profile.get('subscription_tier', session.get('subscription_tier', 'free'))
    
    # 2. Fetch transactions from Firebase
    txns_ref = rtdb.reference(f'completed_transactions/{user_id}').get()
    
    # 3. Clean, Pythonic sorting: Converts the Firebase dictionary to a list and sorts by date (newest first)
    transactions_list = sorted(txns_ref.values(), key=lambda x: x.get('date', ''), reverse=True) if txns_ref else []
        
    return render_template(
        'payments/billing_history.html', 
        profile=profile,               # Passes user data to the HTML
        transactions=transactions_list, # Passes the sorted receipts
        current_plan=current_plan      # Passes the active subscription tier
    )

# --- PAYMENT FAILED PAGE ---
@app.route('/payment-failed')
@login_required
def payment_failed():
    # Pass an optional custom error message via the URL (e.g., /payment-failed?msg=Card+Declined)
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

@app.route('/checkout')
@login_required 
def subscriber_checkout():
    plan_id = request.args.get('plan', 'pro')
    
    # FIX: Removed the quotes around the USD amounts so they are floats, not strings!
    if plan_id == 'basic':
        plan_name, amount_kes, amount_usd = "Smallholder Plan", 700, 5.00
    elif plan_id == 'enterprise':
        plan_name, amount_kes, amount_usd = "Enterprise & NGO", 20000, 150.00
    else:
        plan_id, plan_name, amount_kes, amount_usd = 'pro', "Agribusiness Pro", 3500, 25.00

    return render_template(
        'payments/subscriber_checkout.html',
        plan_id=plan_id, 
        plan_name=plan_name, 
        amount_kes=amount_kes, 
        amount_usd=amount_usd,
        paystack_public_key=os.environ.get('PAYSTACK_PUBLIC_KEY', ''),
        stripe_public_key=os.environ.get('STRIPE_PUBLIC_KEY', ''),
        paypal_client_id=os.environ.get('PAYPAL_CLIENT_ID', '')
    )
    
      
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
        rtdb.reference('market_data').push({
            "commodity": request.form.get('commodity'), "region": request.form.get('region'),
            "price": float(request.form.get('price')), "currency": request.form.get('currency', 'KES'),
            "trend": request.form.get('trend'), "updated_at": {".sv": "timestamp"}
        })
        flash("Market data published!", "success")
    items = rtdb.reference('market_data').get() or {}
    market_list = [{'id': k, **v} for k, v in items.items()]
    return render_template('market data manager.html', market_items=reversed(market_list))

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
@admin_required # Ensure only the top admin can do this
def update_user_role():
    """Updates a user's role (admin/tutor/client) and tier (free/premium)."""
    target_uid = request.form.get('user_id')
    new_role = request.form.get('role')
    new_tier = request.form.get('tier')

    if not target_uid:
        flash("User ID is missing.", "danger")
        return redirect(url_for('admin_subscribers'))

    try:
        # Update Firebase
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
# We leave this open to all logged-in users, but use the "Blur" 
# technique in the HTML template to hide the best parts.
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
@premium_required # <--- ONLY PRO CLIENTS, TUTORS, & ADMINS
def live_market_prices():
    items = MarketData.query.order_by(MarketData.commodity.asc()).all()
    return render_template('live market prices.html', market_items=items)

@app.route('/trends-forecasts')
@login_required
@premium_required # <--- AI INSIGHTS ARE HIGH-VALUE; LOCK THEM
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
    # Security for API: Check session within the function
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
        user_tier = 'admin' # Admins bypass all locks
        
    try:
        courses_data = rtdb.reference('academy_courses').get() or {}
        # Convert dictionary to list and inject the ID
        courses = [{'id': k, **v} for k, v in courses_data.items()]
        # Show newest courses first
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
    # Fetch specific course
    lesson_data = rtdb.reference(f'academy_courses/{course_id}').get()
    
    if not lesson_data:
        flash("This course could not be found.", "warning")
        return redirect(url_for('academy_home'))
        
    lesson_data['id'] = course_id 
    
    # Fetch Comments for this course
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
        # Fallback sample quiz
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
        if user_data.get('role', 'client') != 'client':
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

def tutor_required(f):
    """Gatekeeper: Only Admins or approved Tutors can build courses."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in.", "warning")
            return redirect(url_for('client_login'))
            
        role = session.get('role', 'client')
        if role not in ['admin', 'tutor']:
            flash("Access Denied: You must be an approved Tutor to upload courses.", "danger")
            return redirect(url_for('dashboard'))
            
        return f(*args, **kwargs)
    return decorated_function

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
    plan_id = request.form.get('plan_id', 'pro') 
    raw_amount = request.form.get('amount') 
    
    # Validation & Fallbacks
    try:
        amount = int(float(raw_amount)) if raw_amount else 3500
    except (ValueError, TypeError):
        amount = 3500
        
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
            
            # PERFECTED: Send to the waiting room, NOT the success page!
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
                plan_bought = pending_data.get('plan_id', 'pro')
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
        plan_id = data.get('plan', 'pro')
        
        # Consistent USD pricing (Stripe expects amount in cents)
        pricing_tiers = {
            'basic': {'name': 'Smallholder Plan', 'price': 500},       # $5.00
            'pro': {'name': 'Agribusiness Pro', 'price': 2500},       # $25.00
            'enterprise': {'name': 'Enterprise & NGO', 'price': 15000} # $150.00 (Fixed from 150000)
        }
        
        selected_plan = pricing_tiers.get(plan_id, pricing_tiers['pro'])

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': selected_plan['price'],
                    'product_data': {
                        'name': f"Farmerman Systems: {selected_plan['name']}",
                        'description': f"Access to {plan_id.capitalize()} market intelligence tools"
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
    plan_id = request.args.get('plan_id', 'pro')
    session_id = request.args.get('session_id')
    user_id = session.get('user_id')
    
    # Pricing map for database recording (Standard USD)
    pricing = {'basic': 5.00, 'pro': 25.00, 'enterprise': 150.00}
    
    if session_id and user_id:
        record_successful_transaction(user_id, plan_id, pricing.get(plan_id, 25.0), "Stripe", f"STR_{session_id[-8:]}")
        return redirect(url_for('payment_success'))
    
    return redirect(url_for('pricing'))


# --- 3. PAYPAL LOGIC ---
@app.route('/paypal-transaction-complete', methods=['POST'])
@login_required
def paypal_transaction_complete():
    try:
        data = request.json
        order_id = data.get('orderID')
        plan_id = data.get('plan', 'pro')
        user_id = session.get('user_id')
        
        # Map amount for consistent database records
        pricing = {'basic': 5.00, 'pro': 25.00, 'enterprise': 150.00}
        amount_paid = pricing.get(plan_id, 25.00)
        
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
    plan_id = request.args.get('plan', 'pro')
    user_id = session.get('user_id')
    
    if not reference or not user_id: 
        flash("Invalid transaction reference.", "warning")
        return redirect(url_for('pricing'))
    
    # PAYSTACK_SECRET_KEY should be in your .env file
    secret_key = os.environ.get('PAYSTACK_SECRET_KEY')
    verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {secret_key}"}
    
    try:
        response = requests.get(verify_url, headers=headers)
        response_data = response.json()
        
        if response_data.get('status') is True and response_data.get('data', {}).get('status') == 'success':
            # Paystack sends amount in Kobo/Cents (KES 3500 is 350000)
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
    # Updated to point to the payments folder
    return render_template('payments/payment_success.html')


#==========================================
# STATIC PAGES & ERRORS
# ==========================================
@app.route('/')
def home(): return render_template('home.html')
@app.route('/about')
def about_us(): return render_template('about us.html')
@app.route('/impact')
def impact_initiatives(): return render_template('impact&initiatives.html')
@app.route('/pricing')
def pricing_subscription(): return render_template('payments/pricing_subscription.html')
@app.route('/services')
def services(): return render_template('our services.html')


@app.route('/pricing')
def pricing():
    # Notice the "payments/" folder prefix here
    return render_template('payments/pricing_subscription.html')

@app.route('/terms-of-service')
def terms_of_service(): return render_template('terms of service.html')
@app.route('/refund-policy')
def refund_policy(): return render_template('subscription&refund policy.html')

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
        
        threading.Thread(target=send_async_emails, args=(email, MAIL_USERNAME, user_html, admin_html, name, message, subject)).start()
        
        flash("Message sent! Check your email for a confirmation receipt.", "success")
        return redirect(url_for('contact_us'))
        
    return render_template('contact us.html')

@app.route('/diagnostics', methods=['GET'])
def diagnostics():
    return jsonify({"status": "healthy", "system": "Farmerman Systems", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}), 200

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)