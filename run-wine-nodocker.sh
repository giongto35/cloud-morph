#!/usr/bin/env bash
Xvfb :99 -screen 0 1280x800x16 < /dev/null > /dev/null 2>&1 &
x86_64-w64-mingw32-g++ ./winvm/sendkey.cpp -o ~/.wine/drive_c/synckey.exe -lws2_32 -static-libgcc -static-libstdc++
wine C:\\synckey.exe $3 < /dev/null > /dev/null 2>&1 & 
cd $1
DISPLAY=:99 wine $2 -w < /dev/null > /dev/null 2>&1 &
