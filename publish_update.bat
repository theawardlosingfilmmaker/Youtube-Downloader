@echo off
echo ========================================================
echo      SanTube - Publish Update to GitHub
echo ========================================================
echo.
echo This script will save your current changes and upload them
echo to GitHub so other users (and your auto-update system)
echo can receive them.
echo.

:ASK_MSG
set /p msg="Enter a short description of your changes (e.g. 'Fixed download bug'): "
if "%msg%"=="" goto ASK_MSG

echo.
echo 1. Adding files...
git add .
if %errorlevel% neq 0 (
    echo Error Adding files.
    pause
    exit /b
)

echo 2. Committing changes...
git commit -m "%msg%"
if %errorlevel% neq 0 (
    echo Error committing (Maybe nothing to commit?).
    pause
    exit /b
)

echo 3. Pushing to GitHub...
git push
if %errorlevel% neq 0 (
    echo Error pushing to GitHub. Check your internet or login.
    pause
    exit /b
)

echo.
echo ========================================================
echo      SUCCESS! Update published.
echo ========================================================
echo.
pause
