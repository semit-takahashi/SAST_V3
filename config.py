#!/usr/bin/python3
"""
SAST システム全体の共通情報や共有関数群
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
SEMI-IT Agriculture Support TOOLs [E220-900T22(JP)] LoRa Library

バージョン情報 -------------------------
Ver. 1.0.0 2023/03/21
Ver. 2.0.1 2025/01/20 
Auther F.Takahashi
"""

### TIME Settings
## GATE
SPAN_SEND_CLOUD = 2     #minute
SPAN_CONFIG_UPDATE = 1  #hour
SPAN_BEACON = 60        #sec
## NODE
SPAN_SENSOR = 60        #sec

## SENSOR Vaild MAC Addr 
#  -- write small charactor
VaildMACs = ['49:22:01','49:22:05','49:21:08','49:23:09']

# GAS setting　GAT_setting.py 参照
#GAS = {
#'URL':'https://script.google.com/macros/s/AKfycbw3MOpC9yLOdKagohiN_QCjGocWtPlRibTUtKa96Dy3_FuWzC__PShKxnnVYuu7-_kW8w/exec'
#}

###### Ambient Board URL
AMB = {
'URL':"https://ambidata.io/bd/board.html?id="    
}

###### Non Data send to Ambient
AMB_SEND_NODATA = False

###### Logging
import logging
import logging.handlers  as ih
"""
logger Logger : 通常のlogger
loggerOLED Logger : OLED用のlogger

"""
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

### --- Screen
stream_Handler = logging.StreamHandler()
stream_Handler.setLevel(logging.WARNING)
stream_Handler.setFormatter(logging.Formatter('%(asctime)s::%(module)s:%(levelname)s:%(message)s'))

### --- Syslog --- facility is local1
syslog_Handler = ih.SysLogHandler(address="/dev/log",facility=ih.SysLogHandler.LOG_LOCAL1)
syslog_Handler.setLevel(logging.INFO)
syslog_Handler.setFormatter(logging.Formatter('%(module)s:%(levelname)s:%(message)s'))

### --- File
file_Handler = ih.RotatingFileHandler("./SAST-debug.log")
file_Handler.setLevel(logging.DEBUG)
file_Handler.setFormatter(logging.Formatter('%(asctime)s::%(module)s:%(levelname)s:%(message)s'))
file_Handler.maxBytes = 1024 * 1024
file_Handler.backupCount = 3

### -- Set Handler
logger.addHandler(syslog_Handler)
logger.addHandler(stream_Handler)
logger.addHandler(file_Handler)


### --- OELD Syslog --- facility is local1
loggerOLED = logging.getLogger('OLED')
syslog2_Handler = ih.SysLogHandler(address="/dev/log",facility=ih.SysLogHandler.LOG_LOCAL1)
syslog2_Handler.setLevel(logging.INFO)
syslog2_Handler.setFormatter(logging.Formatter('OLED:%(levelname)s:%(message)s'))
loggerOLED.addHandler( loggerOLED )

### --- Nodeシステム状態

### --- Senser detection time (second)
SEARCH_SECOND = 3.0


###### Main DATA Queue
import queue 
Q = queue.Queue()

##### Time String Functions
import time
import datetime
def getTimeSTR( short=False ) -> str:
    """現在の日付の文字列を返す
    Args:
        short (bool): 短い文字列でTrue. 初期値 False.
    Returns:
        str: 文字列 ( YYYY-MM-DD HH:MM:SS ) / (MM-DD HH:SS)
    """
    if short :
        return time.strftime("%m-%d %H:%M")
    return time.strftime("%Y-%m-%d %H:%M:%S")

def str2Datetime( str ) -> datetime :
    """ライブラリ:SQL用文字列時刻をdatetime(native)型に変換
    Args:
        str : SQLiteで使う日時文字列
    Returns:
        datetime: データ
    """
    try:
        dt = datetime.datetime.strptime(str, "%Y-%m-%d %H:%M:%S")
        return dt
    except Exception as e:
        logger.error(f"[str2time] ERROR : str={e}")
        return None

def IsIntervalWarn( lastTime, interval = 300 ) -> bool:
    """指定した時間から経過したかをチェック
    Args:
        lastTime : SQLite日時文字列
        interval (int, optional): 経過時間（秒）. 初期値 300.
    Returns:
        bool: 経過済 True / 未経過 False
    """
    try :
        last = str2Datetime(lastTime)
        span = datetime.datetime.now() - last
        #logger.debug(f"[IsIntervalWarn] src[{lastTime}] int:{interval}sec span={span.seconds}sec")
        #print(f"[IsIntervalWarn] src[{lastTime}] int:{interval}sec span={span.seconds}sec")
        return True if( span.total_seconds() >= interval ) else False
    except Exception as e :
        logger.warning(f"IsIntervalWarn ERROR {e}")
        return False

def spanTimeforSTR( timeStr:str ) -> time:
    """指定した日時文字列から現在までの経過時間
    Args:
        timeStr (str): 日時文字列
    Returns:
        timedelta : 経過時間のtimedelta
    """
    try : 
        last = str2Datetime(timeStr)
        return datetime.datetime.now() - last
    except Exception as e :
        logger.warning(f"spanTimeforSTR ERROR {e}")
        return False

def toTimespan( time_str:str ) -> time :
    """指定した日時文字列からINT型のtime情報を返す
    Args:
        time_str (str): 日時文字列
    Returns:
        time: int型のタイムデータ
    """
    return int(datetime.datetime.timestamp(str2Datetime(time_str)))

##### Notify Status Enum
from enum import IntEnum
class SENS_ST(IntEnum):
    """センサー状態Enum（DATABASE用) """
    NONE = -1,
    LOST = 0,
    NORMAL = 1,
    LOW_WARN = 2,
    LOW_CAUTION = 3,
    HIGH_WARN = 4,
    HIGH_CAUTION = 5,

#### Node System Status Enum
class NODE_STAT(IntEnum):
    """Nodeのシステム状態（DATABAE用） """
    NONE = 0,
    START = 1,
    WAIT_BEACON = 2,
    WAIT_SEND = 3,
    GOOD = 4,
    CAUTION = 5,
    WARN = 6,
    LOST = 7,


# GAS setting　GAT_setting.py 参照
GAS = {}

try :
    import sys
    sys.path.append('/boot')
    from GAS_setting import URL
    GAS = URL
except ImportError :
    logger.error("/boot/GAS_setting.py Not Found")
    pass
