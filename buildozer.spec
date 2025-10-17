[app]
title = CarPlus Manager
package.name = carplusmanager
package.domain = org.carplus
source.dir = .
source.include_exts = py,kv,db,png,jpg,json,txt
main = main.py
version = 1.0
icon.filename = icon.png
orientation = portrait
fullscreen = 1
android.permissions = WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
requirements = python3,kivy,plyer,sqlite3
android.minapi = 21
android.api = 33
android.archs = arm64-v8a