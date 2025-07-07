from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from config import *
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        if User.query.filter_by(email=email).first():
            return 'Email already exists!'

        new_user = User(name=name, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect('/login')
    return render_template('register.html')

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
            if user.role == 'admin':
                return redirect('/admin')
            else:
                return redirect('/dashboard')
        else:
            return 'Invalid credentials'

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    return f"Welcome, {session['user_name']}! <a href='/logout'>Logout</a> <br><br> <a href='/booking'>Make a Booking</a> <br><br> <a href='/my-bookings'>View My Bookings</a>"

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

        if discount_rule:
            discount = discount_rule.discount_percent / 100
        else:
            discount = 0

        final_price = base_price * (1 - discount)

        new_booking = Booking(
            user_id=session['user_id'],
            journey_id=journey_id,
            seat_type_id=seat_type_id,
            travel_date=travel_date,
            final_price=round(final_price, 2)
        )

        db.session.add(new_booking)
        db.session.commit()

        return f"<h3>Booking Confirmed!</h3><p>Total: £{round(final_price, 2)}<br><a href='/dashboard'>Go to Dashboard</a>"

    return render_template('booking.html', journeys=journeys, seats=seats)

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

    # Only allow user to cancel their own bookings
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

    if cancellation_rule:
        charge_percent = cancellation_rule.charge_percent
    else:
        charge_percent = 100
    
    charge = (charge_percent/100) * original_price

    # Update booking status
    booking.status = 'cancelled'
    db.session.commit()

    # Optionally: log the cancellation fee in a 'cancellations' table if you want
    return f"""
        <h3>Booking Cancelled</h3>
        <p>Cancellation Charge: £{round(charge, 2)}</p>
        <a href='/my-bookings'>Back to My Bookings</a>
    """

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

        return f"<h3>Booking Updated!</h3><p>New Total: £{final_price}</p><a href='/my-bookings'>Go back</a>"

    return render_template('update_booking.html', booking=booking, seat_types=seat_types)

@app.route('/admin')
@admin_required
def admin_dashboard():
    return """
        <h2>Admin Dashboard</h2>
        <button><a href='/admin/users'>View Users</a></button><br>
        <button><a href='/admin/bookings'>View All Bookings</a></button><br>
        <button><a href='/admin/journeys'>Manage Journeys</a></button><br>
        <button><a href='/admin/reports'>View Reports</a></button><br>
        <button><a href='/logout'>Logout</a></button>
    """

@app.route('/admin/users')
@admin_required
def view_users():
    users = User.query.all()
    output = "<h2>All Users</h2><ul>"
    for u in users:
        output += f"<li>{u.name} ({u.email}) - Role: {u.role}</li>"
    output += "</ul><a href='/admin'>Back</a> <br><br> <a href='/admin/update-password'>Update User</a>"
    return output

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

    html = """
    <h2>All Bookings</h2>

    <form method="POST">
        <input type="number" name="booking_id" placeholder="Enter Booking ID" required>
        <button type="submit">Search</button>
        <button><a href="/admin/bookings">Reset</a></button>
    </form>
    <br>
    """

    if bookings:
        html += "<table border='1'><tr><th>ID</th><th>User</th><th>Route</th><th>Date</th><th>Status</th><th>Price</th></tr>"
        for b in bookings:
            html += f"<tr><td>{b.id}</td><td>{b.user_name}</td><td>{b.departure_city} → {b.arrival_city}</td><td>{b.travel_date}</td><td>{b.status}</td><td>£{b.final_price}</td></tr>"
        html += "</table>"
    else:
        html += "<p>No bookings found.</p>"

    html += "<br><a href='/admin'>← Back to Admin Dashboard</a>"
    return html


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
    html = "<h2>Manage Journeys</h2><table border='1'><tr><th>ID</th><th>From → To</th><th>Time</th><th>Fare</th><th>Action</th></tr>"
    for j in journeys:
        html += f"<tr><td>{j.id}</td><td>{j.departure_city} → {j.arrival_city}</td><td>{j.departure_time} → {j.arrival_time}</td><td>£{j.base_fare}</td>"
        html += f"<td><a href='/admin/journeys/edit/{j.id}'>Edit</a> | <a href='/admin/journeys/delete/{j.id}'>Delete</a></td></tr>"

    html += "</table><br>"
    html += """
    <h3>Add Journey</h3>
    <form method='POST'>
        Departure: <input name='departure'><br>
        Arrival: <input name='arrival'><br>
        Departure Time (HH:MM): <input name='departure_time'><br>
        Arrival Time (HH:MM): <input name='arrival_time'><br>
        Base Fare: <input name='base_fare'><br>
        <button type='submit'>Add Journey</button>
    </form>
    <br><a href='/admin'>Back to Admin Dashboard</a>
    """
    return html

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

    return f"""
    <h2>Edit Journey #{journey.id}</h2>
    <form method='POST'>
        Departure: <input name='departure' value='{journey.departure_city}'><br>
        Arrival: <input name='arrival' value='{journey.arrival_city}'><br>
        Departure Time (HH:MM): <input name='departure_time' value='{journey.departure_time.strftime('%H:%M')}'><br>
        Arrival Time (HH:MM): <input name='arrival_time' value='{journey.arrival_time.strftime('%H:%M')}'><br>
        Base Fare: <input name='base_fare' value='{journey.base_fare}'><br>
        <button type='submit'>Update Journey</button>
    </form>
    <br><a href='/admin/journeys'>Cancel</a>
    """

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
    return """
    <h2>Reports Dashboard</h2>
    <ul>
        <li><a href='/admin/reports/monthly-sales'>📅 Monthly Sales</a></li>
        <li><a href='/admin/reports/top-customers'>🧑 Top Customers</a></li>
        <li><a href='/admin/reports/top-routes'>✈️ Most Profitable Routes</a></li>
        <li><a href='/admin/reports/cancellations'>❌ Cancellations</a></li>
    </ul>
    <a href='/admin'>← Back to Admin Dashboard</a>
    """
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

    html = "<h2>📅 Monthly Sales Report</h2>"
    html += "<table border='1'><tr><th>Month</th><th>Total Sales</th></tr>"

    for s in sales:
        html += f"<tr><td>{s.month}</td><td>£{round(s.total, 2)}</td></tr>"

    html += "</table><br><a href='/admin/reports'>← Back to Reports</a>"
    return html


@app.route('/admin/reports/top-customers')
@admin_required
def report_top_customers():
    customers = db.session.query(
        User.name,
        db.func.sum(Booking.final_price).label("total_spent"),
        db.func.count(Booking.id).label("bookings")
    ).join(Booking).filter(Booking.status == 'paid')\
     .group_by(User.id).order_by(db.desc("total_spent")).limit(5).all()

    html = "<h2>Top 5 Customers</h2><table border='1'><tr><th>Name</th><th>Total Spent</th><th># of Bookings</th></tr>"
    for c in customers:
        html += f"<tr><td>{c.name}</td><td>£{round(c.total_spent, 2)}</td><td>{c.bookings}</td></tr>"
    html += "</table><br><a href='/admin/reports'>Back to Reports</a>"
    return html

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

    html = "<h2>Most Profitable Routes</h2><table border='1'><tr><th>Route</th><th>Total Income</th><th>Bookings</th></tr>"
    for r in routes:
        html += f"<tr><td>{r.departure_city} → {r.arrival_city}</td><td>£{round(r.route_income, 2)}</td><td>{r.bookings}</td></tr>"
    html += "</table><br><a href='/admin/reports'>Back to Reports</a>"
    return html

@app.route('/admin/reports/cancellations')
@admin_required
def report_cancellations():
    cancelled = db.session.query(
        db.func.count(Booking.id).label("total_cancelled"),
        db.func.sum(Booking.final_price).label("value_lost")
    ).filter(Booking.status == 'cancelled').first()

    html = "<h2>Cancellations Report</h2>"
    html += f"<p><strong>Total Cancelled Bookings:</strong> {cancelled.total_cancelled}</p>"
    html += f"<p><strong>Estimated Value Lost:</strong> £{round(cancelled.value_lost or 0, 2)}</p>"
    html += "<br><a href='/admin/reports'>Back to Reports</a>"
    return html


# ✅ MOVE THIS TO THE END!
if __name__ == '__main__':
    app.run(debug=True)

