@echo off
set rt11dsk=C:\bin\rt11dsk

del x-ukncbtl\nearth.dsk
@if exist "x-ukncbtl\nearth.dsk" (
  echo.
  echo ####### FAILED to delete old disk image file #######
  exit /b
)
copy x-ukncbtl\sys1002ex.dsk nearth.dsk
%rt11dsk% a nearth.dsk NEARTH.SAV
move nearth.dsk x-ukncbtl\nearth.dsk

@if not exist "x-ukncbtl\nearth.dsk" (
  echo ####### ERROR disk image file not found #######
  exit /b
)

start x-ukncbtl\UKNCBTL.exe /boot
