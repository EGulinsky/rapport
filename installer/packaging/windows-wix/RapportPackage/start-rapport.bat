@echo off
setlocal enabledelayedexpansion
REM Runs once right after Setup finishes (via the Burn bootstrapper's
REM "Launch" checkbox on the finish page), and again any time from the
REM "Start rapport" Start Menu shortcut. %~dp0 always resolves to this
REM script's own folder, independent of the current working directory.
set "COMPOSE_FILE=%~dp0docker-compose.yml"

docker info >nul 2>nul
if not errorlevel 1 goto :docker_ready

where docker >nul 2>nul
if not errorlevel 1 goto :start_desktop

echo Docker not found - downloading Docker Desktop for Windows...
set "DOCKER_ARCH=amd64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "DOCKER_ARCH=arm64"
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "DOCKER_ARCH=arm64"
set "DOCKER_INSTALLER=%TEMP%\Docker Desktop Installer.exe"
curl -L -o "%DOCKER_INSTALLER%" "https://desktop.docker.com/win/main/%DOCKER_ARCH%/Docker%%20Desktop%%20Installer.exe"
if errorlevel 1 (
    echo Download failed. Check your internet connection and try again, or
    echo install Docker manually from https://www.docker.com/get-started/.
    pause
    exit /b 1
)

echo Installing Docker Desktop ^(you may see a Windows admin-permission prompt^)...
"%DOCKER_INSTALLER%" install --quiet --accept-license
set "INSTALL_RESULT=%errorlevel%"
del "%DOCKER_INSTALLER%" >nul 2>nul

if "%INSTALL_RESULT%"=="3010" (
    echo Docker Desktop needs your computer to restart to finish installing
    echo ^(this happens the first time WSL2 is enabled^). Please restart, then
    echo run "Start rapport" again from the Start Menu.
    pause
    exit /b 1
)
if not "%INSTALL_RESULT%"=="0" (
    echo Docker Desktop installation failed ^(exit code %INSTALL_RESULT%^).
    pause
    exit /b 1
)

:start_desktop
echo Starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

echo Waiting for Docker to start...
set "DOCKER_READY=0"
for /l %%i in (1,1,60) do (
    docker info >nul 2>nul
    if not errorlevel 1 (
        set "DOCKER_READY=1"
        goto :docker_wait_done
    )
    timeout /t 3 /nobreak >nul
)
:docker_wait_done

if "%DOCKER_READY%"=="0" (
    echo Docker didn't start in time. Please make sure Docker Desktop is
    echo running, then run "Start rapport" again from the Start Menu.
    pause
    exit /b 1
)

:docker_ready
echo Pulling rapport images ^(this can take a few minutes the first time^)...
docker compose -f "%COMPOSE_FILE%" pull
if errorlevel 1 (
    echo Failed to pull rapport images. Check your internet connection and try again.
    pause
    exit /b 1
)

echo Starting rapport...
docker compose -f "%COMPOSE_FILE%" up -d
if errorlevel 1 (
    echo Failed to start rapport.
    pause
    exit /b 1
)

echo Waiting for rapport to be ready...
set "APP_READY=0"
for /l %%i in (1,1,30) do (
    curl -s -o nul -w "%%{http_code}" http://localhost:8000/health 2>nul | findstr /r "^200$" >nul
    if not errorlevel 1 (
        set "APP_READY=1"
        goto :app_ready
    )
    timeout /t 2 /nobreak >nul
)
:app_ready

if "%APP_READY%"=="0" (
    echo rapport didn't become healthy in time. Run "docker compose -f "%COMPOSE_FILE%" logs" for details.
    pause
    exit /b 1
)

echo rapport is running - opening in your browser: http://localhost:3000
start "" http://localhost:3000

echo.
echo You can close this window. rapport keeps running in the background
echo (managed by Docker) and restarts automatically when your computer restarts.
timeout /t 5 >nul
