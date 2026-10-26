@echo off
chcp 65001 >nul
echo Adding MT5 secrets to GitHub...
echo.

cd /d C:\Users\1234\Desktop\مجلد جديد (2)

echo Setting MT5_LOGIN...
gh secret set MT5_LOGIN --body "490512"

echo Setting MT5_PASSWORD...
gh secret set MT5_PASSWORD --body "Ahmad$0988"

echo Setting MT5_SERVER...
gh secret set MT5_SERVER --body "FusionMarkets-Demo"

echo.
echo Done! Secrets added successfully.
pause
