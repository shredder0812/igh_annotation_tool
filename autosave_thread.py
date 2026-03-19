from PyQt5.QtCore import QThread, pyqtSignal


class AutoSaveThread(QThread):
    save_completed = pyqtSignal()

    def __init__(self, interval_sec: int = 10, parent=None):
        super(AutoSaveThread, self).__init__(parent)
        self.interval_sec = max(1, int(interval_sec))
        self.auto_save_enabled = False
        self._running = True

    def run(self):
        while self._running:
            if self.auto_save_enabled:
                self.save_completed.emit()
            self.sleep(self.interval_sec)

    def set_enabled(self, enabled: bool):
        self.auto_save_enabled = enabled

    def stop(self):
        self._running = False
