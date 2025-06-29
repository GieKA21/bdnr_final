from flask import Flask, render_template, request, redirect, url_for, flash, session
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps
import datetime
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'hidhithere2172')


# --- Daftarkan datetime ke Jinja2 globals ---
app.jinja_env.globals.update(datetime=datetime)

# --- Konfigurasi Upload File ---
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# # Konfigurasi MongoDB
# client = MongoClient('mongodb://localhost:27017/')
# db = client['booking_wisata_db']

import os
MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://Shadiq:Shadiq2172@shadiq.lendtqt.mongodb.net/?retryWrites=true&w=majority&appName=shadiq')
client = MongoClient(MONGO_URI)
db = client['booking_wisata_db']



# Koleksi-koleksi MongoDB
users_col = db['users']
places_col = db['places']
bookings_col = db['bookings']

# --- Decorator untuk Autentikasi dan Otorisasi ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Anda harus login terlebih dahulu.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Anda harus login sebagai admin.', 'error')
            return redirect(url_for('login'))
        user = users_col.find_one({'_id': ObjectId(session['user_id'])})
        if not user or user.get('role') != 'admin':
            flash('Akses ditolak. Hanya admin yang bisa mengakses halaman ini.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes Aplikasi ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'user')

        if not username or not password:
            flash('Username dan password wajib diisi!', 'error')
            return render_template('register.html', username=username)
        
        if users_col.find_one({'username': username}):
            flash('Username sudah terdaftar. Pilih username lain.', 'error')
            return render_template('register.html', username=username)

        new_user = {
            'username': username,
            'password': password,
            'role': role
        }
        users_col.insert_one(new_user)
        flash('Registrasi berhasil! Silakan login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = users_col.find_one({'username': username})

        if user and user['password'] == password:
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f'Selamat datang, {user["username"]}!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Username atau password salah.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('role', None)
    flash('Anda telah logout.', 'info')
    return redirect(url_for('home'))

@app.route('/places')
def places_list():
    search_query = request.args.get('q', '')
    category_filter = request.args.get('category', 'all')
    
    query = {}
    
    if category_filter and category_filter != 'all':
        query['category'] = category_filter
    
    if search_query:
        search_condition = {
            '$or': [
                {'name': {'$regex': search_query, '$options': 'i'}},
                {'location': {'$regex': search_query, '$options': 'i'}}
            ]
        }
        if query:
            query = {'$and': [query, search_condition]}
        else:
            query = search_condition

    places = places_col.find(query)
    
    unique_categories = places_col.distinct('category')

    return render_template('places_list.html', 
                           places=places, 
                           search_query=search_query, 
                           selected_category=category_filter,
                           categories=unique_categories)

@app.route('/places/<id>')
def place_detail(id):
    try:
        place = places_col.find_one({'_id': ObjectId(id)})
        if not place:
            flash('Tempat wisata tidak ditemukan.', 'error')
            return redirect(url_for('places_list'))
        return render_template('place_detail.html', place=place)
    except Exception:
        flash('ID tempat wisata tidak valid.', 'error')
        return redirect(url_for('places_list'))

@app.route('/places/add', methods=['GET', 'POST'])
@admin_required
def add_place():
    if request.method == 'POST':
        name = request.form.get('name')
        location = request.form.get('location')
        description = request.form.get('description')
        price_per_person_str = request.form.get('price_per_person')
        category = request.form.get('category')
        
        image_url = 'https://placehold.co/400x300/a7b7c2/FFFFFF?text=No+Image'
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file.filename == '':
                flash('Tidak ada file yang dipilih untuk diunggah.', 'info')
            elif file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                image_url = url_for('static', filename=f'uploads/{filename}')
            else:
                flash('Jenis file gambar tidak diizinkan.', 'error')
                return render_template('add_edit_place.html', place=request.form)

        if not all([name, location, description, price_per_person_str, category]):
            flash('Semua field wajib diisi!', 'error')
            return render_template('add_edit_place.html', place=request.form)
        
        try:
            price_per_person = float(price_per_person_str)
            if price_per_person <= 0:
                flash('Harga per orang harus lebih dari 0.', 'error')
                return render_template('add_edit_place.html', place=request.form)
        except ValueError:
            flash('Harga per orang harus berupa angka!', 'error')
            return render_template('add_edit_place.html', place=request.form)

        new_place = {
            'name': name,
            'location': location,
            'description': description,
            'price_per_person': price_per_person,
            'image_url': image_url,
            'category': category
        }
        places_col.insert_one(new_place)
        flash('Tempat wisata berhasil ditambahkan!', 'success')
        return redirect(url_for('places_list'))
    return render_template('add_edit_place.html', place=None)

@app.route('/places/edit/<id>', methods=['GET', 'POST'])
@admin_required
def edit_place(id):
    try:
        place = places_col.find_one({'_id': ObjectId(id)})
        if not place:
            flash('Tempat wisata tidak ditemukan.', 'error')
            return redirect(url_for('places_list'))
        
        if request.method == 'POST':
            name = request.form.get('name')
            location = request.form.get('location')
            description = request.form.get('description')
            price_per_person_str = request.form.get('price_per_person')
            category = request.form.get('category')

            image_url = place.get('image_url', 'https://placehold.co/400x300/a7b7c2/FFFFFF?text=No+Image')
            if 'image_file' in request.files:
                file = request.files['image_file']
                if file.filename == '':
                    pass 
                elif file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    image_url = url_for('static', filename=f'uploads/{filename}')
                else:
                    flash('Jenis file gambar tidak diizinkan.', 'error')
                    return render_template('add_edit_place.html', place=place)

            if not all([name, location, description, price_per_person_str, category]):
                flash('Semua field wajib diisi!', 'error')
                return render_template('add_edit_place.html', place=place)
            
            try:
                price_per_person = float(price_per_person_str)
                if price_per_person <= 0:
                    flash('Harga per orang harus lebih dari 0.', 'error')
                    return render_template('add_edit_place.html', place=place)
            except ValueError:
                flash('Harga per orang harus berupa angka!', 'error')
                return render_template('add_edit_place.html', place=place)

            updated_place = {
                'name': name,
                'location': location,
                'description': description,
                'price_per_person': price_per_person,
                'image_url': image_url,
                'category': category
            }
            places_col.update_one({'_id': ObjectId(id)}, {'$set': updated_place})
            flash('Tempat wisata berhasil diperbarui!', 'success')
            return redirect(url_for('place_detail', id=id))
        
        return render_template('add_edit_place.html', place=place)
    except Exception as e:
        flash(f'ID tempat wisata tidak valid atau terjadi kesalahan: {e}', 'error')
        return redirect(url_for('places_list'))

@app.route('/places/delete/<id>')
@admin_required
def delete_place(id):
    try:
        bookings_col.delete_many({'place_id': ObjectId(id)})
        result = places_col.delete_one({'_id': ObjectId(id)})
        if result.deleted_count == 1:
            flash('Tempat wisata dan booking terkait berhasil dihapus!', 'success')
        else:
            flash('Tempat wisata tidak ditemukan.', 'error')
        return redirect(url_for('places_list'))
    except Exception:
        flash('ID tempat wisata tidak valid atau terjadi kesalahan.', 'error')
        return redirect(url_for('places_list'))

@app.route('/book/<place_id>', methods=['GET', 'POST'])
@login_required
def book_place(place_id):
    try:
        place = places_col.find_one({'_id': ObjectId(place_id)})
        if not place:
            flash('Tempat wisata tidak ditemukan.', 'error')
            return redirect(url_for('places_list'))

        if request.method == 'POST':
            booking_date_str = request.form.get('booking_date')
            num_people_str = request.form.get('num_people')

            if not all([booking_date_str, num_people_str]):
                flash('Tanggal booking dan jumlah orang wajib diisi!', 'error')
                return render_template('place_detail.html', place=place)

            try:
                booking_date = datetime.datetime.strptime(booking_date_str, '%Y-%m-%d')
                num_people = int(num_people_str)
                if num_people <= 0:
                    flash('Jumlah orang harus lebih dari 0.', 'error')
                    return render_template('place_detail.html', place=place)
                if booking_date < datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0):
                    flash('Tanggal booking tidak boleh di masa lalu.', 'error')
                    return render_template('place_detail.html', place=place)

            except ValueError:
                flash('Format input tidak valid. Pastikan tanggal dan jumlah orang benar.', 'error')
                return render_template('place_detail.html', place=place)

            total_price = place['price_per_person'] * num_people

            new_booking = {
                'user_id': ObjectId(session['user_id']),
                'place_id': ObjectId(place['_id']),
                'booking_date': booking_date,
                'num_people': num_people,
                'total_price': total_price,
                'status': 'pending', # Status awal adalah 'pending'
                'created_at': datetime.datetime.now()
            }
            bookings_col.insert_one(new_booking)
            flash('Booking Anda telah diajukan dan sedang menunggu konfirmasi admin.', 'info')
            return redirect(url_for('my_bookings'))
        
        return render_template('place_detail.html', place=place)
    except Exception:
        flash('ID tempat wisata tidak valid.', 'error')
        return redirect(url_for('places_list'))


@app.route('/my_bookings')
@login_required
def my_bookings():
    user_id = ObjectId(session['user_id'])

    pipeline = [
        {'$match': {'user_id': user_id}},
        {'$lookup': {
            'from': 'places',
            'localField': 'place_id',
            'foreignField': '_id',
            'as': 'place_details'
        }},
        {'$unwind': '$place_details'},
        {'$sort': {'booking_date': -1}}
    ]
    user_bookings = list(bookings_col.aggregate(pipeline))

    status_aggregation = [
        {'$match': {'user_id': user_id}},
        {'$group': {
            '_id': '$status',
            'count': {'$sum': 1}
        }}
    ]
    booking_status_summary = list(bookings_col.aggregate(status_aggregation))
    
    summary_dict = {item['_id']: item['count'] for item in booking_status_summary}


    return render_template('my_bookings.html', 
                           bookings=user_bookings,
                           booking_summary=summary_dict)

@app.route('/cancel_booking/<booking_id>')
@login_required
def cancel_booking(booking_id):
    try:
        booking = bookings_col.find_one({'_id': ObjectId(booking_id), 'user_id': ObjectId(session['user_id'])})
        if not booking:
            flash('Booking tidak ditemukan atau Anda tidak memiliki izin.', 'error')
            return redirect(url_for('my_bookings'))
        
        # Pengguna hanya bisa membatalkan booking yang pending atau confirmed
        if booking['status'] not in ['confirmed', 'pending']:
            flash('Booking tidak dapat dibatalkan dalam status saat ini.', 'error')
            return redirect(url_for('my_bookings'))

        bookings_col.update_one(
            {'_id': ObjectId(booking_id)},
            {'$set': {'status': 'cancelled'}}
        )
        flash('Booking berhasil dibatalkan!', 'success')
        return redirect(url_for('my_bookings'))
    except Exception:
        flash('ID booking tidak valid atau terjadi kesalahan.', 'error')
        return redirect(url_for('my_bookings'))

# --- Halaman Admin untuk Mengelola Booking ---
@app.route('/admin/bookings')
@admin_required
def admin_bookings():
    # Pipeline untuk mendapatkan semua booking dengan detail user dan place
    pipeline = [
        {'$lookup': { # Join dengan koleksi places
            'from': 'places',
            'localField': 'place_id',
            'foreignField': '_id',
            'as': 'place_details'
        }},
        {'$unwind': '$place_details'}, # Deconstruct the place_details array
        {'$lookup': { # Join dengan koleksi users untuk mendapatkan username
            'from': 'users',
            'localField': 'user_id',
            'foreignField': '_id',
            'as': 'user_details'
        }},
        {'$unwind': '$user_details'}, # Deconstruct the user_details array
        {'$sort': {'created_at': -1}} # Urutkan dari yang terbaru dibuat
    ]
    all_bookings = list(bookings_col.aggregate(pipeline))

    # Agregasi untuk ringkasan status booking secara keseluruhan
    status_summary_admin = [
        {'$group': {
            '_id': '$status',
            'count': {'$sum': 1}
        }}
    ]
    admin_summary_dict = {item['_id']: item['count'] for item in bookings_col.aggregate(status_summary_admin)}

    return render_template('admin_bookings.html', 
                           bookings=all_bookings,
                           booking_summary=admin_summary_dict)

@app.route('/admin/bookings/status/<booking_id>/<status>')
@admin_required
def update_booking_status(booking_id, status):
    if status not in ['confirmed', 'cancelled']:
        flash('Status tidak valid.', 'error')
        return redirect(url_for('admin_bookings'))

    try:
        booking = bookings_col.find_one({'_id': ObjectId(booking_id)})
        if not booking:
            flash('Booking tidak ditemukan.', 'error')
            return redirect(url_for('admin_bookings'))
        
        # Hanya admin yang bisa mengubah status dari 'pending' ke 'confirmed' atau 'cancelled'
        # Atau dari 'confirmed' ke 'cancelled' (jika ada pembatalan dari admin)
        if booking['status'] == 'pending' or (booking['status'] == 'confirmed' and status == 'cancelled'):
            bookings_col.update_one(
                {'_id': ObjectId(booking_id)},
                {'$set': {'status': status}}
            )
            flash(f'Status booking berhasil diubah menjadi {status}!', 'success')
        else:
            flash(f'Tidak dapat mengubah status booking dari {booking["status"]} ke {status}.', 'error')

        return redirect(url_for('admin_bookings'))
    except Exception:
        flash('ID booking tidak valid atau terjadi kesalahan.', 'error')
        return redirect(url_for('admin_bookings'))


if __name__ == '__main__':
    # Contoh data awal untuk admin (jalankan sekali saja untuk membuat admin pertama)
    # if not users_col.find_one({'username': 'admin'}):
    #     users_col.insert_one({'username': 'admin', 'password': 'adminpassword', 'role': 'admin'})
    #     print("Admin user created: username='admin', password='adminpassword'")

    # Pastikan folder uploads ada
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        print(f"Folder '{UPLOAD_FOLDER}' dibuat.")

    app.run(debug=False, host='0.0.0.0', port=os.environ.get('PORT', 5000))