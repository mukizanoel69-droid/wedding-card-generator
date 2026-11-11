import os
import io
import gc
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
            except Exception: pass
                
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
def generate():
    excel_file = request.files['excel_file']
    template_file = request.files['template_image']
    
    event_title = request.form.get('event_title', '').strip()
    custom_gate_password = request.form.get('gate_password', '').strip()
    
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
    if "onrender.com" in host_origin and host_origin.startswith("http://"):
        host_origin = host_origin.replace("http://", "https://")
        
    tickets_db = load_tickets()
    total_rows = len(df)
    
    for index, row in df.iterrows():
        card_number = str(row.get('CARD_NO', '')).strip()
        guest_name = str(row.get('JINA', '')).strip()
        
        if not card_number or not guest_name or card_number == 'nan' or guest_name == 'nan':
            continue
            
        security_hash = hashlib.sha256(f"{card_number}{SECRET_SALT}".encode()).hexdigest()[:10]
        verification_url = f"{host_origin}/verify?id={card_number}&sig={security_hash}"
        
        tickets_db[card_number] = {
            "name": guest_name,
            "signature": security_hash,
            "used": tickets_db.get(card_number, {}).get('used', False),
            "event_title": event_title,
            "gate_password": custom_gate_password
        }
        
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
            
    save_tickets(tickets_db)
    base_template_img.close()
        
    pdf_canvas.save()
    pdf_buffer.seek(0)
    return send_file(pdf_buffer, mimetype='application/pdf', as_attachment=True, download_name='Print_Ready_Secure_Sheets.pdf')
@app.route('/verify', methods=['GET'])
def verify_ticket():
    ticket_id = request.args.get('id')
    client_signature = request.args.get('sig')
    
    tickets_db = load_tickets()
    
    if not ticket_id or ticket_id not in tickets_db: 
        return render_template('verify.html', status='invalid')
    
    ticket = tickets_db.get(ticket_id)
    if not ticket or ticket.get('signature') != client_signature:
        return render_template('verify.html', status='invalid')
        
    event_title = ticket.get('event_title', '')
        
    if ticket.get('used', False):
        return render_template('verify.html', status='used', name=ticket.get('name', 'Mgeni'), event_title=event_title)
        
    return render_template('verify.html', status='valid', name=ticket.get('name', 'Mgeni'), id=ticket_id, event_title=event_title)

@app.route('/mark-used', methods=['POST'])
def mark_used():
    password = request.form.get('password')
    ticket_id = request.form.get('id')
    
    tickets_db = load_tickets()
    if ticket_id in tickets_db:
        saved_custom_password = tickets_db[ticket_id].get('gate_password', '').strip()
        expected_password = saved_custom_password if saved_custom_password else GATE_PASSWORD
        
        if password != expected_password:
            return "Unauthorized: Incorrect Gate Password", 403
            
        tickets_db[ticket_id]['used'] = True
        save_tickets(tickets_db)
        
        signature = tickets_db[ticket_id].get('signature', '')
        return redirect(url_for('verify_ticket', id=ticket_id, sig=signature))
        
    return "Ticket not found", 404

@app.route('/generate-single', methods=['POST'])
def generate_single():
    try:
        template_file = request.files.get('template_image')
        guest_name = request.form.get('guest_name', 'MGENI').strip()
        card_number = request.form.get('guest_card_no', 'MK-000').strip()
        download_format = request.form.get('download_format', 'JPEG').upper()
        
        event_title = request.form.get('event_title', '').strip()
        custom_gate_password = request.form.get('gate_password', '').strip()
        
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
                except Exception: pass
                    
        font_jina = get_custom_font(font_selection, font_size)
        font_namba = get_custom_font(font_selection, num_font_size)
        font_brand = get_custom_font("clean", 24)
        
        if show_phone == 'yes':
            draw.text((800, 40), "MK 0621241005", fill="#FFFFFF", font=font_brand)
        draw.text((text_x, name_y), guest_name, fill=font_color, font=font_jina)
        draw.text((other_y, card_no_y), card_number, fill=font_color, font=font_namba)
        
        security_hash = hashlib.sha256(f"{card_number}{SECRET_SALT}".encode()).hexdigest()[:10]
        host_origin = request.host_url.rstrip('/')
        if "onrender.com" in host_origin and host_origin.startswith("http://"):
            host_origin = host_origin.replace("http://", "https://")
            
        verification_url = f"{host_origin}/verify?id={card_number}&sig={security_hash}"
        
        tickets_db = load_tickets()
        tickets_db[card_number] = {
            "name": guest_name,
            "signature": security_hash,
            "used": tickets_db.get(card_number, {}).get('used', False),
            "event_title": event_title,
            "gate_password": custom_gate_password
        }
        save_tickets(tickets_db)
            
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

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/stats')
def api_stats():
    try:
        selected_event = request.args.get('event', 'ALL').strip()
        tickets_db = load_tickets()
        
        unique_events = []
        latest_event = ""
        for t in tickets_db.values():
            ev = t.get('event_title', '').strip()
            if ev:
                latest_event = ev
                if ev not in unique_events:
                    unique_events.append(ev)
                    
        filtered_tickets = {}
        for card_no, data in tickets_db.items():
            if selected_event == 'ALL' or data.get('event_title', '').strip() == selected_event:
                filtered_tickets[card_no] = data
                
        total_guests = len(filtered_tickets)
        checked_in = sum(1 for t in filtered_tickets.values() if t.get('used', False))
        remaining = total_guests - checked_in
        
        recent_arrivals = []
        for card_no, data in filtered_tickets.items():
            if data.get('used', False):
                recent_arrivals.append({
                    "card_no": card_no,
                    "name": data.get('name', 'Mgeni')
                })
                
        return {
            "total": total_guests,
            "checked_in": checked_in,
            "remaining": remaining,
            "recent": recent_arrivals[-5:],
            "events": unique_events,
            "latest_event": latest_event
        }
    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))