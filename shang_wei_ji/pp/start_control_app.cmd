@echo off
setlocal

cd /d "%~dp0"

set "STREAMLIT_EXE=C:\Users\lenovo\AppData\Local\Programs\Python\Python314\Scripts\streamlit.exe"

if not exist "%STREAMLIT_EXE%" (
    echo Streamlit was not found at:
    echo %STREAMLIT_EXE%
    echo.
    echo Please check the Python/Streamlit installation.
    pause
    exit /b 1
)

"%STREAMLIT_EXE%" run "%~dp0control.py"

echo.
echo The app has stopped.
pause
