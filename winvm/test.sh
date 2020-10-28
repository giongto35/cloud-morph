#!/usr/bin/env bash
x86_64-w64-mingw32-g++ ./syncinput.cpp -o /winevm/synckey.exe -lws2_32 -static-libgcc -static-libstdc++ 
