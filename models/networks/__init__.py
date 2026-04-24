# networks package __init__.py
# This makes networks a proper package

from . import base_networks
from .base_networks import *

# Import MSBDN models
try:
    # Try to import MSBDN-DFF-v1-1 (the model in the checkpoint)
    import importlib.util
    import sys
    import os
    
    # Load MSBDN-DFF-v1-1 from the same directory
    model_path = os.path.join(os.path.dirname(__file__), 'MSBDN-DFF-v1-1.py')
    if not os.path.exists(model_path):
        print(f"Error: Model file not found at {model_path}")
    
    spec = importlib.util.spec_from_file_location("MSBDN-DFF-v1-1", model_path)
    msbdn_module = importlib.util.module_from_spec(spec)
    sys.modules['networks.MSBDN-DFF-v1-1'] = msbdn_module
    spec.loader.exec_module(msbdn_module)
    
    # Make it available in this package
    setattr(sys.modules[__name__], 'MSBDN-DFF-v1-1', msbdn_module)
    
except Exception as e:
    print(f"Warning: Could not load MSBDN-DFF-v1-1: {e}")
