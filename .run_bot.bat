@echo off
:: This is the most important line. It changes the current directory
:: of THIS script to the folder where the .bat file is located.
cd /d "%~dp0"

echo =======================================
echo  Starting Game Night Bot and Web API
echo =======================================
echo.

echo [+] Starting Discord Bot...
:: Corrected Path: main.py is in the root folder, not bot/
start "Discord Bot" cmd /k "python bot/main.py"

echo.
echo [+] Starting Web API Server...
:: This path is correct
start "Web API" cmd /k "python web/web_api.py"

echo.
echo [+] Both applications have been started successfully.
echo You can close this window now if you wish.
pause