#!C:\python27\pythonw.exe
# -*- coding: utf-8 -*-

"""
ZetCode PyQt4 tutorial 

In this example, we create a simple
window in PyQt4.

author: Jan Bodnar
website: zetcode.com 
last edited: October 2011
"""

# import ctypes
# ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

import sys, os
import time
import warnings
import read
from glob import glob
import base64, hashlib, re
import subprocess as sp
import pandas as pd
from threading import Thread
os.environ['PATH'] += ';C:\\Python27\\lib\\site-packages\\numpy\\core;C:\\Program Files\\PothosSDR\\bin;C:\\Program Files\\GTK2-Runtime Win64\\bin;C:\\Program Files\\GTK2-Runtime Win64\\bin;'
# munge current directory so that PyQt4 loads
project_path = os.path.join(os.path.abspath(os.curdir))
sys.path.insert(1,os.path.join(project_path,'grc'))
os.chdir(r'C:\Program Files\PothosSDR\bin')
from PyQt4 import QtGui,QtCore
os.chdir(project_path)
from Queue import Queue
import traceback as tb


name = 'swept_power_to_disk'
python_binary = r'C:\python27\pythonw.exe'
user_hash = base64.urlsafe_b64encode(hashlib.md5(os.environ['USERNAME']).digest()[:6]).replace('=','')

GR_IMPORT_ERROR_MESSAGE = """\
Cannot import gnuradio.

Is the model path environment variable set correctly?
    All OS: PYTHONPATH

Is the library path environment variable set correctly?
    Linux: LD_LIBRARY_PATH
    Windows: PATH
    MacOSX: DYLD_LIBRARY_PATH
"""

def data_timestamp(path, user_hash, kind='swept_power'):
    ''' return the time in seconds given by a file name
    '''
    time_fmt = '%Y-%m-%d_%Hh%Mm%Ss'

    timestamp = re.findall('%s.* ([0-9].*)\.%s.dat'%(user_hash,kind), path)
    if len(timestamp) == 0:
        return None
    return time.mktime(time.strptime(timestamp[0], time_fmt))

def die(error, message):
    msg = "{0}\n\n({1})".format(message, error)
    try:
        import gtk
        d = gtk.MessageDialog(
            type=gtk.MESSAGE_ERROR,
            buttons=gtk.BUTTONS_CLOSE,
            message_format=msg,
        )
        d.set_title(type(error).__name__)
        d.run()
        exit(1)
    except ImportError:
        exit(type(error).__name__ + '\n\n' + msg)


def check_gtk():
    try:
        warnings.filterwarnings("error")
        import pygtk
        pygtk.require('2.0')
        import gtk
        gtk.init_check()
        warnings.filterwarnings("always")
    except Exception as err:
        die(err, "Failed to initialize GTK. If you are running over ssh, "
                 "did you enable X forwarding and start ssh with -X?")


def check_gnuradio_import():
    try:
        from gnuradio import gr
    except ImportError as err:
        die(err, GR_IMPORT_ERROR_MESSAGE)


def check_blocks_path():
    if 'GR_DONT_LOAD_PREFS' in os.environ and not os.environ.get('GRC_BLOCKS_PATH', ''):
        die(EnvironmentError("No block definitions available"),
            "Can't find block definitions. Use config.conf or GRC_BLOCKS_PATH.")


def run_main():
    script_path = os.path.dirname(os.path.abspath(__file__))
    source_tree_subpath = "/grc/scripts"

    if not script_path.endswith(source_tree_subpath):
        # run the installed version
        from gnuradio.grc.main import main
    else:
        sys.path.insert(1, script_path[:-len(source_tree_subpath)])
        from grc.main import main
    exit(main())


class GuiUpdater(QtCore.QObject):
    addText = QtCore.pyqtSignal(str) 
    clearText = QtCore.pyqtSignal()
    updateRestartCount = QtCore.pyqtSignal(int)
    updateStatus = QtCore.pyqtSignal(str)
    updateStartTime = QtCore.pyqtSignal(float)
    stopped = QtCore.pyqtSignal()

class Runner(object):
    def __init__(self, owner_widget):
        self.owner_widget = owner_widget
        self.proc = None
        self.t0 = 0
        self.log_file_name = None

    def __getattribute__(self, name):
        obj = object.__getattribute__(self, name)

        def wrapper(*args, **kws):
            try:
                return obj(*args, **kws)
            except:
                msg = QtGui.QMessageBox()
                msg.setIcon(QtGui.QMessageBox.Critical)
                msg.setText("Stopping execution on the following exception:")
                msg.setInformativeText(tb.format_exc())
                msg.setWindowTitle("Error")
                msg.setStandardButtons(QtGui.QMessageBox.Ok)
                object.__getattribute__(self, 'stop')()
                msg.exec_()

        if callable(obj):
            return wrapper
        else:
            return obj

    # def _exception_dialog(self):

    def start(self):
        if self.proc is None:
            self.owner_widget._updater.clearText.emit()
            thread = Thread(target=lambda: self.watchdog())
            thread.start()

    def stop(self):
        self.owner_widget._updater.stopped.emit()
        proc = self.proc
        if proc is not None and proc.poll() is None:
            self.proc = None
            proc.kill()

    def get_first_filename(self, t0, file_pattern='data/%s*.swept_power.dat'%user_hash):
        recent_files = [p for p in glob(file_pattern) if data_timestamp(p, user_hash, 'swept_power') > t0]

        if len(recent_files) == 0:
            return None
        else:
            return recent_files[0]

    def merge_files_since(self, t0, file_pattern='data/%s*.swept_power.dat'%user_hash):
        ''' 
        '''        
        recent_files = [p for p in glob(file_pattern) if data_timestamp(p, user_hash, 'swept_power') > t0]

        if len(recent_files) > 1:
            for src_path in recent_files[1:]:
                read.swept_average_merge(src_path, recent_files[0])

    def watchdog(self):
        def redirect_output(pipe):
            for line in iter(pipe.readline, b''):
                self.owner_widget._updater.addText.emit(line)

                if self.log_file_name is None:
                    print os.path.abspath('.')
                    data_path = self.get_first_filename(self.t0)
                    if data_path is not None:
                        self.log_file_name = data_path[:-4]+'-log.txt'
                if self.log_file_name is not None:
                    with open(self.log_file_name, 'a') as stream:
                        stream.write('%f\t%s'%(time.time(),line))
                if 'entering initialization' in line:
	                self.owner_widget._updater.updateStatus.emit('Running')   

            pipe.close()

        def write_output(get):
            for line in iter(get, None):
                sys.stdout.write(line)

        restart_count = 0

        # prechecks borrowed from C:\\Program Files\\PothosSDR\\bin\\gnuradio_companion.py
        script_path = os.path.join(project_path, 'grc', name+'.py')
        short_fails = 0
        self.t0 = time.time()
        self.owner_widget._updater.updateStartTime.emit(self.t0)
        self.owner_widget._updater.updateRestartCount.emit(restart_count)
        self.owner_widget._updater.updateStatus.emit('Starting acquisition...')

        try:
            while True:
                respawn_t0 = time.time()

                self.proc = sp.Popen(
                    [python_binary, script_path],
                    shell=False,
                    # close_fds=True,
                    stdout=sp.PIPE,
                    # stdin=sp.PIPE,
                    stderr=sp.PIPE,
                    startupinfo=sp.STARTUPINFO(),
                    bufsize=1,
                    creationflags=sp.CREATE_NEW_PROCESS_GROUP,
                    # stderr=sp.PIPE
                )

                Thread(target=redirect_output, args=(self.proc.stderr,)).start()
                Thread(target=redirect_output, args=(self.proc.stdout,)).start()

                # Thread(
                #     target=write_output, args=(Queue().get,)
                #     ).start()


                try:
                    while True:
                        proc = self.proc

                        if proc is None or proc.poll() is not None:
                            restart_count = restart_count + 1
                            self.owner_widget._updater.updateRestartCount.emit(restart_count)
                            self.owner_widget._updater.updateStatus.emit('Restarting')
                            break

                        # limit each acquisition to no more than 1 day, then restart
                        if time.time()-self.t0 >= 24*60*60:
                            proc.kill()
                            time.sleep(2)

                            # merge previous output files
                            self.merge_files_since(self.t0)
                            self.t0 = time.time()

                            break

                        time.sleep(1)

                    if self.proc is None:
                        break

                except KeyboardInterrupt:
                    # end both the running acquisition and the loop on Ctrl+C
                    self.proc.kill()
                    break

                print time.time()-respawn_t0, short_fails

                if time.time()-respawn_t0 <= 12:  
                    if short_fails >= 3:
                        print '*** ERROR: monitoring quit in less than 10 s. Ending loop ***'
                        raise RuntimeError('spectrum monitoring failed quickly %i times. is the kit connected?'%short_fails)
                    else:
                        short_fails += 1
                else:
                    # continue
                    short_fails = 0

                self.merge_files_since(self.t0)
                time.sleep(1)

        finally:
            self.merge_files_since(self.t0)
            self.proc = None
            self.owner_widget._updater.updateStatus.emit('Stopped')


class Example(QtGui.QWidget):
    
    def __init__(self):
        super(Example, self).__init__()
        
        self.initUI()
        self.runner = Runner(self)
        self.runner.start()

    def initUI(self):
        self._text = QtGui.QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.document().setMaximumBlockCount(5000)
        self._text.setSizePolicy(
            QtGui.QSizePolicy.Expanding, 
            QtGui.QSizePolicy.Expanding)
        font = self._text.font()
        if hasattr(QtGui.QFont, "Monospace"):
            font.setStyleHint(QtGui.QFont.Monospace)
        else:
            font.setStyleHint(QtGui.QFont.Courier)
        font.setFamily("Courier")
        self._text_lines = 0
        self._text.setFont(font)
        self._updater = GuiUpdater()
        self._updater.addText.connect(self.add_text)
        self._updater.clearText.connect(self._text.clear)
        self._updater.stopped.connect(self._stopped)

        self._startButton = QtGui.QPushButton("Start", self)
        self._startButton.setDisabled(True)
        self._startButton.clicked.connect(self.onStartButtonPress)
        self._stopButton = QtGui.QPushButton("Stop", self)
        self._stopButton.clicked.connect(self.onStopButtonPress)

        self._label = QtGui.QLabel("", self)
        self._status = dict(status='Starting', restarts=0, start=time.time())
        self._updater.updateRestartCount.connect(self.set_restart_count)
        self._updater.updateStatus.connect(self.set_status)
        self._updater.updateStartTime.connect(self.set_start)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self._label)
        hbox.addStretch(1)
        hbox.addWidget(self._startButton)
        hbox.addWidget(self._stopButton)

        vbox = QtGui.QVBoxLayout()
        vbox.addStretch(1)
        vbox.addWidget(self._text,QtCore.Qt.AlignTop)
        vbox.addLayout(hbox)

        
        self.setLayout(vbox)        
        self.setGeometry(0,100, 1000, 500)
        self.setWindowTitle('COVID-19 Spectrum Monitor Controller')
        self.setWindowIcon(QtGui.QIcon('share/nist.png'))
    
        self.show()

    def _stopped(self, *args):
        self._stopButton.setDisabled(True)
        self._startButton.setDisabled(False)

    def set_restart_count(self, restarts):
        self._status['restarts'] = int(restarts)
        self.update_info()

    def set_status(self, status):
        self._status['status'] = str(status)
        self.update_info()

    def set_start(self, t0):
        self._status['start'] = float(t0)
        self.update_info()

    def update_info(self):
        if self._status['status'].lower() == 'running':
            elapsed = str(pd.Timedelta(round(time.time()-self._status['start']), unit='s'))
            args = self._status['status'], elapsed, self._status['restarts']
            info = '%s (%s elapsed) / %i respawns' % args
        else:
            info = self._status['status']
        self._label.setText(info)

    def add_text(self, text):
        self._text_lines += 1

        # if self._text_lines > 500:
        #     cursor = QtGui.QTextCursor(Q)
        #     cursor.movePosition(cursor.Start)
        #     cursor.movePosition(cursor.Down, cursorMoveAnchor, 0)
        #     cursor.select(cursor.LineUnderCursor)
        #     cursor.removeSelectedText()
        cursor = QtGui.QTextCursor(self._text.document())
        cursor.movePosition(cursor.End)     
        cursor.insertText(text)
        self._text.moveCursor(QtGui.QTextCursor.End)
        self.update_info()

    def onStartButtonPress(self, state):
        self._startButton.setDisabled(True)
        self.runner.start()
        self._stopButton.setDisabled(False)        

    def onStopButtonPress(self, state):
        self._stopButton.setDisabled(True)
        self.runner.stop()
        self._startButton.setDisabled(False)

    def closeEvent(self, event):
        self.runner.stop()
        time.sleep(0.5)
        event.accept()        

def main():
    # check_gnuradio_import()
    # check_gtk()
    # check_blocks_path()

    app = QtGui.QApplication(sys.argv)
    ex = Example()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()