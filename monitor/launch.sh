#!/bin/bash

echo "Start Launcer"
# wait network connection
/usr/bin/python3 /home/sast/wait_connection.py
echo "Network Coonected .. "

#while ! ping -4 -c 3 google.com > /dev/null; do
#	echo "Waiting for network connection..."
#	sleep 2
#done

SAST_DIR="$HOME/SAST_V301"
MONITOR="$SAST_DIR/monitor/RemoteMonitor.py"
pushd .
cd $SAST_DIR
GOG=`$SAST_DIR/libSQLite.py google_url`
AMB=`$SAST_DIR/libSQLite.py ambient_url`
popd
echo "Google : $GOG"
echo "Ambient : $AMB"

#URL='https://ambidata.io/bd/board.html?id=39477'
#URL='file:///home/sast/start.html'
#/usr/bin/chromium-browser --noerrdialogs --disable-infobars --kiosk $URL 

echo "Launch Chrome Browser"
/usr/bin/chromium-browser --noerrdialogs --noerrdialogs --disable-infobars --gpu --gpu-launcher --in-process-gpu --ignore-gpu-blacklist --ignore-gpu-blocklist --kiosk $GOG $AMB &

sleep 10
if [ -f $MONITOR ]; then
	echo "Start Remote Monitor"
	/usr/bin/python $MONITOR 
fi
echo "done"
