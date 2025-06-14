import os
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY','dev-key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL','sqlite:///library.db')
    SQLALCHEMY_TRACK_MODIFICATIONS=False
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', os.path.join(os.path.dirname(__file__), 'uploads'))
