@echo off
rem Makes NEFONT.MAC from nefont.png (the bitmaps; the comments of NEFONT.MAC stay)
python tools\conv_fontpng.py
if errorlevel 1 (
  echo FAILED
  exit /b 1
)
