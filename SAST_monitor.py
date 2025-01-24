#!/usr/bin/python3
# SAST( SEM-IT Agriculture Support Tool） モニター
# Ver. 1.0.7 2021/03/25
# Author F.Takahashi
#
# 概要
# SIGUSR1を受けて以下の処理を行う
# ・SQLiteからデータを読み込む（表示用）
#   ->OLEDクラスに表示依頼
# タイマー割り込み処理（10秒ごと）
# ・送信ミスデータを検知し、クラウドに再送信
# ・ルータを監視してネットワークエラーを検知
# GPIOスイッチ割り誇示
# ・タクトスイッチ2個のイベントを処理
# 　→ボタン押下時にOLED画面を切り替える
# 　・ネットワークステータス
# 　・バッテリー、センサー距離、湿度
#
import logging
logging.basicConfig(format='%(asctime)s %(message)s',level=logging.INFO)

from libCloud import sent_Ambient, sent_GAS
from libMachineInfo import getMachine_Temp, getIPAddr, getTypeIP, getDefaultRoute, IsAlive, getHostname
from libOLED import OLED
from libGPIO import IO
from libSQLite import SQL
#from libBMP180 import BMP180

from bluepy import btle
import smbus2
import bme280
import time
import struct
import sys
import requests
import json
import threading
import signal

#設定ファイル
sys.path.append('/boot')
from SAST_settings import SENS, AMBIENT, IFTTT, GAS, SAST_NAME

def showSTAT(d=None):
    global D
    if( d == None ):
        S = SQL()
        d = S.latest()
        S.close()
    D.updateStatus( dt=d, net1=d['net1'], net2=d['net2'] )
    D.showStatus()

''' intr_checkRecorde ''' 
def intr_checkRecord(sql_id, timer=30):
    global D
    S = SQL()
    row = S.latest()
    #logging.debug(f"[intr_checkRecord]")
    if sql_id != row['id']:
        logging.debug(f"Get New Recode : {row}")
        sql_id = row['id']
        # 表示データ更新処理
        showSTAT( d=row )
        #D.showStatus( dt=row, sens=len(SENS) ,net1=row['net1'], net2=row['net2'] )
        # データ表示
    S.close()

    # 再度X秒後に自分を呼び出す
    logging.debug(f"check continue : {timer}sec id={sql_id}")
    t=threading.Timer(timer,intr_checkRecord,args=(sql_id,timer))
    t.start()

''' interrupt buton right ''' 
def btn_right(self):
    logging.info("PUSH Right BUTTON")
    global D
    D.showPI()
    time.sleep(5)
    D.showStatus()
    
''' interrupt buton left ''' 
def btn_left(self):
    logging.info("PUSH left BUTTON")
    global D
    D.showStatus2()
    time.sleep(5)
    D.showStatus()

def intr_signal(num, frame):
    logging.info(f"[SAST_monitor] catch SIGNAL {num}")
    showSTAT()

def intr_signal_term(num, frame):
    logging.info(f"[SAST_monitor] intr_term catch SIGNAL {num}")
    global END
    END = False

## --- GPIO init
O = IO(rsw_callback=btn_right, lsw_callback=btn_left)

## --- OLED init
D = OLED(sens=len(SENS)) 

## --- SQL init
DB = SQL()

## ---- Interval
END = True
INTERVAL = 30

### ===== Main 
def main():
    logging.info(f"[SAST_monitor] into Main LOOP")
    # --- Main LOOP
    showSTAT()
    while END:
        logging.debug("Check send error data for Ambient(NET1)")
        rows = DB.get_NET1_Error()
        if( len(rows) != 0 and AMBIENT['use'] ):
            logging.info(f"find SendError DATA(Ambient) num={len(rows)}")
            sendDATA = []
            ids = []
            for d in rows:
                ids.append( d.pop('id') ) 
                del d['opt1'],d['opt2'],d['opt3'],d['net1'],d['net2'],d['net3']
                logging.debug(f"sendDATA = {d}")
                sendDATA.append(d)

            ## --- Ambientは纏めて送信可能 
            ret = sent_Ambient(AMBIENT, sendDATA )
            if( ret ):
                DB.update_NET1(ids)
            else:
                logging.error("Amdient ReSend Error")
        
        logging.debug("Check send error data for GAS(NET2)")
        rows = DB.get_NET2_Error()
        if( len(rows) != 0 and GAS['use'] ):
            logging.info(f"Find SendError DATA(GAS) num={len(rows)}")
            ids = []
            for d in rows:
                ids.append( d.pop('id') ) 
                del d['opt1'],d['opt2'],d['opt3'],d['net1'],d['net2'],d['net3']
                logging.debug("sendDATA = {d}")
                # --- GASは１行毎に処理のため 
                ret = sent_GAS( GAS, d )
                if( ret == False  ):
                    ## --- 送信失敗はIDを削除
                    logging.error("GAS ReSend Error")
                    ids.remove(-1)
            DB.update_NET2(ids)

        # --- Netowork Check
        logging.debug("Check Network")
        MyIP = getIPAddr()
        logging.debug(f"MyIP = {MyIP}")
        if( getTypeIP(MyIP) == True ):
            gateIP = getDefaultRoute()
            if( IsAlive(gateIP) == False):
                logging.warning("ERROR! No reach DefaultRoute {gateIP}")
        else:
            logging.warning(f"ERROR! ignore MyIP={MyIP}")

        ## --- NetworkRESET ? -> 

        ## --- get BATTERY STAT 10sec
        BATT = [None,None,None]
        num = 0
        for sens in SENS:
            BATT[num] = DB.getBattery( sens['MAC'] )
            num += 1
        logging.debug(f"BAT = {BATT} ")
        D.updateStatus2(BATT)

        ## --- Wait 10sec to Main Loop
        time.sleep(INTERVAL)


if __name__ == '__main__':
    # -- START UP 
    logging.info("[SAST_monitor] Waiting Assign IP Assress")
    D.text( 2, 32 , "PLEASE WAIT..." )
    st_time = time.time()

    # --- Check IP Address
    while END:
        ip = getIPAddr()
        if( getTypeIP(ip) ):
            logging.info(f"[SAST_monitor] IP is {ip}({getHostname()})")
            logging.info("IP waiting span is {0:5.2f}sec".format(time.time()-st_time)) 
            D.showPI()
            time.sleep(5)
            break
        logging.debug("[SAST_monitor] while DHCP")
        time.sleep(2)
        continue

    ## --- show status
    showSTAT()

    ## --- Valid SIGNAL hook
    signal.signal(signal.SIGUSR1,intr_signal)
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, intr_signal_term)

    try:
        main()

    except KeyboardInterrupt:
        logging.info("SAST_monitor] chatch CTRL+C")

    del DB
    sys.exit(1)

#### -- history
## Ver.1.0.7
# 切り替え画面にてセンサー距離（RSSI）を表示するようにした。
#
## Ver.1.0.6
# SIGNAL INT、TERMをフックして、終了する様にした
