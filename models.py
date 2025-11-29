from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    books = db.relationship("Book", backref="owner", lazy=True)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    authors = db.Column(db.String(200))
    published_date = db.Column(db.String(20))
    description = db.Column(db.Text)
    thumbnail = db.Column(db.String(300))
    google_books_link = db.Column(db.String(300))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
