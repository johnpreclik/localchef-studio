@echo off
setlocal
cd /d "%~dp0"
rem ================================================================
rem  LocalChef Studio v Dockeru: sestavi obraz a spusti kontejner
rem  Potreba: Docker Desktop (https://www.docker.com/products/docker-desktop/)
rem  Pouziti:  build_docker.bat            (vcetne offline prekladace, obraz ~3 GB)
rem            build_docker.bat noargos    (bez offline prekladace, mensi a rychlejsi)
rem  Aplikace pak bezi v prohlizeci:  http://localhost:6080/
rem  Data kontejneru jsou ve slozce docker_data\localchef_data (oddelene od Windows verze).
rem ================================================================
set IMAGE=localchef-studio:latest
set NAME=localchef
set DATA=%~dp0docker_data\localchef_data
set ARGOS=1
if /i "%~1"=="noargos" set ARGOS=0

where docker >nul 2>nul
if errorlevel 1 (
  echo Docker neni nainstalovany. Nainstaluj Docker Desktop a spust tento skript znovu.
  pause
  exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
  echo Docker Desktop nebezi. Spust ho, pockej, az nabehne, a spust tento skript znovu.
  pause
  exit /b 1
)

rem IP adresa tohoto pocitace v siti - telefon ji dostane v QR kodu (adresa uvnitr kontejneru by nefungovala)
set LANIP=
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1).IPv4Address.IPAddress"`) do set LANIP=%%i
if "%LANIP%"=="" set LANIP=127.0.0.1
echo IP adresa pro telefon: %LANIP%

echo.
echo === Sestavuji obraz %IMAGE% (offline prekladac: %ARGOS%) - poprve to trva i desitky minut ===
docker build -t %IMAGE% --build-arg WITH_ARGOS=%ARGOS% -f docker\Dockerfile .
if errorlevel 1 (
  echo.
  echo Sestaveni obrazu selhalo - vyse je duvod.
  pause
  exit /b 1
)

if not exist "%DATA%" mkdir "%DATA%"
docker rm -f %NAME% >nul 2>nul
echo.
echo === Spoustim kontejner %NAME% ===
docker run -d --name %NAME% --restart unless-stopped --shm-size=1g ^
  -p 127.0.0.1:6080:6080 -p 3665:3665 ^
  -e LOCALCHEF_LAN_HOST=%LANIP% ^
  -v "%DATA%:/data/localchef_data" ^
  %IMAGE%
if errorlevel 1 (
  echo Spusteni kontejneru selhalo.
  pause
  exit /b 1
)

echo.
echo ================================================================
echo  HOTOVO. LocalChef Studio bezi v prohlizeci:  http://localhost:6080/
echo  Telefon (stejna Wi-Fi):            http://%LANIP%:3665/
echo  Data:  %DATA%
echo  Recepty z Windows verze prenes zkopirovanim jejich slozek do
echo  %DATA%\recipes  (pri dalsim startu se samy objevi).
echo  Zastaveni: docker stop %NAME%     Znovu spustit: docker start %NAME%
echo ================================================================
timeout /t 4 >nul
start "" http://localhost:6080/
endlocal
