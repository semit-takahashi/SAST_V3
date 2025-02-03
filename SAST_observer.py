#!/usr/bin/python3
"""
SAST GATE側オブザーバー
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Summary:
GATEWAY側のオブザーバープログラム
PrivateLORAを経由して、SQLiteに蓄積されたデータを判断し、
 グラフ化: Ambient
 通知: Discord
 記録: Google Apps Script
にそれぞれ送信する。

また、センサー状態をを確認して、
・高温警告
・高温注意（5分間隔）
・通信途絶（10分間隔）
を判定して、Discordにて通知する。

SEMI-IT Agriculture Support TOOLs SAST Observer
-------------------------
Ver. 1.0.0 2023/03/21
Ver. 1.0.1 2024/04/27　センサーデータを送信後に削除する対応
Ver. 2.0.1 2025/01/20　大幅改定　GoogleApps経由で設定データ受信 ＆DiscordにてNotify通知
Auther F.Takahashi
"""
## import ORIGINAL
import config as C
import libMachineInfo as M
import libSQLite as SQL

## import system
import datetime
import requests
import ambient
import json
import time
import sys
import signal
import schedule

###### SIGTERM 
def intr_signal_term(num,frame):
    C.logging.info("[SAST_observer] catch SIGTERM")
    sys.exit(1)

signal.signal(signal.SIGTERM, intr_signal_term)

def OverCautionTemp( templ:float , thr ) -> bool:
    """警告温度を超えている？
    Args:
        temp (float): 温度
    Returns:
        bool: True:超えている
    """
    return True if thr <= templ else False 

def OverWanringTemp( templ:float , thr ) -> bool : 
    """注意温度を超えている？
    Args:
        temp (float): 温度
    Returns:
        bool: True:超えている
    """
    return True if thr <= templ else False

def PassedMinute( dateSTR:str, minute:int ) -> bool:
    """指定された時間からX分経過したかどうか？
    Args:
        dateSTR (str): 日付文字列（SQLite）
        minute (int): 経過確認分
    Returns:
        bool: True:経過した / False:経過していない
    """
    try :
        last = dt = datetime.datetime.strptime(dateSTR, "%Y-%m-%d %H:%M:%S")
        span = datetime.datetime.now() - last
        #C.logger.debug(f"[PassedMinute] src[{dateSTR}] int:{minute*60}sec span={span.seconds}sec")
        return True if( span.total_seconds() >= minute*60 ) else False
    except Exception as e :
        C.logger.warning(f"PassedMinute ERROR {e}")
        return False

def makeNotifyMessage( sens:str, node:str, state:C.SENS_ST, val:float , high_caut:float, high_warn:float ) -> str:
    """通知用のメッセージを作成
    Args:
        sens (str): センサー名
        node (str): ノード名
        state (C.SENS_ST): センサー状態
        val (float): 温度
        high_caut(float): 警告温度
        high_warn(float): 注意温度
    Returns:
        str: メッセージ文字列
    """
    mess = ""
    if state == C.SENS_ST.HIGH_CAUTION :
        mess = f"🟥警告!【{node} {sens}】が{high_caut}℃を超えました(現在{val}℃)\n"
        C.logger.debug(mess)
    elif state == C.SENS_ST.HIGH_WARN :
        mess = f"🟠注意!【{node} {sens}】が{high_warn}℃を超えました(現在{val}℃)\n"
        C.logger.debug(mess)
    elif state == C.SENS_ST.LOST :
        mess = f"🏠センサー【{node} {sens}】と接続できません\n電池や設置場所を確認してください\n"
        C.logger.debug(mess)
    return mess


def POST_discord(  mess, token, linkURL ):
    """discordにPOST
       URL https://discord.com/api/webhooks/
    Args:
        mess (str): 通知メッセージ
        token (str): discord URL & TOKEN
        url (str): グラフURL
    Returns:
        int: status_code  200:OK
    """
    try:
        if linkURL != "" :
            m = f"{mess}\n📊グラフ\n{linkURL}"
        else :
            m = mess
        url = "https://discord.com/api/webhooks/"+token
        #C.logger.warning(f"discord : {url}")
        headers = { 'Content-Type': 'application/json' }
        data = {'content': f'{m}'}
        r_post = requests.post(url, headers=headers, data=json.dumps(data) )
        C.logger.debug(f"POST Discord->Result({r_post.status_code})")
        return r_post.status_code
    
    except Exception as e:
        C.logger.error(f"[POST_discord] Excption: {e}")
        return None
 

def sent_Ambient( amb_conf, sendDATA ):
    """Ambientにデータ送信
    Args:
        amb_conf (dict): 送信先のAmbient情報（DICT形式）
        sendDATA (list): 送信データ( { 'd1': data, 'd2':data ..... })
    Returns:
        bool : True 成功 / False 失敗
    """
    sendDATA['created'] = C.getTimeSTR()
    channel = amb_conf['channelID']
    writeKey = amb_conf['writeKey']
    use = amb_conf['use']

    # 利用しない場合は何もしない
    if not use :
        C.logger.warning(f"[sent_Ambient] Not Use Ambient...SKIP")
        return False

    ## データが無い場合は送信しない
    # データが無くても全データを送信する。（無い値は0にしておくため）
    # 利用するかはAmbient側でグラフ設定するため問題ない
    # データロスト時に0になるので、わかりやすいはず

    am = ambient.Ambient(channel, writeKey)

    #データの作成 dictionaryで作成する
    #データはd1~d8として作成する。
    #ローカルタイムスタンプは 'created': 'YYYY-MM-DD HH:mm:ss.sss' として作成する。
    
    for retry in range(3):
        # 2秒間隔で3回リトライ
        try:
            C.logger.info(f"Send Ambient(ch:{channel}) ... ")
            ret = am.send(sendDATA)
            if ret.status_code == 200 :
                C.logger.info(f"Response({ret.status_code}) done")
                return True
            elif ret.status_code == 403 :
                C.logger.warning(f"Response({ret.status_code}) wait 3 sec")
                time.sleep(3)
                continue

            else :
                C.logger.warning(f"Response({ret.status_code}) ")
                time.sleep(0.2)
                return False

        except requests.exceptions.RequestException as e:
            C.logger.error(f"[sent_Ambient] request failed:{e}")

        except Exception as e:
            C.logger.error(f"[sent_Ambient] Exception:{e}")

        time.sleep(2)

    return False 


def sent_GAS( GAS, sendDATA):
    """Google Apps Script(GAS) 宛てにデータ送信
    Args:
        GAS (str): GASのWEB-API
        sendDATA (str): 送信データ（）
    Returns:
        _type_: _description_
    """
    #sendDATA['date'] = C.toTimespan(sendDATA['date'])
    past = time.time()
    for retry in range(3):
        # 3秒間隔で3回リトライ
        try:
            ret = requests.post(GAS, data=json.dumps(sendDATA), headers={'Content-Type': 'application/json'})
            if ret.status_code == 200 :
                C.logger.info(f"Response({ret.status_code}) time={time.time() - past :5.2}sec")
                return True
            else :
                C.logger.warning(f"Response({ret.status_code}) time={time.time() - past :5.2}sec")
                return False

        except requests.exceptions.RequestException as e:
            C.logger.error(f"[sent_GAS] request failed : {e}")

        except Exception as e:
            C.logger.error(f"[sent_GAS] Exception:{e}")

        time.sleep(3)

    return False

def countFromStatus( status:C.SENS_ST , data:dict ) -> int:
    """指定したステータスでカウントを計算
    Args:
        status (IntEnum): センサー状態
        data (dicyt): notifyから取得したdict
    Returns:
        int: カウント値
    """
    if len(data) == 0 : return 1
    if status == data['status'] : return data['count'] + 1
    return 1

def IsRegistMAC( mac ) -> bool :
    """指定したMACのセンサーが登録されているか？
    Args:
        mac (str): センサーMAC
    Returns:
        bool: True 登録済
    """
    name = S.getSensName( mac )
    return False if name == "" else True

def _send_cloud() :
    """GATEWAYのSQLに入っているデータを選別してCloudに送信する
       ・通知が必要かをチェック
       ・必要な物を通知 Discrod
       ・Ambient送信
       ・GAPPS送信
    """
    # SQLライブラリ初期化
    S = SQL.SQL()

    ## === Latestの全データを確認して通知が必要な物はフラグを立てる
    C.logger.info("[SAST_observer] Send Cloud ....")
    notifyListAll = S.getNotifyList(0)
    sensDATAs = S.getLatestAll()

    # -- データが無ければ実行しない
    if len(sensDATAs) == 0:
        C.logger.warning("No Senser DATA ... skip")
        return
    
    # -- dump latest DATA
    #for d in sensDATAs :
    #    C.logger.debug(f"S: {d['mac']} - {d['node']}/{d['templ']}/{d['humid']}/{d['ext']}")

    # -- dump notify DATA
    #for d in notifyListAll :
    #    C.logger.debug(f"L: {d['mac']} - {d['node']}/{d['date']}/{d['lost_date']}/{d['status']}/{d['count']}")


    ## ============================================================================================
    #  センサー温度が閾値超えかをチェック
    C.logger.info(f"Judgement SENS:{len(sensDATAs)}/NOTIFY:{len(notifyListAll)}")
    for n in notifyListAll :
        # センサーデータを検索
        s = _searchSensorData(sensDATAs, n['mac'])
        if s != None :
            # --> センサーがLatestから見つかったので温度検知確認
            # この状態ではLatestにセンサーが存在している（＝LOSTしていない）

            # Node情報なら次にスキップ
            if s['mac'].startswith('00:00:00') : 
                continue

            # 指定したMACの閾値情報を取得
            (lc,lw,hw,hc) = S._getThreshold( s['mac'])

            # この時点で
            # s -- latestに挿入されているセンサー
            # n -- latestのセンサーのnotify情報
            # 更新日(date)、LOST日時()、状態(status)、NOTIFYフラグ(notify)、通知数（count)
            
            # 温度チェックの実施
            if OverCautionTemp( s['templ'] , hc ) :
                #超過なら通知ON（日時、通知、ステータス:警告）を更新
                C.logger.info(f"警告 {s['mac']}")
                count = countFromStatus( C.SENS_ST.HIGH_CAUTION, n )
                S.updateNotify(s['mac'], C.SENS_ST.HIGH_CAUTION, count )

            elif OverWanringTemp( s['templ'], hw ) :
                #注意の温度になっているので前回の状態を確認( 5分経過 )
                C.logger.info(f"check WARN {s['mac']} .... {s['templ']}")
                if n['count'] == 0 :
                    ## 前回の記録が無いので通知する。
                    C.logger.info(f"注意 {s['mac']} <- first ")
                    S.updateNotify(s['mac'], C.SENS_ST.HIGH_WARN, 1 )
                # 前回の記録があるので5分経過を確認
                elif PassedMinute( s['date'], minute=5 ) :
                    # 5分経過していたので通知する
                    C.logger.info(f"注意 {s['mac']} <ｰｰ {n['date']}")
                    count = countFromStatus( C.SENS_ST.HIGH_WARN, n )
                    S.updateNotify(s['mac'], C.SENS_ST.HIGH_WARN, count )
                #5分経過してないなら通知はしないでそのまま
            else :
                #警告、注意でもなく、2分以内の更新なので正常として更新
                C.logger.debug(f"通常 {s['mac']}")
                S.updateNotify(s['mac'], C.SENS_ST.NORMAL, 0 )
        else :
            ## --- > センサーがNotifyの中に無かった場合なのでLOST疑い
            # status == NONE はまだ接続したことが無いのでスキップ
            if n['status'] == C.SENS_ST.NONE :
                C.logger.debug(f"{n['mac']} -- Not Connected ... SKIP")
                continue 

            C.logger.debug(f"L: {n['mac']} - {n['date']}/{C.SENS_ST(n['status']).name}/{n['count']}")
            ## 一度接続したことがあるセンサーなので、LOST疑いあり
            if PassedMinute( n['date'], minute=15 ) and n['status'] == C.SENS_ST.NORMAL :
                # 15分経過かつロストしていない場合は−＞初期のロスト
                C.logger.info(f"LOST {n['mac']} <ｰｰ first")
                S.updateNotify( n['mac'], C.SENS_ST.LOST, 1)

            elif PassedMinute( n['date'], minute=15 ) and n['status'] == C.SENS_ST.LOST :
                # 15分経過＋ロストの場合も通知して継続
                C.logger.info(f"LOST {n['mac']} <- {n['date']} .... c:{n['count']}")
                count = countFromStatus( C.SENS_ST.LOST, n )
                S.updateNotify( n['mac'], C.SENS_ST.LOST, count)

            ## 15分未満の場合は無視
            C.logger.debug(f"OTHER ... SKIP")

    ## ============================================================================================
    #  discord 通知処理
    C.logger.info("Notify to discord ...")
    max_node = S.numNode() # ノード数を取得
    for no in range(1, max_node + 1 ) : #ノード数でループ
        notifyList4Node = S.getNotifyList( no , notify=True )
        ## Notify List が存在するか？ 無ければ通知はSKIP 
        if not len(notifyList4Node) == 0 :
            mess = ""
            token = S.getDiscord( no )
            if token == False : continue #tokenが入っていないならスキップ
            amb_conf = S.getAmbientInfo( no )
            if amb_conf == None : amb_url = ""  #-- AmbientURLが未設定 
            C.logger.info(f"notifyList {notifyList4Node}")
            for notify in notifyList4Node :
                if notify['mac'].startswith('00:00:00') : continue # Node情報ならSKIP
                if notify['status'] == C.SENS_ST.NORMAL : continue # 通常ならSKIP
                if notify['status'] == C.SENS_ST.NONE : continue # 不定ならSKIP
                if notify['count'] >= 10 : continue # 10回以上通知したなら通知無効

                C.logger.info(f"Notify({notify['mac']}) -- {notify['date']} [{C.SENS_ST(notify['status']).name}] ct:{notify['count']}")
                ( sens_name, node_name, nodeNo ) = S.getSensorInfo(notify['mac'])
                ( lc, lw, hw, hc ) = S._getThreshold( notify['mac'])
                sens = _searchSensorData( sensDATAs, notify['mac'])
                templ = sens['templ'] if sens != None else 0
                mess += makeNotifyMessage( sens_name, node_name, notify['status'], templ , hc, hw )

            if mess != "" : ## メッセージが作成されていれば通知
                POST_discord( mess, token, amb_url )

    ## ===========================================================================================
    #  Ambient送信
    C.logger.info("Make Ambient DATA. ")
    ## ---　ノード毎でMACを纏めて、データを生成し、Ambientに送信する
    for node in range(1, S.numNode() + 1 ) :
        # -- ノードのチャンネルデータを取り出す
        amb_conf = S.getAmbientInfo(node)
        if amb_conf == None : continue  # -- Ambentが未設定ならSKIP    
        ##-- Nodeを指定して配列再生成
        res = [[d['node'], d['mac'], d['templ'], d['ambient_conf']] for d in sensDATAs if d['node'] == node]
        #print(res)

        # 送信データのセット
        data = {}
        if C.AMB_SEND_NODATA : 
            # データが設定されていなくてもAmbientに送る場合は、全データをセットしておく
            data = { 'd1':0,'d2':0,'d3':0,'d4':0,'d5':0,'d6':0,'d7':0,'d8':0 }
        else :
            # データを送ら無いときで、センサーデータ無いときはデータ送信をスキップ
            if len(res) == 0 : continue #-- そのノードの送信データが無いのでSKIP

        # 送信データの作成
        for sens in res :
            if sens[1].startswith("00:00:00:00:00:") : continue ## -- NodeはSKIP
            #print(sens)
            if sens[3] == "" : 
                C.logger.error(f"Not set Ambient Index {sens[1]}")
                break
            data[sens[3]] = sens[2]

        #-- データが生成したなら、Ambientに送信
        C.logger.debug(f"Send Ambient(LORA{node:02}) {data}")        
        sent_Ambient( amb_conf, data)



    ## ============================================================================================
    #  GAS 送信
    C.logger.info("Send Google Apps Script (GAS) ....")
    dataS = []
    for data in sensDATAs :
        ## GAS用に日時データを変換（UnixTime）
        data['date'] = C.toTimespan(data['date'])
        ## GASで不要なデータを削除（ambient_conf, node)
        del data['ambient_conf']
        del data['node']
        dataS.append(data)
        ## 不要なキーを削除
    sent_GAS( C.GAS, dataS ) #配列で一気に挿入
    C.logger.info("done.")

    C.logger.info(f"Cloud Send done .... Wait after {C.SPAN_SEND_CLOUD} minutes....\n")


def _searchSensorData( sensDATAs , mac ) :
    """ 内部関数：センサーデータのリストからMACに一致する列を返す """
    for s in sensDATAs :
        if s['mac'] == mac : return s
    return None



def _getSetting4GApps( verbose=False ) :
    ''' GASにて指定されたURLから設定情報を取得して更新する。'''
    C.logger.info(f"[observer] Get Config Data for Google")
    start=time.time()
    header = {"content-type": "application/json"}
    try :
        res = requests.get(f"{C.GAS}?sens=sensor", headers=header)
    except Exception as e :
        C.logger.error(f"[observer] HTTP Connection Error : {e} .... SKIP")
        return False

    # データがGASから取得できた
    if res.status_code == 200 :
        S = SQL.SQL()
        updateDate = None
        try : 
            updateDate = datetime.datetime.strptime(res.json()[0]['date'], "%Y/%m/%d %H:%M:%S")

        except ValueError as e:
            ## GASの日付エラー
            mess = f"Update Date is Invalid ... {res.json()[0]['date']}"
            C.logger.error(mess)
            _sendACK2GAS( mess )
            return False

        # GASデータの取得
        confData = []
        for d in res.json()[1:] :
            confData.append(d)
        (ret, mess ) = S.updateSystemConf( confData, updateDate )

        if verbose :
            import pprint
            C.logger.info(pprint.pformat(confData))
        

        if ret :
            C.logger.info(f"Update done. {time.time() - start:.2f}sec")
            if verbose :
                import pprint
                C.logger.info(pprint.pformat(confData))
            _sendACK2GAS( mess )
            return True
            
        elif ret == None :
            C.logger.error(f"Update Error. {time.time() - start:.2f}sec")
            _sendACK2GAS( mess )

        else :
            C.logger.warning(f"----- No update required {time.time() - start:.2f}sec")
            _sendACK2GAS( mess )
            return False

    else :
        C.logger.error(f"Connection Error code:{res.status_code}  {time.time() - start:.2f}sec")
        _sendACK2GAS( mess )
        C.logger.debug(f"MESS{mess}")


def _sendACK2GAS( message ) :
    """ 内部関数：GASにACKを送信（メッセージ付き）"""

    # ACKを返送(5回実施)
    header = {"content-type": "application/json"}
    count = 0
    while True :
        try :
            res = requests.get(f"{C.GAS}?sens=ack&mess={message}", headers=header)

        except Exception as e :
            C.logger.error(f"HTTP Connection Error : {e} .... SKIP")
            return False
            

        if res.status_code == 200 :
            C.logger.info("ACK response OK done.")
            return True

        else :
            if count <= 5 : 
                C.logger.warning(f"ACK response ERROR {res.status_code} ... retry 10 sec")
                time.sleep(10)
                count += 1
            else :
                C.logger.warning(f"ACK response ERROR {res.status_code} ... SKIP")
                return False


def _checkBattery() :
    """ センサーのバッテリーをチェックして通知する """
    C.logger.info("[SAST_observer] _checkBattery()")
    # 有効なMACのセンサーの中で最新のデータを取得する（hisotryから）
    # 各ノード毎に情報を整理する。
    # 通知を使ってメッセージをなげる

    battery_info = {}
    S = SQL.SQL()
    mess = ""
    for node in range( 1, S.numNode()+1 ) :
        sensors = S.getSensors( node )
        for s in sensors :
            # センサーデータ取得
            try :
                ( mac, name ) = s
                ( batt, date, rssi, ext ) = S.getBattery(mac)
                battery_info['name'] = name
                battery_info['batt'] = batt
                C.logger.info(f"{name}:{mac}({date})- {batt}%")
            except Exception as e :
                C.logger.debug(f"No data {mac} ... skikp")
                continue
            #情報生成
            if batt <= 15.0 : 
                mess += f"{name} : {batt}% 要交換!!\n"
            else :
                mess += f"{name} : {batt}% \n"
        
        #通知メッセージ作成
        if mess == "" : continue # メッセージ無いならスキップ
        ( no, node_name) = S.getNodeInfo( node )
        mess = f"{node_name} のバッテリー情報\n" + mess 
        
        # DIscord通知
        token = S.getDiscord( node )
        POST_discord( mess, token, "" )
        mess = ""
    
def _intr_term( num, frame) :
    C.logger.warning("SIGTERM catch exit...num}")
    sys.exit(0)

## MAIN
if __name__ == '__main__' :
    C.logger.info(f"START Observer GATGEWAY")

    args = sys.argv
    if len(args) != 1 and args[1].upper() == "CLEAR" :
        C.logger.info("-> CLEAR ALL DATABASE ")
        S = SQL.SQL("CLEAR")
        del S
        sys.exit()
 
    elif len(args) != 1 and args[1].upper() == "CONFIG" :
        C.logger.info("->Update Config from Google Apps")
        start=time.time()
        if _getSetting4GApps(verbose=True) :
            print(f"Update done. {time.time() - start:.2f}sec")
        else :
            print(f"No need Update. {time.time() - start:.2f}sec")
        sys.exit()     

    ### UNIX Signal Register
    signal.signal(signal.SIGTERM, _intr_term)
    signal.signal(signal.SIGHUP, _intr_term)

    ### Check GAS URL Setting 
    ##1 URL Not SET
    if C.GAS == {} :
        C.logger.error("Not Register GAS WEB-API URL")
        C.logger.error("NBUild /boot/GAS_ssetting/py and Resgtert System... shutdown")
        sys.exit(1)
    ##2 URL 404
    import requests
    try :
        res = requests.get(C.GAS)
    except Exception as e:
        C.logger.error(f"GAS URL {C.GAS} is Error Occord \n{e}")
        sys.exit(1)

    C.logger.info("[Observer] Init GATEWAY Databases...")
    S = SQL.SQL("STARTUP_GATE")

    # 設定情報の更新
    _getSetting4GApps(True)

    ### =========== スケジューラ登録
    ## 2分毎に秒にsend_cloud()を実行
    C.logger.info(f"[observer] _send_cloud() {C.SPAN_SEND_CLOUD} minutes.")
    schedule.every(C.SPAN_SEND_CLOUD).minutes.do(_send_cloud)

    ## 1時間毎にGoogleから設定情報を取得して更新
    C.logger.info(f"[observer] _getSetting4GApps() {C.SPAN_CONFIG_UPDATE} hours.")
    schedule.every(C.SPAN_CONFIG_UPDATE).hours.do(_getSetting4GApps)

    ## 毎日朝8時にバッテリー情報を通知
    C.logger.info(f"[observer] _checkBattery() 8:15 hours.")
    schedule.every().day.at("08:00").do(_checkBattery)

    ## 実行し続ける ループ 
    while True:
        # 次の行で実行まで待つ。
        schedule.run_pending()
        # 終わったらsleepしてもう一度
        time.sleep(1)
