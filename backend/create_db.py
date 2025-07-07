from flask import Flask
from models.database import db, init_db
from models.user import User
from models.article import Article
import os

app = Flask(__name__)
init_db(app)

with app.app_context():
    db.create_all()
    print('Base de données initialisée avec succès !') 