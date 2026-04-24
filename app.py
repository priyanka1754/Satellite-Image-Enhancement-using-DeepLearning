"""
Image Enhancement Application
Detects and removes multiple adverse atmospheric noises from images
"""

import os
import io
import base64
import numpy as np
import torch
import torchvision.transforms as transforms
from PIL import Image
from flask import Flask, render_template, request, jsonify
import cv2
from skimage.color import rgb2lab, lab2lch
from skimage.exposure import rescale_intensity
import gc

# Import models
from models.networks.base_networks import *
import importlib

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'

# Create necessary folders
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# Global model variable
weather_model = None
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


def load_model(checkpoint_path=None):
    """Load the atmospheric noise removal model"""
    global weather_model
    
    try:
        import sys
        
        # Add models directory to sys.path
        models_dir = os.path.join(os.path.dirname(__file__), 'models')
        if models_dir not in sys.path:
            sys.path.insert(0, models_dir)
        
        # Import networks package (this registers all necessary modules)
        import networks
        
        # Load checkpoint if provided
        if checkpoint_path and os.path.exists(checkpoint_path):
            print(f"Loading checkpoint from {checkpoint_path}...")
            checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
            
            # Check if checkpoint is the model itself (old format) or contains state_dict (new format)
            if isinstance(checkpoint, torch.nn.Module):
                # Old format: checkpoint IS the model
                weather_model = checkpoint
                print(f"[OK] Loaded model directly from checkpoint (old format)")
            elif isinstance(checkpoint, dict) and 'state_dict' in checkpoint:
                # New format: checkpoint contains state_dict
                # Create model instance first
                weather_model = networks.getattr(networks, 'MSBDN-DFF-v1-1').Net()
                weather_model.load_state_dict(checkpoint['state_dict'], strict=False)
                print(f"[OK] Loaded state_dict from checkpoint (new format)")
            else:
                raise ValueError(f"Unknown checkpoint format: {type(checkpoint)}")
            
            weather_model = weather_model.to(device)
            weather_model.eval()
            print(f"[OK] Model loaded successfully on {device}")
        else:
            print(f"No checkpoint found at {checkpoint_path}")
            print("Model will run in detection-only mode")
        
    except Exception as e:
        print(f"[ERROR] Could not load model - {str(e)}")
        import traceback
        traceback.print_exc()
        print("Running in detection-only mode")


def detect_haze(image_np):
    """
    Detect haze in image using Dark Channel Prior with improved accuracy
    Returns percentage of haze coverage
    """
    try:
        # Convert to float
        img = image_np.copy()
        if img.max() > 1.0:
            img = img.astype(np.float32) / 255.0
        
        # Calculate dark channel
        kernel_size = 15
        dark_channel = np.min(img, axis=2)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        dark_channel = cv2.erode(dark_channel, kernel)
        
        # Haze is present where dark channel is bright
        # Stricter threshold to reduce false positives
        haze_threshold = 0.25  # Increased from 0.2 (more conservative)
        haze_mask = (dark_channel > haze_threshold).astype(np.float32)
        
        # Remove small isolated areas
        kernel_clean = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        haze_mask = cv2.morphologyEx(haze_mask, cv2.MORPH_OPEN, kernel_clean)
        
        haze_percentage = (np.sum(haze_mask) / haze_mask.size) * 100
        
        # Only report if significant haze (> 2%)
        if haze_percentage < 2.0:
            return 0.0
        
        return min(haze_percentage, 100.0)
    except Exception as e:
        print(f"Haze detection error: {e}")
        return 0.0


def detect_shadow(image_np):
    """
    Detect shadows with improved sensitivity
    Catches both subtle and prominent shadows
    Returns percentage of shadow coverage
    """
    try:
        img_uint8 = (image_np * 255).astype(np.uint8) if image_np.max() <= 1.0 else image_np.astype(np.uint8)
        
        # Check if image is grayscale/monochrome
        if len(img_uint8.shape) == 3:
            r, g, b = img_uint8[:, :, 0], img_uint8[:, :, 1], img_uint8[:, :, 2]
            rg_diff = np.abs(r.astype(np.float32) - g.astype(np.float32))
            rb_diff = np.abs(r.astype(np.float32) - b.astype(np.float32))
            gb_diff = np.abs(g.astype(np.float32) - b.astype(np.float32))
            
            avg_diff = (np.mean(rg_diff) + np.mean(rb_diff) + np.mean(gb_diff)) / 3
            if avg_diff < 5.0:
                print("[INFO] Grayscale image detected - skipping shadow detection")
                return 0.0
        
        # Convert to LAB color space
        lab = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2LAB)
        l_channel = lab[:, :, 0]
        
        # Method 1: Statistical approach (for subtle shadows)
        mean_brightness = np.mean(l_channel)
        std_brightness = np.std(l_channel)
        shadow_threshold_subtle = mean_brightness - 0.8 * std_brightness  # Lowered from 1.2
        subtle_shadows = (l_channel < shadow_threshold_subtle).astype(np.uint8) * 255
        
        # Method 2: Absolute darkness (for prominent shadows like tower shadows)
        # Catch very dark areas regardless of image statistics
        absolute_dark = (l_channel < 80).astype(np.uint8) * 255  # NEW: absolute threshold
        
        # Method 3: Relative darkness (for medium shadows)
        relative_dark = (l_channel < mean_brightness * 0.6).astype(np.uint8) * 255  # NEW
        
        # Combine all methods (OR logic - if ANY method detects it)
        shadow_mask = cv2.bitwise_or(subtle_shadows, absolute_dark)
        shadow_mask = cv2.bitwise_or(shadow_mask, relative_dark)
        
        # Additional check: low saturation (shadows are usually desaturated)
        hsv = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2HSV)
        low_saturation = (hsv[:, :, 1] < 80).astype(np.uint8) * 255  # Increased from 60
        
        # Refine: shadows should be dark AND have low saturation
        shadow_mask = cv2.bitwise_and(shadow_mask, low_saturation)
        
        # Remove small noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))  # Smaller kernel
        shadow_mask = cv2.morphologyEx(shadow_mask, cv2.MORPH_OPEN, kernel)
        shadow_mask = cv2.morphologyEx(shadow_mask, cv2.MORPH_CLOSE, kernel)
        
        # Calculate percentage
        shadow_percentage = (np.sum(shadow_mask > 0) / shadow_mask.size) * 100
        
        # Lower reporting threshold to catch more shadows
        if shadow_percentage < 2.0:  # Lowered from 3.0
            return 0.0
        
        return min(shadow_percentage, 100.0)
    except Exception as e:
        print(f"Shadow detection error: {e}")
        return 0.0


def detect_cloud(image_np):
    """
    Detect clouds with aggressive detection to catch all cloud types
    Detects: thick clouds, thin clouds, semi-transparent clouds
    Returns percentage of cloud coverage
    """
    try:
        img_uint8 = (image_np * 255).astype(np.uint8) if image_np.max() <= 1.0 else image_np.astype(np.uint8)
        hsv = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2HSV)
        
        # Method 1: Detect thick/bright clouds (very bright + very low saturation)
        brightness_threshold_high = 220
        saturation_threshold_low = 30
        
        thick_cloud_mask = np.logical_and(
            hsv[:, :, 2] > brightness_threshold_high,
            hsv[:, :, 1] < saturation_threshold_low
        ).astype(np.float32)
        
        # Method 2: Detect medium clouds (bright + low saturation)
        brightness_threshold_med = 200
        saturation_threshold_med = 40
        
        medium_cloud_mask = np.logical_and(
            hsv[:, :, 2] > brightness_threshold_med,
            hsv[:, :, 1] < saturation_threshold_med
        ).astype(np.float32)
        
        # Method 3: Detect very white areas (all RGB channels high)
        r, g, b = img_uint8[:, :, 0], img_uint8[:, :, 1], img_uint8[:, :, 2]
        white_threshold = 210
        white_mask = np.logical_and(
            np.logical_and(r > white_threshold, g > white_threshold),
            b > white_threshold
        ).astype(np.float32)
        
        # Combine all detection methods
        cloud_mask = np.maximum(thick_cloud_mask, medium_cloud_mask)
        cloud_mask = np.maximum(cloud_mask, white_mask)
        
        # Check for soft edges (clouds have soft edges, buildings have sharp edges)
        gray = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = cv2.GaussianBlur(edges.astype(np.float32), (15, 15), 0)
        
        # Areas with many edges are less likely to be clouds
        # But don't completely exclude them (clouds can have some texture)
        low_edge_areas = (edge_density < np.mean(edge_density) * 0.8).astype(np.float32)
        
        # Apply edge filter but keep it gentle (multiply instead of AND)
        cloud_mask = cloud_mask * (0.3 + 0.7 * low_edge_areas)
        
        # Threshold back to binary
        cloud_mask = (cloud_mask > 0.3).astype(np.float32)
        
        # Clean up small noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        cloud_mask = cv2.morphologyEx(cloud_mask, cv2.MORPH_OPEN, kernel)
        cloud_mask = cv2.morphologyEx(cloud_mask, cv2.MORPH_CLOSE, kernel)
        
        cloud_percentage = (np.sum(cloud_mask) / cloud_mask.size) * 100
        
        # Lower threshold to catch more clouds (was 5.0, now 2.0)
        if cloud_percentage < 2.0:
            return 0.0
        
        return min(cloud_percentage, 100.0)
    except Exception as e:
        print(f"Cloud detection error: {e}")
        return 0.0





def analyze_image(image_np):
    """
    Analyze image for disturbances: Haze, Shadow, Cloud only
    Returns dictionary with percentages
    """
    disturbances = {
        'haze': detect_haze(image_np),
        'shadow': detect_shadow(image_np),
        'cloud': detect_cloud(image_np)
    }
    
    # Calculate total disturbance
    disturbances['total'] = min(sum(disturbances.values()), 100.0)
    
    return disturbances


def enhance_image(image_np, disturbances=None):
    """
    AI-Powered image enhancement using deep learning
    - Uses MSBDN-RDFF model when haze is detected
    - Removes shadows using inpainting when detected
    - Handles haze, shadows, and clouds
    """
    global weather_model
    
    enhanced = image_np.copy()
    
    # Use AI model ONLY if there's actual haze (>5%)
    # This prevents unnecessary processing and preserves image quality
    haze_level = disturbances.get('haze', 0) if disturbances else 0
    
    # Apply haze removal if detected (lowered threshold for better detection)
    if weather_model is not None and haze_level > 2.0:  # Lowered from 5.0 to 2.0
        try:
            transform = transforms.Compose([transforms.ToTensor()])
            pil_image = Image.fromarray((enhanced * 255).astype(np.uint8) if enhanced.max() <= 1.0 
                                       else enhanced.astype(np.uint8))
            input_tensor = transform(pil_image).unsqueeze(0).to(device)
            
            with torch.no_grad():
                output = weather_model(input_tensor)
            
            enhanced = output.squeeze(0).cpu().numpy()
            enhanced = np.transpose(enhanced, (1, 2, 0))
            enhanced = np.clip(enhanced, 0, 1)
            
            print(f"[OK] Applied AI Model (MSBDN-RDFF) for haze removal ({haze_level:.1f}%)")
        except Exception as e:
            print(f"[WARNING] Model error: {e}")
    else:
        print(f"[INFO] AI Model skipped - No significant haze detected ({haze_level:.1f}%)")
    
    # Apply shadow removal if shadows detected
    shadow_level = disturbances.get('shadow', 0) if disturbances else 0
    if shadow_level > 0:
        try:
            enhanced = remove_shadows(enhanced)
            print(f"[OK] Applied shadow removal ({shadow_level:.1f}%)")
        except Exception as e:
            print(f"[WARNING] Shadow removal error: {e}")
    
    # Apply cloud removal if clouds detected
    cloud_level = disturbances.get('cloud', 0) if disturbances else 0
    if cloud_level > 0:
        try:
            enhanced = remove_clouds(enhanced)
            print(f"[OK] Applied cloud removal ({cloud_level:.1f}%)")
        except Exception as e:
            print(f"[WARNING] Cloud removal error: {e}")
    
    # Apply gentle final enhancement
    try:
        enhanced = apply_safe_enhancement(enhanced)
        print("[OK] Applied final enhancement")
    except Exception as e:
        print(f"[WARNING] Final enhancement error: {e}")
    
    return enhanced


def remove_shadows(image_np):
    """
    Robust shadow removal using Illumination Correction
    Restores brightness in shadow regions to match non-shadow regions
    """
    try:
        # Convert to uint8
        img_uint8 = (image_np * 255).astype(np.uint8) if image_np.max() <= 1.0 else image_np.astype(np.uint8)
        
        # Convert to LAB color space
        lab = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        
        # 1. Shadow Detection (Improved)
        # Use simple statistics which usually work best for prominent shadows
        mean_l = np.mean(l_channel)
        std_l = np.std(l_channel)
        
        # Threshold: pixels significantly darker than mean
        shadow_thresh = mean_l - 0.6 * std_l  # Increased sensitivity (was 1.5*std in safe mode)
        
        shadow_mask = (l_channel < shadow_thresh).astype(np.float32)
        
        # 2. Refine Mask
        # Remove small noise and smooth edges
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        shadow_mask = cv2.morphologyEx(shadow_mask, cv2.MORPH_CLOSE, kernel)
        shadow_mask = cv2.morphologyEx(shadow_mask, cv2.MORPH_OPEN, kernel)
        
        # Smooth boundaries for natural transition
        shadow_mask_blurred = cv2.GaussianBlur(shadow_mask, (15, 15), 0)
        
        # 3. Calculate Correction Amount
        # Get average brightness of shadow vs non-shadow areas
        mask_bool = shadow_mask > 0.5
        if np.sum(mask_bool) == 0 or np.sum(~mask_bool) == 0:
            return image_np # No shadows or all shadow
            
        shadow_mean = np.mean(l_channel[mask_bool])
        non_shadow_mean = np.mean(l_channel[~mask_bool])
        
        diff = non_shadow_mean - shadow_mean
        
        # If difference is small, it might not be a shadow
        if diff < 10:
            return image_np
            
        # 4. Apply Correction (Stronger)
        # Add the difference back to the shadow regions
        # We use a factor slightly > 1.0 to compensate for light falloff
        correction_factor = 1.0 
        correction = shadow_mask_blurred * diff * correction_factor
        
        l_corrected = l_channel.astype(np.float32) + correction
        l_corrected = np.clip(l_corrected, 0, 255).astype(np.uint8)
        
        # 5. Color Correction (Shadows are often cooler/bluer)
        # Gently warm up the shadow areas
        a_corrected = a_channel.astype(np.float32)
        b_corrected = b_channel.astype(np.float32)
        
        # Subtle color boost in shadows to match illuminated areas
        a_corrected += shadow_mask_blurred * 2.0
        b_corrected += shadow_mask_blurred * 2.0 # More yellow
        
        a_corrected = np.clip(a_corrected, 0, 255).astype(np.uint8)
        b_corrected = np.clip(b_corrected, 0, 255).astype(np.uint8)
        
        # Reconstruct
        lab_corrected = cv2.merge([l_corrected, a_corrected, b_corrected])
        result = cv2.cvtColor(lab_corrected, cv2.COLOR_LAB2RGB)
        
        return result.astype(np.float32) / 255.0
        
    except Exception as e:
        print(f"Shadow removal error: {e}")
        return image_np


def remove_clouds(image_np):
    """
    Safe cloud removal
    Only uses inpainting for small specks. 
    For large "clouds" (which might be sky), it does nothing or gentle enhancement.
    """
    try:
        # Convert to uint8
        img_uint8 = (image_np * 255).astype(np.uint8) if image_np.max() <= 1.0 else image_np.astype(np.uint8)
        
        # Simple Cloud Detection
        # Clouds are bright and low saturation
        hsv = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2HSV)
        v_channel = hsv[:,:,2]
        s_channel = hsv[:,:,1]
        
        # Strict thresholds for "obstructive cloud"
        cloud_mask = np.logical_and(v_channel > 220, s_channel < 30).astype(np.uint8) * 255
        
        # Calculate coverage
        cloud_pct = (np.sum(cloud_mask) / cloud_mask.size) * 100
        
        if cloud_pct < 0.5:
             return image_np
             
        # Case 1: Small scattered clouds (< 5%) -> Inpainting is safe
        if cloud_pct < 5.0:
            print(f"[INFO] Removing small clouds ({cloud_pct:.1f}%) using inpainting")
            # Dilate mask slightly to cover edges
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            dilated_mask = cv2.dilate(cloud_mask, kernel, iterations=2)
            
            # Inpaint
            result = cv2.inpaint(img_uint8, dilated_mask, 3, cv2.INPAINT_TELEA)
            return result.astype(np.float32) / 255.0
            
        # Case 2: Large cloud coverage -> Inpainting looks fake, brightness reduction looks muddy.
        # Best action: Do nothing specific for clouds, rely on Dehaze/Contrast enhancement.
        # Or apply a global Dehaze to "see through" thin clouds.
        
        print(f"[INFO] Large cloud area ({cloud_pct:.1f}%) detected - skipping artifact-prone removal")
        
        # Just return the original image (other enhancers like Dehaze will handle visibility)
        return image_np
        
    except Exception as e:
        print(f"[ERROR] Cloud removal failed: {e}")
        return image_np


def apply_safe_enhancement(image_float):
    """Gentle final enhancement to improve visibility"""
    img_uint8 = (image_float * 255).astype(np.uint8)
    
    # Gentle contrast enhancement
    lab = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    img_uint8 = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2RGB)
    
    # Gentle color boost
    hsv = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.2, 0, 255)
    img_uint8 = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    
    return img_uint8.astype(np.float32) / 255.0


def numpy_to_base64(image_np):
    """Convert numpy array to base64 string"""
    # Ensure image is in correct range
    if image_np.max() <= 1.0:
        image_np = (image_np * 255).astype(np.uint8)
    else:
        image_np = image_np.astype(np.uint8)
    
    # Convert to PIL Image
    pil_image = Image.fromarray(image_np)
    
    # Convert to base64
    buffered = io.BytesIO()
    pil_image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"


@app.route('/')
def index():
    """Render main page"""
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400

        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No image selected'}), 400

        # Read image
        image_bytes = file.read()
        nparr = np.frombuffer(image_bytes, np.uint8)
        image_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        image_rgb = cv2.cvtColor(image_cv, cv2.COLOR_BGR2RGB)
        image_np = image_rgb.astype(np.float32) / 255.0

        # Analyze disturbances
        disturbances = analyze_image(image_np)

        # --- NEW: Check if clouds are too dense ---
        cloud_level = disturbances.get('cloud', 0)
        if cloud_level >= 20.0:  # adjust threshold as needed
            return jsonify({
                'success': False,
                'error': 'Clouds are too dense. Please upload another image.',
                'disturbances': {
                    'haze': round(disturbances['haze'], 2),
                    'shadow': round(disturbances['shadow'], 2),
                    'cloud': round(cloud_level, 2),
                    'total': round(disturbances['total'], 2)
                }
            }), 400

        # Enhance only if clouds are not too dense
        enhanced_np = enhance_image(image_np, disturbances)

        # Convert images to base64
        original_b64 = numpy_to_base64(image_np)
        enhanced_b64 = numpy_to_base64(enhanced_np)

        # Prepare response
        response = {
            'success': True,
            'disturbances': {
                'haze': round(disturbances['haze'], 2),
                'shadow': round(disturbances['shadow'], 2),
                'cloud': round(cloud_level, 2),
                'total': round(disturbances['total'], 2)
            },
            'images': {
                'original': original_b64,
                'enhanced': enhanced_b64
            }
        }

        return jsonify(response)

    except Exception as e:
        print(f"Analysis error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/analyze_dual', methods=['POST'])
def analyze_dual():
    """Analyze and compare two uploaded images"""
    try:
        if 'image1' not in request.files or 'image2' not in request.files:
            return jsonify({'error': 'Both images are required'}), 400
        
        file1 = request.files['image1']
        file2 = request.files['image2']
        
        if file1.filename == '' or file2.filename == '':
            return jsonify({'error': 'Both images must be selected'}), 400
        
        # Read first image
        image_bytes1 = file1.read()
        nparr1 = np.frombuffer(image_bytes1, np.uint8)
        image_cv1 = cv2.imdecode(nparr1, cv2.IMREAD_COLOR)
        image_rgb1 = cv2.cvtColor(image_cv1, cv2.COLOR_BGR2RGB)
        image_np1 = image_rgb1.astype(np.float32) / 255.0
        
        # Read second image
        image_bytes2 = file2.read()
        nparr2 = np.frombuffer(image_bytes2, np.uint8)
        image_cv2 = cv2.imdecode(nparr2, cv2.IMREAD_COLOR)
        image_rgb2 = cv2.cvtColor(image_cv2, cv2.COLOR_BGR2RGB)
        image_np2 = image_rgb2.astype(np.float32) / 255.0
        
        # Convert images to base64
        image1_b64 = numpy_to_base64(image_np1)
        image2_b64 = numpy_to_base64(image_np2)
        
        # Prepare response
        response = {
            'success': True,
            'mode': 'dual',
            'images': {
                'image1': image1_b64,
                'image2': image2_b64
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Dual analysis error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Try to load model if checkpoint exists
    checkpoint_path = 'checkpoints/student_model.pth'
    if os.path.exists(checkpoint_path):
        load_model(checkpoint_path)
    else:
        print("No checkpoint found. Running in detection-only mode.")
        print("To enable image enhancement, place model checkpoint at:", checkpoint_path)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
