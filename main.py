import os
import json
import base64
import stripe
import requests
from datetime import datetime
from functools import wraps 
from werkzeug.utils import secure_filename
from werkzeug.exceptions import NotFound

import os
from dotenv import load_dotenv
import smtplib
import threading
from email.message import EmailMessage
from datetime import datetime

# 1. LOAD THE SECRET VARIABLES
load_dotenv()

# ==========================================
# EMAIL SMTP CONFIGURATION
# ==========================================
# 2. FETCH THE VARIABLES SECURELY
MAIL_USERNAME = os.environ.get('MAIL_USERNAME') 
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') 
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 465

# ... the rest of your Firebase setup and routes continue below ...


# Flask Imports
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash, send_from_directory, abort

# Firebase Imports
import firebase_admin
from firebase_admin import credentials, auth, db as firebase_db

# Internal Project Imports
from models import db as sqlalchemy_db, User, MarketData, Transaction 
from ai_logic.ai_engine import generate_price_forecast
from mpesa import initiate_stk_push

app = Flask(__name__)
app.secret_key = 'delstarford_works_secret_key' 
# Force sessions to be saved permanently in the browser to prevent desyncs
app.config['PERMANENT_SESSION_LIFETIME'] = 86400 # 24 hours

# ==========================================
# CONSTANTS & CONFIGURATIONS
# ==========================================
FIREBASE_WEB_API_KEY = "AIzaSyDy41jUJ8h7zYE9Ocj7pPNGGXCq5RRbN-s"

# Payment API Configuration
stripe.api_key = 'sk_test_your_stripe_secret_key_here'
MPESA_CONSUMER_KEY = 'your_consumer_key'
MPESA_CONSUMER_SECRET = 'your_consumer_secret'
MPESA_SHORTCODE = '174379'

# Upload Settings for Admin Hub
ALLOWED_TRAINING_EXTENSIONS = {'mp4', 'pdf', 'png', 'jpg', 'jpeg', 'docx', 'mp3', 'wav', 'avi', 'webp'}
PREMIUM_CONTENT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'premium_content')
os.makedirs(PREMIUM_CONTENT_FOLDER, exist_ok=True) 

def allowed_training_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_TRAINING_EXTENSIONS

# ==========================================
# DATABASE & FIREBASE INITIALIZATION
# ==========================================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///farmerman.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
sqlalchemy_db.init_app(app)

# Global RTDB reference
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

    # CONNECTION TEST: Verify we can see the users node immediately
    test_fetch = rtdb.reference('users').get()
    if test_fetch:
        print(f"Connection Verified: Found {len(test_fetch)} records in 'users' node.")
    else:
        print("Warning: Connection successful but 'users' node appears empty or path is wrong.")

except Exception as e:
    print(f"Firebase Initialization Error: {e}")

with app.app_context():
    sqlalchemy_db.create_all()



def send_async_emails(user_email, admin_email, user_msg_html, admin_msg_html, name, message_body, inquiry_subject):
    """The background worker that connects to Gmail and sends the generated templates."""
    try:
        with smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT) as server:
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            
            # 1. Send to User
            user_msg = EmailMessage()
            user_msg['Subject'] = "We received your message - Farmerman Systems"
            user_msg['From'] = f"Farmerman Support <{MAIL_USERNAME}>"
            user_msg['To'] = user_email
            user_msg.set_content("Thank you for contacting Farmerman Systems. We will get back to you shortly.")
            user_msg.add_alternative(user_msg_html, subtype='html')
            server.send_message(user_msg)
            
            # 2. Send to Admin (Now uses the dropdown subject!)
            admin_msg = EmailMessage()
            admin_msg['Subject'] = f"🚨 {inquiry_subject} Inquiry from {name}"
            admin_msg['From'] = f"Farmerman Server <{MAIL_USERNAME}>"
            admin_msg['To'] = admin_email 
            admin_msg.set_content(f"New {inquiry_subject} message from {name}: {message_body}")
            admin_msg.add_alternative(admin_msg_html, subtype='html')
            server.send_message(admin_msg)
            
    except Exception as e:
        print(f"Failed to send background emails: {e}")






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
def admin_required(f):
    """Absolute protection for Admin routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash("Access Denied: Administrator privileges required.", "danger")
            return redirect(url_for('client_login'))
        return f(*args, **kwargs)
    return decorated_function

def subscriber_required(f):
    """Protects premium media and courses. Admins automatically bypass."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access the Farmerman Academy.", "warning")
            return redirect(url_for('client_login'))
            
        # Admins get immediate free access to all premium content
        if session.get('role') == 'admin':
            return f(*args, **kwargs)
            
        if session.get('subscription_tier') != 'pro':
            flash("Premium Feature: Please upgrade to Agribusiness Pro.", "info")
            return redirect(url_for('pricing_subscription'))
            
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
# ROBUST AUTHENTICATION ROUTES
# ==========================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email').strip()
        password = request.form.get('password')
        full_name = request.form.get('fullName').strip()
        try:
            user = auth.create_user(email=email, password=password, display_name=full_name)
            
            # Initialize profile in RTDB
            rtdb.reference(f'users/{user.uid}').set({
                'full_name': full_name, 'email': email, 'role': 'client', 
                'subscription_tier': 'free', 'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            session.permanent = True
            session.update({'user_id': user.uid, 'user_email': email, 'role': 'client', 'subscription_tier': 'free'})
            flash("Account created! Welcome to Farmerman Systems.", "success")
            return redirect(url_for('subscriber_checkout'))
        except Exception as e: 
            flash(f"Registration Error: {str(e)}", "danger")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def client_login():
    if request.method == 'POST':
        email = request.form.get('email').strip()
        password = request.form.get('password')
        
        try:
            # 1. Firebase Auth
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
                session['role'] = raw_role
                session['subscription_tier'] = str(user_data.get('subscription_tier', 'free')).strip().lower()
            else:
                # Auto-heal: If user exists in Auth but not DB, create a default profile
                user_ref.set({'email': email, 'role': 'client', 'subscription_tier': 'free'})
                session['role'] = 'client'
                session['subscription_tier'] = 'free'

            # 3. Secure the Session
            session.permanent = True 
            session['user_id'] = uid
            session['user_email'] = email

            # 4. Strict Routing
            if session.get('role') == 'admin':
                flash("Welcome back, Administrator!", "success")
                return redirect(url_for('admin_dashboard'))
                
            flash("Welcome back to Farmerman Systems!", "success")
            return redirect(url_for('dashboard'))
            
        except requests.exceptions.HTTPError:
            flash("Invalid email or password.", "danger")
        except Exception as e:
            print(f"Login System Error: {e}")
            flash("System error. Check console.", "danger")
            
    return render_template('client login.html')


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email').strip()
        
        try:
            # Firebase REST API for Password Reset
            request_ref = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={FIREBASE_WEB_API_KEY}"
            headers = {"content-type": "application/json; charset=UTF-8"}
            data = {
                "requestType": "PASSWORD_RESET",
                "email": email
            }
            
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
            print(f"Password Reset Error: {e}")
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
    return redirect(url_for('client_login')) 


# ==========================================
# CLIENT DASHBOARD & SETTINGS
# ==========================================
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('client_login'))
    try:
        profile = rtdb.reference(f'users/{session["user_id"]}').get() or {}
        # Ensure template always has fallback data
        if 'full_name' not in profile: profile['full_name'] = 'Valued Farmer'
        return render_template('dashboard.html', profile=profile)
    except Exception as e:
        print(f"Dashboard Error: {e}")
        return render_template('dashboard.html', profile={'full_name': 'User'})
    
@app.route('/billing')
def billing(): 
    if 'user_id' not in session: return redirect(url_for('client_login'))
    uid = session['user_id']
    profile = rtdb.reference(f'users/{uid}').get() or {}
    txns = rtdb.reference(f'completed_transactions/{uid}').get()
    txn_list = sorted(txns.values(), key=lambda x: x.get('date', ''), reverse=True) if txns else []
    return render_template('billing.html', profile=profile, transactions=txn_list)

@app.route('/settings', methods=['GET', 'POST'])
def account_settings(): 
    if 'user_id' not in session: return redirect(url_for('client_login'))
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
def subscriber_checkout():
    if 'user_id' not in session: return redirect(url_for('register'))
    return render_template('subscriber checkout.html')

# ==========================================
# TRAINING ACADEMY (Fully Protected)
# ==========================================
@app.route('/agripreneur-training')
@subscriber_required
def agripreneur_training():
    """Only Pro users and Admins can access this page."""
    try:
        content_data = rtdb.reference('training_content').get() or {} 
        all_content = list(content_data.values())
    except Exception:
        all_content = []

    categorized_content = {
        'agripreneur': [c for c in all_content if c.get('category') == 'agripreneur'],
        'aqua': [c for c in all_content if c.get('category') == 'aqua'],
        'econ': [c for c in all_content if c.get('category') == 'econ']
    }
    return render_template('agripreneur_training.html', content=categorized_content)

@app.route('/secure-media/<path:filename>')
@subscriber_required
def secure_media(filename):
    """Gatekeeper for physical files. Admins and Pro users pass automatically."""
    try:
        return send_from_directory(PREMIUM_CONTENT_FOLDER, filename, as_attachment=False)
    except NotFound:
        abort(404, description="Media not found. It may have been deleted.")

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
            flash(f'Invalid file type. Allowed: {", ".join(ALLOWED_TRAINING_EXTENSIONS)}', 'danger')

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













# ==========================================
# MOBILE API: ADMIN HUB
# ==========================================
@app.route('/api/admin/subscribers', methods=['GET'])
@token_admin_required
def api_admin_subscribers():
    """Returns a JSON list of all users for the Flutter Admin Hub."""
    try:
        all_users = rtdb.reference('users').get()
        # Convert Firebase dictionary into a list and inject the UID into each record
        subscribers_list = [{'uid': uid, **data} for uid, data in all_users.items()] if all_users else []
        return jsonify(subscribers_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/update-user', methods=['POST'])
@token_admin_required
def api_admin_update_user():
    """Allows the Flutter Admin Hub to change a user's role or tier."""
    data = request.json
    uid = data.get('uid')
    new_role = data.get('role')
    new_tier = data.get('subscription_tier')
    
    if not uid or not new_role or not new_tier:
        return jsonify({"error": "Missing parameters"}), 400
        
    try:
        # Update the exact user in the Realtime Database
        rtdb.reference(f'users/{uid}').update({
            'role': new_role,
            'subscription_tier': new_tier
        })
        return jsonify({"success": True, "message": "User permissions synchronized."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# MOBILE API: CONTENT MANAGER
# ==========================================
@app.route('/api/admin/content-history', methods=['GET'])
@token_admin_required
def api_admin_content_history():
    """Returns a JSON list of recent website content edits."""
    try:
        history_ref = rtdb.reference('content_history')
        # Fetch the 20 most recent edits
        recent_edits = history_ref.order_by_key().limit_to_last(20).get()
        
        if recent_edits:
            edits_list = list(recent_edits.values())
            edits_list.reverse() # Put the newest edits at the top
            return jsonify(edits_list), 200
            
        return jsonify([]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/content', methods=['POST'])
@token_admin_required
def api_admin_update_content():
    """Allows the Flutter app to publish new text to the website."""
    data = request.json
    page_id = data.get('page_id')
    title = data.get('title')
    body = data.get('body')
    
    if not page_id or not title or not body:
        return jsonify({"error": "Missing page_id, title, or body"}), 400
        
    try:
        # 1. Update the live site content
        rtdb.reference(f'site_content/{page_id}').set({
            'title': title,
            'body': body,
            'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        # 2. Add an entry to the history ledger
        rtdb.reference('content_history').push({
            'page': page_id,
            'summary': f"Updated {title[:20]}...",
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        return jsonify({"success": True, "message": "Content published"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ==========================================
# MOBILE API: MARKET DATA MANAGER
# ==========================================
@app.route('/api/admin/data-manager', methods=['POST'])
@token_admin_required
def api_admin_add_market_data():
    """Allows the Flutter app to publish new market prices."""
    data = request.json
    commodity = data.get('commodity')
    region = data.get('region')
    price = data.get('price')
    
    if not commodity or not region or price is None:
        return jsonify({"error": "Missing commodity, region, or price"}), 400
        
    try:
        # Push the new record into the database with a server timestamp
        rtdb.reference('market_data').push({
            "commodity": commodity,
            "region": region,
            "price": float(price),
            "currency": data.get('currency', 'KES'),
            "trend": data.get('trend', 'stable'),
            "updated_at": {".sv": "timestamp"}
        })
        return jsonify({"success": True, "message": "Market data published"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/delete-market-data/<item_id>', methods=['DELETE'])
@token_admin_required
def api_admin_delete_market_data(item_id):
    """Allows the Flutter app to delete a market price entry."""
    try:
        # Target the specific ID and remove it
        rtdb.reference(f'market_data/{item_id}').delete()
        return jsonify({"success": True, "message": "Entry removed"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ==========================================
# MOBILE API: BILLING & M-PESA
# ==========================================
@app.route('/api/process-mpesa', methods=['POST'])
@token_required
def api_process_mpesa():
    """Initiates an M-Pesa STK Push from the Flutter mobile app."""
    data = request.json
    phone = data.get('phone_number')
    amount = data.get('amount', 1)  # Defaulting to 1 for sandbox testing
    
    if not phone:
        return jsonify({"error": "Phone number is required"}), 400
        
    try:
        # 1. Call your existing M-Pesa integration function
        res = initiate_stk_push(phone, amount)
        
        # 2. Check if Safaricom accepted the request
        if res.get('ResponseCode') == '0':
            checkout_request_id = res.get("CheckoutRequestID")
            
            # 3. Save the pending transaction using the secure UID from the token
            uid = request.user['uid'] 
            
            rtdb.reference(f'pending_transactions/{checkout_request_id}').set({
                'user_id': uid, 
                'amount': amount, 
                'status': 'pending',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            return jsonify({
                "success": True, 
                "message": "STK Push initiated successfully."
            }), 200
        else:
            # Safaricom rejected the request (e.g., invalid number)
            error_msg = res.get('errorMessage', 'Failed to initiate M-Pesa request.')
            return jsonify({"error": error_msg}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


























# ==========================================
# PUBLIC MARKET INTELLIGENCE & AI
# ==========================================
@app.route('/market-intelligence')
def market_intelligence():
    try:
        featured_items = rtdb.reference('market_data').order_by_key().limit_to_last(3).get()
        preview_list = [{'id': k, **v} for k, v in featured_items.items()] if featured_items else []
        preview_list.reverse()
        return render_template('market intelligence.html', preview=preview_list)
    except Exception:
        return render_template('market intelligence.html', preview=[])

@app.route('/live-market-prices')
def live_market_prices():
    items = MarketData.query.order_by(MarketData.commodity.asc()).all()
    return render_template('live market prices.html', market_items=items)

@app.route('/trends-forecasts')
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
    items = rtdb.reference('market_data').get() or {}
    return jsonify([{'id': k, **v} for k, v in items.items()]), 200

# ==========================================
# PAYMENTS & CALLBACKS
# ==========================================
@app.route('/process-mpesa', methods=['POST'])
def process_mpesa():
    phone = request.form.get('phone_number')
    res = initiate_stk_push(phone, 1)
    if res.get('ResponseCode') == '0':
        rtdb.reference(f'pending_transactions/{res.get("CheckoutRequestID")}').set({
            'user_id': session['user_id'], 'amount': 1, 'status': 'pending'
        })
        flash("Check your phone!", "success")
        return redirect(url_for('payment_success'))
    flash("Error initiating M-Pesa.", "danger")
    return redirect(url_for('subscriber_checkout'))

@app.route('/mpesa-callback', methods=['POST'])
def mpesa_callback():
    data = request.json
    stk = data.get('Body', {}).get('stkCallback', {})
    if stk.get('ResultCode') == 0:
        meta = stk.get('CallbackMetadata', {}).get('Item', [])
        receipt = next((i['Value'] for i in meta if i['Name'] == 'MpesaReceiptNumber'), 'UNKNOWN')
        pending = rtdb.reference(f'pending_transactions/{stk.get("CheckoutRequestID")}').get()
        if pending:
            uid = pending.get('user_id')
            rtdb.reference(f'users/{uid}').update({'subscription_tier': 'pro'})
            rtdb.reference(f'completed_transactions/{uid}').push({
                'receipt_number': receipt, 'amount': pending.get('amount'),
                'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'plan': 'Pro Monthly'
            })
            rtdb.reference(f'pending_transactions/{stk.get("CheckoutRequestID")}').delete()
    return jsonify({"ResultCode": 0}), 200

@app.route('/success')
def payment_success(): return render_template('success.html')

# ==========================================
# STATIC PAGES & ERRORS
# ==========================================
@app.route('/')
def home(): return render_template('home.html')
@app.route('/about')
def about_us(): return render_template('about us.html')
@app.route('/impact')
def impact_initiatives(): return render_template('impact&initiatives.html')
@app.route('/pricing')
def pricing_subscription(): return render_template('pricing&subscription.html')
@app.route('/services')
def services(): return render_template('our services.html')
@app.route('/privacy-policy')
def privacy_policy(): return render_template('privacy policy.html')
@app.route('/terms-of-service')
def terms_of_service(): return render_template('terms of service.html')
@app.route('/refund-policy')
def refund_policy(): return render_template('subscription&refund policy.html')



#CONTACT US: Now with dropdown subjects and background email processing!

@app.route('/contact', methods=['GET', 'POST'])
def contact_us(): 
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject') # CAPTURES THE DROPDOWN
        message = request.form.get('message')
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. Save to Firebase RTDB (Now includes subject)
        rtdb.reference('contact_inquiries').push({
            'name': name, 
            'email': email,
            'subject': subject,
            'message': message, 
            'timestamp': timestamp
        })
        
        # 2. Render the HTML templates into strings
        current_year = datetime.now().year
        
        user_html = render_template('email_user_confirmation.html', 
                                    name=name, message=message, year=current_year)
                                    
        # Pass the subject into the admin template
        admin_html = render_template('email_admin_notification.html', 
                                     name=name, email=email, subject=subject, message=message, timestamp=timestamp)
        
        # 3. Pass everything to the background thread
        threading.Thread(
            target=send_async_emails, 
            args=(email, MAIL_USERNAME, user_html, admin_html, name, message, subject)
        ).start()
        
        # 4. Instantly redirect the user
        flash("Message sent! Check your email for a confirmation receipt.", "success")
        return redirect(url_for('contact_us'))
        
    return render_template('contact us.html')










@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    # Use the port assigned by Render, or default to 5000 for local dev
    port = int(os.environ.get("PORT", 5000))
    # Must use 0.0.0.0 to be visible to the outside world on Render
    app.run(host='0.0.0.0', port=port)