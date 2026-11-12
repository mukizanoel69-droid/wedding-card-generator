import os
import re
import io
import gc
import uuid
import hashlib
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps

import pandas as pd
import qrcode
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from werkzeug.security import generate_password_hash, check_password_hash

from flask import Flask, render_template, request, send_file, redirect, url_for, flash, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
app = Flask(__name__)

# --- CONFIGURATION ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'JamboLetu_Master_Secret_2026_ChangeInProd')

database_url = os.environ.get('DATABASE_URL', 'sqlite:///jamboletu.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Card Print Constants
GATE_PASSWORD = "MK_GATE_TEAM_2026"
A4_WIDTH, A4_HEIGHT = A4
CARD_PRINT_WIDTH = 255   
CARD_PRINT_HEIGHT = 150  
SECRET_SALT = "JamboLetuStudio2026_SecureKey"

# Developer & Notification Credentials (Set in Render Environment Variables)
DEV_EMAIL = os.environ.get('DEV_EMAIL', 'mukizanoel69@gmail.com')
DEV_PHONE = os.environ.get('DEV_PHONE', '0621241005')
SMTP_EMAIL = os.environ.get('SMTP_EMAIL', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
SMS_API_KEY = os.environ.get('SMS_API_KEY', '')
SMS_SECRET_KEY = os.environ.get('SMS_SECRET_KEY', '')
SMS_SENDER_ID = os.environ.get('SMS_SENDER_ID', 'JAMBOLETU')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# --- DATABASE MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_developer = db.Column(db.Boolean, default=False)
    cards_generated = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    events = db.relationship('Event', backref='creator', lazy=True)

class Event(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = db.Column(db.String(150), nullable=False)
    event_date = db.Column(db.String(50), nullable=False)
    gate_password = db.Column(db.String(100), default="MK_GATE_TEAM_2026")
    status = db.Column(db.String(20), default='pending')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tickets = db.relationship('Ticket', backref='event', lazy=True, cascade="all, delete-orphan")

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    card_number = db.Column(db.String(50), nullable=False)
    guest_name = db.Column(db.String(150), nullable=False)
    guest_phone = db.Column(db.String(25), nullable=True)
    signature = db.Column(db.String(64), nullable=False)
    used = db.Column(db.Boolean, default=False)
    checked_in_at = db.Column(db.DateTime, nullable=True)
    duplicate_attempts = db.Column(db.Integer, default=0)
    event_id = db.Column(db.String(36), db.ForeignKey('event.id'), nullable=False)

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action_type = db.Column(db.String(50), nullable=False)
    details = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.before_request
def update_last_seen():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
# --- HELPER FUNCTIONS: VALIDATION, FONTS & NOTIFICATIONS ---
def get_custom_font(font_selection, text_size):
    try:
        if font_selection == "formal":
            return ImageFont.truetype("DejaVuSerif.ttf", text_size)
        elif font_selection == "fancy":
            return ImageFont.truetype("DejaVuSans-Oblique.ttf", text_size)
        return ImageFont.truetype("DejaVuSans.ttf", text_size)
    except IOError:
        try:
            return ImageFont.truetype("arial.ttf", text_size)
        except IOError:
            return ImageFont.load_default()

def is_strong_password(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must include at least one uppercase letter (A-Z)."
    if not re.search(r"[a-z]", password):
        return False, "Password must include at least one lowercase letter (a-z)."
    if not re.search(r"\d", password):
        return False, "Password must include at least one number (0-9)."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\\/;'~`]", password):
        return False, "Password must include at least one special character (e.g., @, #, $, !)."
    return True, "Strong password"

def send_email_alert(to_email, subject, body_text):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print(f"[EMAIL LOG] To: {to_email} | Subj: {subject} | Body: {body_text}")
        return False
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body_text, 'plain'))
        with smtplib.SMTP_SSL('://gmail.com', 465) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False

def send_sms_whatsapp_alert(phone_number, message):
    if not phone_number:
        return False
    clean_phone = str(phone_number).strip().replace("+", "").replace(" ", "")
    if clean_phone.startswith("0") and len(clean_phone) == 10:
        clean_phone = "255" + clean_phone[1:]

    if not SMS_API_KEY:
        print(f"[SMS/WHATSAPP LOG] To: {clean_phone} | Msg: {message}")
        return False
    try:
        url = "https://beem.africa"
        payload = {
            "source_addr": SMS_SENDER_ID,
            "encoding": 0,
            "schedule_time": "",
            "message": message,
            "recipients": [{"recipient_id": 1, "dest_addr": clean_phone}]
        }
        res = requests.post(url, json=payload, auth=(SMS_API_KEY, SMS_SECRET_KEY), timeout=8)
        return res.status_code == 200
    except Exception as e:
        print(f"[SMS/WHATSAPP ERROR] {e}")
        return False

def get_system_telemetry_summary():
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    five_mins_ago = datetime.utcnow() - timedelta(minutes=5)
    
    total_users = User.query.count()
    online_users = User.query.filter(User.last_seen >= five_mins_ago).count()
    logins_today = ActivityLog.query.filter(ActivityLog.action_type == 'login', ActivityLog.timestamp >= today_start).count()
    total_cards = db.session.query(db.func.sum(User.cards_generated)).scalar() or 0
    return (
        f"--- JAMBOLETU LIVE TELEMETRY ---\n"
        f"Total Registered Users: {total_users}\n"
        f"Currently Online (Last 5m): {online_users}\n"
        f"Logins Today: {logins_today}\n"
        f"Total Cards Generated System-Wide: {total_cards}\n"
    )

# Notify Developer Automatically on Any Abnormal Server Error (500)
@app.errorhandler(500)
def handle_500_error(e):
    err_msg = f"Abnormal 500 Server Error on {request.path}: {str(e)}"
    try:
        db.session.add(ActivityLog(action_type='error', details=err_msg[:250]))
        db.session.commit()
    except Exception:
        pass
    send_email_alert(DEV_EMAIL, "[CRITICAL] JamboLetu System Error", err_msg)
    send_sms_whatsapp_alert(DEV_PHONE, f"CRITICAL ALERT: {err_msg[:130]}")
    return "An unexpected system error occurred. The developer has been notified.", 500
# --- AUTHENTICATION ROUTES ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not username or not email or not password:
            flash("All required fields must be filled.", "danger")
            return redirect(url_for('register'))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for('register'))

        valid_pw, pw_msg = is_strong_password(password)
        if not valid_pw:
            flash(pw_msg, "danger")
            return redirect(url_for('register'))

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or Email already exists.", "danger")
            return redirect(url_for('register'))

        is_dev = (email == DEV_EMAIL.lower())
        new_user = User(
            username=username,
            email=email,
            phone=phone,
            password_hash=generate_password_hash(password),
            is_developer=is_dev
        )
        db.session.add(new_user)
        db.session.add(ActivityLog(action_type='register', details=f"New user: {username} ({email})"))
        db.session.commit()

        summary = get_system_telemetry_summary()
        send_email_alert(
            DEV_EMAIL,
            f"[JamboLetu] New User Registered: {username}",
            f"New user registered:\nUsername: {username}\nEmail: {email}\nPhone: {phone}\n\n{summary}"
        )

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username_or_email = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email.lower())
        ).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            user.last_seen = datetime.utcnow()
            db.session.add(ActivityLog(action_type='login', details=f"User logged in: {user.username}"))
            db.session.commit()

            summary = get_system_telemetry_summary()
            send_email_alert(
                DEV_EMAIL,
                f"[JamboLetu] User Login: {user.username}",
                f"User '{user.username}' ({user.email}) just logged in.\nCards generated by this user: {user.cards_generated}\n\n{summary}"
            )

            return redirect(url_for('index'))
        flash("Invalid username/email or password.", "danger")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = serializer.dumps(user.email, salt='password-reset-salt')
            reset_url = url_for('reset_password', token=token, _external=True)
            send_email_alert(
                user.email,
                "JamboLetu - Password Reset Request",
                f"Hello {user.username},\n\nClick the link below to reset your password (expires in 30 minutes):\n{reset_url}\n\nIf you did not request this, ignore this email."
            )
        flash("If that email exists in our system, a password reset link has been sent.", "info")
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=1800)
    except (SignatureExpired, BadSignature):
        flash("The password reset link is invalid or has expired.", "danger")
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(request.url)

        valid_pw, pw_msg = is_strong_password(new_password)
        if not valid_pw:
            flash(pw_msg, "danger")
            return redirect(request.url)

        user = User.query.filter_by(email=email).first_or_404()
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash("Your password has been updated! You can now log in.", "success")
        return redirect(url_for('login'))
    return render_template('reset_password.html')
# --- EVENT MANAGEMENT & DEVELOPER ADMIN ROUTES ---
def developer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_developer:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@login_required
def index():
    user_events = Event.query.filter_by(user_id=current_user.id).order_by(Event.created_at.desc()).all()
    approved_events = [e for e in user_events if e.status == 'approved']
    return render_template('index.html', events=user_events, approved_events=approved_events)

@app.route('/create-event', methods=['POST'])
@login_required
def create_event():
    title = request.form.get('event_title', '').strip()
    event_date = request.form.get('event_date', '').strip()
    gate_password = request.form.get('gate_password', 'MK_GATE_TEAM_2026').strip()

    if not title or not event_date:
        flash("Event Name and Event Date are required.", "danger")
        return redirect(url_for('index'))

    initial_status = 'approved' if current_user.is_developer else 'pending'

    new_event = Event(
        title=title,
        event_date=event_date,
        gate_password=gate_password if gate_password else "MK_GATE_TEAM_2026",
        status=initial_status,
        user_id=current_user.id
    )
    db.session.add(new_event)
    db.session.commit()

    if initial_status == 'pending':
        admin_url = url_for('developer_admin', _external=True)
        send_email_alert(
            DEV_EMAIL,
            f"[JamboLetu] Approval Needed: {title}",
            f"User '{current_user.username}' created a new event requiring your approval:\n"
            f"Event: {title}\nDate: {event_date}\n\n"
            f"Approve or Reject here:\n{admin_url}"
        )
        send_sms_whatsapp_alert(
            DEV_PHONE,
            f"JamboLetu Alert: User {current_user.username} created event '{title}' ({event_date}). Log in to approve."
        )
        flash("Event created! Waiting for administrator approval before generating cards.", "warning")
    else:
        flash("Event created and automatically approved!", "success")

    return redirect(url_for('index'))

@app.route('/developer-admin')
@login_required
@developer_required
def developer_admin():
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    five_mins_ago = datetime.utcnow() - timedelta(minutes=5)

    stats = {
        "total_users": User.query.count(),
        "online_users": User.query.filter(User.last_seen >= five_mins_ago).count(),
        "logins_today": ActivityLog.query.filter(ActivityLog.action_type == 'login', ActivityLog.timestamp >= today_start).count(),
        "registrations_today": ActivityLog.query.filter(ActivityLog.action_type == 'register', ActivityLog.timestamp >= today_start).count(),
        "total_cards": db.session.query(db.func.sum(User.cards_generated)).scalar() or 0,
        "pending_events": Event.query.filter_by(status='pending').count()
    }
    all_events = Event.query.order_by(Event.created_at.desc()).all()
    all_users = User.query.order_by(User.last_seen.desc()).all()
    recent_logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(30).all()

    return render_template('developer_admin.html', stats=stats, events=all_events, users=all_users, logs=recent_logs)

@app.route('/developer-admin/event/<event_id>/<action>', methods=['POST'])
@login_required
@developer_required
def moderate_event(event_id, action):
    ev = Event.query.get_or_404(event_id)
    if action == 'approve':
        ev.status = 'approved'
        db.session.commit()
        send_email_alert(
            ev.creator.email,
            f"Event Approved: {ev.title}",
            f"Hello {ev.creator.username},\n\nYour event '{ev.title}' ({ev.event_date}) has been approved! You can now generate cards on JamboLetu."
        )
        send_sms_whatsapp_alert(
            ev.creator.phone,
            f"JamboLetu: Hongera! Tukio lako '{ev.title}' limeidhinishwa. Sasa unaweza kutengeneza kadi."
        )
        flash(f"Event '{ev.title}' approved!", "success")
    elif action == 'reject':
        ev.status = 'rejected'
        db.session.commit()
        flash(f"Event '{ev.title}' rejected.", "danger")
    return redirect(url_for('developer_admin'))

@app.route('/download-template')
@login_required
def download_template():
    df = pd.DataFrame({
        'CARD_NO': ['001', '002'],
        'JINA': ['Juma Hamisi', 'Anna Wilson'],
        'SIMU': ['0757123456', '0712987654']
    })
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        df.to_excel(w, index=False, sheet_name='Guests')
    buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='Template.xlsx')
# --- CARD PREVIEW & BULK GENERATION ROUTES ---
@app.route('/preview', methods=['POST'])
@login_required
def preview_card():
    template_file = request.files['template_image']
    guest_name = request.form.get('preview_name', 'ANDIKA JINA HAPA').strip()
    
    font_selection = request.form.get('font_type', 'clean')
    font_color = request.form.get('font_color', '#2D0A31')
    font_size = int(request.form.get('font_size', 36))
    num_font_size = int(request.form.get('num_font_size', 36))
    
    text_x = int(request.form.get('text_x', 280))     
    name_y = int(request.form.get('name_y', 815))     
    card_no_y = int(request.form.get('card_no_y', 815)) 
    other_y = int(request.form.get('other_y', 730))   
    
    show_logo = request.form.get('show_logo', 'yes')
    show_phone = request.form.get('show_phone', 'yes')
    logo_size = int(request.form.get('logo_size', 90))
    logo_x = int(request.form.get('logo_x', 700))
    logo_y = int(request.form.get('logo_y', 20))
    qr_x_input = int(request.form.get('qr_x', 80))    
    qr_y_input = int(request.form.get('qr_y', 470))   
    
    template_file.seek(0)
    card_img = Image.open(template_file).convert("RGBA")
    draw = ImageDraw.Draw(card_img)
    
    if show_logo == 'yes':
        logo_path = os.path.join(os.path.dirname(__file__), 'logo.png')
        if os.path.exists(logo_path):
            try:
                logo_layer = Image.open(logo_path).convert("RGBA")
                logo_layer = logo_layer.resize((logo_size, logo_size))
                card_img.paste(logo_layer, (logo_x, logo_y), logo_layer)
            except Exception:
                pass
                
    font_jina = get_custom_font(font_selection, font_size)
    font_namba = get_custom_font(font_selection, num_font_size)
    font_brand = get_custom_font("clean", 24)
            
    if show_phone == 'yes':
        draw.text((800, 40), "MK 0621241005", fill="#FFFFFF", font=font_brand)
    draw.text((text_x, name_y), guest_name, fill=font_color, font=font_jina)
    draw.text((other_y, card_no_y), "MK-001 TEST", fill=font_color, font=font_namba)
    
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data("https://jamboletu.com")
    qr.make(fit=True)
    qr_graphic = qr.make_image(fill_color="#1E3A8A", back_color="white").convert("RGBA").resize((220, 220))
    card_img.paste(qr_graphic, (qr_x_input, qr_y_input), qr_graphic)
    
    buf = io.BytesIO()
    card_img.convert("RGB").save(buf, format="JPEG", quality=95)
    buf.seek(0)
    card_img.close()
    return send_file(buf, mimetype='image/jpeg')

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    event_id = request.form.get('event_id', '').strip()
    event = Event.query.filter_by(id=event_id, user_id=current_user.id).first()
    if not event:
        return "Invalid or unauthorized event selected.", 403
    if event.status != 'approved':
        return "This event is still pending administrator approval. Cards cannot be generated yet.", 403

    excel_file = request.files['excel_file']
    template_file = request.files['template_image']
    
    font_selection = request.form.get('font_type', 'clean')
    font_color = request.form.get('font_color', '#2D0A31')
    font_size = int(request.form.get('font_size', 36))
    num_font_size = int(request.form.get('num_font_size', 36))
    
    text_x = int(request.form.get('text_x', 280))     
    name_y = int(request.form.get('name_y', 815))     
    card_no_y = int(request.form.get('card_no_y', 815)) 
    other_y = int(request.form.get('other_y', 730))   
    
    show_logo = request.form.get('show_logo', 'yes')
    show_phone = request.form.get('show_phone', 'yes')
    logo_size = int(request.form.get('logo_size', 90))
    logo_x = int(request.form.get('logo_x', 700))
    logo_y = int(request.form.get('logo_y', 20))
    qr_x_input = int(request.form.get('qr_x', 80))    
    qr_y_input = int(request.form.get('qr_y', 470))   
    
    df = pd.read_excel(excel_file)
    pdf_buffer = io.BytesIO()
    pdf_canvas = canvas.Canvas(pdf_buffer, pagesize=A4)
    
    start_x, start_y = 42.5, 46.0  
    processed_count = 0
    
    template_file.seek(0)
    base_template_img = Image.open(template_file).convert("RGB")
    
    if show_logo == 'yes':
        logo_path = os.path.join(os.path.dirname(__file__), 'logo.png')
        if os.path.exists(logo_path):
            try:
                logo_layer = Image.open(logo_path).convert("RGBA").resize((logo_size, logo_size), Image.Resampling.BILINEAR)
                base_template_img.paste(logo_layer, (logo_x, logo_y), logo_layer)
                logo_layer.close()
            except Exception:
                pass

    font_jina = get_custom_font(font_selection, font_size)
    font_namba = get_custom_font(font_selection, num_font_size)
    font_brand = get_custom_font("clean", 24)
    
    if show_phone == 'yes':
        base_draw = ImageDraw.Draw(base_template_img)
        base_draw.text((800, 40), "MK 0621241005", fill="#FFFFFF", font=font_brand)
    
    host_origin = request.host_url.rstrip('/')
    if ("onrender.com" in host_origin or "jamboletu.com" in host_origin) and host_origin.startswith("http://"):
        host_origin = host_origin.replace("http://", "https://")
        
    total_rows = len(df)
    
    for index, row in df.iterrows():
        card_number = str(row.get('CARD_NO', '')).strip()
        guest_name = str(row.get('JINA', '')).strip()
        guest_phone = str(row.get('SIMU', '')).strip()
        if guest_phone == 'nan':
            guest_phone = ''
        
        if not card_number or not guest_name or card_number == 'nan' or guest_name == 'nan':
            continue
            
        security_hash = hashlib.sha256(f"{event.id}:{card_number}:{SECRET_SALT}".encode()).hexdigest()[:12]
        
        ticket = Ticket.query.filter_by(event_id=event.id, card_number=card_number).first()
        if not ticket:
            ticket = Ticket(
                card_number=card_number,
                guest_name=guest_name,
                guest_phone=guest_phone,
                signature=security_hash,
                event_id=event.id
            )
            db.session.add(ticket)
        else:
            ticket.guest_name = guest_name
            ticket.guest_phone = guest_phone
            ticket.signature = security_hash
        db.session.flush()

        verification_url = f"{host_origin}/verify?tid={ticket.id}&sig={security_hash}"
        
        card_img = base_template_img.copy()
        draw = ImageDraw.Draw(card_img)
                    
        draw.text((text_x, name_y), guest_name, fill=font_color, font=font_jina)
        draw.text((other_y, card_no_y), card_number, fill=font_color, font=font_namba)
            
        qr = qrcode.QRCode(version=2, box_size=4, border=1)
        qr.add_data(verification_url)
        qr.make(fit=True)
        qr_graphic = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((220, 220), Image.Resampling.NEAREST)
        card_img.paste(qr_graphic, (qr_x_input, qr_y_input))
            
        image_stream = io.BytesIO()
        card_img.save(image_stream, format="JPEG", quality=72, optimize=False)
        image_stream.seek(0)
            
        r_idx = (processed_count % 10) // 2
        c_idx = (processed_count % 10) % 2
        cx = start_x + c_idx * CARD_PRINT_WIDTH
        cy = start_y + (4 - r_idx) * CARD_PRINT_HEIGHT
            
        pdf_canvas.drawImage(canvas.ImageReader(image_stream), cx, cy, width=CARD_PRINT_WIDTH, height=CARD_PRINT_HEIGHT)
        pdf_canvas.setStrokeColorRGB(0.8, 0.8, 0.8)
        pdf_canvas.setLineWidth(0.5)               
        pdf_canvas.rect(cx, cy, CARD_PRINT_WIDTH, CARD_PRINT_HEIGHT, stroke=1, fill=0)
            
        image_stream.close()
        card_img.close()
        qr_graphic.close()
        
        processed_count += 1
        if processed_count % 10 == 0 and processed_count < total_rows: 
            pdf_canvas.showPage()
        if processed_count % 50 == 0:
            gc.collect()
            
    current_user.cards_generated += processed_count
    db.session.add(ActivityLog(action_type='generate', details=f"{current_user.username} generated {processed_count} bulk cards for '{event.title}'"))
    db.session.commit()
    base_template_img.close()
        
    pdf_canvas.save()
    pdf_buffer.seek(0)
    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name=f'{event.title}_Cards.pdf')
# --- SINGLE CARD GENERATOR, GATE VERIFICATION & ISOLATED DASHBOARD ---
@app.route('/generate-single', methods=['POST'])
@login_required
def generate_single():
    try:
        event_id = request.form.get('event_id', '').strip()
        event = Event.query.filter_by(id=event_id, user_id=current_user.id).first()
        if not event:
            return "Invalid or unauthorized event selected.", 403
        if event.status != 'approved':
            return "This event is still pending administrator approval.", 403

        template_file = request.files.get('template_image')
        guest_name = request.form.get('guest_name', 'MGENI').strip()
        card_number = request.form.get('guest_card_no', 'MK-000').strip()
        guest_phone = request.form.get('guest_phone', '').strip()
        download_format = request.form.get('download_format', 'JPEG').upper()
        
        font_selection = request.form.get('font_type', 'clean')
        font_color = request.form.get('font_color', '#2D0A31')
        font_size = int(request.form.get('font_size', 36))
        num_font_size = int(request.form.get('num_font_size', 36))
        
        text_x = int(request.form.get('text_x', 280))     
        name_y = int(request.form.get('name_y', 815))     
        card_no_y = int(request.form.get('card_no_y', 815)) 
        other_y = int(request.form.get('other_y', 730))   
        
        show_logo = request.form.get('show_logo', 'yes')
        show_phone = request.form.get('show_phone', 'yes')
        logo_size = int(request.form.get('logo_size', 90))
        logo_x = int(request.form.get('logo_x', 700))
        logo_y = int(request.form.get('logo_y', 20))
        qr_x_input = int(request.form.get('qr_x', 80))    
        qr_y_input = int(request.form.get('qr_y', 470))   
        
        if not template_file or template_file.filename == '':
            return "Missing template background image file", 400
            
        template_file.seek(0)
        card_img = Image.open(template_file).convert("RGBA")
        draw = ImageDraw.Draw(card_img)
        
        if show_logo == 'yes':
            logo_path = os.path.join(os.path.dirname(__file__), 'logo.png')
            if os.path.exists(logo_path):
                try:
                    logo_layer = Image.open(logo_path).convert("RGBA").resize((logo_size, logo_size), Image.Resampling.NEAREST)
                    card_img.paste(logo_layer, (logo_x, logo_y), logo_layer)
                    logo_layer.close()
                except Exception:
                    pass
                    
        font_jina = get_custom_font(font_selection, font_size)
        font_namba = get_custom_font(font_selection, num_font_size)
        font_brand = get_custom_font("clean", 24)
        
        if show_phone == 'yes':
            draw.text((800, 40), "MK 0621241005", fill="#FFFFFF", font=font_brand)
        draw.text((text_x, name_y), guest_name, fill=font_color, font=font_jina)
        draw.text((other_y, card_no_y), card_number, fill=font_color, font=font_namba)
        
        security_hash = hashlib.sha256(f"{event.id}:{card_number}:{SECRET_SALT}".encode()).hexdigest()[:12]
        
        ticket = Ticket.query.filter_by(event_id=event.id, card_number=card_number).first()
        if not ticket:
            ticket = Ticket(
                card_number=card_number,
                guest_name=guest_name,
                guest_phone=guest_phone,
                signature=security_hash,
                event_id=event.id
            )
            db.session.add(ticket)
        else:
            ticket.guest_name = guest_name
            ticket.guest_phone = guest_phone
            ticket.signature = security_hash

        current_user.cards_generated += 1
        db.session.add(ActivityLog(action_type='generate', details=f"{current_user.username} generated single card {card_number} for '{event.title}'"))
        db.session.commit()

        host_origin = request.host_url.rstrip('/')
        if ("onrender.com" in host_origin or "jamboletu.com" in host_origin) and host_origin.startswith("http://"):
            host_origin = host_origin.replace("http://", "https://")
            
        verification_url = f"{host_origin}/verify?tid={ticket.id}&sig={security_hash}"
            
        qr_graphic = qrcode.make(verification_url, box_size=4, border=1).convert("RGBA").resize((220, 220), Image.Resampling.NEAREST)
        card_img.paste(qr_graphic, (qr_x_input, qr_y_input), qr_graphic)
        
        buf = io.BytesIO()
        ext = "png" if download_format == "PNG" else "jpeg"
        mimetype = f"image/{ext}"
        save_format = "PNG" if download_format == "PNG" else "JPEG"
        
        if save_format == "JPEG":
            card_img.convert("RGB").save(buf, format=save_format, quality=95)
        else:
            card_img.save(buf, format=save_format)
            
        buf.seek(0)
        card_img.close()
        qr_graphic.close()
        
        filename = f"Kadi_{card_number}.{ext}"
        return send_file(buf, mimetype=mimetype, as_attachment=True, download_name=filename)
        
    except Exception as e:
        return f"Error executing single designer studio render process: {str(e)}", 500

@app.route('/verify', methods=['GET'])
def verify_ticket():
    ticket_id = request.args.get('tid', type=int)
    client_signature = request.args.get('sig', '')
    
    if not ticket_id:
        return render_template('verify.html', status='invalid')
        
    ticket = Ticket.query.get(ticket_id)
    if not ticket or ticket.signature != client_signature:
        return render_template('verify.html', status='invalid')

    if ticket.event.status != 'approved':
        return render_template('verify.html', status='invalid')
        
    event_header = f"{ticket.event.title} ({ticket.event.event_date})"
        
    if ticket.used:
        ticket.duplicate_attempts += 1
        db.session.commit()

        # Alert Event Creator (Admin) about Duplicate Entry Attempt
        creator = ticket.event.creator
        alert_msg = (
            f"SECURITY ALERT ({ticket.event.title}): Card #{ticket.card_number} "
            f"for '{ticket.guest_name}' was scanned AGAIN after already entering!"
        )
        send_email_alert(creator.email, f"[GATE ALERT] Duplicate Scan: {ticket.guest_name}", alert_msg)
        send_sms_whatsapp_alert(creator.phone, alert_msg)

        return render_template('verify.html', status='used', name=ticket.guest_name, event_title=event_header)
        
    return render_template('verify.html', status='valid', name=ticket.guest_name, id=ticket.id, event_title=event_header)

@app.route('/mark-used', methods=['POST'])
def mark_used():
    password = request.form.get('password', '').strip()
    ticket_id = request.form.get('id', type=int)
    
    ticket = Ticket.query.get(ticket_id)
    if not ticket:
        return "Ticket not found", 404

    expected_password = ticket.event.gate_password.strip() if ticket.event.gate_password else GATE_PASSWORD
    if password != expected_password:
        return "Unauthorized: Incorrect Gate Password", 403
        
    ticket.used = True
    ticket.checked_in_at = datetime.utcnow()
    db.session.commit()

    # Notify Guest via SMS/WhatsApp upon Entry
    if ticket.guest_phone:
        welcome_msg = (
            f"Karibu {ticket.guest_name}! Kadi yako #{ticket.card_number} "
            f"imehakikiwa kikamilifu kwenye {ticket.event.title}. Tunakutakia wakati mwema!"
        )
        send_sms_whatsapp_alert(ticket.guest_phone, welcome_msg)
        
    return redirect(url_for('verify_ticket', tid=ticket.id, sig=ticket.signature))

@app.route('/event/<event_id>/dashboard')
@login_required
def event_dashboard(event_id):
    event = Event.query.get_or_404(event_id)
    if event.user_id != current_user.id and not current_user.is_developer:
        abort(403)
    return render_template('dashboard.html', event=event)

@app.route('/api/event/<event_id>/stats')
@login_required
def api_event_stats(event_id):
    event = Event.query.get_or_404(event_id)
    if event.user_id != current_user.id and not current_user.is_developer:
        return {"error": "Unauthorized"}, 403

    tickets = Ticket.query.filter_by(event_id=event.id).order_by(Ticket.id.asc()).all()
    total_guests = len(tickets)
    checked_in = sum(1 for t in tickets if t.used)
    remaining = total_guests - checked_in

    guest_list = []
    for t in tickets:
        guest_list.append({
            "card_no": t.card_number,
            "name": t.guest_name,
            "phone": t.guest_phone or "-",
            "entered": t.used,
            "checked_in_at": t.checked_in_at.strftime("%H:%M:%S") if t.checked_in_at else "-"
        })

    return {
        "event_title": event.title,
        "event_date": event.event_date,
        "status": event.status,
        "total": total_guests,
        "checked_in": checked_in,
        "remaining": remaining,
        "guests": guest_list
    }

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))