# 🚀 Quick Commands - Satellite Image Enhancement System

## 📋 Essential Commands

### 1. Start Application
```powershell
cd d:\SatelliteImage
python app.py
```
**Access**: http://127.0.0.1:5000

---

### 2. Stop Application
```powershell
# Press Ctrl+C in the terminal
# OR
Stop-Process -Name python -Force
```

---

### 3. Install Dependencies (First Time Only)
```powershell
cd d:\SatelliteImage
pip install -r requirements.txt
```

---

### 4. Check Python Version
```powershell
python --version
```
**Required**: Python 3.8 or higher

---

### 5. Verify Installation
```powershell
cd d:\SatelliteImage
python -c "import torch; import cv2; import flask; print('All dependencies installed!')"
```

---

## 🔧 Troubleshooting Commands

### Check if Port 5000 is in Use
```powershell
netstat -ano | findstr :5000
```

### Kill Process on Port 5000
```powershell
# Find the PID from above command, then:
taskkill /PID <PID_NUMBER> /F
```

### Reinstall Dependencies
```powershell
pip install --upgrade -r requirements.txt
```

---

## 📁 File Management Commands

### List Project Files
```powershell
cd d:\SatelliteImage
Get-ChildItem -Recurse -File | Select-Object Name, Length, DirectoryName
```

### Check Model File
```powershell
Get-Item checkpoints\student_model.pth
```

### View Logs (if running in background)
```powershell
Get-Content app.log -Tail 50 -Wait
```

---

## 🎯 Quick Start Workflow

```powershell
# 1. Navigate to project
cd d:\SatelliteImage

# 2. Start application
python app.py

# 3. Open browser
start http://127.0.0.1:5000

# 4. When done, press Ctrl+C to stop
```

---

## 🌐 Access URLs

- **Main Application**: http://127.0.0.1:5000
- **Single Image Mode**: http://127.0.0.1:5000 (default)
- **Dual Image Mode**: Toggle in UI

---

## 💡 Usage Tips

### Upload Image
1. Click "Single Image" or "Compare Two Images"
2. Click "Choose Image" button
3. Select image file (JPG, PNG, JPEG)
4. Wait for processing
5. View results

### Download Results
- Click download button on enhanced image
- Saves as PNG with timestamp

---

## 📊 System Status Commands

### Check if App is Running
```powershell
Get-Process python -ErrorAction SilentlyContinue
```

### View Python Processes
```powershell
Get-Process python | Select-Object Id, ProcessName, StartTime
```

### Check Memory Usage
```powershell
Get-Process python | Select-Object ProcessName, @{Name="Memory(MB)";Expression={[math]::Round($_.WorkingSet/1MB,2)}}
```

---

## 🔄 Restart Application

```powershell
# Quick restart
Stop-Process -Name python -Force; python app.py
```

---

## 📝 Development Commands

### Run in Debug Mode (Already Default)
```powershell
python app.py
# Debug mode is enabled by default
```

### Run on Different Port
```powershell
# Edit app.py, change:
# app.run(debug=True, host='0.0.0.0', port=5000)
# to:
# app.run(debug=True, host='0.0.0.0', port=8080)
```

---

## ✅ Current Status

**Application**: Running ✅
**Port**: 5000 ✅
**URL**: http://127.0.0.1:5000 ✅

**Ready to use!** 🎉
