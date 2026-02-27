import os
import json
import base64
import stripe
import requests
from datetime import datetime
from functools import wraps 
from werkzeug.utils import secure_filename
from werkzeug.exceptions import NotFound

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

@app.route('/contact', methods=['GET', 'POST'])
def contact_us(): 
    if request.method == 'POST':
        rtdb.reference('contact_inquiries').push({
            'name': request.form.get('name'), 'email': request.form.get('email'),
            'message': request.form.get('message'), 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        flash("Message sent!", "success")
        return redirect(url_for('contact_us'))
    return render_template('contact us.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)