#!/bin/bash
# Kill ONLY the upwork-signup automation Chrome (by profile path). NEVER touches other Chromes.
powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { \$_.CommandLine -like '*upwork-signup*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }" 2>/dev/null
echo "automation chrome killed (others untouched)"
