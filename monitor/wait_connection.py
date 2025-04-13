#!/usr/bin/python3
import ipget
import sys
import time

def getIPAddr( iface = 'wlan0', subnet=False ):
    """IPv4アドレスを返す
    Args:
        iface (str, optional): インタフェース. 初期値 'wlan0'.
        subnet (bool, optional): サブネットを付けるか？. 初期値 False.
    Returns:
        str: IPアドレス文字列
    """
    count = 0
    while True :
        if count > 60 : break
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
            print(f"getIPAddr : {e} count:{count}")
            count += 1
            time.sleep(1.0)
            continue

    return None

if __name__ == '__main__':
    ret = getIPAddr()
    if ret != None :
        print("done.")
        sys.exit(0)
    print("toumeout")
    sys.exit(1)
