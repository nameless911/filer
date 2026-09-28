"""外から「状態を保存して終わって」と頼まれる窓口。

build.ps1 が、起動しっぱなしの exe を上書きする前に使う。強制終了ではなく、
こちらで状態を保存してから自分で終わるので、再起動後に同じ窓とタブが戻る。

名前付きパイプ \\\\.\\pipe\\Filer-<プロセスID> で待ち受ける。
プロセス ID を名前に含めるので、ソースから動かしている分と exe の分が混ざらない。

やり取りは UTF-8 の一行ずつ：
  → quit-for-restart <保存先のパス>
  ← ok                  保存した。これから終わる
  ← busy <理由>          今は終われない（ダイアログやメニューが開いている等）
"""

import os

from PySide6.QtNetwork import QLocalServer

_SERVER = None


def server_name(pid=None):
    return f"Filer-{pid or os.getpid()}"


def start(on_quit_request):
    """待ち受けを始める。on_quit_request(path) は None（受けた）か理由の文字列を返す。

    受けたときは on_quit_request の中で保存まで済ませ、終了は返答の後に行う。
    """
    global _SERVER
    if _SERVER is not None:
        return
    server = QLocalServer()
    QLocalServer.removeServer(server_name())
    if not server.listen(server_name()):
        return   # 窓口が作れなくても本体は動かす。ビルド側は窓を閉じる方法に切り替える。

    def on_connection():
        sock = server.nextPendingConnection()
        if sock is None:
            return

        def on_ready():
            if not sock.canReadLine():
                return
            line = bytes(sock.readLine()).decode("utf-8", errors="replace").strip()
            cmd, _, arg = line.partition(" ")
            if cmd != "quit-for-restart":
                reply, accepted = f"busy 知らない頼みです: {cmd}", False
            else:
                reason = on_quit_request(arg.strip() or None)
                reply, accepted = ("ok", True) if reason is None else (f"busy {reason}", False)
            sock.write((reply + "\n").encode("utf-8"))
            sock.flush()
            sock.waitForBytesWritten(1000)
            sock.disconnectFromServer()
            if accepted:
                from PySide6.QtWidgets import QApplication
                QApplication.quit()

        sock.readyRead.connect(on_ready)
        sock.disconnected.connect(sock.deleteLater)

    server.newConnection.connect(on_connection)
    _SERVER = server
