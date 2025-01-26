#!/bin/bash
#SAST V3 Startup Script 

# Board LED Green 
function LED_green () {
	/usr/bin/raspi-gpio set 19 op dh
	sleep 0.1
	/usr/bin/raspi-gpio set 19 op dl
}
# Board LED Red
function LED_red () {
	/usr/bin/raspi-gpio set 13 op dh
	sleep 0.1
	/usr/bin/raspi-gpio set 13 op dl
}

# Green LED 0.1秒点灯（スクリプト動作確認用）
/usr/bin/raspi-gpio set 13 op dh
/usr/bin/raspi-gpio set 19 op dh

#python Path
PYTHON="/usr/bin/python3"

# ディレクトリ移動
EXE_DIR="$HOME/SAST_V301"
cd $EXE_DIR

# startup Message
$PYTHON $EXE_DIR/libOLED.py STARTUP 

# プロセスKILL
echo "Kill Python3 Process ... "
/usr/bin/sudo /usr/bin/killall python3
echo "done."
echo ""

# ホスト名取得
host=$(hostname)
len=${#host}-2

# 下2桁取得
node=${host:${len}:2}
echo " " >> stderr.log
echo "SAST START : `date '+%Y-%m-%d %H:%M:%S'` "
echo "SAST START : `date '+%Y-%m-%d %H:%M:%S'` " >> stderr.log
echo "$host($node)" >> stderr.log
echo "hostname is $host > NodeNO is $node"
echo "hostname is $host > NodeNO is $node" >> stderr.log

if [ $node == "00" ]; then
	echo "Type Gateway"
	echo "Type Gateway"  >> stderr.log
  	$PYTHON $EXE_DIR/libOLED.py STARTUP "Waiting for" "Connection..." 2>> stderr.log
	while ! ping -c 1 google.com > /dev/null; do
		echo "Waiting for network connection..."  >> stderr.log
		sleep 2
	done
	echo "Network connection established." >> stderr.log
	/usr/bin/raspi-gpio set 13 op dl
	echo "Start libOLED" >> stderr.log
	$PYTHON $EXE_DIR/libOLED.py 2>> stderr.log &
	sleep 1
	echo "Start libLORA" >> stderr.log
	$PYTHON $EXE_DIR/libLORA.py GATE 2>> stderr.log &
	sleep 5
	echo "Start SAST_observer" >> stderr.log
	$PYTHON $EXE_DIR/SAST_observer.py 2>> stderr.log &
	echo "check SAST_observer process EXIT.... until 10sec" 
	/usr/bin/raspi-gpio set 13 op dl
	/usr/bin/raspi-gpio set 19 op dl
	wait $!
	if [ $? -ne 0 ]; then
		echo "SAST_observer System ERROR.... Don't Continue."
		/usr/bin/raspi-gpio set 13 op dh
		exit 1
	fi
else
	echo "Type Node"
	echo "Type Node" >> stderr.log
	echo "Start libOLED" >> stderr.log
	/usr/bin/raspi-gpio set 13 op dl
	$PYTHON $EXE_DIR/libOLED.py 2>> stderr.log &
	sleep 1
	echo "Start libLORA" >> stderr.log
	$PYTHON $EXE_DIR/libLORA.py NODE 2>> stderr.log &
	sleep 5
	echo "Start SAST_recorder" >> stderr.log
	$PYTHON $EXE_DIR/SAST_recorder.py 2>> stderr.log &
	/usr/bin/raspi-gpio set 13 op dl
	/usr/bin/raspi-gpio set 19 op dl
fi
echo "shell script done."
echo ""
LED_green
LED_green
exit 0
