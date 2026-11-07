import os
import io
import json
import hashlib
import pandas as pd
import qrcode
from flask import Flask, render_template, request, send_file, redirect, url_for
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = Flask(__name__)

DB_FILE = os.path.join(os.path.dirname(__file__), 'tickets.json')
GATE_PASSWORD = "MK_GATE_TEAM_2026"

A4_WIDTH, A4_HEIGHT = A4
CARD_PRINT_WIDTH = 255   
CARD_PRINT_HEIGHT = 150  
SECRET_SALT = "EnockFarajaWedding2026_SecureKey"

def load_tickets():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_tickets(data):
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error saving tickets file: {e}")

def get_custom_font(font_selection, text_size):
    try:
        if font_selection == "formal": return ImageFont.truetype("DejaVuSerif.ttf", text_size)
        elif font_selection == "fancy": return ImageFont.truetype("DejaVuSans-Oblique.ttf", text_size)
        return ImageFont.truetype("DejaVuSans.ttf", text_size)
    except IOError:
        try: return ImageFont.truetype("arial.ttf", text_size)
        except IOError: return ImageFont.load_default()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download-template')
def download_template():
    df = pd.DataFrame({'CARD_NO': ['001', '002'], 'JINA': ['Juma Hamisi', 'Anna Wilson']})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as w:
        df.to_excel(w, index=False, sheet_name='Guests')
    buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='Template.xlsx')

@app.route('/preview', methods=['POST'])
def preview_card():
    template_file = request.files['template_image']
    guest_name = request.form.get('preview_name', 'LENATUS PETER MVINGE').strip()
    
    font_selection = request.form.get('font_type', 'clean')
    font_color = request.form.get('font_color', '#2D0A31')
    font_size = int(request.form.get('font_size', 36))
    num_font_size = int(request.form.get('num_font_size', 36))
    
    text_x = int(request.form.get('text_x', 280))     
    name_y = int(request.form.get('name_y', 815))     
    card_no_y = int(request.form.get('card_no_y', 815)) 
    other_y = int(request.form.get('other_y', 730))   
    
    show_logo = request.form.get('show_logo', 'yes')
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
            except Exception: pass
                
    font_jina = get_custom_font(font_selection, font_size)
    font_namba = get_custom_font(font_selection, num_font_size)
    font_brand = get_custom_font("clean", 24)
            
    draw.text((800, 40), "MK 0621241005", fill="#FFFFFF", font=font_brand)
    draw.text((text_x, name_y), guest_name, fill=font_color, font=font_jina)
    draw.text((other_y, card_no_y), "MK-001 TEST", fill=font_color, font=font_namba)
    
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data("https://onrender.com")
    qr.make(fit=True)
    qr_graphic = qr.make_image(fill_color="#1E3A8A", back_color="white").convert("RGBA").resize((220, 220))
    card_img.paste(qr_graphic, (qr_x_input, qr_y_input), qr_graphic)
    
    buf = io.BytesIO()
    card_img.convert("RGB").save(buf, format="JPEG", quality=95)
    buf.seek(0)
    card_img.close()
    return send_file(buf, mimetype='image/jpeg')
@app.route('/generate', methods=['POST'])
def generate():
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
    base_template_img = Image.open(template_file).convert("RGBA")
    
    logo_layer = None
    if show_logo == 'yes':
        logo_path = os.path.join(os.path.dirname(__file__), 'logo.png')
        if os.path.exists(logo_path):
            try:
                logo_layer = Image.open(logo_path).convert("RGBA").resize((logo_size, logo_size), Image.Resampling.NEAREST)
            except Exception: pass

    font_jina = get_custom_font(font_selection, font_size)
    font_namba = get_custom_font(font_selection, num_font_size)
    font_brand = get_custom_font("clean", 24)
    
    # SAFE LOGIC: Clean up domain routing scheme for proxies
    host_origin = request.host_url.rstrip('/')
    if "onrender.com" in host_origin and host_origin.startswith("http://"):
        host_origin = host_origin.replace("http://", "https://")
        
    tickets_db = load_tickets()
    
    for index, row in df.iterrows():
        card_number = str(row.get('CARD_NO', '')).strip()
        guest_name = str(row.get('JINA', '')).strip()
        
        if not card_number or not guest_name:
            continue
            
        security_hash = hashlib.sha256(f"{card_number}{SECRET_SALT}".encode()).hexdigest()[:10]
        verification_url = f"{host_origin}/verify?id={card_number}&sig={security_hash}"
        
        tickets_db[card_number] = {"name": guest_name, "signature": security_hash, "used": tickets_db.get(card_number, {}).get('used', False)}
        
        card_img = base_template_img.copy()
        draw = ImageDraw.Draw(card_img)
        
        if logo_layer:
            card_img.paste(logo_layer, (logo_x, logo_y), logo_layer)
                    
        draw.text((800, 40), "MK 0621241005", fill="#FFFFFF", font=font_brand)
        draw.text((text_x, name_y), guest_name, fill=font_color, font=font_jina)
        draw.text((other_y, card_no_y), card_number, fill=font_color, font=font_namba)
            
        qr_graphic = qrcode.make(verification_url, box_size=4, border=1).convert("RGBA").resize((220, 220), Image.Resampling.NEAREST)
        card_img.paste(qr_graphic, (qr_x_input, qr_y_input), qr_graphic)
            
        image_stream = io.BytesIO()
        card_img.convert("RGB").save(image_stream, format="JPEG", quality=85)
        image_stream.seek(0)
            
        r_idx = (processed_count % 10) // 2
        c_idx = (processed_count % 10) % 2
        cx = start_x + c_idx * CARD_PRINT_WIDTH
        cy = start_y + (4 - r_idx) * CARD_PRINT_HEIGHT
            
        pdf_canvas.drawImage(canvas.ImageReader(image_stream), cx, cy, width=CARD_PRINT_WIDTH, height=CARD_PRINT_HEIGHT)
        pdf_canvas.setStrokeColorRGB(0.8, 0.8, 0.8) 
        pdf_canvas.setLineWidth(0.5)               
        pdf_canvas.rect(cx, cy, CARD_PRINT_WIDTH, CARD_PRINT_HEIGHT, stroke=1, fill=0)
            
        card_img.close()
        qr_graphic.close()
        
        processed_count += 1
        if processed_count % 10 == 0 and processed_count < len(df): 
            pdf_canvas.showPage()
            
    save_tickets(tickets_db)
    base_template_img.close()
    if logo_layer:
        logo_layer.close()
        
    pdf_canvas.save()
    pdf_buffer.seek(0)
    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name='Print_Ready_Secure_Sheets.pdf')

@app.route('/verify', methods=['GET'])
def verify_ticket():
    ticket_id = request.args.get('id')
    client_signature = request.args.get('sig')
    
    tickets_db = load_tickets()
    
    # SAFE LOGIC: Strict existence drop controls to prevent KeyError crashes
    if not ticket_id or ticket_id not in tickets_db: 
        return render_template('verify.html', status='invalid')
    
    ticket = tickets_db.get(ticket_id)
    if not ticket or ticket.get('signature') != client_signature:
        return render_template('verify.html', status='invalid')
        
    if ticket.get('used', False):
        return render_template('verify.html', status='used', name=ticket.get('name', 'Mgeni'))
        
    return render_template('verify.html', status='valid', name=ticket.get('name', 'Mgeni'), id=ticket_id)

@app.route('/mark-used', methods=['POST'])
def mark_used():
    password = request.form.get('password')
    ticket_id = request.form.get('id')
    
    if password != GATE_PASSWORD:
        return "Unauthorized: Incorrect Gate Password", 403
        
    tickets_db = load_tickets()
    if ticket_id in tickets_db:
        tickets_db[ticket_id]['used'] = True
        save_tickets(tickets_db)
        
        signature = tickets_db[ticket_id].get('signature', '')
        return redirect(url_for('verify_ticket', id=ticket_id, sig=signature))
        
    return "Ticket not found", 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))