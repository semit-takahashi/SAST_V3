#!/usr/bin/python3
"""
Raspberry Pi NODE側MAIN SAST_recorder.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Summary:
NODE側のMAINプログラム
1分おきに、本ノードにぶら下がるTH-1センサーの情報を取得してSQLiteに蓄積する。

SEMI-IT Agriculture Support TOOLs V3
バージョン情報 -------------------------
Ver. 1.0.0 2023/03/21
Ver. 2.0.5 2025/01/18 MAC範囲を指定して、そのMACのセンサーデータを取得する
Auther F.Takahashi
"""

## import ORIGINAL
import config as C
import libMachineInfo as M
import libSensor as SENSOR
import libSQLite as SQL

## import system
import time
import sys
import signal
import schedule

###### SIGTERM 
def intr_signal_term(num,frame):
    C.logging.info("[SAST_recorder] catch SIGTERM")
    sys.exit(1)

signal.signal(signal.SIGTERM, intr_signal_term)


def _getSensorDATA() :
    ''' 指定されたNODEのセンサーのデータを読み取ってSQLに保存 (makerリスト版)'''
    sql = SQL.SQL()
    sensorValues = []
    C.logger.debug(f"MACS -> {C.VaildMACs}")

    # -- MACリストを用いて、BLEから情報取得
    try :
        sensorValues = SENSOR.getSensorsDATA_th1(C.VaildMACs)

    except TypeError as e :
        # -- ROOTじゅやない
        C.logger.error("this Program MUST be run as ROOT!!")
        sys.exit(1)

    except ValueError as e :
        # -- センサーが未指定
        C.logger.error(f"No Sensors resonded... {C.VaildMACs}")
        return
    
    except Exception as e :
        # -- 其れ以外のエラー
        C.logger.error(f"_getSensorDATA(): catch Excepton : {e}")

    #C.logger.info(f"sensorValues: {sensorValues}")
    # -- NODEを追加してデータを更新
    for val in sensorValues :
        val['node'] = NODE_NO
        sql.appendData(val)

    return 

def _intr_term( num, frame) :
    C.logger.warning(f"SIGTERM catch exit... {num}")
    sys.exit(0)

###### NODE 
NODE_NO = M.getNodeNo()
NODE_NAME = ''

######  === MAIN LOOP ================================================= 
if __name__ == '__main__':
    C.logger.info(f"START Recoder NODE {NODE_NO}")

    signal.signal(signal.SIGTERM, _intr_term)
    signal.signal(signal.SIGHUP, _intr_term)

    args = sys.argv
    if len(args) != 1 and args[1].upper() == "CLEAR" :
        C.logger.info("-> DATABASE CLEAR ALL DATA ")
        S = SQL.SQL("CLEAR")
        del S
    
    S = SQL.SQL()

    try :
        NODE_NAME = S.getNodeInfo(NODE_NO)[1]
        C.logger.info(f"NAME is {NODE_NAME}")
    except Exception as e :
        ## データベースから取得できなかったとき
        import libMachineInfo as M
        NODE_NAME = f"lora{M.getNodeNo():02}"
        C.logger.warning(f"Unable to Get Node-Name > {NODE_NAME}")
    
    start_sec = NODE_NO*10 - 10
    sec = f":{start_sec:02}"
    C.logger.info(f"send sensor every {sec} second.\n")

    ## DATABASE 
    C.logger.info("[Recoder] Init NODE Databases...")
    S = SQL.SQL("STARTUP_NODE")

    ## データを送信するするスケジュール登録
    schedule.every().minute.at(sec).do(_getSensorDATA)

    ## 無限ループ
    while True:
        # 次の行で実行まで待つ。
        schedule.run_pending()
        # 終わったらsleepしてもう一度
        time.sleep(1)
