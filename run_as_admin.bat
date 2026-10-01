@echo off
rem 以管理员身份启动异环自动竞拍（游戏带 ACE 反作弊以管理员运行，必须提权否则点击被 UIPI 拦截）
powershell -NoProfile -Command "Start-Process -FilePath 'D:\pytools\python.exe' -ArgumentList '\"D:\NTE-auto-ggg\main.py\"' -Verb RunAs"
