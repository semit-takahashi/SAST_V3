#!/bin/bash

lastid=$(xdotool getactivewindow)
id=$(xdotool search --onlyvisible --class chromium-browser)
xdotool windowfocus --sync $id >> $HOME/reload.log 2>&1
xdotool key ctrl+r >> $HOME/reload.log 2>&1
# 最後にフォーカスを戻す
xdotool windowfocus --sync $lastid >> $HOME/reload.log 2>&1
