# ==================================================
# START PROJECT 01 BACKEND
# to run, type the following into powershell: powershell -ExecutionPolicy Bypass -File .\backend\start.ps1
# ==================================================

# go to project directory
cd C:\dev\project01_data_platform\backend

# activate virtual environment
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1

# run API
uvicorn main:app --reload