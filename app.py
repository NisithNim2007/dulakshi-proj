from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from config import *
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from flask import make_response
from reportlab.pdfgen import canvas
from io import BytesIO
from smtplib import SMTP
from email.message import EmailMessage
from flask import jsonify
from email.utils import formataddr
import os

app = Flask(__name__)
app.config.from_pyfile('config.py')
db = SQLAlchemy(app)

from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'admin':
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

# Models
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(255))
    role = db.Column(db.String(20), default='user')

class Journey(db.Model):
    __tablename__ = 'journeys'
    id = db.Column(db.Integer, primary_key=True)
    departure_city = db.Column(db.String(100))
    arrival_city = db.Column(db.String(100))
    departure_time = db.Column(db.Time)
    arrival_time = db.Column(db.Time)
    base_fare = db.Column(db.Float)

class SeatType(db.Model):
    __tablename__ = 'seat_types'
    id = db.Column(db.Integer, primary_key=True)
    type_name = db.Column(db.String(50))  # Economy, Business, First
    multiplier = db.Column(db.Float)

class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    journey_id = db.Column(db.Integer, db.ForeignKey('journeys.id'))
    seat_type_id = db.Column(db.Integer, db.ForeignKey('seat_types.id'))
    travel_date = db.Column(db.Date)
    final_price = db.Column(db.Float)
    status = db.Column(db.String(20), default='paid')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Cancellation(db.Model):
    __tablename__ = 'cancellations'
    id = db.Column(db.Integer, primary_key=True)
    days_before = db.Column(db.Integer)
    charge_percent = db.Column(db.Integer)

class Discount(db.Model):
    __tablename__ = 'discounts'
    id = db.Column(db.Integer, primary_key=True)
    days_before = db.Column(db.Integer)
    discount_percent = db.Column(db.Integer)

def send_cancellation_email(user_email, user_name, booking_id, route, travel_date, charge_amount):
    msg = EmailMessage()
    msg['Subject'] = f"Booking #{booking_id} Cancelled – Horizon Travels"
    msg['From'] = formataddr(("Horizon Travels", app.config['MAIL_USERNAME']))
    msg['To'] = user_email

    msg.set_content(f"""\
Hi {user_name},

Your booking (#{booking_id}) has been cancelled.

🔹 Route: {route}
🔹 Travel Date: {travel_date}
🔹 Cancellation Fee: £{charge_amount:.2f}

We hope to see you again soon!  
If you have any questions, please reach out to our support team.

— Horizon Travels Team
""")

    try:
        with SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as smtp:
            smtp.starttls()
            smtp.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            smtp.send_message(msg)
        print("✅ Cancellation email sent.")
    except Exception as e:
        print("❌ Failed to send cancellation email:", e)

def send_thank_you_email(email, name):
    msg = EmailMessage()
    msg['Subject'] = "🎉 Welcome to Horizon Travels!"
    msg['From'] = formataddr(("Horizon Travels", app.config['MAIL_USERNAME']))  # ✅ correct format
    msg['To'] = email

    msg.set_content(f"""\
Hi {name},

Thank you for registering with Horizon Travels! ✈️
We’re excited to have you on board and can’t wait to take you to amazing destinations.

Feel free to book your first trip now through your dashboard.

Safe travels!  
- The Horizon Travels Team
""")

    try:
        with SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as smtp:
            smtp.starttls()
            smtp.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            smtp.send_message(msg)
        print("✅ Thank-you email sent successfully.")
    except Exception as e:
        print("❌ Failed to send email:", e)



@app.route('/')
def index():
    return render_template('index.html', show_minimal_nav=True)

from flask import Flask, render_template, request, redirect, session, url_for, jsonify  # ✅ include jsonify

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()  # ✅ JSON from AJAX
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')

        if not name or not email or not password:
            return jsonify({'success': False, 'message': 'Missing fields'}), 400

        if User.query.filter_by(email=email).first():
            # 👉 On frontend JSON AJAX call
            return jsonify({'success': False, 'redirect': '/email-exists'}), 409

        new_user = User(name=name, email=email, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()

        send_thank_you_email(email, name)

        return jsonify({'success': True})

    return render_template('register.html')

@app.route('/email-exists')
def email_exists():
    return render_template('email_exists.html')


@app.route('/sending-thank-you')
def sending_thank_you():
    email = session.get('registered_email')
    name = session.get('registered_name')

    if not email or not name:
        return redirect('/register')

    send_thank_you_email(email, name)

    session.pop('registered_email', None)
    session.pop('registered_name', None)

    return '', 200  # just signal JS that it's done



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['role'] = user.role

            # 👇 Redirect based on role
            return redirect('/dashboard')
        else:
            return render_template('invalid_login.html')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('dashboard.html')

@app.route('/booking', methods=['GET', 'POST'])
def booking():
    if 'user_id' not in session:
        return redirect('/login')

    journeys = Journey.query.all()
    seats = SeatType.query.all()

    if request.method == 'POST':
        journey_id = int(request.form['journey_id'])
        seat_type_id = int(request.form['seat_type_id'])
        travel_date = datetime.strptime(request.form['travel_date'], '%Y-%m-%d').date()

        journey = Journey.query.get(journey_id)
        seat = SeatType.query.get(seat_type_id)

        # Calculate base price
        base_price = journey.base_fare * seat.multiplier

        # Discount logic
        days_diff = (travel_date - date.today()).days
        discount = 0
        if(days_diff > 120):
            return f"<h3>Error !!!!. Booking greater than 4 months.</h3><br><br><a href='/booking'>Back to Booking</a>."
        discount_rule = (
            Discount.query
            .filter(Discount.days_before <= days_diff)
            .order_by(Discount.days_before.desc())
            .first()
        )

        discount = discount_rule.discount_percent / 100 if discount_rule else 0
        discount_amount = base_price*discount
        final_price = round(base_price - discount_amount, 2)

        return render_template(
            'booking_summary.html',
            journey=journey,
            seat=seat,
            travel_date=travel_date,
            base_price=journey.base_fare,
            seat_multiplier=seat.multiplier,
            discount_percent=int(discount * 100),
            discount_amount=round(discount_amount, 2),
            final_price=final_price,
            journey_id=journey_id,
            seat_type_id=seat.id
        )

    return render_template('booking.html', journeys=journeys, seats=seats)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect('/login')

    user = User.query.get(session['user_id'])

    # Determine active tab
    selected_tab = request.args.get('tab', 'edit')  # default to 'edit'

    # Handle form submission
    if request.method == 'POST':
        form_type = request.form.get('form_type')

        if form_type == 'profile':
            new_name = request.form['name']
            new_email = request.form['email']

            # Check for email conflict
            existing = User.query.filter(User.email == new_email, User.id != user.id).first()
            if existing:
                return "Email already in use."

            user.name = new_name
            user.email = new_email
            session['user_name'] = new_name
            db.session.commit()

            # Stay on profile tab
            return redirect(url_for('profile', tab='edit'))

        elif form_type == 'password':
            current = request.form['current_password']
            new = request.form['new_password']
            confirm = request.form['confirm_password']

            if not check_password_hash(user.password, current):
                return "Current password incorrect."
            if new != confirm:
                return "New passwords do not match."

            user.password = generate_password_hash(new)
            db.session.commit()

            # Stay on password tab
            return redirect(url_for('profile', tab='password'))

    return render_template('profile.html', user=user, selected_tab=selected_tab)



def send_email(user_email, pdf_data, booking_id):
    msg = EmailMessage()
    msg['Subject'] = f"Your Horizon Travels Receipt #{booking_id}"
    msg['From'] = formataddr(("Horizon Travels", app.config['MAIL_USERNAME']))
    msg['To'] = user_email

    msg.set_content(f"""\
Hi there,

Thank you for your booking with Horizon Travels! 🎉
Please find your booking receipt (#{booking_id}) attached as a PDF.

We look forward to having you onboard!

– Horizon Travels Team
""")

    # Attach PDF
    msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=f'receipt_{booking_id}.pdf')

    try:
        with SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as smtp:
            smtp.starttls()
            smtp.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            smtp.send_message(msg)
        print("✅ PDF receipt email sent successfully.")
    except Exception as e:
        print("❌ Failed to send PDF receipt:", e)

@app.route('/confirm-booking', methods=['POST'])
def confirm_booking():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Invalid data'}), 400

    try:
        booking = Booking(
            user_id=session['user_id'],
            journey_id=int(data['journey_id']),
            seat_type_id=int(data['seat_type_id']),
            travel_date=datetime.strptime(data['travel_date'], '%Y-%m-%d').date(),
            final_price=float(data['final_price'])
        )
        db.session.add(booking)
        db.session.commit()

        user = User.query.get(session['user_id'])
        journey = Journey.query.get(booking.journey_id)
        seat = SeatType.query.get(booking.seat_type_id)

        # === 📄 PDF RECEIPT BUFFER ===
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=(600, 800))
        pdf.setTitle(f"Horizon Receipt #{booking.id}")

        # === 🖼 Logo + Heading ===
        logo_path = "static/images/horizon_logo.png"
        pdf.drawImage(logo_path, 40, 730, width=70, height=40, preserveAspectRatio=True)
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(120, 745, "Horizon Travels")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(120, 730, "Booking Receipt")
        pdf.drawRightString(570, 745, f"Date: {datetime.today().strftime('%Y-%m-%d')}")

        # === 🧾 Receipt Box ===
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(40, 690, "Receipt Summary")
        pdf.setLineWidth(0.5)
        pdf.line(40, 685, 560, 685)

        data_table = [
            ["Booking ID", f"{booking.id}"],
            ["Passenger Name", user.name],
            ["Email", user.email],
            ["Travel Date", str(booking.travel_date)],
            ["From", journey.departure_city],
            ["To", journey.arrival_city],
            ["Departure Time", journey.departure_time.strftime('%H:%M')],
            ["Arrival Time", journey.arrival_time.strftime('%H:%M')],
            ["Seat Type", seat.type_name],
            ["Total Paid", f"£{booking.final_price:.2f}"]
        ]

        y_start = 660
        row_height = 22
        pdf.setFont("Helvetica", 10)

        for label, value in data_table:
            pdf.setFillColorRGB(0.95, 0.95, 0.95)
            pdf.rect(40, y_start - row_height + 4, 240, row_height, fill=True, stroke=False)
            pdf.setFillColorRGB(1, 1, 1)
            pdf.rect(280, y_start - row_height + 4, 280, row_height, fill=False, stroke=False)
            pdf.setFillColorRGB(0, 0, 0)

            pdf.drawString(50, y_start, label)
            pdf.drawString(290, y_start, str(value))
            y_start -= row_height

        # === 💬 Footer ===
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.drawString(40, 80, "Thank you for booking with Horizon Travels! ✈️")
        pdf.drawString(40, 65, "Questions? Contact us at support@horizontravels.com")

        pdf.showPage()
        pdf.save()
        buffer.seek(0)

        send_email(user.email, buffer.read(), booking.id)

        return jsonify({
            'success': True,
            'redirect_url': f'/receipt/{booking.id}'
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500




@app.route('/receipt/<int:booking_id>')
def receipt(booking_id):
    if 'user_id' not in session:
        return redirect('/login')

    booking = db.session.query(
        Booking,
        Journey,
        SeatType,
        User
    ).join(Journey, Booking.journey_id == Journey.id)\
     .join(SeatType, Booking.seat_type_id == SeatType.id)\
     .join(User, Booking.user_id == User.id)\
     .filter(Booking.id == booking_id, Booking.user_id == session['user_id'])\
     .first()

    if not booking:
        return "Booking not found or unauthorized.", 404

    return render_template('receipt.html', booking=booking)

@app.route('/download-receipt/<int:booking_id>')
def download_receipt(booking_id):
    if 'user_id' not in session:
        return redirect('/login')

    booking = db.session.query(
        Booking,
        Journey,
        SeatType,
        User
    ).join(Journey, Booking.journey_id == Journey.id)\
     .join(SeatType, Booking.seat_type_id == SeatType.id)\
     .join(User, Booking.user_id == User.id)\
     .filter(Booking.id == booking_id, Booking.user_id == session['user_id'])\
     .first()

    if not booking:
        return "Unauthorized", 403

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(595.27, 841.89))  # A4 size

    # 🖼 Add logo (adjust path if needed)
    logo_path = os.path.join(app.root_path, 'static', 'images', 'horizon_logo.png')
    if os.path.exists(logo_path):
        pdf.drawInlineImage(logo_path, 40, 770, width=50, height=50)

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(100, 780, "Horizon Travels – Booking Receipt")

    pdf.setFont("Helvetica", 12)
    pdf.line(40, 765, 555, 765)

    y = 740
    spacing = 20

    def row(label, value):
        nonlocal y
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, y, f"{label}:")
        pdf.setFont("Helvetica", 12)
        pdf.drawString(200, y, str(value))
        y -= spacing

    row("Booking ID", booking.Booking.id)
    row("Name", booking.User.name)
    row("Email", booking.User.email)
    row("Route", f"{booking.Journey.departure_city} → {booking.Journey.arrival_city}")
    row("Departure Time", booking.Journey.departure_time.strftime("%H:%M"))
    row("Arrival Time", booking.Journey.arrival_time.strftime("%H:%M"))
    row("Travel Date", booking.Booking.travel_date.strftime('%Y-%m-%d'))
    row("Seat Type", booking.SeatType.type_name)
    row("Status", booking.Booking.status)
    row("Total Price", f"£{booking.Booking.final_price:.2f}")

    pdf.setFont("Helvetica-Oblique", 10)
    pdf.drawString(50, y - 20, "Thank you for booking with Horizon Travels! ✈️")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return make_response(buffer.read(), {
        'Content-Type': 'application/pdf',
        'Content-Disposition': f'attachment; filename=receipt_{booking.Booking.id}.pdf'
    })


@app.route('/my-bookings')
def my_bookings():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    raw_bookings = db.session.query(
        Booking.id,
        Booking.travel_date,
        Booking.final_price,
        Booking.status,
        Journey.departure_city,
        Journey.arrival_city,
        Journey.departure_time,
        Journey.arrival_time,
        SeatType.type_name.label('seat_type')
    ).join(Journey, Booking.journey_id == Journey.id)\
     .join(SeatType, Booking.seat_type_id == SeatType.id)\
     .filter(Booking.user_id == user_id)\
     .order_by(Booking.created_at.desc())\
     .all()
    
    bookings = []
    for index, row in enumerate(raw_bookings, start=1):
        bookings.append({
            'display_id': index,
            'booking_id': row.id,
            'travel_date': row.travel_date,
            'final_price': row.final_price,
            'status': row.status,
            'departure_city': row.departure_city,
            'arrival_city': row.arrival_city,
            'departure_time': row.departure_time,
            'arrival_time': row.arrival_time,
            'seat_type': row.seat_type
        })

    return render_template('my_bookings.html', bookings=bookings)

@app.route('/cancel-booking/<int:booking_id>', methods=['POST'])
def cancel_booking(booking_id):
    if 'user_id' not in session:
        return redirect('/login')

    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != session['user_id']:
        return "Unauthorized", 403

    days_left = (booking.travel_date - date.today()).days
    original_price = booking.final_price

    cancellation_rule = (
        Cancellation.query
        .filter(Cancellation.days_before <= days_left)
        .order_by(Cancellation.days_before.desc())
        .first()
    )

    charge_percent = cancellation_rule.charge_percent if cancellation_rule else 100
    charge = round((charge_percent / 100) * original_price, 2)

    # Update booking status
    booking.status = 'cancelled'
    db.session.commit()

    # Send cancellation email
    user = User.query.get(booking.user_id)
    journey = Journey.query.get(booking.journey_id)
    route = f"{journey.departure_city} → {journey.arrival_city}"
    send_cancellation_email(
        user.email,
        user.name,
        booking.id,
        route,
        booking.travel_date.strftime('%Y-%m-%d'),
        charge
    )

    return render_template(
        'cancel_confirmation.html',
        booking_id=booking.id,
        route=route,
        travel_date=booking.travel_date.strftime('%Y-%m-%d'),
        charge=round(charge, 2)

    )

@app.route('/update-booking/<int:booking_id>', methods=['GET', 'POST'])
def update_booking(booking_id):
    if 'user_id' not in session:
        return redirect('/login')

    booking = Booking.query.get_or_404(booking_id)

    # Only allow update by owner and only if not cancelled
    if booking.user_id != session['user_id'] or booking.status != 'paid':
        return "Unauthorized or booking not active", 403

    seat_types = SeatType.query.all()

    if request.method == 'POST':
        new_date = datetime.strptime(request.form['travel_date'], '%Y-%m-%d').date()
        new_seat_id = int(request.form['seat_type_id'])

        # Get related objects
        journey = Journey.query.get(booking.journey_id)
        new_seat = SeatType.query.get(new_seat_id)

        # Calculate new price with discount logic
        days_diff = (new_date - date.today()).days
        discount = 0
        if 91 <= days_diff <= 120:
            discount = 0.30
        elif 80 <= days_diff <= 90:
            discount = 0.20
        elif 60 <= days_diff <= 79:
            discount = 0.10
        elif 45 <= days_diff <= 59:
            discount = 0.05

        base_price = journey.base_fare * new_seat.multiplier
        final_price = round(base_price * (1 - discount), 2)

        # Update the booking
        booking.travel_date = new_date
        booking.seat_type_id = new_seat_id
        booking.final_price = final_price
        db.session.commit()

        return render_template(
            'update_confirmation.html',
            booking_id=booking.id,
            travel_date=new_date.strftime('%Y-%m-%d'),
            seat_type=new_seat.type_name,
            final_price=final_price
        )


    return render_template('update_booking.html', booking=booking, seat_types=seat_types)

@app.route('/admin')
@admin_required
def admin_dashboard():
    return redirect('/dashboard')

@app.route('/admin/users')
@admin_required
def view_users():
    users = User.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/bookings', methods=['GET', 'POST'])
@admin_required
def view_all_bookings():
    search_id = request.form.get('booking_id') if request.method == 'POST' else None

    query = db.session.query(
        Booking.id,
        User.name.label('user_name'),
        Journey.departure_city,
        Journey.arrival_city,
        Booking.travel_date,
        Booking.status,
        Booking.final_price
    ).join(User, Booking.user_id == User.id)\
     .join(Journey, Booking.journey_id == Journey.id)

    if search_id:
        query = query.filter(Booking.id == search_id)

    bookings = query.order_by(Booking.travel_date.desc()).all()

    return render_template('admin_bookings.html', bookings=bookings)


@app.route('/admin/journeys', methods=['GET', 'POST'])
@admin_required
def manage_journeys():
    journeys = Journey.query.all()
    if request.method == 'POST':
        dep = request.form['departure']
        arr = request.form['arrival']
        dep_time = datetime.strptime(request.form['departure_time'], '%H:%M').time()
        arr_time = datetime.strptime(request.form['arrival_time'], '%H:%M').time()
        fare = float(request.form['base_fare'])

        new_journey = Journey(
            departure_city=dep,
            arrival_city=arr,
            departure_time=dep_time,
            arrival_time=arr_time,
            base_fare=fare
        )
        db.session.add(new_journey)
        db.session.commit()
        return redirect('/admin/journeys')
    
    journeys = Journey.query.all()
    return render_template('admin_journeys.html', journeys=journeys)

@app.route('/make-admin')
def make_admin():
    if 'user_id' not in session:
        return redirect('/login')
    user = User.query.get(session['user_id'])
    user.role = 'admin'
    db.session.commit()
    return "You are now an admin! <a href='/admin'>Go to Admin Panel</a>"

@app.route('/clear-cancelled', methods=['POST'])
def clear_cancelled():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    # Delete all cancelled bookings for this user
    Booking.query.filter_by(user_id=user_id, status='cancelled').delete()
    db.session.commit()

    return redirect('/my-bookings')

@app.route('/admin/update-password', methods=['GET', 'POST'])
@admin_required
def update_user_password():
    if request.method == 'POST':
        email = request.form['email']
        new_password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            return "Password updated successfully."
        else:
            return "User not found."
    return render_template('update_user.html')

@app.route('/admin/journeys/delete/<int:journey_id>')
@admin_required
def delete_journey(journey_id):
    journey = Journey.query.get_or_404(journey_id)
    db.session.delete(journey)
    db.session.commit()
    return redirect('/admin/journeys')

@app.route('/admin/journeys/edit/<int:journey_id>', methods=['GET', 'POST'])
@admin_required
def edit_journey(journey_id):
    journey = Journey.query.get_or_404(journey_id)

    if request.method == 'POST':
        journey.departure_city = request.form['departure']
        journey.arrival_city = request.form['arrival']
        journey.departure_time = datetime.strptime(request.form['departure_time'], '%H:%M').time()
        journey.arrival_time = datetime.strptime(request.form['arrival_time'], '%H:%M').time()
        journey.base_fare = float(request.form['base_fare'])

        db.session.commit()
        return redirect('/admin/journeys')

    return render_template('edit_journey.html', journey=journey)

@app.route('/admin/search-booking', methods=['GET', 'POST'])
@admin_required
def search_booking():
    result = None

    if request.method == 'POST':
        booking_id = request.form['booking_id']

        result = db.session.query(
            Booking.id,
            Booking.travel_date,
            Booking.final_price,
            Booking.status,
            User.name.label('user_name'),
            SeatType.type_name.label('seat_type'),
            Journey.departure_city,
            Journey.arrival_city,
            Journey.departure_time,
            Journey.arrival_time
        ).join(User, Booking.user_id == User.id)\
         .join(Journey, Booking.journey_id == Journey.id)\
         .join(SeatType, Booking.seat_type_id == SeatType.id)\
         .filter(Booking.id == booking_id).first()

    return render_template('search_book.html', result=result)

@app.route('/admin/reports')
@admin_required
def reports_dashboard():
    return render_template('reports_dashboard.html')

@app.route('/admin/reports/monthly-sales')
@admin_required
def report_monthly_sales():
    sales = db.session.query(
        db.func.date_format(Booking.travel_date, "%Y-%m").label("month"),
        db.func.sum(Booking.final_price).label("total")
    ).filter(Booking.status == 'paid')\
     .group_by("month")\
     .order_by("month")\
     .all()
    
    return render_template('monthly_sales.html', sales=sales)


@app.route('/admin/reports/top-customers')
@admin_required
def report_top_customers():
    customers = db.session.query(
        User.name,
        db.func.sum(Booking.final_price).label("total_spent"),
        db.func.count(Booking.id).label("bookings")
    ).join(Booking).filter(Booking.status == 'paid')\
     .group_by(User.id).order_by(db.desc("total_spent")).limit(5).all()
    
    return render_template('top_customers.html', customers=customers)

@app.route('/admin/reports/top-routes')
@admin_required
def report_top_routes():
    routes = db.session.query(
        Journey.departure_city,
        Journey.arrival_city,
        db.func.sum(Booking.final_price).label("route_income"),
        db.func.count(Booking.id).label("bookings")
    ).join(Booking).filter(Booking.status == 'paid')\
     .group_by(Journey.id)\
     .order_by(db.desc("route_income")).all()

    return render_template('top_routes.html', routes=routes)

@app.route('/admin/reports/cancellations')
@admin_required
def report_cancellations():
    cancelled = db.session.query(
        db.func.count(Booking.id).label("total_cancelled"),
        db.func.sum(Booking.final_price).label("value_lost")
    ).filter(Booking.status == 'cancelled').first()

    return render_template('cancellations.html', cancelled=cancelled)


# ✅ MOVE THIS TO THE END!
if __name__ == '__main__':
    app.run(debug=True)

