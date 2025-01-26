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

def _existI2Cevice(address):
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

def getBatteryPiSugar3() :
    """ PiSugar3 のI2Cレジスタ(0x57）からバッテリー容量を返す
        I2Cが無い場合やアクセス不可の場合は-1を返す
    """
    level = -1
    try:
        bus = smbus2.SMBus(I2C_BUS)
        level= bus.read_byte_data(I2C_PiSugar_REG, 0x2a)

    except Exception as e:
        C.logger.warning(f"No DATA from {I2C_PiSugar_REG} addr.")
    
    finally:
        bus.close()
        return level

'''
def getBatteryPiSugar() :
    """ PiDugar3のパッテリー容量を検出"""
    if _existI2Cevice(I2C_PiSugar) : 
        import pisugar as PS
        try :
            conn, event_conn = PS.connect_tcp('raspberrypi.local')
            s = PS.PiSugarServer(conn, event_conn)
            return s.get_battery_level()
        except Exception as e :
            return -1
    else :
        return -1
'''

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
        subnet (bool, optional): サブネットを付けるか？. 初期値 False.

    Returns:
        str: IPアドレス文字列
    """
    ip = ipget.ipget()
    if ip == '' :
        return '0.0.0.0'
    if subnet :
        return ip.ipaddr( iface )
    return ip.ipaddr(iface).split('/')[0]

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
    """DCHPをリセットして再割り当て

    """
    subprocess.check_output(['/sbin/dhclient','-r'], shell=True)
    time.sleep(5)
    subprocess.check_output(['/sbin/dhclient'], shell=True)
    time.sleep(1)
    print("IP = {getIPAddr()}")

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
    cmd = f"/bin/ping -c 3 {IPAddr} "
    ret = subprocess.run(['/bin/ping','-c','2',IPAddr],stdout=subprocess.DEVNULL)
    #ret = subprocess.run(f"[{cmd):")
    #print(ret)
    if( ret.returncode == 0 ): return True
    return False

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

if __name__ == '__main__':
    print("libMachine.py TEST")
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

    print(f"PiSugar: {_existI2Cevice(I2C_PiSugar)}")
    print(f"PiSugar3 Battery Level : {getBatteryPiSugar3()}")
    

    print(f"IsRoot : {isRootUser()}")
