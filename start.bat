@echo off
echo Starting San's Youtube Intruder...
call venv\Scripts\activate
start http://localhost:5000
python app.py
pause
