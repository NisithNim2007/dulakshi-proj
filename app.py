from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from config import *

app = Flask(__name__)
app.config.from_pyfile('config.py')
db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(255))
    role = db.Column(db.String(20), default='user')

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
