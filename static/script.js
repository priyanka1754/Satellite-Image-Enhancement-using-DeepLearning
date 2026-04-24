// Global variables
let currentOriginalImage = null;
let currentEnhancedImage = null;

// DOM Elements
const uploadSection = document.getElementById('uploadSection');
const analysisSection = document.getElementById('analysisSection');
const loadingOverlay = document.getElementById('loadingOverlay');
const imageInput = document.getElementById('imageInput');
const uploadButton = document.getElementById('uploadButton');
const uploadCard = document.querySelector('.upload-card');
const resetButton = document.getElementById('resetButton');
const statusBadge = document.getElementById('statusBadge');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
});

function setupEventListeners() {
    // Upload button click
    uploadButton.addEventListener('click', () => {
        imageInput.click();
    });

    // Upload card click
    uploadCard.addEventListener('click', (e) => {
        if (e.target !== uploadButton) {
            imageInput.click();
        }
    });

    // File input change
    imageInput.addEventListener('change', handleFileSelect);

    // Drag and drop
    uploadCard.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadCard.style.borderColor = 'rgba(102, 126, 234, 0.8)';
    });

    uploadCard.addEventListener('dragleave', () => {
        uploadCard.style.borderColor = 'rgba(102, 126, 234, 0.3)';
    });

    uploadCard.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadCard.style.borderColor = 'rgba(102, 126, 234, 0.3)';

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    });

    // Reset button
    resetButton.addEventListener('click', resetAnalysis);
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        handleFile(file);
    }
}

function handleFile(file) {
    // Validate file
    if (!file.type.startsWith('image/')) {
        showError('Please select a valid image file');
        return;
    }

    if (file.size > 16 * 1024 * 1024) {
        showError('File size must be less than 16MB');
        return;
    }

    // Show loading
    showLoading();
    updateStatus('Processing...', 'warning');

    // Create FormData
    const formData = new FormData();
    formData.append('image', file);

    // Send to server
    fetch('/analyze', {
        method: 'POST',
        body: formData
    })
        .then(response => {
            if (!response.ok) {
                throw new Error('Analysis failed');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                displayResults(data);
                updateStatus('Analysis Complete', 'success');
            } else {
                throw new Error(data.error || 'Unknown error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showError('Failed to analyze image: ' + error.message);
            updateStatus('Error', 'error');
        })
        .finally(() => {
            hideLoading();
        });
}

function displayResults(data) {
    // Store images
    currentOriginalImage = data.images.original;
    currentEnhancedImage = data.images.enhanced;

    // Update images
    document.getElementById('originalImage').src = data.images.original;
    document.getElementById('enhancedImage').src = data.images.enhanced;

    // Show analysis section
    uploadSection.classList.add('hidden');
    analysisSection.classList.remove('hidden');

    // Scroll to results
    setTimeout(() => {
        analysisSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}


function resetAnalysis() {
    // Clear file input
    imageInput.value = '';

    // Reset images
    currentOriginalImage = null;
    currentEnhancedImage = null;

    // Reset disturbance list
    const disturbanceList = document.getElementById('disturbanceList');
    const disturbanceTitle = document.getElementById('disturbanceTitle');
    if (disturbanceList) {
        disturbanceList.innerHTML = '<p style="color: rgba(255, 255, 255, 0.7); font-size: 1.1rem; margin: 0; text-align: center;">Analyzing...</p>';
    }
    if (disturbanceTitle) {
        disturbanceTitle.textContent = 'Detected Disturbances';
    }

    // Show upload section
    analysisSection.classList.add('hidden');
    uploadSection.classList.remove('hidden');

    // Update status
    updateStatus('Ready', 'success');

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function showLoading() {
    loadingOverlay.classList.remove('hidden');
}

function hideLoading() {
    loadingOverlay.classList.add('hidden');
}

function updateStatus(text, type = 'success') {
    const statusDot = statusBadge.querySelector('.status-dot');
    const statusText = statusBadge.querySelector('span:last-child');

    statusText.textContent = text;

    // Update dot color
    const colors = {
        success: '#34d399',
        warning: '#fbbf24',
        error: '#f87171'
    };

    if (statusDot) {
        statusDot.style.background = colors[type] || colors.success;
    }
}

function showError(message) {
    // Create error notification
    const notification = document.createElement('div');
    notification.className = 'error-notification';
    notification.innerHTML = `
        <div style="
            position: fixed;
            top: 2rem;
            right: 2rem;
            background: linear-gradient(135deg, rgba(248, 113, 113, 0.95) 0%, rgba(239, 68, 68, 0.95) 100%);
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
            z-index: 10000;
            animation: slideInRight 0.3s ease;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            max-width: 400px;
        ">
            <div style="display: flex; align-items: center; gap: 1rem;">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="12" y1="8" x2="12" y2="12"/>
                    <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <div>
                    <div style="font-weight: 600; margin-bottom: 0.25rem;">Error</div>
                    <div style="font-size: 0.9rem; opacity: 0.9;">${message}</div>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(notification);

    // Remove after 5 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 5000);
}

function downloadImage(type) {
    const image = type === 'original' ? currentOriginalImage : currentEnhancedImage;

    if (!image) {
        showError('No image available to download');
        return;
    }

    // Create download link
    const link = document.createElement('a');
    link.href = image;
    link.download = `${type}_image_${Date.now()}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // Show success message
    showSuccessMessage(`${type.charAt(0).toUpperCase() + type.slice(1)} image downloaded successfully!`);
}

function showSuccessMessage(message) {
    const notification = document.createElement('div');
    notification.innerHTML = `
        <div style="
            position: fixed;
            top: 2rem;
            right: 2rem;
            background: linear-gradient(135deg, rgba(52, 211, 153, 0.95) 0%, rgba(16, 185, 129, 0.95) 100%);
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
            z-index: 10000;
            animation: slideInRight 0.3s ease;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        ">
            <div style="display: flex; align-items: center; gap: 1rem;">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                    <polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
                <div style="font-weight: 600;">${message}</div>
            </div>
        </div>
    `;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

// Add animation styles
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
// Mode switching function
function switchUploadMode(mode) {
    uploadMode = mode;

    const singleContainer = document.getElementById('singleUploadContainer');
    const dualContainer = document.getElementById('dualUploadContainer');
    const singleBtn = document.getElementById('singleModeBtn');
    const dualBtn = document.getElementById('dualModeBtn');

    if (mode === 'single') {
        singleContainer.style.display = 'block';
        dualContainer.style.display = 'none';
        singleBtn.style.background = 'rgba(102, 126, 234, 0.8)';
        singleBtn.style.color = 'white';
        dualBtn.style.background = 'transparent';
        dualBtn.style.color = 'rgba(102, 126, 234, 0.8)';

        // Reset dual mode files
        image1File = null;
        image2File = null;
        document.getElementById('image1Name').textContent = '';
        document.getElementById('image2Name').textContent = '';
        document.getElementById('analyzeBothButton').disabled = true;
    } else {
        singleContainer.style.display = 'none';
        dualContainer.style.display = 'block';
        dualBtn.style.background = 'rgba(102, 126, 234, 0.8)';
        dualBtn.style.color = 'white';
        singleBtn.style.background = 'transparent';
        singleBtn.style.color = 'rgba(102, 126, 234, 0.8)';
    }
}

// Handle dual file selection
function handleDualFileSelect(e, imageNumber) {
    const file = e.target.files[0];
    if (!file) return;

    // Validate file
    if (!file.type.startsWith('image/')) {
        showError('Please select a valid image file');
        return;
    }

    if (file.size > 16 * 1024 * 1024) {
        showError('File size must be less than 16MB');
        return;
    }

    // Store file
    if (imageNumber === 1) {
        image1File = file;
        document.getElementById('image1Name').textContent = file.name;
    } else {
        image2File = file;
        document.getElementById('image2Name').textContent = file.name;
    }

    // Enable analyze button if both images are selected
    const analyzeBothButton = document.getElementById('analyzeBothButton');
    if (image1File && image2File) {
        analyzeBothButton.disabled = false;
        analyzeBothButton.style.opacity = '1';
        analyzeBothButton.style.cursor = 'pointer';
    }
}

// Handle dual image analysis
function handleDualAnalysis() {
    if (!image1File || !image2File) {
        showError('Please select both images');
        return;
    }

    // Show loading
    showLoading();
    updateStatus('Processing...', 'warning');

    // Create FormData with both images
    const formData = new FormData();
    formData.append('image1', image1File);
    formData.append('image2', image2File);
    formData.append('mode', 'dual');

    // Send to server
    fetch('/analyze_dual', {
        method: 'POST',
        body: formData
    })
        .then(response => {
            if (!response.ok) {
                throw new Error('Analysis failed');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                displayDualResults(data);
                updateStatus('Analysis Complete', 'success');
            } else {
                throw new Error(data.error || 'Unknown error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showError('Failed to analyze images: ' + error.message);
            updateStatus('Error', 'error');
        })
        .finally(() => {
            hideLoading();
        });
}

// Display dual image results
function displayDualResults(data) {
    // Store images
    currentOriginalImage = data.images.image1;
    currentEnhancedImage = data.images.image2;

    // Update images
    document.getElementById('originalImage').src = data.images.image1;
    document.getElementById('enhancedImage').src = data.images.image2;

    // Update labels
    document.querySelector('.image-container:first-child .image-label').textContent = 'Image 1';
    document.querySelector('.image-container:last-child .image-label').textContent = 'Image 2';

    // Hide metrics section for dual mode
    document.querySelector('.metrics-container').style.display = 'none';

    // Show analysis section
    uploadSection.classList.add('hidden');
    analysisSection.classList.remove('hidden');

    // Scroll to results
    setTimeout(() => {
        analysisSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}
