from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change this in production

# Database setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///books.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

#User upload book cover if missing
UPLOAD_FOLDER = 'static/profile_pics'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB limit
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.Text, default="This user hasn't written a bio yet.")
    profile_pic = db.Column(db.String(300), default="default.png")  # store filename
    books = db.relationship('Book', backref='owner', lazy=True)

# Book model
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    authors = db.Column(db.String(200))
    description = db.Column(db.Text)
    thumbnail = db.Column(db.String(300))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Create DB tables
with app.app_context():
    db.create_all()

# ---------------- ROUTES ---------------- #

# Home page - show all books from all users
@app.route('/')
def index():
    books = Book.query.all()
    return render_template('index.html', books=books, user=session.get('username'))

# User registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        if User.query.filter_by(username=username).first():
            return "Username already exists!"

        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('register.html')

# User login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('my_books'))

        return "Invalid credentials!"

    return render_template('login.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# My Books page - only logged-in user's books
@app.route('/my_books')
def my_books():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    books = Book.query.filter_by(user_id=session['user_id']).all()
    return render_template('my_books.html', books=books, user=session['username'])

# New Search/add book route
@app.route('/search_books')
def search_books():
    query = request.args.get('q')
    if not query:
        return jsonify([])

    url = f"https://www.googleapis.com/books/v1/volumes?q={query}"
    r = requests.get(url)
    data = r.json()

    results = []
    if "items" in data:
        for item in data["items"][:5]:
            info = item["volumeInfo"]
            results.append({
                "google_id": item["id"],  # unique identifier
                "title": info.get("title"),
                "authors": ", ".join(info.get("authors", [])),
                "thumbnail": info.get("imageLinks", {}).get("thumbnail", ""),
                "description": info.get("description", "No description available.")
            })

    return jsonify(results)

# New Search/add book ID route
@app.route('/add_book_by_id', methods=['POST'])
def add_book_by_id():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 403

    google_id = request.json.get('google_id')
    if not google_id:
        return jsonify({"error": "No book ID provided"}), 400

    url = f"https://www.googleapis.com/books/v1/volumes/{google_id}"
    r = requests.get(url)
    data = r.json()
    info = data.get("volumeInfo", {})

    new_book = Book(
        title=info.get("title"),
        authors=", ".join(info.get("authors", [])),
        description=info.get("description", "No description available."),
        thumbnail=info.get("imageLinks", {}).get("thumbnail", ""),
        user_id=session['user_id']
    )
    db.session.add(new_book)
    db.session.commit()

    return jsonify({
        "success": True,
        "title": new_book.title,
        "authors": new_book.authors.split(", "),
        "thumbnail": new_book.thumbnail,
        "description": new_book.description,
        "book_id": new_book.id
    })

# Allow multiple books to be added
@app.route('/add_books', methods=['POST'])
def add_books():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 403

    query = request.form.get('query')
    if not query:
        return jsonify({"error": "No query provided"}), 400

    url = f"https://www.googleapis.com/books/v1/volumes?q={query}"
    r = requests.get(url)
    data = r.json()

    if "items" not in data:
        return jsonify({"error": "No books found"}), 404

    results = []
    for item in data["items"][:10]:  # limit to 10 results
        info = item["volumeInfo"]
        results.append({
            "google_id": item["id"],
            "title": info.get("title"),
            "authors": info.get("authors", []),
            "description": info.get("description", "No description available."),
            "thumbnail": info.get("imageLinks", {}).get("thumbnail", "")
        })

    return jsonify(results)

@app.route('/add_books_by_ids', methods=['POST'])
def add_books_by_ids():
    if 'user_id' not in session:
        return jsonify({"error": "Login required"}), 403

    ids = request.json.get('google_ids', [])
    if not ids:
        return jsonify({"error": "No book IDs provided"}), 400

    added_books = []
    for google_id in ids:
        url = f"https://www.googleapis.com/books/v1/volumes/{google_id}"
        r = requests.get(url)
        data = r.json()
        info = data.get("volumeInfo", {})

        new_book = Book(
            title=info.get("title"),
            authors=", ".join(info.get("authors", [])),
            description=info.get("description", "No description available."),
            thumbnail=info.get("imageLinks", {}).get("thumbnail", ""),
            user_id=session['user_id']
        )
        db.session.add(new_book)
        added_books.append({
            "title": new_book.title,
            "authors": new_book.authors.split(", "),
            "thumbnail": new_book.thumbnail,
            "description": new_book.description
        })

    db.session.commit()
    return jsonify({"success": True, "books": added_books})

# Open search results in new page 
@app.route('/search_results')
def search_results():
    query = request.args.get('q')
    if not query:
        return "No query provided", 400

    url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=25"
    r = requests.get(url)
    data = r.json()

    # Get all Google IDs already in the user's collection
    user_books = Book.query.filter_by(user_id=session['user_id']).all()
    user_google_ids = {b.google_id for b in user_books if hasattr(b, "google_id")}

    books = []
    if "items" in data:
        for item in data["items"]:
            info = item["volumeInfo"]
            google_id = item["id"]
            books.append({
                "google_id": google_id,
                "title": info.get("title"),
                "authors": ", ".join(info.get("authors", [])),
                "description": info.get("description", "No description available."),
                "thumbnail": info.get("imageLinks", {}).get("thumbnail", ""),
                "already_added": google_id in user_google_ids
            })

    return render_template("search_results.html", books=books, query=query)

# Remove book from user's collection
@app.route('/delete_book/<int:book_id>', methods=['POST'])
def delete_book(book_id):
    if 'user_id' not in session:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Login required"}), 403
        return redirect(url_for('login'))

    book = Book.query.get_or_404(book_id)

    if book.user_id != session['user_id']:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Unauthorized"}), 403
        return redirect(url_for('my_books'))

    db.session.delete(book)
    db.session.commit()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True, "book_id": book.id})
    else:
        return redirect(url_for('my_books'))

#Profile Page Route
@app.route('/profile/<username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    books = Book.query.filter_by(user_id=user.id).all()
    return render_template('profile.html', profile_user=user, books=books, user=session.get('username'))

#Edit Profile Page
@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    current_user = User.query.get(session['user_id'])

    if request.method == 'POST':
        bio = request.form.get('bio')
        if bio:
            current_user.bio = bio

        # Handle profile picture upload
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                current_user.profile_pic = filename

        db.session.commit()
        return redirect(url_for('profile', username=current_user.username))

    return render_template('edit_profile.html', user=session.get('username'), profile_user=current_user)

if __name__ == '__main__':
    app.run(debug=True)
