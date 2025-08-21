# passenger_wsgi.py
import sys
import os

# Ajoute le répertoire de l'application au chemin de Python
# pour que les imports fonctionnent correctement
sys.path.insert(0, os.path.dirname(__file__))

# Importe l'objet 'app' depuis votre fichier 'app.py'
# et le renomme en 'application', le nom par défaut que Passenger cherche.
from app import app as application