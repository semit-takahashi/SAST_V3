#!/bin/bash
if [ "$#" -ne 2 ]; then
	echo "WPA Add scripts"
	echo "usage: $0 SSID KEY"
	exit
fi
WPA_SUP="/etc/wpa_supplicant/wpa_supplicant.conf"
WPA_PAS="/usr/bin/wpa_passphrase"
# キー表示
$WPA_PAS $1 $2 

read -p "追加しますか？" yn
case "$yn" in [yY]*);; *) echo "中止" ; exit ;; esac
$WPA_PAS $1 $2 | sudo /usr/bin/tee -a $WPA_SUP

echo "show $WPA_SUP"
sudo cat $WPA_SUP

