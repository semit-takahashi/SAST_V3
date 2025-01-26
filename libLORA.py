#!/usr/bin/python3
"""
Private LoRa 通信モジュール
  GatewayとNodeの両対応（送信データのbyte列を共有）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Summary:
---------
Gatewayから送信されたBeaconをNode受信、その後、NodeのNoに応じた遅延タイミングでGatewayにデータを送信。
この手段にて、Node間のデータコリジョンを回避してる。
これらのNoは、ホスト名の下2桁に決定する。
例: hoge00 -> Gateway , hoge01 ->wq Node01, hoge02 -> Node02 
システムにてホスト名を共通化させることで判別可能としている。
なお、システムを近距離で利用する場合は、ADDR_GATEWAY、ADDR_NODEを個別に設定することを推奨する。

SEMI-IT Agriculture Support TOOLs [E220-900T22(JP)] LoRa Library
バージョン情報 -------------------------
Ver. 1.1.0 2023/04/16  F.Takahashi
Ver. 2.0.1 2025/01/18   通信処理を纏め、ACKを返す処理とした。
                        また、データ先頭に送信バイト数を付与して受信側（GATE）で読み込む処理とした
"""
import config as C
import signal
import time
import datetime
import serial
import threading
import struct
import sys
import schedule
import libMachineInfo as M
from enum import IntEnum
from libSQLite import SQL

try:
    import RPi.GPIO as GPIO
except:
    C.logger.warning("GPIO not fond, Start MOCK!")
    import Mock.GPIO as GPIO

### -- Lora ADDR
GATE_ADDR = 0x2310
GATE_CHANNEL = 0
BCAST_ADDR = 0xffff
NODE_CHANNEL = 10
### -- UART Port
PORT = '/dev/ttyS0'
BAUD = 115200
### -- Sensor Data Structure
# LEN(ushort)
L_LEN = '@H'
# NODE(B), CH(B), SEQ(ushort), MAC(6B) ,TIME(L), templ(h), humid(h), batt(h), rssi(h), stat(s)
L_DATA = '@BBH6sLhhhhh' ### -- Beacon Data Structure
# TYPE(B), SEQ(B), TIME(L)
L_BEACON = '@BBL'
### -- Beacon Interval
BEACON_INTERVAL = 60 # Beacon自体の送信間隔（秒）
BEACON_COUNT = 1  # 回送信する(送信間隔は60秒→コード側記載
### --- Sender Interval
DATA_SEND_COUNT = 1         # 1データの送信回数
DATA_SEND_TIME = 0.1        # 送信間隔（秒）
### --- ACK 
class RESCODE(IntEnum):
    """ Response CODE  """
    NONE = 0
    ACK = 1,
    BCAST = 3,
    TIMEOUT = -1,

### GPIO settings
LED_G = 19
LED_R = 13
AUX_PIN = 25
M0_PIN = 5
M1_PIN = 6

### NODE NO (Globals)
NODE_NO = -1

#### Global SQL Instance
S = SQL()

def setupGPIO() :
    """GPIOポート初期化
    """
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(LED_G, GPIO.OUT)
    GPIO.setup(LED_R, GPIO.OUT)
    GPIO.setup(M0_PIN, GPIO.OUT)
    GPIO.setup(M1_PIN, GPIO.OUT)
    GPIO.setup(AUX_PIN, GPIO.IN)

def setMode( mode=0 ) :
    """E220のモード設定

    Args:
        mode (int, optional): モード指定. 初期値 0.
    """
    if mode == 0 :   # M0=low,M1=low
        C.logger.info("E220 setmode=0")
        GPIO.output(M0_PIN, 0)
        GPIO.output(M1_PIN, 0)
    elif mode == 1 : # M0=high,M1=low
        C.logger.info("E220 setmode=1")
        GPIO.output(M0_PIN, 1)
        GPIO.output(M1_PIN, 0)
    elif mode == 2 : # M0=low,M1=high
        C.logger.info("E220 setmode=2")
        GPIO.output(M0_PIN, 0)
        GPIO.output(M1_PIN, 1)
    elif mode == 3 : # M0=high,M1=high
        C.logger.info("E220 setmode=3")
        GPIO.output(M0_PIN, 1)
        GPIO.output(M1_PIN, 1)

def WaitAUX() :
    """E220が可動状態になるまで待機(HIGHで終了) """
    C.logger.info("E220-900T22 Wait AUX PIN...")
    while not GPIO.input( AUX_PIN ) :
        C.logger.debug(">>Not Ready..")
        time.sleep(0.2)
    C.logger.info("E220-900T22 is Ready!!")

def Led( type="RED", sw=True ) :
    """LEDをON/OFFする
    Args:
        type (str, optional): "RED"赤、"GREEN",緑. 初期値"RED".
        sw (bool, optional): True:ON / False:OFF. 初期値 True.
    """
    ''' LED ON/OFF'''
    if type == "RED" :      GPIO.output( LED_R, sw )
    elif type == "GREEN" :  GPIO.output( LED_G, sw )
    else : C.logger.warning(f"LED {type} is Unknown")

light_wait = 0.05
def _Led_ON_OFF( led=LED_R, sec=light_wait ) :
    ''' LED 指定時間ON->OFF'''
    GPIO.output( led, 1 )
    time.sleep( sec )
    GPIO.output( led, 0 )

def _Led_flash_thread( type, times ) :
    off_time = 0.5
    #C.logger.debug(f"LED {type} -> {times}")
    if type == "RED" :
        for i in range( 0, times ) : 
            _Led_ON_OFF( LED_R )
            time.sleep( off_time )
    elif type == "GREEN" :
        for i in range( 0, times ) : 
            _Led_ON_OFF( LED_G )
            time.sleep( off_time )
    else : C.logger.warning(f"LED {type} is Unknown")

def Led_flash( led, times = 3, join=False ) :
    """指定回数LEDを点灯
    指定回数LEDを点滅（スレッド起動で変更動作用）join=Trueで終了待機
    Args:
        led (srt): LEDの指定 GHREEN or RED
        times (int, optional): 点滅回数. 初期値 3.
        join (bool, optional): スレッドを待機するか？. 初期値 False.
    """
    C.logger.debug(f"LED {led}({times})")
    led = threading.Thread( target=_Led_flash_thread, args=( led, times ))
    led.start()
    if join : led.join()


class Lora_GATE :
    """ LoRa Gateway Class
    Summary: 一定間隔でBeaconを送信する（初期値1分）、またNodeからのデータを受信して、SQLに記録する。
    """ 
    _Lora_Fixed_addr = True
    sendDATA = {}
    _ser = None

    def __init__(self) -> None:
        S = SQL()
        C.logger.info(f"START Lora_GATE  {M.getHostname()}")
        #S.initLatest()
        S.initNotify()
        signal.signal(signal.SIGTERM, self._intr_term)
        signal.signal(signal.SIGHUP, self._intr_term)
        self._ser = serial.Serial(PORT, BAUD, timeout=10) 
        self.thr_Reciver = threading.Thread(target=self._reciver, name="Rerciver", daemon=True )
        self.thr_Beacon  = threading.Thread(target=self._beacon_sender , name="Beacon", daemon=True )
        self.thr_Reciver.start()
        self.thr_Beacon.start()

    def __del__(self) -> None:
        C.logger.info("Lora_GATE destruct...")
        self._ser .close()

    def _reciver(self) :
        ''' Thread起動 LoRa Data Reciver '''
        S = SQL() ## Thread 起動なので必須
        prev_time = time.time()
        sequence = 0
        channel = 0
        while True :
            # -- データ受信待機（23バイトで分割されてLISTに）
            datas, node_rssi = self._recv_Data()
            # 一つずつ処理
            for data in datas :
                #node_rssi = int(raw_data[-1]) - 256         #最終バイトは、RSSI
                #data = bytes(raw_data[:len(raw_data)-1])    #残りがデータ

                try : 
                    # 順にデータのデコード
                    (node, ch, seq, mac, time_s, templ, humid, batt, rssi, status ) = data_unpack(data)
                except Exception as e :
                    C.logger.warning(f"Decode Error -- {e}")
                    continue

                Led_flash("GREEN",1)  #LED点灯
                nodeNO = node
                sequence = seq
                channel = ch

                C.logger.info(f"Node:{node}/{ch}[{node_rssi}dBm] SEQ:{seq} MAC:{mac} [{time_s}] {templ} {humid} {batt} {rssi} {status}")

                ## SQLへの投入データ生成
                sdata = {}
                sdata['node'] = node
                sdata['date'] = time_s.strftime("%Y-%m-%d %H:%M:%S")
                sdata['mac'] = mac
                sdata['templ'] = templ
                sdata['humid'] = humid
                sdata['batt'] = batt

                # 送信データがNode本体かSenstorかでRSSIを変える
                if mac.startswith('00:00:00') :
                    #C.logger.debug("DATA is Node")
                    sdata['rssi'] = node_rssi
                else :
                    #C.logger.debug("DATA is Sensor")
                    sdata['rssi'] = rssi
                sdata['status'] = status

                if S.useSensor(node, mac) : 
                    #-- Config登録済のMACのみ登録（ぶら下がっているnodeの場合のみ）
                    S.appendData(sdata)
                
            # データ配列の処理終了で1個ACKを送信
            self._send_ack(node, channel, sequence)



    def _send_ack(self, node, channel, seq, ack='A' ) :
        ''' ACK を返送 '''
        payload = bytearray()
        if self._Lora_Fixed_addr : payload += makeLoraADDR( GATE_ADDR+node, channel)
        data = struct.pack(L_BEACON, ord(ack), seq, int(time.time()) )
        payload += data
        C.logger.debug(f"ACK:{ack} {payload.hex()}")
        while True :
            if self._ser .out_waiting == 0 : break
        #print(f"ack payload ={payload}")
        self._ser .write( bytes(payload) )
        self._ser .flush()
        payload = None


    def _recv_Data(self) -> list:
        '''Revice Lora return Bytes() '''
        C.logger.debug("Waiting DATA Recive ... ")
        payload = bytearray()   # ByteArryじゃないと追記できない
        payload_rssi = bytes()
        header = bytearray()
        datas = list()
        length = 0

        while True:
            # ヘッダーの受信待ち
            #print(f"ser : in_waiting({ self._ser.in_waiting})")
            if self._ser.in_waiting != 0 :
                header = self._ser.read(struct.calcsize(L_LEN))
                if len(header) != struct.calcsize(L_LEN) : 
                    C.logger.error(f"L_LEN decode  header({len(header)} : {header.hex()}) --- skip")
                    continue
                length, = struct.unpack(L_LEN,header)
                C.logger.debug(f"header({length}) : {header}")
                break
            else :
                time.sleep(0.5)
                continue


        while True:
           # 指定長のデータ受信待ち
            if self._ser.in_waiting != 0 :
                payload = self._ser.read(length)
                payload_rssi = self._ser.read(1) # RSSI取得
            else :
                time.sleep(0.2)
                continue

            # データ分解
            s = struct.calcsize(L_DATA)
            rssi = int.from_bytes(payload_rssi,'big') - 256
            datas = [payload[i:i+s] for i in range(0, len(payload), s )]
            #C.logger.debug(f"Recived datas={datas}")
            return datas , rssi 
   
    def _beacon_sender(self) :
        ''' 毎分0秒に Beaconを送信 scheduler利用 '''
        C.logger.info(" START Beacon Sender ... ")

        ## 毎分0秒に_send_beacon()を実行
        schedule.every().minute.at(":00").do(self._send_beacon)

        ## 実行し続ける ループ 
        while True:
            # 次の行で実行まで待つ。
            schedule.run_pending()
            time.sleep(1)

    def _send_beacon(self) :
        ''' Beaconを送信  BEACON_COUNT回 ビーコンを送信'''
        C.logger.info(f" Send Beacon >> {BEACON_COUNT} times")
        Led_flash("RED", 3)
        for i in range( 1 , BEACON_COUNT+1 ) :
            payload = bytearray()
            if self._Lora_Fixed_addr : 
                payload += makeLoraADDR( BCAST_ADDR, NODE_CHANNEL)
            data = struct.pack(L_BEACON, ord('B'), i, int(time.time()) )
            payload += data
            C.logger.debug(f" Beacon :{i} {payload.hex()}")
            while True :
                if self._ser .out_waiting == 0 : break
            self._ser .write( bytes(payload) )
            self._ser .flush()
            payload = None
        C.logger.debug(" Beacon Sended.")

    def _intr_term(self, num, frame) :
        C.logger.warning(f"[GATE] SIGTERM catch exit...")
        sys.exit(1)


class Lora_NODE :
    """LoRa Node Class
    Summary: 初期化後Beaconをスレッド待機。Beacon受信後、指定されているNodeの数に合わせて待機後、SQLからデータを読み取って送信する。
    送信するmethodはScheduleにて一定間隔で起動される（初期値1分）
    20250119追記 S=SQL()はスレッドローカルで生成必須
    """
    _ser = None
    _Lora_Fixed_addr = True
    _BeaconReviced = None
    _NodeNo = 0
    _thr_Beacon = None
    _thr_Sender = None
    _seq : int = 0 
    _TimeSkew : bool = False

    def getSeq(self) -> int :
        ''' シーケンス番号の生成 byteでループ'''
        self._seq = ( self._seq + 1 ) % 255
        return self._seq

    def __del__(self) -> None:
        C.logger.info("Lora_NODE destruct...")
        self._ser.close()
        
    def __init__(self, nodeNO ) -> None:
        S = SQL()
        #S.initLatest()
        S.changeNodeStatus(C.NODE_STAT.START.value)
        self._ser = serial.Serial(PORT, BAUD, timeout=60)
        self._thr_Beacon = threading.Thread(target=self._beaconReciver, name="BeaconReciver", daemon=True )
        self._thr_Sender = threading.Thread(target=self._sender, name="Sender", daemon=True )
        self._thr_Beacon.start()
        self._NodeNo = nodeNO
        signal.signal(signal.SIGTERM, self._intr_term)
        signal.signal(signal.SIGHUP, self._intr_term)
        C.logger.info(f"START LoRa Node - NO:{self._NodeNo}")

    def _sender(self) :
        ''' Thread起動 LoRa Data Sender '''
        C.logger.info("Start Sender thread.")
        base_time = time.time()
        next_time = 0
        while True :
            t = threading.Thread(target=self._send_data, name="send_data")
            t.start()
            t.join()
            next_time = ((base_time - time.time()) % BEACON_INTERVAL) or BEACON_INTERVAL
            C.logger.debug(f"done ... sleep({next_time})")
            time.sleep(next_time)
    

    def _send_data(self) :
        ''' Thread起動 LoRa Data Sender '''
        C.logger.debug("[_send_data] Send Data ... START")
        S = SQL() ### Thread用に必須

        setMode(0)
        WaitAUX()
        C.logger.info("Lora Module Wakeup... done")

        sendDATA = list()

        ## NODE本体の情報（MACをNODEにする）
        node_mac = '00:00:00:00:00:0'+str(self._NodeNo)
        templ = M.getMachine_Temp()
        seq = self.getSeq()  
        batt = M.getBatteryPiSugar3()
        sendDATA.append( data_pack( self._NodeNo, seq, node_mac, int(time.time()), templ, 0.0, batt, 0, 0 ) )

        ## センサーの情報をSQLから取得
        sensorDATA = S.getLatestDATA(NODE_NO, delete=True)
        C.logger.debug(f"Sensor is ({len(sensorDATA)})")
        for s in sensorDATA :
            s['status'] = S.getStatus( s['mac'])
            C.logger.debug(f"SENSOR : {s}")
            sendDATA.append( data_pack( self._NodeNo, seq, s['mac'], C.toTimespan(s['date']), s['templ'], s['humid'], s['batt'], s['rssi'], s['status'] ))
        
        #C.logger.debug(f"sendDATA : {sendDATA}")
        ## 1つのデータにパッキング
        stream = makeSendDataStream( GATE_ADDR, GATE_CHANNEL, sendDATA)
        C.logger.debug(f" SEND({len(stream)})> {stream.hex()}")

        ## データの送信
        Led_flash( "GREEN", len(sendDATA) )

        ## get SEQ No
        C.logger.info(f"Send SEQ = {seq}")

        while True :
            if self._ser.out_waiting == 0 : break
        self._ser.write( bytes(stream) )
        self._ser.flush()

        C.logger.debug("Data Sended.")

        ## ACK待ち 
        time.sleep(1) # 応答まで1秒待ち
        ret, timeL = self._wait_ack( seq )
        if ret == RESCODE.ACK :
            C.logger.info("recv: ACK ")
        else :
            C.logger.error(f"recv: {ret}")

        ## LoRa Module DeepSleep
        setMode(3)
        WaitAUX()
        C.logger.info("Lora Module sleep zzzz....")

    def _wait_ack(self, sequence, TIME_OUT = 1 ) :
        ''' ホストから戻りコードを受信する'''
        C.logger.debug(f"wait_ack... seq={sequence}")
        time.sleep(1.0) # 0.5秒
        payload = bytearray()
        if self._ser.in_waiting != 0 : payload = self._ser.read_all()
        elif self._ser.in_waiting == 0 and len(payload) != 0:
            ## バッファ無くてpayloadが何もないのでちょっと待って再呼び出し
            time.sleep(0.10)
            payload = self._ser.read_all()

        if len(payload) == 0 :
            ## それでも応答無しはNACK
            return RESCODE.NONE, None

        #print(f"payload({len(payload)}) {payload}")

        # データの分割
        s = struct.calcsize(L_BEACON)+1
        C.logger.info(f"Recv< {payload.hex()}({len(payload)})")
        datas = [payload[i:i+s] for i in range(0, len(payload), s )]
        Led("GREEN", sw=True )  #LED 緑点灯

        mutch = False
        ack = False
        for raw_data in datas :
            if len(raw_data) -1 != struct.calcsize(L_BEACON) :
                ## バイト列の長さが違うのデコード出来ない エラー
                C.logger.error(f"Not decode ({len(raw_data)}) : {raw_data} ")
                continue
            rssi = int(raw_data[-1]) - 256         #最終バイトは、RSSI
            data = bytes(raw_data[:len(raw_data)-1])    #残りがデータ
            C.logger.debug(f"data< {data.hex()}({len(data)}) [{rssi}dBm]")
            type, seq, timeL = struct.unpack(L_BEACON, data)
            if chr(type) == 'A' :
                ack = True
                C.logger.debug(f"-Recv: ACK SEQ>{seq}")
                if sequence == seq : 
                    # ACK で seqが一緒なので成功
                    Led("GREEN", sw=False)  #LED消灯
                    return RESCODE.ACK, timeL
                else :
                    C.logger.error(f"-No Much SEQ <> {seq}")
                    Led("GREEN", sw=False)  #LED消灯
                    Led_flash("RED",2)  #LED点灯
                    # SEQがマッチしない場合は他のバッファの可能性がある
                    continue 
                
            elif chr(type) == 'B' :
                C.logger.debug("-Recv: Beacon ... SKIP")
                #Beaconは読み飛ばし
                continue

            else : 
                ## デコードできない場合
                C.logger.error(f"-Recv: Ignore typeCode={type}")
                Led("GREEN", sw=False)  #LED消灯
                Led_flash("RED",3)  #LED点灯
                return RESCODE.TIMEOUT, None

        # バッファを全部確認したので返答
        if ack == True : 
            #ACKはあるけど、SEQが返ってないのでNONEを返す
            Led("GREEN", sw=False)  #LED消灯
            Led_flash("RED",1)  #LED点灯
            return RESCODE.NONE, timeL

        C.logger.error(f"-Recv: Ignore DATA")
        Led("GREEN", sw=False)  #LED消灯
        Led_flash("RED",3)  #LED点灯
        return RESCODE.NONE, None

    def _beaconReciver(self) :
        ''' Beaconを受信する SEQ=1受信すると送信間隔を設定して終了 '''
        C.logger.info("Start Beacon Reciver.")

        setMode(0)
        WaitAUX()

        S = SQL() ## thread起動で必須
        S.changeNodeStatus(C.NODE_STAT.WAIT_BEACON.value)
        Led( "RED", True)
        while True :
            type, seq, recv_datetime, rssi = self._recv_beacon()
            C.logger.info(f"--Beacon({type}) < DATE:{recv_datetime}  RSSI:{rssi}")
            if self._BeaconReviced == None and seq == 1 :
                # --- Node NO x 10 秒待機
                S.changeNodeStatus(C.NODE_STAT.WAIT_SEND.value)
                wait_sec = M.getNodeNo() * 10
                self._BeaconReviced = time.time()
                C.logger.info(f"Waiting {wait_sec} sec ... ")
                Led( "RED", False)
                Led( "GREEN" , True )
                time.sleep( wait_sec ) 
                self._thr_Sender.start()
                S.changeNodeStatus(C.NODE_STAT.GOOD.value)
                Led( "GREEN" , False )
                break

        setMode(3)
        WaitAUX()
        C.logger.info("Terminate Beacon Reciver.")
    
    def _recv_beacon(self) :
        ''' Revice Becon '''
        C.logger.debug("Wait Beacon Recive ...")
        payload = bytearray()   # ByteArryじゃないと追記できない
        while True:
            if self._ser .in_waiting != 0:
                payload += self._ser.read_all()

            elif self._ser.in_waiting == 0 and len(payload) != 0:
                time.sleep(0.010) # さらに待って追加受信
                payload += self._ser.read_all()

            if len(payload) -1 == struct.calcsize(L_BEACON) :
                rssi = int(payload[-1]) - 256
                beacon = bytes(payload[:len(payload)-1])
                code, seq, recv_date = struct.unpack( L_BEACON, beacon )
                recv_datetime = datetime.datetime.fromtimestamp(recv_date)
                diffTime = datetime.datetime.now() - recv_datetime
                C.logger.debug(f"Recive({chr(code)}) date:{recv_datetime} diff:{diffTime.seconds} rssi:{rssi}")
                if datetime.timedelta(seconds=10) < diffTime :
                    C.logger.error("SystemTime difference with the GATEWAY is more than 10 seconds!!")
                    self._TimeSkew = True
                return ( chr(code), seq, recv_datetime, rssi ) 

            time.sleep(1.0)

    def _intr_term(self, num, frame) :
        C.logger.warning("[NODE] SIGTERM catch exit...")
        sys.exit(0)


''' Libraries '''
def build_datas( payload, struct_str, is_rssi=True, is_fidxed=True) :
    if is_fidxed :
        s = struct.calcsize(struct_str)+3
    else :
        s = struct.calcsize(struct_str)+3
    
    #print(f"payload({len(payload)}) = {payload.hex()}")

    if is_rssi :
        datas = [payload[i:i+s] for i in range(0, len(payload), s+1 )]
    else :
        datas = [payload[i:i+s] for i in range(0, len(payload), s )]

    for data in datas :
        print(f"data : {data}")
    



def data_pack( node, seq, mac, times:int, templ, humid, batt, rssi, status ) :
    ''' Encode DATA ByteString  Throw Exception '''
    templ_s = int(templ * 10)
    humid_s = int(humid * 10)
    batt_s = int(batt * 10)
    mac_s = MAC_encode(mac)
    data = struct.pack( L_DATA , node, NODE_CHANNEL, seq, mac_s, times, templ_s, humid_s, batt_s, rssi, status)
    #print(f"{node} {NODE_CHANNEL} {seq} {mac} {times} {templ_s} {humid_s} {batt_s} {rssi} {status} -> \n{data} len={len(data)}")
    return data

def data_unpack( data:bytes ) :
    ''' Decode DATA ByteString  Throw Exception '''
    if len(data) != struct.calcsize(L_DATA) :
        C.logger.error(f"DateSize Missmatch require({struct.calcsize(L_DATA)} <- {len(data)} )")
    node, node_ch, seq,mac_s, times, templ_s,humid_s,batt_s,rssi,stat = struct.unpack( L_DATA, data )
    mac = MAC_decode(mac_s)  # Throw Exception
    time_s = datetime.datetime.fromtimestamp(times)
    #Add Check DATA 2023/04/16
    if not (1 <= node <=99) : raise Exception(f"NODE Error {node}")
    if not (0 <= seq  <=65535) : raise Exception(f"SEQ Error {seq}" )
    if not ( time_s.date() == datetime.date.today() ) :raise Exception(f"DATE Error {time_ｓ}")
    #if not ( -10 <= templ_s <= 80 ) : raise Exception("Templ Error")    
    #if not ( 0 <= humid_s <= 100 ) : raise Exception("Humid Error") 
    if not ( -1 <= stat <= 10 ) : raise Exception(f"STATUS Error {stat}") 
    return node, node_ch, seq, mac, time_s, templ_s/10, humid_s/10, batt_s/10, rssi, stat
    
def MAC_decode( mac:bytes ) :
    '''Encode Bytes for MAC Address'''
    a,b,c,d,e,f = struct.unpack('@6B', mac )
    return f"{a:02x}:{b:02x}:{c:02x}:{d:02x}:{e:02x}:{f:02x}"

def MAC_encode( mac:str ) :
    '''Decode String MAC to Bytes'''
    ret = bytearray()
    mac_s = mac.split(':')
    for s in mac_s :
        try:
            ret.append(int(s,16))
        except ValueError as e:
            return None
    return bytes(ret)

def makeLoraADDR( addr, channel ) :
    ''' 固定アドレス送信時にアドレスデータを作成 addr, channelは16進'''
    C.logger.debug(f"LORA_ADDR: 0x{addr:04x} - 0x{channel:04x}")
    t_addr = int(addr)
    t_addr_H = t_addr >> 8
    t_addr_L = t_addr & 0xFF
    t_ch = int(channel)
    b = bytes([t_addr_H, t_addr_L, t_ch])
    return b

def makeSendDataStream ( addr, channnel, data : list )  -> bytearray :
    ''' 送信データをLENGTHを付けて作成する''' 
    stream = bytearray()
    buff = bytearray()
    size = 0

    ## 送信先GATEのアドレス（固定アドレス）
    stream += makeLoraADDR( addr, channnel ) 

    ## データサイズ計算
    for d in data :
        size += len(d)
        buff += d

    # データ連結
    stream += (struct.pack(L_LEN, size))
    stream += buff
    C.logger.debug(f" LEN>{size}")

    return stream

#### ------------------------------------------------------- main
if __name__ == "__main__" :
    setupGPIO()
    NODE_NO=M.getNodeNo()
    args = sys.argv

    try :
        if args[1].upper() == 'LED' :
            print("Flash LED GREEN join=True")
            Led_flash( "GREEN" ,times=5, join=True )
            print("Flash LED RED")
            Led_flash( "RED" ,times=5, join=True )
            print("Flash LED RED & GREEN ")
            Led_flash( "RED" ,times=3 )
            Led_flash( "GREEN" ,times=3 )
            sys.exit(0)

        elif args[1].upper() == 'GATE' :
            if NODE_NO != 0 : 
                C.logger.critical(f"ERROR This Machine NODE - {M.getHostname()}")
                sys.exit(0)
            C.logger.info(f"--- GATEWAY --- {NODE_NO:02}")
            print("lilbLoRa.py -- START for GATE")

            ## E220 LoRa Module init
            setMode(0)
            WaitAUX()

            ## START UP Lora Thread
            GATE = Lora_GATE()

            # 無限ループ（CTRL+CでInterrupt）
            while True:
                time.sleep(10)

        
        elif args[1].upper() == 'NODE' :
            if NODE_NO == 0 : 
                C.logger.critical(f"ERROR!!! This HOST is GATEWAY - {M.getHostname()}")
                sys.exit(0)
            C.logger.info(f"--- NODE -- {NODE_NO:02}")
            print(f"lilbLoRa.py -- START for NODE{NODE_NO:02}")

            ## E220 LoRa Module init
            #setMode(0)
            #WaitAUX()

            ## START UP Lora Thread
            NODE = Lora_NODE(NODE_NO)

            # 無限ループ（CTRL+CでInterrupt）
            while True:
                time.sleep(10)

        elif args[1].upper() == 'AUX' :
            mode = 'HIGH' if GPIO.input(AUX_PIN) == 1 else 'LOW'
            C.logger.info(f"AUX pin is {mode}")
            sys.exit(0)

        elif args[1].upper() == 'ADDR' :
            print(  makeLoraADDR( GATE_ADDR, GATE_CHANNEL) )
            sys.exit(0)

    except KeyboardInterrupt :
        print("CTRL+C exit")
        sys.exit(0)
