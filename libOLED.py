#!/usr/bin/python3
"""
Raspberry Pi SSD-1306 OLED 画面表示ライブラリ
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SEMI-IT Agriculture Support TOOLs V3
バージョン情報 -------------------------
Ver. 1.0.0 2023/03/21
Ver. 2.0.1 2025/01/20 CPU表示を時刻と同時に自動表示する
Auther F.Takahashi

memo：128x64 モニタ 8ドットサイズ→ 16文字×8行
"""

import config as C
import libMachineInfo as M
import libSQLite as S
import sys
import time
import threading
import signal
# Adafruit SSD1306 Library
import Adafruit_SSD1306
from PIL import Image, ImageDraw, ImageFont

## ---- OLEDひょじせってい
OLED_ROTATE=True    # 180度回転させて表示の場合 True
TOP_MARGINE = 1     # 上部からマージンドット

# set adaftuit Library LOG LEVEL
import logging
l = logging.getLogger()
l.setLevel(logging.INFO)

class OLED:
    ## -- SSD1306 data
    _disp = None
    _image = None
    _draw = None
    _width = 0
    _height = 0
    _size = 16
    font = None
    fontS = None
    _lock = None

    def __init__(self, sens = 1):
        try:
            self._disp = Adafruit_SSD1306.SSD1306_128_64(rst=None, i2c_address=0x3c)
        except Exception as e:
            C.loggerOLED.warning(f"Error SSD1306 init : {e}")
            self._disp = None
            return 

        self._disp.begin()
        self._disp.display()
        self._width = self._disp.width
        self._height = self._disp.height
        self._image = Image.new('1', (self._width, self._height))
        self._draw = ImageDraw.Draw(self._image)
        self._draw.rectangle((0,0,self._width,self._height), outline=0, fill=0)

        # Load default font.
        #self.fontS = imageFont.load_default()
        #self.fontS = imageFont.truetype("Minecraft.ttf",11)
        #self.fontS = imageFont.truetype("Minecraftia-Regular.ttf",10)
        self.fontS = ImageFont.truetype("./font/DotGothic16-Regular.ttf",12)
        self.font = ImageFont.truetype("./font/fonts-japanese-gothic.ttf", 16)

        # mutex
        self._lock = threading.Lock()
        
        # signal term
        signal.signal(signal.SIGTERM, self._intr_term)
        signal.signal(signal.SIGHUP, self._intr_term)
        signal.signal(signal.SIGUSR1, self._intr_user1)
        

    def clear(self):
        ''' Clear _display '''
        self._draw.rectangle((0,0,self._width,self._height), outline=0, fill=0)
        self._disp.clear()
        self._disp.display()

    def _text(self,x, y, mess , ANSI = False ):
        ''' x,yにテキストを表示 '''
        if ANSI == True :
            self._draw.text((x,y), mess, font=self.fontS, fill=255)
        else:
            self._draw.text((x,y), mess, font=self.font, fill=255)
        self._disp.image(self._image)
        self._disp.display()

    def showPI(self):
        """Raspberry Piの情報を表示  """
        C.loggerOLED.debug('showPI')

        NODE = M.getNodeNo()
        IP = M.getIPAddr()
        HOST = M.getHostname()
        NET = M.getTypeIP(IP)
        #Temp = M.getMachine_Temp()
        SSID = M.getSSID()
        RSSI = S.getNodeRSSI(NODE)
        #DISK = M.getDiskSpace()
     
        ## --- _display
        y = [0,16,32,48]
        self._draw.rectangle((0, y[1],self._width,self._height), outline=0, fill=0)

        ## 2nd Line
        self._draw.text((0,y[1]), f"{NODE} {IP}",font=self.fontS, fill=255)

        ## 3rd Line
        self._draw.text((0,y[2]), f"{SSID}",font=self.fontS, fill=255)

        ## 4th Line- BATT        
        batt = M.getBatteryPiSugar3()
        if batt != -1 : 
            self._draw.text((0,y[3]),f"R:{RSSI} B:{batt:3d}%", font=self.font, fill=255)
        
        self._disp.image(self._image)
        self._disp.display()

    def showSTARTUP(self, mess=[]) :
        """スタートアップメッセージ表示
        Args:
            mess (str): 表示メッセージ
        """
        y = [0,16,32,48]
        self._draw.rectangle(( 0, 0,self._width,self._height), outline=0, fill=0)
        self._draw.text((0,  y[0]), f"SAST STARTUP .... ",font=self.font, fill=255)
        for i in range( 0, len(mess) ) :
            self._draw.text((0, y[i+1]), mess[i], font=self.font, fill=255)
        self._disp.image(self._image)
        self._disp.display()


    def viewGATEWAY(self, IPAddr:str, rssi:list, update=False) -> None: 
        """ゲートウェイの情報を表示
        Args:
            IPAddr (str): IPアドレス文字列
            rssi (list): 各ノードのRSSI（リスト）
        """
        self._lock.acquire() # 排他制御開始
        i = TOP_MARGINE
        y = [0,16,32,48]
        l=len(IPAddr)
        #self._draw.rectangle(( 0, 0,self._width-1,self._height-1), outline=1, fill=0)  枠線
        if not update :
            self._draw.rectangle(( 0, 0,self._width,self._height), outline=0, fill=0)
            self._draw.text((0, y[0]+i), f"SAST", font=self.font, fill=255)
        else :
            self._draw.rectangle(( 0, y[1],l*8+1,y[2]), outline=0, fill=0)  # --- IPアドレスの幅だけ塗りつぶし 2025/01/22
            self._draw.rectangle(( 0, y[2],self._width,self._height), outline=0, fill=0)
        ## -- IP
        self._draw.text((0, y[1]+i), f"{IPAddr}", font=self.fontS, fill=255)
        ## - RSSI
        rs_xy=[(0,y[2]),(0,y[3]),(7*6,y[2]),(7*6,y[3]),(14*6,y[2]),(14*6,y[3])]
        for i in range(0, len(rssi) ) : 
            self._draw.text(rs_xy[i], f"{i+1}:{rssi[i]:4d}", font=self.fontS, fill=255)

        ''' GATEWAYはバッテリ無しなので削除
        ## - BATT        
        batt = M.getBatteryPiSugar3()
        if batt != -1 : 
            self._draw.rectangle((128-3*8,y[3], self._width,self._height), outline=0, fill=0)
            self._draw.text((128-3*8,y[3]),f"{batt:3d}", font=self.font, fill=255)
        '''

        ### -- VIEW
        self._disp.image(self._image)
        self._disp.display()
        self._lock.release() # 排他制御解除


    def viewNODE(self, node:int, sens:tuple, stat:int, ssid:str, update=False) -> None:
        """ノードの情報を表示
        Args:
            node (int): ノード番号
            sens (tuple): センサーの稼働状況
            stat (int): 本体のステータス
        """
        self._lock.acquire() # 排他制御開始
        i = TOP_MARGINE
        y = [0,16,32,48] 
        templ = M.getMachine_Temp()
        #self._draw.rectangle(( 0, 0,self._width-1,self._height-1), outline=1, fill=0)  枠線
        if not update :
            self._draw.rectangle(( 0, 0,self._width,self._height), outline=0, fill=0)
            self._draw.text((0, y[0]+i), f"N{node:02d}", font=self.font, fill=255)
        else :
            self._draw.rectangle(( 0, y[1],10*8+1,y[2]), outline=0, fill=0)  # --- 機器温度の部分のみ塗りつぶし 2025/01/22
            self._draw.rectangle(( 0, y[2],self._width,self._height), outline=0, fill=0)

        ## -- TEMP,SENS,STATUS
        self._draw.text((0, y[1]+i), f"TEMP:{templ:3.0f}C", font=self.font, fill=255)
        self._draw.text((0, y[2]+i), f"SENS:{sens:2}", font=self.font, fill=255)
        self._draw.text((0, y[3]+i), f" {C.NODE_STAT(stat).name}", font=self.font, fill=255)

        ## -- SSID
        if ssid != "" : self._draw.text((8*8, y[2]+i), f"{ssid}", font=self.fontS, fill=255)

        ## - BATT        
        batt = M.getBatteryPiSugar3()
        if batt != -1 : 
            self._draw.rectangle((128-3*8,y[3], self._width,self._height), outline=0, fill=0)
            bt = "@" if M.isChargePiSuger3() else  " " # -- 充電中は＠表示
            self._draw.text((128-4*8,y[3]),f"{bt}{batt:3d}", font=self.font, fill=255)

        ### -- VIEW
        self._disp.image(self._image)
        self._disp.display()
        self._lock.release() # 排他制御解除
    
    def _makeDate(self, margine , colon) :
        """ 時計表示＆CPU利用率表示"""
        tm = C.getTimeSTR(short=True)
        cpu = M.getCPU()
        if colon != 0 : tm = tm.replace(':', ' ')
        self._draw.rectangle(( 40, margine,self._width,15), outline=0, fill=0)
        self._draw.text((40, margine), tm, font=self.font, fill=255)
        if colon == 0 :
            self._draw.rectangle(( 96, margine+16,self._width,32), outline=0, fill=0)
            self._draw.text((96, margine+16), f"{cpu:3.0f}%", font=self.font, fill=255)

    def viewDate(self) :
        """時刻表示（0.5秒毎にコロンを点滅） Thread呼び出し """
        i=1
        while True :
            self._lock.acquire() # 排他制御開始
            i = (i+1) % 2
            self._makeDate( TOP_MARGINE, i)
            self._disp.image(self._image)
            self._disp.display()
            self._lock.release() # 排他制御解除
            time.sleep(0.5) # 0.5秒


    def _textFill(self) :
        """テスト（画面にテキスト表示）"""
        i = TOP_MARGINE
        y = [0,16,32,48] 
        self._draw.rectangle(( 0, 0,self._width,self._height), outline=0, fill=0)
        #self._draw.rectangle(( 0, 0,self._width-1,self._height-1), outline=1, fill=0)  枠線
        self._draw.text((0, y[0]+i), f"1234567890123456", font=self.font, fill=255)
        self._draw.text((0, y[1]+i), f"1234567890123456", font=self.font, fill=255)
        self._draw.text((0, y[2]+i), f"1234567890123456", font=self.font, fill=255)
        self._draw.text((0, y[3]+i), f"1234567890123456", font=self.font, fill=255)
        self._disp.image(self._image)
        self._disp.display()


    def loopNode(self) :
        """ NODE用 OLEDメインループ  """
        nodeno = M.getNodeNo()
        C.logger.info(f"START OLED for Node{nodeno}")
        allSens = list()
        allSens = S.numSensorsMe()
        ssid = M.getSSID()
        stat = C.NODE_STAT.NONE
        # 初期表示
        self.viewNODE(nodeno, allSens, stat, ssid )
 
        # 時計更新スレッド起動
        thr_date = threading.Thread( target=o.viewDate, name='time', daemon=True )
        thr_date.start()

        # 情報更新
        while True:
            try :
                stat = S.getNodeStatus()
            except ValueError as e :
                C.logger.warning("SQL status Table not init ")
                stat = C.NODE_STAT.NONE
            #C.logger.info(f"NODE STAT = {C.NODE_STAT(stat)}")
            ssid = M.getSSID()
            allSens = S.numSensorsMe()
            self.viewNODE(nodeno, allSens, stat, ssid, update=True)
            time.sleep(10)  # 10秒おきに更新

    def loopGateWay(self) -> None :
        """ GATEWAY用 OLEDメインループ  """
        C.logger.info("START GateWay OLED ")
        rssi = S.getNodeRSSI()
        ip = M.getIPAddr()
        # 初期表示
        o.viewGATEWAY(ip,rssi)

        # 時計スレッド機能
        thr_date = threading.Thread( target=o.viewDate, name='time', daemon=True )
        thr_date.start()

        #情報更新
        while True:
            rssi = S.getNodeRSSI()
            ip = M.getIPAddr()
            o.viewGATEWAY(ip, rssi, update=True)
            time.sleep(10)  # 10秒おきに更新

    def _intr_term(self, num, frame) :
        """ Signal Shutdown """
        C.logger.warning("SIGTERM catch exit...")
        o.clear()
        sys.exit(0)

    def _intr_user1(self, num ,frame ) :
        """ signal SIGUSR1 """
        C.logger.warning("signal SIGUSR1 ... show PI Info")
        o.showPI()
        time.sleep(5)
        return

        

S = S.SQL()
if __name__ == '__main__':
    args = sys.argv
    o = OLED()

    try: 
        if len(args) >= 2 :
            if args[1].upper() == 'INFO' :
                o.showPI()

            elif args[1].upper() == 'CLEAR' :
                o.clear()

            elif args[1].upper() == 'STARTUP' :
                mess = []
                for i in range(2, len(args) ) :
                    mess.append(args[i])
                #C.loggerOLED.info(f">START: {mess}")
                o.showSTARTUP(mess)
                sys.exit()

            elif args[1].upper() == 'TIME' :
                o.showPI()
                thr_date = threading.Thread( target=o.viewDate, name='time' )
                thr_date.start()
                thr_date.join()
                while True:
                    time.sleep(5)

            elif args[1].upper() == 'TEXTFILL' :
                o.textFill()

            elif args[1].upper() == 'GATE' :
                print(f"libOLED.py -- START GATE")
                o.clear()
                o.loopGateWay()

            elif args[1].upper() == 'NODE' :
                print(f"libOLED.py -- START NODE({M.getNodeNo():02})")
                o.clear()
                o.loopNode()

        else : # テストじゃない
            while True :
                node = M.getNodeNo()

                if node == 0 :
                    print(f"libOLED.py -- START GATE")
                    o.clear()
                    o.loopGateWay()

                else :
                    print(f"libOLED.py -- START NODE({node:02})")
                    o.clear()
                    o.loopNode()
            
        '''
        TODO
        プログラムからの表示内容更新は、mqueue（PISIX IPC）を使って実装
        GATEWAYは無し
        NODEはステータス更新（起動、Bacon待機、送信開始、通常、）
        https://qiita.com/y-amadatsu/items/bf3242d19c8bc5ffe0a7
        20230207 結局 SQLにステータスを入れて連携した。
        '''
    
    except KeyboardInterrupt :
        C.logger.warning("OLED Terminate.")
        o.clear()
        sys.exit(9)
