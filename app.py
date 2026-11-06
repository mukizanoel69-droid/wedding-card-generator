import os
import io
import hashlib
import pandas as pd
import qrcode
from flask import Flask, render_template, request, send_file, redirect, url_for
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = Flask(__name__)

# Ultra-fast live memory framework database tracking entrance statuses
TICKET_DATABASE = {}

# Official staff gate control entry authorization password
GATE_PASSWORD = "MK_GATE_TEAM_2026"

A4_WIDTH, A4_HEIGHT = A4
CARD_PRINT_WIDTH = 255   
CARD_PRINT_HEIGHT = 150  
SECRET_SALT = "EnockFarajaWedding2026_SecureKey"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    excel_file = request.files['excel_file']
    template_file = request.files['template_image']
    
    text_x = int(request.form.get('text_x', 280))     
    name_y = int(request.form.get('name_y', 815))     
    card_no_y = int(request.form.get('card_no_y', 815)) 
    other_y = int(request.form.get('other_y', 730))   
    
    qr_x_input = int(request.form.get('qr_x', 80))    
    qr_y_input = int(request.form.get('qr_y', 470))   
    
    df = pd.read_excel(excel_file)
    
    pdf_buffer = io.BytesIO()
    pdf_canvas = canvas.Canvas(pdf_buffer, pagesize=A4)
    
    start_x = 42.5  
    start_y = 46.0  
    processed_count = 0
    
    logo_layer = None
    try:
        logo_path = os.path.join(os.path.dirname(__file__), 'logo.png')
        if os.path.exists(logo_path):
            logo_layer = Image.open(logo_path).convert("RGBA")
            logo_layer = logo_layer.resize((90, 90))
    except Exception:
        logo_layer = None # Safely skip if the file is unreadable or missing
        
    for index, row in df.iterrows():
        card_number = str(row.get('CARD_NO', '')).strip()
        guest_name = str(row.get('JINA', '')).strip()
        
        # 1. Generate unique security tokens for every guest item row
        security_hash = hashlib.sha256(f"{card_number}{SECRET_SALT}".encode()).hexdigest()[:10]
        
        # 2. Build live dynamic domain routing strings
        host_origin = request.host_url.rstrip('/')
        verification_url = f"{host_origin}/verify?id={card_number}&sig={security_hash}"
        
        # Seed record initialization into live check tracking system
        TICKET_DATABASE[card_number] = {"name": guest_name, "signature": security_hash, "used": False}
        
        template_file.seek(0)
        card_img = Image.open(template_file).convert("RGBA")
        draw = ImageDraw.Draw(card_img)
        
        try:
             # This checks a common Linux font path first
             font_jina = ImageFont.truetype("DejaVuSans.ttf", 36)
             font_namba = ImageFont.truetype("DejaVuSans.ttf", 36)
             font_brand = ImageFont.truetype("DejaVuSans.ttf", 24)
        except IOError:
             try:
                 font_jina = ImageFont.truetype("arial.ttf", 36)
                 font_namba = ImageFont.truetype("arial.ttf", 36)
                 font_brand = ImageFont.truetype("arial.ttf", 24)
             except IOError:
                 font_jina = ImageFont.load_default()
                 font_namba = ImageFont.load_default()
                 font_brand = ImageFont.load_default()
                
            # Draw branding texts, logo icons, and client names
        draw.text((800, 40), "MK 0621241005", fill="#FFFFFF", font=font_brand)
        if logo_layer:
            card_img.paste(logo_layer, (700, 20), logo_layer)
                
        draw.text((text_x, name_y), guest_name, fill="#2D0A31", font=font_jina)
        draw.text((other_y, card_no_y), card_number, fill="#2D0A31", font=font_namba)
            
        qr = qrcode.QRCode(box_size=4, border=1)
        qr.add_data(verification_url)
        qr.make(fit=True)
        qr_graphic = qr.make_image(fill_color="#1E3A8A", back_color="white").convert("RGBA")
        qr_graphic = qr_graphic.resize((220, 220))
        card_img.paste(qr_graphic, (qr_x_input, qr_y_input), qr_graphic)
            
        image_stream = io.BytesIO()
        card_img.convert("RGB").save(image_stream, format="JPEG", quality=98)
        image_stream.seek(0)
            
        row_position_index = (processed_count % 10) // 2
        column_position_index = (processed_count % 10) % 2
            
        computed_x = start_x + column_position_index * CARD_PRINT_WIDTH
        computed_y = start_y + (4 - row_position_index) * CARD_PRINT_HEIGHT
            
        pdf_canvas.drawImage(canvas.ImageReader(image_stream), computed_x, computed_y, width=CARD_PRINT_WIDTH, height=CARD_PRINT_HEIGHT)
            
        # Thin grey cutout border guide bounding boxes
        pdf_canvas.setStrokeColorRGB(0.8, 0.8, 0.8) 
        pdf_canvas.setLineWidth(0.5)               
        pdf_canvas.rect(computed_x, computed_y, CARD_PRINT_WIDTH, CARD_PRINT_HEIGHT, stroke=1, fill=0)
            
        processed_count += 1
        if processed_count % 10 == 0 and processed_count < len(df):
            pdf_canvas.showPage()
            
    pdf_canvas.save()
    pdf_buffer.seek(0)
    
    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name='Print_Ready_Secure_Sheets.pdf')

# --- DUAL-MODE ROUTE: SAFE FOR GUESTS, LOGIN ACTIONABLE FOR CREW ---
@app.route('/verify', methods=['GET'])
def verify_ticket():
    ticket_id = request.args.get('id')
    client_signature = request.args.get('sig')
    
    if not ticket_id or ticket_id not in TICKET_DATABASE:
        return render_template('verify.html', status='invalid')
        
    ticket = TICKET_DATABASE[ticket_id]
    if ticket['signature'] != client_signature:
        return render_template('verify.html', status='fraud')
        
    # Simply renders details without altering check-in status definitions
    return render_template('verify.html', status='ok', ticket=ticket, ticket_id=ticket_id, signature=client_signature)

# --- AUTHORIZED ENTRANCE APPROVAL GATE ROUTE ---
@app.route('/confirm', methods=['POST'])
def confirm_entry():
    ticket_id = request.form.get('id')
    client_signature = request.form.get('sig')
    password_input = request.form.get('password')
    
    # Verify password authentication credentials
    if password_input != GATE_PASSWORD:
        return "<h1>❌ AUTHENTICATION ERROR: Nenosiri la Gateni si Sahihi!</h1>", 401
        
    if ticket_id in TICKET_DATABASE and TICKET_DATABASE[ticket_id]['signature'] == client_signature:
        TICKET_DATABASE[ticket_id]['used'] = True # Officially check them in
        
    return redirect(url_for('verify_ticket', id=ticket_id, sig=client_signature))

if __name__ == '__main__':
    app.run(debug=True)