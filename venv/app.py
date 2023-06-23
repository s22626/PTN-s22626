from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
from werkzeug.utils import secure_filename
import os

# Set the upload folder path
UPLOAD_FOLDER = os.path.join(os.getcwd(),'venv', 'static', 'uploads')

app = Flask(__name__, static_folder='static')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'your_secret_key'



# SQLite database connection
conn = sqlite3.connect('room_reservation.db', check_same_thread=False)
cursor = conn.cursor()

# Route for home page
@app.route('/')
def home():
    return redirect('/login')

# Route for user registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        password = request.form['password']

        try:
            # Open a new database connection
            conn = sqlite3.connect('room_reservation.db', check_same_thread=False)
            cursor = conn.cursor()

            # Check if the user already exists
            cursor.execute('SELECT * FROM user WHERE name=?', (name,))
            existing_user = cursor.fetchone()

            if existing_user:
                return "Username already exists"
            else:
                # Insert the new user into the database
                cursor.execute('INSERT INTO user (name, password, role) VALUES (?, ?, ?)', (name, password, 'user'))
                conn.commit()

                # Redirect to the login page after successful registration
                return redirect('/login')
        finally:
            # Close the database connection
            if conn:
                conn.close()
    else:
        return render_template('register.html')

# Route for user login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form['name']
        password = request.form['password']

        # Check if the user exists in the database
        cursor.execute('SELECT id, role FROM user WHERE name=? AND password=?', (name, password))
        user = cursor.fetchone()

        if user:
            session['user_id'] = user[0]
            session['role'] = user[1]
            return redirect('/dashboard')
        else:
            return "Invalid username or password"
    else:
        return render_template('login.html')

# Route for user dashboard
@app.route('/dashboard')
def dashboard():
    if 'user_id' in session:
        user_id = session['user_id']
        role = session['role']

        if role == 'owner':
            # Fetch all rooms
            cursor.execute('SELECT * FROM room')
            rooms = cursor.fetchall()

            # Fetch all reservations
            cursor.execute('SELECT r.room_id, rm.name, r.start_date, r.end_date FROM reservation r JOIN room rm ON r.room_id = rm.id')
            reservations = cursor.fetchall()

            return render_template('owner_dashboard.html', rooms=rooms, reservations=reservations)
        elif role == 'user':
            # Fetch user reservations
            cursor.execute('SELECT reservation.id, room.name, reservation.start_date, reservation.end_date FROM reservation JOIN room ON reservation.room_id = room.id WHERE reservation.user_id = ?',
                        (user_id,))
            reservations = cursor.fetchall()

            # Fetch all rooms
            rooms = get_all_rooms()

            return render_template('user_dashboard.html', reservations=reservations, rooms=rooms)
        else:
            return "Invalid user role"
    else:
        return redirect('/login')

# Route for room listings
@app.route('/rooms')
def room_listings():
    cursor.execute('SELECT * FROM room')
    rooms = cursor.fetchall()
    return render_template('rooms.html', rooms=rooms)

# Route for editing a room
@app.route('/edit_room/<int:room_id>', methods=['GET', 'POST'])
def edit_room(room_id):
    if 'user_id' in session:
        if request.method == 'POST':
            # Retrieve form data
            name = request.form['name']
            description = request.form['description']

            # Update the room in the database
            cursor.execute('UPDATE room SET name = ?, description = ? WHERE id = ?', (name, description, room_id))
            conn.commit()

            # Redirect to the owner's dashboard or display a success message
            return redirect('/dashboard')
        else:
            # Fetch the room from the database based on the room_id
            cursor.execute('SELECT * FROM room WHERE id = ?', (room_id,))
            room = cursor.fetchone()

            if room:
                return render_template('edit_room.html', room=room)
            else:
                return redirect('/dashboard')
    else:
        return redirect('/login')

# Route for deleting a room
@app.route('/rooms/delete/<int:room_id>', methods=['POST'])
def delete_room(room_id):
    if 'user_id' in session:
        role = session['role']

        if role == 'owner':
            # Delete the room from the database
            cursor.execute('DELETE FROM room WHERE id=?', (room_id,))
            conn.commit()

            return redirect('/rooms/manage')
        else:
            return "Access denied"
    else:
        return redirect('/dashboard')
    
# Route for adding a new room
@app.route('/add_room', methods=['GET', 'POST'])
def add_room():
    if 'user_id' in session:
        if request.method == 'POST':
            name = request.form['name']
            description = request.form['description']
            photo = request.files['photo']

            # Save the photo to a designated location
            filename = secure_filename(photo.filename)
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            # Insert the room into the database with the photo path
            cursor.execute('INSERT INTO room (name, description, photo_path) VALUES (?, ?, ?)',
                           (name, description, filename))
            conn.commit()

            return redirect('/dashboard')

        return render_template('add_room.html')
    else:
        return redirect('/login')

# Route for booking a room
@app.route('/book_room/<int:room_id>', methods=['POST'])
def book_room(room_id):
    if 'user_id' in session:
        user_id = session['user_id']
        start_date = request.form['start_date']
        end_date = request.form['end_date']

        # Check if there are any overlapping reservations for the room during the specified date range
        cursor.execute('SELECT * FROM reservation WHERE room_id = ? AND ((start_date <= ? AND end_date >= ?) OR (start_date <= ? AND end_date >= ?) OR (start_date >= ? AND end_date <= ?))',
                       (room_id, start_date, start_date, end_date, end_date, start_date, end_date))
        overlapping_reservations = cursor.fetchall()

        if overlapping_reservations:
            room = cursor.execute('SELECT * FROM room WHERE id = ?', (room_id,)).fetchone()
            error = 'Room "' + room[1] + '" is already booked during the specified date range.'
            rooms = get_all_rooms()
            return render_template('user_dashboard.html', rooms=rooms, error=error)

        # Create a new reservation
        cursor.execute('INSERT INTO reservation (user_id, room_id, start_date, end_date) VALUES (?, ?, ?, ?)',
                       (user_id, room_id, start_date, end_date))
        conn.commit()

        return redirect('/dashboard')
    else:
        return redirect('/login')
    
@app.route('/cancel_reservation/<int:reservation_id>', methods=['POST'])
def cancel_reservation(reservation_id):
    if 'user_id' in session:
        user_id = session['user_id']

        # Check if the reservation belongs to the logged-in user
        cursor.execute('SELECT * FROM reservation WHERE id = ? AND user_id = ?', (reservation_id, user_id))
        reservation = cursor.fetchone()

        if reservation:
            # Delete the reservation
            cursor.execute('DELETE FROM reservation WHERE id = ?', (reservation_id,))
            conn.commit()

            flash('Reservation canceled successfully', 'success')
        else:
            flash('Reservation not found or unauthorized', 'error')

        return redirect('/dashboard')
    else:
        return redirect('/login')
    
def get_all_rooms():
    cursor.execute('SELECT * FROM room')
    rooms = cursor.fetchall()
    return rooms

if __name__ == '__main__':
    app.run(debug=True)