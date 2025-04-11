#!/usr/bin/python3
"""
Raspberry Pi 機器情報取得ライブラリ libMachine.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SEMI-IT Agriculture Support TOOLs V3
バージョン情報 -------------------------
Ver. 1.0.0 2023/03/21
Auther F.Takahashi
"""
import config as C
import os
import subprocess
import time
import psutil
import signal
import ipget
import smbus2


SAST_MONITOR = "SAST_monitor.py"

I2C_BUS = 1
I2C_PiSugar = 0x68
I2C_PiSugar_REG = 0x57

def _existI2CDevice(address):
    """ I2Cデバイスが存在するか？"""
    try:
        bus = smbus2.SMBus(I2C_BUS)
        bus.read_byte(address)
        C.logger.debug(f"デバイス {hex(address)} が検出されました")
        ret = True
    except OSError as e:
        C.logger.debug(f"デバイス {hex(address)} は検出されませんでした{e}")
        ret = False
    finally:
        bus.close()
    return ret

def isChargePiSuger3() :
    """ PiSugar3で充電中なのかを認識 
    Retuens:
            True/False
    """
    charge = False
    try:
        bus = smbus2.SMBus(I2C_BUS)
        chr = bus.read_byte_data(I2C_PiSugar_REG, 0x02)
        if chr & 0x80 != 0: charge = True
        #print(f"isChargePiSuger3 {bin(chr)}")

    except Exception as e:
        pass

    finally:
        bus.close()
        return charge
   

def getBatteryPiSugar3() -> int : 
    """ PiSugar3 のI2Cレジスタ(0x57）からバッテリー容量を返す
        I2Cが無い場合やアクセス不可の場合は-1を返す
        2025/01/30修正
        RTCの一部製品でEEPROMがある製品は、正しく値が返ってくる。
        この場合、0xffが戻り値なら-1を返す。
    Returns:
        int : バッテリー%
    """
    try:
        bus = smbus2.SMBus(I2C_BUS)
        level= bus.read_byte_data(I2C_PiSugar_REG, 0x2a)
        if level == 255 : level = -1

    except Exception as e:
        #C.logger.warning(f"No DATA from {I2C_PiSugar_REG} addr.")
        level = -1
    
    finally:
        bus.close()
        return level

def getVoltagePiSugar3() -> float :
    """ PiSugar3から電池電圧を取得
    Returns:
        float : 電池電圧
    """
    level = 0.0
    try:
        bus = smbus2.SMBus(I2C_BUS)
        vH = bus.read_byte_data(I2C_PiSugar_REG, 0x22)
        vL = bus.read_byte_data(I2C_PiSugar_REG, 0x23)
        level = ( (vH << 8) + vL ) / 1000

    except Exception as e:
        #C.logger.warning(f"No DATA from {I2C_PiSugar_REG} addr.")
        level = -1
    
    finally:
        bus.close()
        return level
    
def getWakeUpTime() : 
    """ PiSugar3の起動時刻を取得
    Returns:
        str : Wakeup Timt String
    """
    tHH = -1
    tMM = -1
    tSS = -1
    try :
        bus = smbus2.SMBus(I2C_BUS)
        boot = bus.read_byte_data(I2C_PiSugar_REG, 0x40)
        if boot == 0x00 :
            C.logger.warning("Disabled Timer ")
            print(f"ob:{bin(boot)} ")

        else :
            tHH = hex2dec(bus.read_byte_data(I2C_PiSugar_REG, 0x45))
            tMM = hex2dec(bus.read_byte_data(I2C_PiSugar_REG, 0x46))
            tSS = hex2dec(bus.read_byte_data(I2C_PiSugar_REG, 0x47))
            tHH = (tHH + 9 ) % 24
            C.logger.warning(f"Enable Timer {tHH:02}:{tMM:02}:{tSS:02}")
            #print(f"ob:{bin(boot)} ")

    except Exception as e:
        print(e)
        C.logger.warning(f"No DATA from {I2C_PiSugar_REG} addr.")
    
    finally:
        bus.close()
        return (tHH,tMM,tSS)

def setWakeUpTime( on : bool, hh=0, mm=0 ,ss=0 ) -> str :
    """ PiSugar3の起動時刻を変更もしくは無効
    Returns:
        str : Wakeup Timt String
    """
    if not( 0<=hh<=23 ) : raise ValueError(f"Error Hour {hh}")
    if not( 0<=mm<=60 ) : raise ValueError(f"Error Minute {mm}")
    if not( 0<=mm<=60 ) : raise ValueError(f"Error Second {ss}")
    try :
        bus = smbus2.SMBus(I2C_BUS)
        # PiSugar3の書き換えを可能に変更
        wp = bus.read_byte_data(I2C_PiSugar_REG, 0x0b)
        bus.write_byte_data(I2C_PiSugar_REG, 0x0b, 0x29)

        if not on :
            # タイマー無効
            bus.write_byte_data(I2C_PiSugar_REG, 0x40, 0x00)
            C.logger.warning(f"Disable Wake Up Time")
        else :
            # タイマー設定
            bus.write_byte_data(I2C_PiSugar_REG, 0x40, 0x80)
            bus.write_i2c_block_data(I2C_PiSugar_REG, 0x45, 
                    [dec2hex( (hh-9)%24 ), dec2hex(mm),dec2hex(ss)])
            C.logger.warning(f"Write TIME {hh:02}:{mm:02}:{ss:02}")

        #PiSugar3の書き換えを不可に変更
        bus.write_byte_data(I2C_PiSugar_REG, 0x00, wp)

    except ValueError as e:
        C.logger.warning(e)
        return False

    except Exception as e:
        C.logger.warning(f"No DATA from {I2C_PiSugar_REG} addr.")
        return False
    
    finally:
        bus.close()
        return True

def dec2hex( decimal_number ) :
    decimal_digits = [int(d) for d in str(decimal_number)] 
    hex_digits = []
    for digit in decimal_digits:
        hex_digits.append(hex(digit)[2:].upper()) # 各桁を16進数に変換し、リストに格納
    hex_string = "".join(hex_digits) # 16進数のリストを結合して文字列にする
    return int("0x" + hex_string, 16) # 16進数の文字列を整数に変換


def hex2dec( hex_number ):
    hex_string = hex(hex_number)[2:].upper() # 16進数を文字列に変換 ("0xFF" -> "FF")
    try :
        return  int( hex_string )
    except Exception as e:
        return  -1

def isRootUser() :
    """プロセス起動ユーザがroot?
    environではr/etc/rc.localからの起動時にroot判定が出来ないので、getuid()でも確認
    Returns:
        bool: YES
    """
    if os.getuid() == 0 : return True
    return True if os.environ.get("USER") == "root" else False

def sendSIG4Monitor():
    """_summary_

    Returns:
        _type_: _description_
    """
    C.logger.debug("[sendSIG4Monitor]")
    pid = None
    for proc in psutil.process_iter(attrs=["pid", "name"]):
        if proc.info["name"] == SAST_MONITOR : pid = proc.info["pid"]
    if pid == None :
        return False
    C.logger.debug(f"Monitor PID {pid}")
    os.kill(int(pid), signal.SIGUSR1)
    return True

def getHostname():
    """ホスト名を返す
    Returns:
        str: ホスト名
    """
    return f"{os.uname()[1]}"

def getNodeNo() :
    """ノードNoを返す
    ホスト名の下2桁がNodeNo 0はGATEWAY
    Returns:
        int : ノードNO0
    """
    host = getHostname()
    return int(host[-2:])

def getIPAddr( iface = 'wlan0', subnet=False ):
    """IPv4アドレスを返す
    Args:
        iface (str, optional): インタフェース. 初期値 'wlan0'.
        subnet (bool, optional): サブネットを付けるか？ 初期値 False.
    Returns:
        str: IPアドレス文字列
    """
    count = 0
    while True :
        if count > 10 : break
        try :
            ip = ipget.ipget()
            if ip == None : 
                count += 1
                time.sleep(1.0)
                continue
            if subnet :
                return ip.ipaddr( iface )
            return ip.ipaddr(iface).split('/')[0]

        except ValueError as e :
            C.logger.warning(f"getIPAddr  : {e}")
            count += 1
            time.sleep(1.0)
            continue
    return None

def getIPAddrV6( iface = 'wlan0' ):
    """IPv6アドレスを返す
    Args:
        iface (str, optional): インタフェース. 初期値 'wlan0'.
    Returns:
        str: IPアドレス文字列
    """
    ip6 = ipget.ipget()
    return ip6.ipaddr6( iface )

def getMACAdr( iface='wlan0' ) :
    """MACアドレスを返す
    Args:
        iface (str, optional): インタフェース. 初期値 'wlan0'.
    Returns:
        str: MACアドレス文字列
    """
    mac = ipget.ipget()
    return mac.mac( iface )

def getTypeIP(IP):
    """指定したIPv4のアドレスタイプを返す
    Args:
        IP (str): IPアドレス文字列
    Returns:
        str: None:なし, InPriv:InPrivate,Private:プライベート,Global:グローバル
    """
    ''' check IP Type '''
    if IP == ""  : return "None"
    elif IP.startswith('0.0.0.0') : return "None"
    elif IP.startswith('169.254') : return "InPriv"
    elif IP.startswith('192.168') or IP.startswith('172.16') or IP.startswith('10.') : return "Private"
    return "Global"

def resetDHCP():
    """DCHPをリセットして再割り当て """
    subprocess.check_output(['/sbin/dhclient','-r'], shell=True)
    time.sleep(5)
    subprocess.check_output(['/sbin/dhclient'], shell=True)
    time.sleep(1)
    C.logger.warning(f"resetDHCP done  IP = {getIPAddr()}")

def getDefaultRoute():
    """デフォルトルータアドレスを返す
    Returns:
         str: デフォルトルータのIP
    """
    cmd = "/sbin/route | /bin/grep default | /usr/bin/awk '{print $2}'"
    routeIP = subprocess.check_output(cmd, shell = True ).decode()
    if routeIP == "0.0.0.0" or routeIP == "" : return None
    return routeIP.strip()

def IsAlive(IPAddr):
    """指定したIPのPin応答があるか？
    Args:
        IPAddr (str): IPアドレス文字列
    Returns:
        bool: 
    """
    #cmd = f"/bin/ping -c 3 {IPAddr} "
    ret = subprocess.run(['/bin/ping','-c','3',IPAddr],stdout=subprocess.DEVNULL)
    #ret = subprocess.run(f"[{cmd):")
    #print(ret)
    return True if( ret.returncode == 0 ) else False

def getSSID():
    """wlan0が接続しているSSIDを返す
    Returns:
        str: SSID文字列
    """
    try:
        cmd = "/sbin/iwgetid -r"
        SSID = subprocess.check_output(cmd, shell = True ).decode()
        return SSID.strip()

    except subprocess.CalledProcessError as e :
        C.logger.warning(f"getSSID() Subprecess ERROR : {e}")
        return ""
    
    except Exception as e:
        C.logger.error(f"getSSID() : Exeption:{e}")
        return ""

def getMachine_Temp():
    """Raspberry PiのCPU温度を返す

    Returns:
        float: CPU温度
    """
    temp =  subprocess.run("vcgencmd measure_temp", shell=True, encoding='utf-8', stdout=subprocess.PIPE).stdout.split('=')
    temp = temp[1].split("'")
    C.logger.debug("Machine Temp:{}C".format(temp[0]))
    return float(temp[0])

def getMachine_Clock():
    """CPUのクロック数を返す

    Returns:
        float: クロック数
    """
    freq = subprocess.run("vcgencmd measure_clock arm", shell=True, encoding='utf-8', stdout=subprocess.PIPE).stdout.split('=')
    freq = int(freq[1].replace('\n', '')) / 1000000000
    C.logger.debug("Machine Clock:{}GHz".format(freq))
    return freq

def getMachine_Volt():
    """CPUの電圧を返す

    Returns:
        float: CPU電圧
    """
    volt = subprocess.run("vcgencmd measure_volts", shell=True, encoding='utf-8', stdout=subprocess.PIPE).stdout.split('=')
    volt = volt[1].replace('\n', '')
    volt = float(volt.replace('V',''))
    C.logger.debug("Machine Volt:{}V".format(volt))
    return volt

def getSerial():
    """Raspberry Piのシリアルナンバーを返す

    Returns:
        str: シリアルナンバー
    """
    cpuserial = "0000000000000000"
    try:
        with open('/proc/cpuinfo','r') as f :
            for line in f:
                if line[0:6]=='Serial':
                    cpuserial = line[10:26]
            return cpuserial
    except Exception as e:
        C.logger.warning(f"getSerial : Exception {e}")
        return None

def getDiskSpace() :
    """SDカードの容量を返す

    Returns:
        str: 容量/全容量の文字列
    """
    cmd = "/bin/df -h | /usr/bin/awk '$NF==\"/\"{printf \"disk %d/%dGB %s\", $3,$2,$5}'"
    Disk = subprocess.check_output(cmd, shell = True ).decode()
    return Disk

def getCPU() :
    """CPUの利用率
    Returns:
        float: 使用率
    """
    return psutil.cpu_percent(interval=0.1)   

def getBTdeviceList() :
    """取得できるBluetoothのインタフェースリストを返す
    """
    interfaces = []
    try:
        # hciconfigコマンドを実行してBluetoothインターフェースの情報を取得
        result = subprocess.run(['hciconfig'], capture_output=True, text=True, check=True)
        output_lines = result.stdout.splitlines()

        # 出力結果からインターフェース名を抽出
        for line in output_lines:
            if "hci" in line :
                name = line.split(":")[0].strip()
                bus = line.split(":")[3].strip()
                id = int(name.replace('hci',''))
                interfaces.append({'id':id,'name':name,'bus':bus})
    except FileNotFoundError:
        C.logger.error("Not Fine hciconfig Command ")
        return None
    except subprocess.CalledProcessError as e:
        C.logger.error(f"hciconfig Error Found : {e}")

    return interfaces

def getBTdeviceID() :
    """ 利用するBluetoothのInterfaceIDを返す"""
    BTlist = getBTdeviceList()
    for bt in BTlist :
        if bt['bus'] == 'USB' :
            C.logger.debug(f"Blutooh is USB {bt['name']}")
            return bt['id']
    return 0


if __name__ == '__main__':
    import sys
    args = sys.argv
    if len(args) != 1 and args[1].upper() == 'CLEAR_WAKEUP' :
        print("Disable Wakeup")
        setWakeUpTime( False )
        sys.exit(1)

    if len(args) != 1 and args[1].upper() == 'SET_WAKEUP' :
        print("Enable Wakeup evary 7:0:0")
        setWakeUpTime( True,7,0,0 )
        sys.exit(1)

    print("libMachine.py TEST")

#    print(f"PiSugar3 Wakeup Time:")
#    getWakeUpTime()
#    setWakeUpTime( True, 0,9,9 )
#    getWakeUpTime()
#    setWakeUpTime( True, 7,59,59 )
#    getWakeUpTime()
#    setWakeUpTime( True, 10,30,30 )
#    getWakeUpTime()
#    setWakeUpTime( False )
#    getWakeUpTime()
#    setWakeUpTime( True, 7,0,0 )
#    getWakeUpTime()
#    sys.exit(1)

    MyHOST = getHostname()
    print(f"HOST is {MyHOST}") 
    print(f"NODE No is {getNodeNo()}")

    MyIP = getIPAddr()
    MyIPv6 = getIPAddrV6()
    print(f"MyIP is {MyIP} ({MyIPv6})") 
    print(f"IP Type is {getTypeIP(MyIP)}")
    print(f"SSID is {getSSID()}")

    IP = getDefaultRoute()
    ret = IsAlive(IP)
    print(f"default router {IP} is {ret}")

    IP = "www.google.com"
    ret = IsAlive(IP)
    print(f"{IP} is {ret}")

    print( "Machine Information")
    print(f"Temp   : {getMachine_Temp()}")
    print(f"Clock  : {getMachine_Clock()}")
    print(f"Volt   : {getMachine_Volt()}")
    print(f"Serial : {getSerial()}")
    print(f"CPU%   : {getCPU()}")

    print(f"PiSugar: {_existI2CDevice(I2C_PiSugar)}")
    print(f"PuSugar3 Power Connect? : {isChargePiSuger3()}")
    print(f"PiSugar3 Battery Level : {getBatteryPiSugar3()}")
    print(f"PiSugar3 Voltage Level : {getVoltagePiSugar3()}")
    print(f"PiSugar3 Wakeup Time   : {getWakeUpTime()}")
    
    print(f"IsRoot : {isRootUser()}")
    print(f"getBTdeviceList : {getBTdeviceList()}")
    print(f"getBTdeviceID : {getBTdeviceID()}")

    print("libMachine debug done.")
    
