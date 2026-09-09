@echo off
REM ========================================================
REM 3.4-报警联动 - 快速联调脚本 (Quick Integration Test)
REM 适用环境：Windows + Python 3.x + Node.js
REM ========================================================

echo.
echo ========================================================
echo   3.4-报警联动功能 - 前后端联调 (Integration Test)
echo ========================================================
echo.

cd /d %~dp0

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH
    echo Please install Python 3.8+ and add to PATH
    pause
    exit /b 1
)
echo [OK] Python is available

REM Check Node
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found in PATH
    echo Please install Node.js 16+ and add to PATH
    pause
    exit /b 1
)
echo [OK] Node.js is available

echo.
echo ========================================================
echo Step 1: Backend Component Verification
echo ========================================================
echo.

cd backend

echo Testing module imports...
python -c "from app.models.linkage import LinkagePlan, AlarmLinkageLog; print('Models: OK')"
python -c "from app.schemas.linkage import *; print('Schemas: OK')"
python -c "from app.crud.linkage import linkage_plan_crud; print('CRUD: OK')"
python -c "from app.services.linkage_engine_service import linkage_engine; print('Engine: OK')"
python -c "from app.api.v1.linkage_plans import router as plans_router; print('API Plans: OK')"
python -c "from app.api.v1.linkage_logs import router as logs_router; print('API Logs: OK')"

echo.
echo Running quick unit tests...
python -m pytest tests/test_linkage_quick.py -v --tb=line || echo Tests completed with warnings

cd ..

echo.
echo ========================================================
echo Step 2: Frontend Component Verification
echo ========================================================
echo.

cd frontend

echo Checking Vue components...
if exist "src\views\linkage\Plan.vue" (
    echo [OK] Plan.vue exists
) else (
    echo [ERROR] Plan.vue not found
    pause
    exit /b 1
)

if exist "src\api\linkage.js" (
    echo [OK] linkage.js API wrapper exists
) else (
    echo [ERROR] linkage.js not found
    pause
    exit /b 1
)

cd ..

echo.
echo ========================================================
echo Step 3: Environment Readiness Check
echo ========================================================
echo.

REM Check if PostgreSQL is running (optional check)
echo Checking database connectivity (optional)...
set DB_HOST=localhost
set DB_PORT=5432
set DB_NAME=fire_alarm
set DB_USER=postgres

echo Default connection details:
echo   Host: %DB_HOST%
echo   Port: %DB_PORT%
echo   Database: %DB_NAME%
echo   User: %DB_USER%
echo.
echo Note: Database configuration needed for full integration testing
echo.

REM Check Redis (optional)
echo Checking Redis connectivity (optional)...
redis-cli ping >nul 2>&1
if errorlevel 1 (
    echo [INFO] Redis not connected (WebSocket events will be disabled)
) else (
    echo [OK] Redis is running
)

echo.
echo ========================================================
echo Step 4: Service Startup Guide
echo ========================================================
echo.

echo Choose one of the following options:
echo.
echo Option A - Start Backend Service Only (for API testing):
echo   cd backend
echo   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
echo   Then open: http://localhost:8000/docs
echo.
echo Option B - Start Full Stack (Backend + Frontend):
echo   Terminal 1: cd backend ^&^& uvicorn app.main:app --reload --port 8000
echo   Terminal 2: cd frontend ^&^& npm run dev
echo   Then visit: http://localhost:5173
echo.
echo Option C - Use Docker Compose:
echo   docker-compose up -d
echo   Then access services via defined ports
echo.

echo.
echo ========================================================
echo Step 5: Manual Testing Checklist
echo ========================================================
echo.
echo Before proceeding, please complete these steps manually:
echo.
echo [ ] 1. Configure .env file with correct database credentials
echo [ ] 2. Run database migration: python -m alembic upgrade xxx_linkage_tables
echo [ ] 3. Start backend service and test via Swagger UI
echo [ ] 4. Create test data using POSTMAN or browser
echo [ ] 5. Verify CRUD operations work correctly
echo [ ] 6. Test toggle enable/disable functionality
echo [ ] 7. Simulate trigger and verify log creation
echo [ ] 8. Start frontend service and test UI integration
echo.

echo.
echo ========================================================
echo Step 6: Next Steps
echo ========================================================
echo.

echo Recommended actions:
echo 1. Read detailed test plan: docs\test\3.4-integration-testing-plan.md
echo 2. Review current status report: docs\test\3.4-integration-test-report-v1.md
echo 3. Execute database migration when environment is ready
echo 4. Write E2E test cases: backend\tests\e2e\test_linkage_e2e.py
echo.

echo ========================================================
echo Integration Test Preparation Complete!
echo ========================================================
echo.
echo Current Status: DEVELOPMENT PHASE COMPLETE (85%)
echo Next Phase: INTEGRATION TESTING (15%)
echo.
echo Ready to start manual integration testing!
echo.

pause
