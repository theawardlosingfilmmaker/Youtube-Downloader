@echo off
echo ===================================================
echo           Installing / repairing SanTube...
echo ===================================================
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Creating Python environment...
    python -m venv venv
)
echo Installing / updating yt-dlp, its YouTube helper, deno and Flask...
venv\Scripts\python.exe -m pip install -q -U pip
venv\Scripts\python.exe -m pip install -q -U -r requirements.txt
echo Updating ffmpeg...
venv\Scripts\python.exe santube_cli.py --update

set "APP_NAME=SanTube"
set "ICON_PATH=%~dp0static\logo.ico"
set "SHORTCUT_SCRIPT=%temp%\CreateShortcut.vbs"

echo Set oWS = WScript.CreateObject("WScript.Shell") > "%SHORTCUT_SCRIPT%"
:: 1. Desktop shortcut (opens SanTube)
echo Set oLink = oWS.CreateShortcut(oWS.SpecialFolders("Desktop") ^& "\%APP_NAME%.lnk") >> "%SHORTCUT_SCRIPT%"
echo oLink.TargetPath = "%~dp0Santube.vbs" >> "%SHORTCUT_SCRIPT%"
echo oLink.WorkingDirectory = "%~dp0" >> "%SHORTCUT_SCRIPT%"
echo oLink.IconLocation = "%ICON_PATH%" >> "%SHORTCUT_SCRIPT%"
echo oLink.Save >> "%SHORTCUT_SCRIPT%"
:: 2. Start Menu shortcut
echo Set oLink = oWS.CreateShortcut(oWS.SpecialFolders("StartMenu") ^& "\Programs\%APP_NAME%.lnk") >> "%SHORTCUT_SCRIPT%"
echo oLink.TargetPath = "%~dp0Santube.vbs" >> "%SHORTCUT_SCRIPT%"
echo oLink.WorkingDirectory = "%~dp0" >> "%SHORTCUT_SCRIPT%"
echo oLink.IconLocation = "%ICON_PATH%" >> "%SHORTCUT_SCRIPT%"
echo oLink.Save >> "%SHORTCUT_SCRIPT%"
:: 3. Start silently in the background when Windows starts
echo Set oLink = oWS.CreateShortcut(oWS.SpecialFolders("Startup") ^& "\%APP_NAME% (background).lnk") >> "%SHORTCUT_SCRIPT%"
echo oLink.TargetPath = "%~dp0SanTube_Background.vbs" >> "%SHORTCUT_SCRIPT%"
echo oLink.WorkingDirectory = "%~dp0" >> "%SHORTCUT_SCRIPT%"
echo oLink.Save >> "%SHORTCUT_SCRIPT%"
cscript /nologo "%SHORTCUT_SCRIPT%"
del "%SHORTCUT_SCRIPT%"

echo Starting SanTube in the background...
wscript.exe "%~dp0SanTube_Background.vbs"
echo.
echo ===================================================
echo  Done. SanTube is on your Desktop and Start Menu,
echo  and now starts quietly whenever Windows starts.
echo ===================================================
pause
