@echo off
setlocal
cd /d "%~dp0"
rem ================================================================
rem  Sestaveni LocalChefStudio.exe (vse vcetne offline prekladace)
rem  Spust dvojklikem ve slozce, kde je localchef_studio_vX.Y.py
rem ================================================================
rem Soubor aplikace ma verzi v nazvu (localchef_studio_v1.5.py) - vezme se ten, ktery tu je
set APP=
for %%f in (localchef_studio_v*.py) do set APP=%%f
if not exist "%APP%" (
  echo Chybi localchef_studio_vX.Y.py ve stejne slozce jako tento skript.
  if not defined CI pause
  exit /b 1
)

rem Stejna verze PyQt6 / WebEngine jako v tvem Pythonu -> exe se chova 1:1 jako .py verze
set PYQT_VER=
set WE_VER=
for /f "usebackq delims=" %%v in (`python -c "import importlib.metadata as m; print(m.version('PyQt6'))" 2^>nul`) do set PYQT_VER=%%v
for /f "usebackq delims=" %%v in (`python -c "import importlib.metadata as m; print(m.version('PyQt6-WebEngine'))" 2^>nul`) do set WE_VER=%%v
set PKG_QT=PyQt6
if defined PYQT_VER set PKG_QT=PyQt6==%PYQT_VER%
set PKG_WE=PyQt6-WebEngine
if defined WE_VER set PKG_WE=PyQt6-WebEngine==%WE_VER%
echo Pouzita verze: %PKG_QT% %PKG_WE%

echo.
echo [1/3] Vytvarim cisty virtualni Python (.venv-build) ...
if not exist ".venv-build\Scripts\python.exe" (
  python -m venv .venv-build || goto :err
)
call ".venv-build\Scripts\activate.bat" || goto :err

echo.
echo [2/3] Instaluji knihovny (poprve to trva i desitky minut) ...
python -m pip install --upgrade pip || goto :err
python -m pip install pyinstaller %PKG_QT% %PKG_WE% beautifulsoup4 argostranslate deepl recipe-scrapers py7zr || goto :err

rem PyQt6 si s sebou nosi starsi Microsoft knihovny (msvcp140 / vcruntime140). Offline prekladac
rem (onnxruntime) s nimi pada uz pri sestavovani (kod 3221225477). Nahradime je novejsimi ze systemu.
set QTBIN=
for /f "usebackq delims=" %%d in (`python -c "import PyQt6,os;print(os.path.join(os.path.dirname(PyQt6.__file__),'Qt6','bin'))"`) do set QTBIN=%%d
if not exist "%SystemRoot%\System32\msvcp140.dll" (
  echo.
  echo !!! V systemu chybi Microsoft Visual C++ Redistributable ^(x64^).
  echo     Stahni a nainstaluj: https://aka.ms/vs/17/release/vc_redist.x64.exe
  echo     a potom spust tento skript znovu.
  goto :err
)
for %%f in (msvcp140.dll msvcp140_1.dll msvcp140_2.dll msvcp140_atomic_wait.dll msvcp140_codecvt_ids.dll vcruntime140.dll vcruntime140_1.dll concrt140.dll) do (
  if exist "%QTBIN%\%%f" if exist "%SystemRoot%\System32\%%f" (
    copy /y "%SystemRoot%\System32\%%f" "%QTBIN%\%%f" >nul && echo   aktualizovano: %%f
  )
)
python -c "import PyQt6.QtCore, onnxruntime; print('  kontrola: PyQt6 + onnxruntime OK')" || goto :err

echo.
echo [3/3] Sestavuji exe (trva nekolik minut) ...
pyinstaller --noconfirm --clean --windowed --onedir --name LocalChefStudio ^
  --collect-all argostranslate --collect-all ctranslate2 --collect-all sentencepiece ^
  --collect-all stanza --collect-all minisbd --collect-all sacremoses --collect-all deepl ^
  --copy-metadata argostranslate ^
  --collect-all recipe_scrapers --collect-all extruct --collect-all rdflib --collect-all pyRdfa --collect-all mf2py ^
  --collect-all w3lib --collect-all html_text --collect-all jstyleson --collect-all isodate --collect-all lxml_html_clean ^
  --copy-metadata rdflib --copy-metadata recipe-scrapers ^
  --collect-all py7zr --collect-all pyppmd --collect-all pybcj --collect-all inflate64 --collect-all multivolumefile ^
  "%APP%" || goto :err

echo.
set DIST=dist\LocalChefStudio
if exist "DISCLAIMER.txt" copy /y "DISCLAIMER.txt" "%DIST%\DISCLAIMER.txt" >nul

rem Microsoft knihovny (Visual C++ runtime) primo k exe a k torch\lib -> offline prekladac
rem funguje i na pocitaci, kde neni nainstalovany Visual C++ Redistributable (chyba WinError 126).
for %%f in (msvcp140.dll msvcp140_1.dll msvcp140_2.dll msvcp140_atomic_wait.dll msvcp140_codecvt_ids.dll vcruntime140.dll vcruntime140_1.dll concrt140.dll vcomp140.dll) do (
  if exist "%SystemRoot%\System32\%%f" (
    copy /y "%SystemRoot%\System32\%%f" "%DIST%\_internal\%%f" >nul
    if exist "%DIST%\_internal\torch\lib" copy /y "%SystemRoot%\System32\%%f" "%DIST%\_internal\torch\lib\%%f" >nul
  )
)
echo Pribaleny knihovny Visual C++ runtime.

echo ================================================================
echo  HOTOVO:  %CD%\%DIST%\LocalChefStudio.exe
echo  Cisty program bez dat. Na jiny pocitac prenes CELOU slozku %DIST%.
echo  Vlastni data: zkopiruj slozku localchef_data vedle LocalChefStudio.exe
echo  (kdyz chybi, program si pri spusteni vytvori prazdnou).
echo ================================================================
if not defined CI pause
exit /b 0

:err
echo.
echo !!! Sestaveni selhalo - viz chyba vyse.
if not defined CI pause
exit /b 1
