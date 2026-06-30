import os
import sys

# 1. Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

# 2. Import the Flask application instance as 'application' for Passenger
from main import app as application
