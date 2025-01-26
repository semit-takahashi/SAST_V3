#!/bin/bash

DEST_USER="sast"
SAST_DIR='SAST_V301'
DEST_PATH="/home/${DEST_USER}/${SAST_DIR}"
CURRENT=`pwd`

SRC_PATH=""
SRC_FILES="start.sh lib*.py config.py SAST_[a-z]*.py setup_bashrc.sh"
DBS_FILES="sql_sastv3.sqlite"

SET_PATH="settings"
SET_FILES="E220_config.py E220_setting.ini GAS_setting.py"

FNT_PATH="font"
FNT_FILES="DotGothic16-Regular.ttf fonts-japanese-gothic.ttf"

if [ $# -ne 1 ]; then
    echo "Usage : $0 hostname"
    exit 1
fi

echo "mkdir Remote host $1"
/usr/bin/ssh ${DEST_USER}@$1.local mkdir -p ${SAST_DIR}/${SET_PATH} ${SAST_DIR}/${FNT_PATH}


DEST="$DEST_USER@$1.local:$DEST_PATH"

echo "copy SOURCE files... ${SRC_PATH}"
cd ${CURRENT}/${SRC_PATH}
/usr/bin/scp ${SRC_FILES} ${DEST}/${SRC_PATH}
echo ""
echo "copy SETTING files... ${SRC_PATH}/${SET_PATH}"
#cd ${CURRENT}/${SRC_PATH}
/usr/bin/scp ${SET_FILES} ${DEST}/${SET_PATH}
echo ""
echo "copy FONT files... ${SRC_PATH}/${FNT_PATH}"
cd ${CURRENT}/${FNT_PATH}
/usr/bin/scp ${FNT_FILES} ${DEST}/${FNT_PATH}


echo << EOS
setup process..
1. $ configure bash
> 
bash setup_bashrc

2. install librarys 
sudo raspi-config
>change hostname 
>system Expand
>Update
>Interface Enable
 Enable I2C
 Enable Serial NNO->YES
>exit
>>>reboot

2. install librarys 
sudo apt install -y sqlite3 git python3-dev python3-pip vim 
sudo pip3 install Adafruit_SSD1306 Pillow ipget pyserial schedule
sudo pip3 install git+https://github.com/AmbientDataInc/ambient-python-lib.git 
sudo pip3 install wiringpi psutil schedule ipget bluepy smbus2


3. add user Permissions
bluepy-helper eg. python3 - bluepy 1.3.0 
>
sudo setcap cap_net_raw+e  /usr/local/lib/python3.9/dist-packages/bluepy/bluepy-helper
sudo setcap cap_net_admin+eip  /usr/local/lib/python3.9/dist-packages/bluepy/bluepy-helper
sudo setcap cap_net_raw+ep /usr/bin/hcitool 

4. GAS Setting file move to /boot
>
sudo mv -f settings/GAS_setting.py /boot

5. Bluetooth ＆ Serial Console Stting
> add script /boot/config.txt
dtparam=i2c_arm=on
dtoverlay=i2c-rtc,ds3231,dwc2
enable_uart=1

> add text /boot/cmndline.txt

5. crontab -e and Add startup Script
@reboot /bin/bash /home/${DEST_USER}/${SAST_DIR}/start.sh

6. edit Rsyslogd.conf
sudo vi /etc/rsyslogd.conf
>
local1*.      -/var/log/SAST.log


4. execute Raspi-Config
2.Interface
 -> I2C Enable
 -> Serial Enable  NO->YES -> Reboot

reboot after

6.RTC clock Enable
sudo hwclock -w --verbose

7. SQLIte3 Library Initialize
cd $SAST_DIR; ./libSQLite.py CLEAR -> YES

EOS
echo "done."
