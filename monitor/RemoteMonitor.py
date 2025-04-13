#!/usr/bin/python3
import AbShutter
import time
import os
import sys

SHUTTER="AB Shutter3"
USER='sast'
THRESHOLD = 10
K1_count = 0
K2_count = 0
AB = None

def cb_shutter( dev, code, value) :
    """AbShutter CallBack func """

    global K1_count, K2_count, AB

    if code == 115 and value == 1 and K1_count == 0: # iPhoneShutter PUSH & K1=0
        AB.logger.info("iPhone PUSH")
        K1_count = 1 
        return

    elif code == 115 and value == 0 and K1_count < THRESHOLD : 
        AB.logger.info("iPhone short PUSH")
        os.system(f'export XAUTHORITY=/home/{USER}/.Xauthority;export DISPLAY=:0;xdotool key ctrl+R')
        K1_count = 0
        return

    elif code == 115 and value == 1 and K1_count != 0 : # 
        AB.logger.info("iPhone Reset")
        K1_count = 0
        return

    elif code == 115 and value == 2 and K1_count != 0 : # iPhoneHutter HOLD && K1!=0
        AB.logger.info(f"iPhone HOLD - {K1_count}")
        K1_count += 1
        if K1_count >= THRESHOLD : 
            AB.logger.warning("Execute Shutdown ....")
            os.system('sudo shutdown -h now')

    elif code == 28 and value == 1 :
        ## Chomium-browser to CTRL + TAB 
        AB.logger.info("Android PUSH ")
        os.system(f'export XAUTHORITY=/home/{USER}/.Xauthority;export DISPLAY=:0;xdotool key ctrl+Tab')
            
if __name__ == '__main__' :
    
    while True :
        try : 
            AB = AbShutter.AbShutter( name="AB Shutter3", dev=-1, cb_func=cb_shutter ,debug=True)
            break
        except Exception as e :
            print(e)
            time.sleep(10)
            continue
    try :
        AB.logger.info("ABShutter3 Connected.")
        #print("ABShutter3 Connected.")
        AB.start()
        AB.join()
        while True:
            time.sleep(10)

        print("Terminate.")
    
    except KeyboardInterrupt :
        AB = None
        print("RemoteMonitor Terminate.")
        sys.exit(0)
