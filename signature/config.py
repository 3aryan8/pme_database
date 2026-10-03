"""
Configuration settings for the Streamlit YOLO application.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define storage paths
STORAGE_PATH = os.path.join(BASE_DIR, 'storage')
OUTPUT_PATH = os.path.join(BASE_DIR, 'output')
EXTRACTED_PATH = os.path.join(BASE_DIR, 'extracted')
MODEL_PATH = os.path.join(BASE_DIR, 'model_weights', 'best.pt')

# Application settings
APP_TITLE = "📘 Minecraftors StampExtractor"
APP_DESCRIPTION = "Your Document Assistant"

# Create directories if they don't exist
def initialize_directories():
    """Create necessary directories if they don't exist."""
    for path in [STORAGE_PATH, OUTPUT_PATH, EXTRACTED_PATH]:
        if not os.path.exists(path):
            os.makedirs(path)
