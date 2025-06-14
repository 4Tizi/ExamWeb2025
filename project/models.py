from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from markdown import markdown
import bleach, os, hashlib

from extensions import db, login_manager

book_genres = db.Table(
    'book_genres',
    db.Column('book_id', db.Integer, db.ForeignKey('book.id',ondelete='CASCADE')),
    db.Column('genre_id', db.Integer, db.ForeignKey('genre.id',ondelete='CASCADE'))
)

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    last_name = db.Column(db.String(64), nullable=False)
    first_name = db.Column(db.String(64), nullable=False)
    middle_name = db.Column(db.String(64))
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    role = db.relationship('Role')
    reviews = db.relationship('Review', back_populates='user', cascade='all, delete', passive_deletes=True)

    @property
    def full_name(self):
        return f"{self.last_name} {self.first_name} {self.middle_name or ''}".strip()

    @property
    def password(self):
        raise AttributeError()

    @password.setter
    def password(self, pwd):
        self.password_hash = generate_password_hash(pwd)

    def verify_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Genre(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)

class Cover(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(128), nullable=False)
    mimetype = db.Column(db.String(64), nullable=False)
    md5_hash = db.Column(db.String(64), nullable=False, unique=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id', ondelete='CASCADE'), nullable=False)

class Book(db.Model):
    @property
    def description_html(self):
        from markdown import markdown
        import bleach
        allowed=['p','ul','ol','li','strong','em','code','pre','blockquote','h1','h2','h3','br']
        return bleach.clean(markdown(self.description, output_format='html'), tags=allowed, strip=True)

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    publisher = db.Column(db.String(128), nullable=False)
    author = db.Column(db.String(128), nullable=False)
    pages = db.Column(db.Integer, nullable=False)

    genres = db.relationship('Genre', secondary=book_genres, backref='books')
    cover = db.relationship('Cover', backref='book', uselist=False, cascade='all, delete')
    reviews = db.relationship('Review', back_populates='book', cascade='all, delete', passive_deletes=True)

    def avg_rating(self):
        approved_reviews = [r.rating for r in self.reviews if r.status and r.status.name == 'approved']
        return round(sum(approved_reviews)/len(approved_reviews),2) if approved_reviews else None

class ReviewStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id',ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id',ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    text_md = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status_id = db.Column(db.Integer, db.ForeignKey('review_status.id'), nullable=False)

    book = db.relationship('Book', back_populates='reviews')
    user = db.relationship('User', back_populates='reviews')
    status = db.relationship('ReviewStatus')

    @property
    def text_html(self):
        allowed = ['p','ul','ol','li','strong','em','code','pre','blockquote','h1','h2','h3','br']
        return bleach.clean(markdown(self.text_md, output_format='html'), tags=allowed, strip=True)
