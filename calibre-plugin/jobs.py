"""Background subprocess runner with a streaming progress dialog."""

import os
import signal
import subprocess

from qt.core import (QDialog, QDialogButtonBox, QPlainTextEdit, QProgressBar,
                     QObject, QThread, Qt, QVBoxLayout, pyqtSignal)


class _Worker(QObject):
    """Runs the CLI in a thread, streaming stdout lines back to the GUI."""

    line = pyqtSignal(str)
    finished = pyqtSignal(int, str, str)  # returncode, output_path, full_log

    def __init__(self, cmd, env):
        QObject.__init__(self)
        self.cmd = cmd
        self.env = env
        self._proc = None

    def run(self):
        try:
            self._proc = subprocess.Popen(
                self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=self.env, start_new_session=True,
            )
        except Exception as e:  # noqa: BLE001 - report any launch failure
            self.finished.emit(-1, "", "Failed to launch command:\n%s" % e)
            return

        lines = []
        out_path = ""
        for raw in self._proc.stdout:
            text = raw.rstrip("\n")
            if text.startswith("OUTPUT_PATH\t"):
                out_path = text.split("\t", 1)[1]
                continue
            lines.append(text)
            self.line.emit(text)
        self._proc.wait()
        self.finished.emit(self._proc.returncode, out_path, "\n".join(lines))

    def abort(self):
        if self._proc and self._proc.poll() is None:
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    self._proc.terminate()
                except Exception:
                    pass


class ProgressDialog(QDialog):
    """Modal dialog showing live progress; inspect .returncode/.output_path after exec()."""

    def __init__(self, gui, cmd, env, title="Generating audio"):
        QDialog.__init__(self, gui)
        self.setWindowTitle(title)
        self.resize(680, 400)
        self.returncode = None
        self.output_path = ""
        self.full_log = ""
        self._running = True

        layout = QVBoxLayout(self)
        self.bar = QProgressBar(self)
        self.bar.setRange(0, 0)  # busy / indeterminate
        layout.addWidget(self.bar)

        self.log = QPlainTextEdit(self)
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        layout.addWidget(self.log)

        self.bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.bb.rejected.connect(self._on_button)
        layout.addWidget(self.bb)

        self._thread = QThread(self)
        self._worker = _Worker(cmd, env)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.line.connect(self._append)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    def _append(self, text):
        if text:
            self.log.appendPlainText(text)

    def _on_button(self):
        if self._running:
            self._worker.abort()
            self.bb.setEnabled(False)
            self._append("Cancelling…")
        else:
            self.accept()

    def _on_finished(self, rc, out_path, full_log):
        self.returncode = rc
        self.output_path = out_path
        self.full_log = full_log
        self._running = False
        self._thread.quit()
        self._thread.wait(3000)
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self._append("\nDone." if rc == 0 else "\nFailed (exit %s)." % rc)
        self.bb.setEnabled(True)
        self.bb.setStandardButtons(QDialogButtonBox.StandardButton.Close)

    def closeEvent(self, ev):
        # Don't let the window close (and orphan the thread) while running.
        if self._running:
            self._worker.abort()
            ev.ignore()
        else:
            ev.accept()
