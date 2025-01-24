#!/usr/bin/python3
"""
Raspberry Pi センサー情報取得ライブラリ libSensor.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Summary:
INKBIRD TH-1向けに、BLEアドバタイズをサーチしてそのなかの情報をデコードする。
なお、bluepyの仕様上、scanはroot権限（sudo）で実施する必要があるため、
本ライブラリを利用する上位のmainは、rootで起動させること。

SEMI-IT Agriculture Support TOOLs V3
バージョン情報 -------------------------
Ver. 1.0.0 2023/03/21
Auther F.Takahashi
"""

import config as C
import time
import struct
import libMachineInfo as M
try :
    from bluepy import btle
except ImportError :
    C.logger.warning("Module 'bluepy' not fond")
    pass

def getSenserData_th1(mac:list ) -> list :
    """INKBIRD TH1のセンサーデータを取得（個別）

    Summary:
    センサーデータの温度、湿度、外部センサー有無を返す
    バッテリーは別モジュールにてroot権限で動作させる必要あり。

    Args:
        mac (list): 取得したいMACアドレスのリスト（BLE）

    Returns:
        list: sensorValue
    """
    start = time.time()
    try:
        with btle.Peripheral(mac) as peripheral :
            service = peripheral.getServiceByUUID(0xfff0)
            characteristics = service.getCharacteristics(0xfff2)
            sensorRAW = characteristics[0].read()
            C.logger.debug(f"{mac} -> {sensorRAW} : {len(sensorRAW)}")
            #C.logger.debug(f"characteristics : {characteristics[0].uuid}")
            (temp, humid, ext, uk2, uk3) = struct.unpack('<hh?BB', sensorRAW)
            sensorValue = {
                    'date' : C.getTimeSTR(),
                    'templ': temp / 100,
                    'humid': humid / 100,
                    'ext': ext
            }
            C.logger.info(f"{mac} -> {sensorValue}")
            C.logger.info(f"Search time {time.time() - start:.2f}sec")
            return sensorValue

    except btle.BTLEException as eb:
        C.logger.error(f" bulepy Exception : {eb}")
        C.logger.info(f"Search time {time.time() - start:.2f}sec")
        return None

    except Exception as ex:
        C.logger.error(f" Exception :{ex}")
        C.logger.info(f"Search time {time.time() - start:.2f}sec")
        return None

def getSensorsDATA_th1( maker:list ) -> list:
    """メーカID（MAC先頭3バイト）をもとに、INKBIRD-TH1 のBEL アドバタイズデータを検索してリストとして返す。

    Summary:
    MACアドレスリストを元に、BLEデバイスのアドバタイズデータを取得（5秒）
    温度、湿度、バッテリー％、外部センサー有無をリストとして返す。
    本館数を利用する場合はプロセスをあらかじめsudoで起動させておく必要がある。
    ROOTで無い場合は、Noneを返す

    Args:
        sens (list): センサーMACリスト

    Returns:
        list: sensorValue

    Attention:
        この関数はBluetoothbのscan()を利用するため、root（sudo）で実行する必要があります。
        this function is running must by ROOT user
    """
    #if not M.isRootUser() :
        #C.logger.error("this Function must be run as root user (sudo) .")
        #raise TypeError("not ROOT")

    C.logger.info(f"getSensor DATA >> {maker}")
    sensList = list()
    start = time.time()
    ret = list()

    scanner =  btle.Scanner()
    devs = scanner.scan(C.SEARCH_SECOND)
    ## devsで取得されるのはScanEntryの配列
    ## see : http://ianharvey.github.io/bluepy-doc/scanentry.html
    C.logger.debug(f"scan complete {len(devs)} ")
    stime = C.getTimeSTR()

    for dev in devs:
        val = dev.getValueText(255)
        C.logger.debug(f"> {dev.addr} : {val}")
        if( val is None or len(val) != 18) : continue
        (temp,humid,ext,uk1,uk2,batt,uk3) = struct.unpack('<hh?BBBB', bytes.fromhex(val))
        temp /=100
        humid /=100
        rssi = dev.rssi
        sensList.append({'mac':dev.addr.lower(),'batt':batt,'templ':temp,'humid':humid,'ext':ext,'rssi':rssi,'date':stime})
        C.logger.info(sensList[-1])

    # --　指定されたメーカーコードに一致するデータの抽出            
    for s in sensList :
        if s['mac'][:8] in maker :
            C.logger.info(f"add> {s['mac']} {s['templ']} {s['batt']} {s['rssi']}")
            ret.append(s)

    C.logger.debug(f"device : {len(ret)}")
    C.logger.info(f"Search time {time.time() - start:.2f}sec")
    return ret

if __name__ == '__main__':
    from libSQLite import SQL
    import sys

    # --- advatized
    S = SQL()
    ret = getSensorsDATA_th1(C.VaildMACs)
    print(f"RET({len(ret)}) = {ret}")

    sys.exit()

