@echo off

rem Define ESCchar to use in ANSI escape sequences
rem https://stackoverflow.com/questions/2048509/how-to-echo-with-different-colors-in-the-windows-command-line
for /F "delims=#" %%E in ('"prompt #$E# & for %%E in (1) do rem"') do set "ESCchar=%%E"

for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "YY=%dt:~2,2%" & set "YYYY=%dt:~0,4%" & set "MM=%dt:~4,2%" & set "DD=%dt:~6,2%"
set "DATESTAMP=%YYYY%-%MM%-%DD%"
set REVISION=0
for /f %%i in ('git rev-list HEAD --count 2^>nul') do (set REVISION=%%i)
echo REV.%REVISION% %DATESTAMP%

echo 	.ASCII /REV.%REVISION% %DATESTAMP%/ > VERSIO.MAC

@if exist NEARTH.LST del NEARTH.LST
@if exist NEARTH.OBJ del NEARTH.OBJ
@if exist NEARTH.MAP del NEARTH.MAP
@if exist NEARTH.SAV del NEARTH.SAV
@if exist NEARTH.SAV del NEARTH.SAV

python tools\check_names.py
if errorlevel 1 goto :Failed
tools\macro11.exe NEARTH.MAC -l NEARTH.lst -o NEARTH.obj -rt11 -se -yus -ysl 32
if errorlevel 1 goto :Failed
findstr /RC:"^[ABDEILMNOPQRTUZ\*] " NEARTH.lst
if %errorlevel%==0 goto :Failed
echo NEARTH COMPILED SUCCESSFULLY

tools\pclink11.exe /VERBOSITY:1 NEARTH.obj /MAP /EXECUTE:NEARTH.SAV
if errorlevel 1 (
  echo ======= LINK FAILED =======
  goto :Failed
)
for /f "delims=" %%a in ('findstr /B "Undefined globals" NEARTH.MAP') do set "undefg=%%a"
if not "%undefg%"=="" (
  echo ======= LINK FAILED: Undefined globals =======
  goto :Failed
)
echo NEARTH LINKED SUCCESSFULLY

dir /-c NEARTH.SAV|findstr /R /C:"NEARTH.SAV"

echo %ESCchar%[92mSUCCESS%ESCchar%[0m
exit

:Failed
@echo off
echo %ESCchar%[91mFAILED%ESCchar%[0m
exit /b

:FileSize
set fsize=%~z1
exit /b 0
