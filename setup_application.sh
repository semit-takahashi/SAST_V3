#!/bin/bash
echo "1.System Update"
sudo apt update -y
sudo apt upgrade -y
sudo apt autoremove -y

echo "2.Install Libraries ... "
sudo apt install -y sqlite3 git python3-dev python3-pip vim 
sudo pip3 install wiringpi psutil schedule ipget bluepy 
sudo pip3 install Adafruit_SSD1306 Pillow ipget pyserial schedule
sudo pip3 install git+https://github.com/AmbientDataInc/ambient-python-lib.git 

echo "2.Add permissions"
bluepy-helper eg. python3 - bluepy 1.3.0 
sudo setcap cap_net_raw+e  /usr/local/lib/python3.9/dist-packages/bluepy/bluepy-helper
sudo setcap cap_net_admin+eip  /usr/local/lib/python3.9/dist-packages/bluepy/bluepy-helper
sudo setcap cap_net_raw+ep /usr/bin/hcitool 

