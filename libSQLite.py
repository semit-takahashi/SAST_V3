#!/usr/bin/python3
"""
Raspberry Pi SQLiteライブラリ libSQLite.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Summary:
データ保存を行うSQLiteのライブラリ。
GATEWAYとNODEで共通利用する。
初期利用時には、Sensor、Nodeの初期化 SQL("SETUP")
LINE通知先の動的更新は、SQL("LINE")を実行

なお、
NODEの利用時は、レコーダ側にて、SQL("STARTUP_NODE")
GATEWAYの利用時は、レコーダ側にて、SQL("STARTUP_GATEWAY")
をそれぞれ実行して、キャシュをクリアすること。

SEMI-IT Agriculture Support TOOLs V3
バージョン情報 -------------------------
Ver. 1.0.2 2023/04/16
Ver. 2.0.2 2025/01/20 通信処理変更にて更新
Auther F.Takahashi
"""

import config as C
import sqlite3
import sys
import json
import datetime
from enum import IntEnum
DB_PATH = './sql_sastv3.sqlite'

class SQL:
    connection = None

    def __init__(self,mode=""):
        self.connection = sqlite3.connect(DB_PATH)
        #self.connection.isolation_level = None
        if mode != "" : self.createTables( mode )

    def createTables(self, mode="") :
        """テーブル作成
        Args:
            mode 作成モードの指定 <br/>
            未指定: テーブル情報の作成（既存は消さない)<br/>
            clear :全テーブルクリア<br/>
            setup :ノード、センサー情報の初期読み取り<br/>
            STARTUP_NODE :notify、latest, statusのクリア
            STARTUP_GATE 
            . 初期値 "".
        """
        C.logger.info(f"[createTables] Create Table {mode}")
        c = self.connection.cursor()

        if mode.upper() == "CLEAR" :
            C.logger.warning("DROP All Tables.")
            c.execute("DROP TABLE IF EXISTS history")
            c.execute("DROP TABLE IF EXISTS notify")
            c.execute("DROP TABLE IF EXISTS latest")
            c.execute("DROP TABLE IF EXISTS status")
            c.execute("DROP TABLE IF EXISTS conf")
            c.execute("DROP TABLE IF EXISTS conf_date")
            c.connection.commit()

        elif mode.upper() == "STARTUP_NODE" :
            C.logger.warning("[createTables] STARTUP_NODE .... ")
            self.initLatest()
            return

        elif mode.upper() == "STARTUP_GATE" :
            C.logger.warning("[createTables] STARTUP_GATE ....") 
            self.initLatest()
            self._rebuildNotify()
            return 

        ### -- CREATE Tables
        C.logger.warning("[createTables] CREATE TABLES ....")
        # history 
        c.execute("CREATE TABLE IF NOT EXISTS history ( id INTEGER UNIQUE, mac TEXT NOT NULL, date TEXT NOT NULL, node INTEGER, templ REAL, humid REAL, batt REAL, rssi INTEGER, ext INTEGER, light REAL, status INTEGER, PRIMARY KEY(id AUTOINCREMENT))")
        # notify（必ず新規）
        c.execute("CREATE TABLE IF NOT EXISTS notify ( mac TEXT NOT NULL, date TEXT, lost_date TEXT, status INTEGER NOT NULL, notify INTEGER, count INTEGER, node TEXT, PRIMARY KEY(mac))")
        # latest（必ず新規）
        c.execute("CREATE TABLE IF NOT EXISTS latest ( mac TEXT NOT NULL, date TEXT NOT NULL, node INTEGER, templ REAL, humid REAL, batt REAL, rssi INTEGER, ext INTEGER, light REAL, status INTEGER, PRIMARY KEY(mac))")
        # status(必ず新規で一つのデータ)
        c.execute("CREATE TABLE IF NOT EXISTS status ( id INTEGER UNIQUE, stat INTEGER, PRIMARY KEY(id AUTOINCREMENT))")
        # conf（）
        c.execute("CREATE TABLE IF NOT EXISTS conf ( mac TEXT NOT NULL, name TEXT, node TEXT, use BOOLEAN, warn TEXT, ambient_conf TEXT, discord_token TEXT, memo TEXT, PRIMARY KEY(mac) )")
        # conf（）
        c.execute("CREATE TABLE IF NOT EXISTS conf_date ( id INTEGER NOT NULL, date TEXT NOT NULL, PRIMARY KEY( id ) )")
        # 確定
        c.connection.commit()

        # ステータス初期化
        self.changeNodeStatus()


    def initNotify( self ) :
        """Notifyテーブルを初期化する """
        C.logger.debug(f"initNotify()")

        ## MACアドレス再登録
        self._rebuildNotify()

        date = C.getTimeSTR()
        c = self.connection.cursor()
        query = f"UPDATE notify SET status=-1, date='{date}', count=0, notify=0"
        try:
            c.execute( query )
            c.connection.commit()
            return
        except sqlite3.IntegrityError as e :
            C.logger.error(f"[initNotify] ERROR:{e} ")
            return 

    def initLatest( self ) :
        """Latestテーブルを初期化する """
        C.logger.debug(f"initLatest()")
        c = self.connection.cursor()
        query = f"DELETE from latest"
        try:
            c.execute( query )
            c.connection.commit()
            return
        except sqlite3.IntegrityError as e :
            C.logger.error(f"[initLatest] ERROR:{e} ")

    def changeNodeStatus(self, stat=0) :
        """Nodeのシステムステータスを更新（OLEDが利用する）
        TABLEが空の場合は、初期値を代入
        Args:
            stat (int): ステータス
        """
        C.logger.info(f"changeStatus({stat})")
        c = self.connection.cursor()
        try :
            ct = c.execute("SELECT count(id) from status")
            res = c.fetchone()
            #C.logger.debug(f"res = {res[0]} {type(res[0])}")
            if res[0] == 0 :
                ## 初期化必須
                C.logger.warning(f"Status Table init {stat}")
                c.execute(f"INSERT INTO status (stat) values({stat})")
                c.connection.commit()
                return
            ## 通常更新
            c.execute(f"UPDATE status SET stat={stat} where id=1")
            c.connection.commit()
            return 
        except sqlite3.Error as e :
            C.logger.error(f"[changeNodeStatus] {e}")
            return False
        
    def getNodeStatus(self) :
        """システムステータスを取得
        Raises:
            ValueError: 未初期化時
        Returns:
            int: ステータス種別
        """
        C.logger.debug("getStatus")
        c = self.connection.cursor()
        try :
            c.execute(f"select stat from status where id=1")
            res = c.fetchone()
            #C.logger.debug(f"res = {res} {type(res)}")
            # Queryの戻り値が無い場合はNone
            if res == None :
                raise ValueError("status not init")
            return C.NODE_STAT(res[0])
        except sqlite3.Error as e :
            C.logger.error(f"[getNodeStatus] {e}")
            return False


    def isArriveNode( self, node ) :
        """ 指定したNOodeの応答があったか（10分以内）

        Args:
            node (int): Node番号
        """
        C.logger.debug(f"isArriveNode()")
        ## 10分前の時刻を計算→文字列に変更
        span = datetime.datetime.now()-datetime.timedelta(minutes=10)
        span_str = span.strftime("%Y-%m-%d %H:%M:%S")
        query = f"SELECT count( distinct mac) from history where date>'{span_str}' and mac='00:00:00:00:00:{node:02}'"
        c = self.connection.cursor()
        try :
            c.execute(query)
            ret = c.fetchone()
            return True if ret != None else False
               
        except sqlite3.Error as e :
            C.logger.error(f"[isArriveNode] {e}")
            return 0


    def numSensorsMe(self) :
        """ Node向け。過去1時間で検知したセンサーの個数を返す（全体数）
        Returns:
            num(int): センサー個数
        """
        C.logger.debug(f"numSensorsMe()")
        ## 1時間前の時刻を計算→文字列に変更
        span = datetime.datetime.now()-datetime.timedelta(hours=1)
        span_str = span.strftime("%Y-%m-%d %H:%M:%S")
        query = f"SELECT count( distinct mac) from history where date>'{span_str}'"
        c = self.connection.cursor()
        try :
            c.execute(query)
            ret = c.fetchone()
            return ret[0] if ret != None else 0

        except sqlite3.Error as e :
            C.logger.error(f"[numSensorsMe] {e}")
            return 0

    def getSensors(self, node ) :
        """指定されたノードのセンサーリストを返す
        Args:
            node (int): ノードNO
        Returns:
            tuple: センサーMACと名称(mac,name)
        """
        C.logger.debug(f"getSensors( {node} )")
        query = f"SELECT mac, name from conf where node = {node}"
        #C.logger.debug(f"QUERY = {query}")
        c = self.connection.cursor()
        try :
            c.execute(query)
            return c.fetchall()
        except sqlite3.Error as e :
            C.logger.error(f"[getSensors] {e}")
            return False
    
    def getBattery( self, mac ) :
        """ Historyの最新のセンサー情報を返す
        Args:
            mac (str): センサーMAC
        Returns:
            ( batt, date, rssi, ext )
        """
        C.logger.debug(f"getBattery({mac})")
        query = f"SELECT batt, date, rssi, ext FROM history WHERE mac ='{mac}' ORDER BY date DESC LIMIT 1"
        c = self.connection.cursor()
        try :
            c.execute(query)
            ret = c.fetchone()
            return ret
        except sqlite3.Error as e :
            C.logger.error(f"[getBattery] {e}")
            return False

    def getNodeInfo(self, node ) :
        """指定されたノード情報
        Args:
            node (int): ノードNO
        Returns:
            tuple: ノード情報（nodeNO, name）
        """
        C.logger.debug(f"getNodeInfo( {node} )")
        query = f"SELECT node, name from conf where node='LORA{node:02}'"
        #C.logger.debug(f"QUERY = {query}")
        try :
            c = self.connection.cursor()
            c.execute(query)
            return c.fetchone()
        except sqlite3.Error as e :
            C.logger.error(f"[getNodeInfo] {e}")
            return False

    def getSensorInfo(self, mac:str ) :
        """指定したセンサーの情報＋ノード名
        Args:
            mac (str): センサーMAC
        Returns: tuple
            sens_name, node_name, nodeNo, warn
        """
        C.logger.debug(f"getSensorInfo( {mac} )")
        c = self.connection.cursor()
        try :
            query =f"SELECT name, node, warn from conf WHERE mac = '{mac}'"
            c.execute(query)
            res = c.fetchone()
            name = res[0] if res != None else None
            if name == None :
                C.logger.error(f"getSensorInfo: Not Found MAC {mac}")
                return None,None,None,None

            warn = {}
            lC,lW,hW,hC = res[2].split(sep=',')
            warn['lC'] = None if lC.upper() == 'NONE' else float(lC)
            warn['lW'] = None if lW.upper() == 'NONE' else float(lW)
            warn['hW'] = None if hW.upper() == 'NONE' else float(hW)
            warn['hC'] = None if hC.upper() == 'NONE' else float(hC)
            node_no = int(res[1])

            query =f"SELECT name from conf WHERE node = 'LORA{node_no:02}'"
            c.execute(query)
            res = c.fetchone()
            node_name = res[0] if res != None else None
            return name, node_name, node_no, warn

        except ValueError as e :
            C.logger.error(f"[getSensorInfo] {e} < {mac}")
            return None,None,None,None
        
        except sqlite3.Error as e :
            C.logger.error(f"[getSensorInfo] {e} < {mac}")
            return None,None,None,None

    def getDiscord( self, node ) :
        """指定したnodeのDiscod Token
        Args:
            node (int): ノードNO_
        """
        #C.logger.info(f"getDiscode : {node}") 
        query =f"SELECT discord_token from conf where node='LORA{node:02}'"
        c = self.connection.cursor()
        try :
            c.execute(query)
            ret = c.fetchone()
            if ret != None :
                return ret[0]
            return None
        
        except sqlite3.Error as e :
            C.logger.error(f"getDiscod: Exception {e}")
            return False

    def getNodeRSSI( self ) :
        """ 各ノードのRSSIを返す（配列）
        Retuerns:
            list() : Node毎のRSSI
        """
        C.logger.debug(f"getNodeRSSI()") 
        data = [0] * self.numNode()
        for node in range(1 , self.numNode()+1) :
            query =f"select mac, rssi, date from history where mac LIKE '00:00:00:00:00:{node:02}' order by date desc limit 1"
            c = self.connection.cursor()
            try :
                c.execute(query)
                (mac, rssi, date ) = c.fetchone()
                #print(f"{mac[-2:]} - {rssi} / {date}")
                if mac != None :
                    if C.spanTimeforSTR(date) < datetime.timedelta(hours=1) : data[int(mac[-2:])-1] = rssi
            except TypeError :
                #C.logger.debug(f"[getNodeRSSI] No Data ")
                continue

            except sqlite3.Error as e :
                C.logger.error(f"[getNodeRSSI] Exception {e}")
                return False
            
        return data

    def appendData(self, data):
        """センサーの結果情報を追加(INSERT)  同時にlatestのデータも更新する
        Args:
            data (dict): センサー情報 必須はdata('mac')
        Returns:
            bool: 追加結果
        """
        C.logger.debug(f"appendData()> {data['mac']}")

        ## 日付が指定されていない場合に追加
        if 'date' not in data :
            C.logger.warning("Nothing DATE field in DATA")
            data['date'] = C.getTimeSTR()

        ## クエリ作成（historyとlatest）
        columns = ', '.join(data.keys())
        placeholders = ':'+', :'.join(data.keys())
        history_query = 'INSERT INTO history (%s) VALUES (%s)' % (columns, placeholders)
        latest_query = 'INSERT OR REPLACE INTO latest (%s) VALUES (%s)' % (columns, placeholders)

        try :
            c = self.connection.cursor()
            #C.logger.debug(f"QUERY : {history_query}")
            #C.logger.debug(f"QUERY : {latest_query}")
            c.execute(history_query,data)
            c.execute(latest_query,data)
            self.connection.commit()
            return True, data['date']

        except sqlite3.Error as e :
            C.logger.error(f"[appendData] {e}")
            return False, None
        
    def isExistSensor(self, mac) : 
        """ 2024/04/25 追加 登録されているセンサーか？
        Args:
            mac(str): センサーかNodeのMAC
        Returns:
            bool: 検索結果
        """
        if mac.startswith('00:00:00:00:00') :
            # NODEの場合
            #C.logger.debug(f"[isExistSensor] sensor is Node > {mac}")
            return True
        else :
            # センサーの場合なのでDATABASE確認
            try :
                c = self.connection.cursor()
                c.execute(f"select count(mac) from conf where mac = '{mac}'")
                if c.fetchall()[0][0] == 0 :
                    C.logger.warning(f"[isExistSensor] WARNING not regist MAC > {mac}")
                    return False
                return True

            except sqlite3.Error as e :
                C.logger.error(f"[isExistSensor] {e}")
                return None

    def useSensor(self, node, mac ) -> bool : 
        """ 2025/01/18 追加 利用可能なセンサーか？
            2025/01/23 修正 nodeも指定して違うNodeにMACがぶら下がっているときに無効化
        Args:
            node(int): node
            mac(str): センサーかNodeのMAC
        Returns:
            bool: 検索結果
        """
        c = self.connection.cursor()
        if mac.startswith('00:00:00:00:00') :
            try :
                # NODEの場合
                c.execute(f"select count(mac) from conf where mac='{mac}'")
                res = c.fetchone()
                return True if res != None else False

            except sqlite3.Error as e :
                C.logger.error(f"[useSensor] error :{e}")
                return False
        
        else :
            # センサーの場合なのでDATABASE確認
            try :
                c.execute(f"select use from conf where mac='{mac}' and node={node}")
                res = c.fetchone()
                return True if res != None else False

            except sqlite3.Error as e :
                C.logger.error(f"[useSensor] error :{e}")
                return False

    def _rebuildNotify(self) -> int :
        """ 内部関数：Notifyテーブルに有効なMACを再登録する
            return(int):追加した個数
        """
        #指定したmacのNotifyがあるか？（無いなら挿入）
        C.logger.info(f"_rebuildNotify()")
        c = self.connection.cursor()
        try :
            # トランザクションスタート
            c.execute('BEGIN')

            # NotifyTable更新
            ValidMACs = self._getSensors(valid=True) #TRUEのMACのみ抽出
            if ValidMACs != None :
                for mac in ValidMACs :
                    c.execute(f"SELECT mac FROM notify WHERE mac='{mac}'")
                    res = c.fetchone()
                    if res == None :
                        node_no = self.getNodeNo( mac )
                        sql = f"REPLACE INTO notify(mac,status,node) VALUES('{mac}', {C.SENS_ST.NORMAL}, {node_no})"
                        c.execute(sql)


            inValidMACs = self._getSensors(valid=True) #TRUEのMACのみ抽出
            if inValidMACs != None :
                for mac in inValidMACs :
                    node_no = self.getNodeNo( mac )
                    sql = f"DELETE FROM latest WHERE mac='{mac}'"
                    c.execute(sql)
            # commit（トランザクション終了
            c.connection.commit()

            # データ登録数の抽出
            num = 0
            c.execute("SELECT COUNT(mac) from notify")
            res = c.fetchone()
            num = int(res[0]) if res != None else 0
            C.logger.info(f"[_rebuildNotify] valid MAC : {num}")
            return num
        
        except sqlite3.Error as e:
            C.logger.error(f"[_rebuildNotify] {e}")
            c.connection.rollback()
            return False
            
    def getNotify( self, mac ) :
        """指定したMACのNotifyを取得する 
        Args:
            mac (str): センサーのMAC
        """
        C.logger.info(f"getNotify({mac})")
        c = self.connection.cursor()
        query = f"SELECT * notify WHERE mac='{mac}'"
        try :
            c.execute(query)
            ret = c.fetchone()
            if ret != None : return None
            return self._encode_notify(ret)
        
        except sqlite3.Error as e:
            C.logger.error(f"[getNotify] {e}")
            return False

    def updateNotify( self, mac, state, count ) -> bool :
        """指定したMACのNotifyを更新して、フラグを立てる 
        Args:
            mac (str): センサーのMAC
            state (SENS_ST ): センサー状態
        """
        #指定したmacのNotifyがあるか？（無いなら挿入）
        C.logger.info(f"updateNotify {mac}-{C.SENS_ST(state).name}-{count}")
        try :
            c = self.connection.cursor()
            date = C.getTimeSTR()
            notify = 0 if state == C.SENS_ST.NORMAL else 1
            query = f"UPDATE notify SET date='{date}', status={state}, notify={notify}, count={count} WHERE mac='{mac}'"
            #print(query)
            c.execute(query)
            c.connection.commit()
            return True
        
        except sqlite3.Error as e:
            C.logger.error(f"[updateNotify] {e}")
            return False

    def getNotifyList( self, node_no = 0 , ClearfNotify=False) -> list :
        """ Notifyにてノードを指定したリストを返す
        Args:
            node_no (int): ノード番号（デフォルト0は全取得）
            notify(bool): True:フラグあり / False: フラグ無し
        Returns:
            list: センサーリストのdict型list
        """
        #C.logger.debug(f"getNotifyList({node_no} {notify}")
        data = list()
        c = self.connection.cursor()
        dquery = ""
        if ClearfNotify :
            if node_no == 0 :
                query = f"SELECT node, mac, date, lost_date, status, count, notify FROM notify WHERE notify=1"
                dquery= f"UPDATE notify SET notify=0"
            else :
                query = f"SELECT node, mac, date, lost_date, status, count, notify FROM notify WHERE node={node_no} and notify=1"
                dquery= f"UPDATE notify SET notify=0 AND node={node_no}"
        else :
            if node_no == 0 :
                query = f"SELECT node, mac, date, lost_date, status, count, notify FROM notify "
            else :
                query = f"SELECT node, mac, date, lost_date, status, count, notify FROM notify WHERE node={node_no}"
                
        try:
            if ClearfNotify :
                # 通知有りは更新あるのでトランザクション処理
                c.execute("BEGIN")

            c.execute(query)
            results = c.fetchall()

            ## 通知として取得の場合は通知後にフラグ落とす
            if ClearfNotify :
                #C.logger.warning("[getNotifyList] Notify off ")
                c.execute(dquery)
                c.connection.commit()

            ## 1件も無ければ空を返す
            if len(results) == 0 : 
                #C.logger.debug("[getNotifyList] No data")
                return data

            ## 結果を取得
            for res in results :
                data.append(self._encode_notify(res))
            return data
        
        
        except sqlite3.Error as e :
            C.logger.error(f"[getNotifyList] error:{e}")
            return data


    def getLatest(self, mac):
        """MACアドレスを指定して最新(latest)のデータを取得
        Args:
            macs (list): MACアドレスのリスト
        Returns:
            tuple: latest情報（ templ, humid, batt, rssi, node ）
        """
        C.logger.debug(f"getLatest {mac}")

        ## -- 複数のMACをリストにしたWhereを作成
        try:
            c = self.connection.cursor()
            c.execute(f"SELECT templ, humid, batt, rssi, node FROM latest where mac = '{mac}';")
            ret = c.fetchone()
            return ret
        
        except sqlite3.Error as e:
            C.logger.error(f"[getLatest] ERROR : {e}")
            return None

    def getSensName( self, mac ) :
        """指定したMACの名称を返す
        Args:
            mac (str): MACアドレス
        Returns:
            str: 付与してあるセンサーの名称
        """
        C.logger.debug(f"getSensName( {mac} )")
        c = self.connection.cursor()
        try:
            query = f"SELECT name from conf where mac='{mac}'"
            c.execute(query)
            res = c.fetchone()
            if res != None : 
                return res[0]
            C.logger.error(f"name is Not Found from {mac}")
            return ""
 
        except sqlite3.Error as e:
            C.logger.error(f"sqlite3 SELECT ERROR : {e}")
            return ""


    def getLatestDATA(self, node, delete=False ) :
        """指定したnodeの最新データを返す。データは消さない
        Args:
            node (int): ノードNO
        Returns:
            dict(list): 最新のセンサーデータ（Latest）
        """
        C.logger.debug(f"getLatestDATA({node})")
        result = list()
        c = self.connection.cursor()
        query = f"select * from latest where node={node};"
        try:
            # トランザクションを開始
            if delete : # データの削除
                c.execute('BEGIN')

            c.execute(query)
            results = c.fetchall()
            if len(results) == 0 : return result

            if delete : # データの削除
                C.logger.info("[getLatestDATA] delete Latest")
                c.execute(f"DELETE from latest;")
                self.connection.commit()

            for res in results :
                result.append( self._encode_data_latest_node(res) )
            return result

        except sqlite3.Error as e:
            C.logger.error(f"[getLatestDATA] ERROR: {e}")
            if delete :
                ## delete時のExceptionはロールバック
                c.connection.rollback()
            return result
        
    def getLatestAll(self, delete=True) :
        """ Latestの全データを取得する。
            なお、Nodeで実行するとNode内のセンサー
            GateWayなら全センサーデータになる。
            実行すると、Latestテーブルからデータは消える
        Returns:
            dict(list): 最新のセンサデータ（Latest）
        """
        C.logger.debug(f"getLatestALL(delete={delete})")
        c = self.connection.cursor()
        result = list()
        try :
            # トランザクションを開始
            if delete :
                c.execute('BEGIN')
            # センサーデータの取得
            c.execute(f"select L.mac,L.date,L.node,L.templ,L.humid,L.batt,L.rssi,L.ext,L.light,L.status,C.ambient_conf from latest as L inner join conf as C on (L.mac=C.mac);")
            results = c.fetchall()

            if delete : # データの削除
                C.logger.info("[getLatestAll] delete Latest")
                c.execute(f"DELETE from latest;")
                self.connection.commit()

            if len(results) == 0 : return result
            for res in results :
                result.append( self._encode_data_latest(res) )
            return result

        except sqlite3.Error as e:
            C.logger.error(f"[getLatestAll({delete})] ERROR: {e}")
            if delete :
                ## delete時のExceptionはロールバック
                c.connection.rollback()
            return result


    def getStatus(self, mac ) :
        """指定したmacのstatusを返す
        Args:
            mac (str): MAC文字列
        Returns:
            Enum(int)): ステータス（Nofityテーブル内）
        """
        C.logger.debug(f"getStatus( {mac} )")
        c = self.connection.cursor()
        try:
            query = f"SELECT status from notify where mac='{mac}'"
            c.execute(query)
            res = c.fetchone()
            if res == None :
                return C.SENS_ST.NONE
            return res[0]

        except sqlite3.Error as e:
            C.logger.error(f"[getStatus] ERROR: {e}")
            return None

    def updateSystemConf(self, data , cloud_date ) :
        """ システム情報を更新する。
        Args:
            data 更新用のJSON配列
        Returns:
            True  : 更新成功
            False : 更新不要（更新日が過去）
            None  : 更新できない（システムエラー）
            + mess : エラーメッセージ
        """ 
        C.logger.debug(f"updateSystemConf({cloud_date})")
        c = self.connection.cursor()
        conf_date = None
        # 日付確認
        try :
            c.execute("SELECT date FROM conf_date")
            res = c.fetchone()
            if res != None : # 日付があるか？
                conf_date = C.str2Datetime(res[0]) 
                C.logger.debug(f"conf: {conf_date} / cloud: {cloud_date} ")
                if conf_date == cloud_date :
                    # 更新日が一緒なので更新しない
                    #C.logger.info("No updates needed..")
                    return False, ""
        except sqlite3.Error as e:
            mess = f"[updateSystemConf] ERROR : {e}"
            C.logger.error(mess)
            return None, mess

        try : 
            # 情報更新
            C.logger.info(f"Update configure.... {conf_date} -> {cloud_date}")
            column = ', '.join(data[0].keys())
            placeholder = ':'+', :'.join(data[0].keys())

            # トランザクション開始
            c.execute('BEGIN TRANSACTION;')

            # 既存データの削除
            sql = "DELETE from conf"
            c.execute(sql)
 
            # 最新データのインサート
            sql = f"INSERT INTO conf({column}) VALUES({placeholder})"
            for d in data :
                d['mac'] = d['mac'].lower() #macを小文字に変換
                c.execute(sql, d )
 
            # 更新日付の更新
            sql=f"REPLACE INTO conf_date(id, date) VALUES(1, '{cloud_date}')"
            c.execute(sql)
            c.connection.commit()

        except sqlite3.Error as e:
            mess = f"[updateSystemConf] UPDATE ERROR : {e}"
            c.connection.rollback()
            C.logger.error(mess)
            return None, mess

        # Notify Table 構築
        self.initNotify()
        return True, "Update done."

    def _getSensors(self, valid=True) :
        """有効なセンサーのリスト
        Argument:
            valid(bool)  
                  True:有効センサー
                  False:無効センサー
        Returns:
            list : センサーのリスト 
        """
        #C.logger.debug(f"_getSensors()")
        c = self.connection.cursor()
        macs = list()
        try :
            ql = 1 if valid==True else 0
            query = f'SELECT mac FROM conf WHERE use="{ql}"'
            c.execute(query)
            res = c.fetchone()
            if res != None :
                # データ有り
                macs = list()
                macs += res
                for mac in c.fetchall() : macs += mac
            return macs
        except sqlite3.Error as e:
            C.logger.error(f"[_getSensors] ERROR : {e}")
            return macs
        
    def _getThreshold( self, mac ) :
        """ センサー閾値の取得
        Args:
            mac (str): センサーのMAC
        Returns:
            tuple: ( low_warn, low_caution, high_caution, high_warn ) (低温警告, 低温注意, 高温注意, 高温警告)
        """
        #C.logger.debug(f"_getThreshold()")
        c = self.connection.cursor()
        try :
            query = f"SELECT warn FROM conf WHERE mac='{mac}'"
            c.execute(query)
            res = c.fetchone()
            if res != None :
                lC,lW,hW,hC = res[0].split(sep=',')
                low_caution = None if lC.upper() == 'NONE' else float(lC)
                low_warn = None if lW.upper() == 'NONE' else float(lW)
                high_warn = None if hW.upper() == 'NONE' else float(hW)
                high_caution = None if hC.upper() == 'NONE' else float(hC)
                return low_caution,low_warn,high_warn,high_caution
            return None, None, None, None

        except sqlite3.Error as e:
            C.logger.error(f"sqlite3 ERROR : {e}")
            return None, None, None, None
    
    def getAmbientInfo( self, node_no ) :
        """ Ambient接続情報を取得
        Args:
            node_no (int): node No
        Returns:
            dict: 
        """
        #C.logger.debug(f"getAmbientInfo( LORA{node_no:02} )")
        c = self.connection.cursor()
        data = {}
        try :
            query = f"SELECT ambient_conf FROM conf WHERE node='LORA{node_no:02}'"
            c.execute(query)
            res = c.fetchone()
            if res != None :
                #print(res[0])
                data = json.loads(res[0])
                #C.logger.debug(f"NODE:{node_no}>{data}")
                return data
            return None
        except json.JSONDecodeError as e:
            C.logger.error(f"[getAmbientInfo] ERROR: {e}")
            return None

        except sqlite3.Error as e:
            C.logger.error(f"[getAmbientInfo] ERROR: {e}")
            return None
        
    def getAmbientIndex(self, mac ) -> str :
        """ 指定したMACのAmbientのData番号を返す
        Args:
            mac (str): センサーMAC
        Returns:
            str: data番号（""未設定）
        """
        #C.logger.debug(f"getAmbientIndex({mac})")
        c = self.connection.cursor()
        try :
            query = f"SELECT ambient_conf FROM conf WHERE mac='{mac}'"
            c.execute(query)
            res = c.fetchone()
            if res != None :
                return res[0]
            return ""

        except sqlite3.Error as e:
            C.logger.error(f"[getAmbientIndex] {e}")
            return None

        except TypeError as e:
            C.logger.error(f"[getAmbientIndex] {e}")
            return None
       
    def numNode(self) -> int :
        """ confにあるnodeの個数
        Returns:
            int: NODEの個数
        """ 
        #C.logger.debug(f"numNode()")
        c = self.connection.cursor()
        try :
            query = f"SELECT COUNT(*) FROM conf WHERE node LIKE'LORA__'"
            c.execute(query)
            res = c.fetchone()
            return int(res[0])-1

        except sqlite3.Error as e:
            C.logger.error(f"[numNode] ERROR: {e}")
            return 0

    def getNodeNo( self, mac ) -> int :
        """ センサーMACがぶら下がっているNODEのNOを返す
        Args:
            mac (str): センサーMAC
        Returns:
            int: NodeNO (-1はエラー)
        """
        #C.logger.debug(f"getNodeNo()") ## 表示うるさい
        c = self.connection.cursor()
        try :
            query = f"SELECT node FROM conf WHERE mac = '{mac}'"
            c.execute(query)
            res = c.fetchone()
            if res != None :
                return int(res[0])

        except sqlite3.Error as e:
            C.logger.error(f"[getNodeNo] ERROR: {e}")
            return -1


# -----------------------------------------------------------------------------

    def _encode_notify(self,d):
        """内部関数 notifyのtupleをdictに変換
        Args:
            d (tuple): notifyテーブルのクエリー結果
        Returns:
            dict: dict形式
        """
        if( d == None ): return None
        ret = {}
        ret['node'] = d[0]
        ret['mac'] = d[1]
        ret['date'] = d[2]
        ret['lost_date'] = d[3]
        ret['status'] = int(d[4])
        ret['count'] = int(d[5])
        ret['notify'] = int(d[6])
        return ret

    def _encode_data_latest_node(self,d):
        """内部関数 センサーデーターhistoryのtupleをdictに変換 node用（
        Args:
            d (tuple): hisoty,latestテーブルのクエリー結果
        Returns:
            dict: dict形式
        """
        if( d == None ): return None
        #C.logger.debug(f"ENC -> {d}")
        ret = {}
        ret['mac'] = d[0]
        ret['date'] = d[1]
        ret['node'] = d[2]
        ret['templ'] = d[3]
        ret['humid'] = d[4]
        ret['batt'] = d[5]
        ret['rssi'] = d[6]
        ret['ext'] = d[7]
        ret['light'] = d[8]
        ret['status'] = int(d[9]) if d[9] != None else -1
        return ret

    def _encode_data_latest(self,d):
        """内部関数 センサーデーターlatestのtupleをdictに変換
        Args:
            d (tuple): hisoty,latestテーブルのクエリー結果
        Returns:
            dict: dict形式
        """
        if( d == None ): return None
        #C.logger.debug(f"ENC -> {d}")
        ret = {}
        ret['mac'] = d[0]
        ret['date'] = d[1]
        ret['node'] = d[2]
        ret['templ'] = d[3]
        ret['humid'] = d[4]
        ret['batt'] = d[5]
        ret['rssi'] = d[6]
        ret['ext'] = d[7]
        ret['light'] = d[8]
        ret['status'] = int(d[9]) if d[9] != None else -1
        ret['ambient_conf'] = d[10]
        return ret

    def __del__(self):
        #C.logger.debug("[SQL] call del()")
        self.connection.close()


if __name__ == '__main__':
    import sys
    import pprint
    args = sys.argv
    S = None

    if len(args) != 1 and args[1].upper() == 'CLEAR' :
        print("DATABSE Clear All TABLEs ")
        ret = input("Aer you OK? yes/[No]")
        if ret.upper() == 'YES' :
            S = SQL("clear")
            del S
            print("clear!!")
        else : print("Abort...")
        sys.exit()

    elif len(args) != 1 and args[1].upper() == 'CONFIG' :
        print("setup System Configuration")
        import SAST_observer as O
        O._getSetting4GApps(verbose=True)
        sys.exit()

    elif len(args) != 1 and args[1].upper() == "STATUS" :
        print("TEST status")
        S = SQL("startup")
        for i in range(0,6):
            S.changeNodeStatus(i)
            print(S.getNodeStatus())
        S.createTables('startup')
        print(S.getNodeStatus())
        sys.exit(0)

    elif len(args) != 1 and args[1].upper() == "VALID" :
        S = SQL()
        print("Valid MACs")
        pprint.pprint(f"Valid TRUE  : {S._getSensors(valid=True)}")
        pprint.pprint(f"Valid FALSE : {S._getSensors(valid=False)}")

    elif len(args) != 1 and args[1].upper() == "WARN" :
        S = SQL()
        print("WARN Info")
        for mac in S._getSensors(valid=True) :
            lw, lc, hc, hw = S._getThreshold(mac)
            pprint.pprint(f"{mac} -- {lw},{lc},{hc},{hw}")

    elif len(args) != 1 and args[1].upper() == "SENSINFO" :
        S = SQL()
        print("SENS Info")
        macs = S._getSensors(True)
        for mac in macs :
            name, node_name, node_no , warn= S.getSensorInfo(mac)
            pprint.pprint(f"{mac}-{name},{node_name},{node_no} {warn}")

    elif len(args) != 1 and args[1].upper() == "AMBIENT" :
        S = SQL()
        print("AMBIENT Info")
        num = S.numNode()
        for no in range( 1, num+1) :
            amb = S.getAmbientInfo(no)
            pprint.pprint(f"LORA{no:02} -- {amb}")

    elif len(args) != 1 and args[1].upper() == "DISCORD" :
        S = SQL()
        print("Discord Token LIST")
        num = S.numNode()
        for no in range( 1, num+1) :
            discord = S.getDiscord(no)
            pprint.pprint(f"LORA{no:02} -- {discord}")

    elif len(args) != 1 and args[1].upper() == "LATEST" :
        S = SQL()
        print("view Latest")
        res = S.getLatestAll(delete=False)
        for r in res :
            pprint.pprint(r)

    elif len(args) != 1 and args[1].upper() == "NODE_RSSI" :
        S = SQL()
        print("node RSSI")
        ret = S.getNodeRSSI()
        num = S.numNode()
        print(f"node:{num}")
        pprint.pprint(ret)
    
    elif len(args) != 1 and args[1].upper() == "AMB_INDEX" :
        S = SQL()
        print("Ambient Index")
        MACs = S._getSensors()
        for mac in S._getSensors() :
            index = S.getAmbientIndex(mac)
            print(f"{mac}: {index}")

    elif len(args) != 1 and args[1].upper() == "SPAN_TIME" :
        S = SQL()
        print("Span Time")
        tstr = "2025-01-22 22:47:09"
        td = C.spanTimeforSTR(tstr)
        tdd = datetime.timedelta(hours=1)
        print(td )
        print(tdd)
        print(td <= tdd)

    elif len(args) != 1 and args[1].upper() == "NUMSENS" :
        S = SQL()
        print("num Of Sensors")
        num= S.numSensorsMe()
        print(f"sensors->{num}")

    elif len(args) != 1 and args[1].upper() == "ARRIVE" :
        S = SQL()
        print("Arrive Node")
        for node in range(1, S.numNode()+1) :
            print(f"NODE:{node} is {S.isArriveNode(node)}")


    print("libSQL not oprateed.")
