#!/usr/bin/env bash
# WINEPATH="C:\\MinGW\\bin;C:\\MinGW\\lib;C:\\MinGW\\include" wine C:\\synckey.exe Notepad < /dev/null > /dev/null 2>&1 &
#/usr/bin/entrypoint wine synckey.exe Notepad < /dev/null > /dev/null 2>&1 &
/usr/bin/entrypoint wine synckey.exe $3 &
cd $1; /usr/bin/entrypoint wine $2 -w
