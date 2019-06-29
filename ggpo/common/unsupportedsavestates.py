# -*- coding: utf-8 -*-
import glob
import hashlib
import json
import os
import re
import urllib.request as Request
import urllib.parse as Parse
import time
from PyQt4 import QtCore
from ggpo.common.util import logdebug, findGamesavesDir, sha256digest


def readLocalJsonDigest():
    localJsonDigest = {}
    d = findGamesavesDir()
    if d:
        localjson = os.path.join(d, SyncWorker.JSON_INDEX_FILENAME)
        if os.path.isfile(localjson):
            # noinspection PyBroadException
            try:
                localJsonDigest = json.load(file(localjson).read())
            except:
                pass
        if not localJsonDigest:
            return writeLocalJsonDigest()
    return localJsonDigest


def writeLocalJsonDigest():
    localJsonDigest = {}
    d = findGamesavesDir()
    if d:
        localjson = os.path.join(d, SyncWorker.JSON_INDEX_FILENAME)
        for filename in glob.glob(os.path.join(d, '*.fs')):
            localJsonDigest[os.path.basename(filename)] = sha256digest(filename)
        # noinspection PyBroadException
        try:
            f = open(localjson, 'w')
            f.write(json.dumps(localJsonDigest, sort_keys=True, indent=2))
        except:
            pass
    return localJsonDigest


class SyncWorker(QtCore.QObject):
    sigFinished = QtCore.pyqtSignal(int, int, int)
    sigStatusMessage = QtCore.pyqtSignal(str)
    SAVESTATES_GITHUB_BASE_URL = 'https://raw.github.com/poliva/fightcadestates/newfba/'
    JSON_INDEX_FILENAME = 'index.json'
    SAVESTATES_INDEX_URL = SAVESTATES_GITHUB_BASE_URL + JSON_INDEX_FILENAME

    def __init__(self, checkonly=False):
        QtCore.QObject.__init__(self)
        self.checkonly = checkonly
        self.added = 0
        self.updated = 0
        self.nochange = 0

    def download(self):
        d = findGamesavesDir()
        if not d:
            self.sigStatusMessage.emit('Can\'t find Savestates Directory')
            self.sigFinished.emit(self.added, self.updated, self.nochange)
            return
        localJsonDigest = readLocalJsonDigest()
        # noinspection PyBroadException
        try:
            # gotta love CPython's GIL, yield thread
            time.sleep(0.05)
            response = Request.urlopen(self.SAVESTATES_INDEX_URL, timeout=3)
            games = json.load(response)

            for filename, shahash in games.items():
                if re.search(r'[^ .a-zA-Z0-9_-]', filename):
                    logdebug().error("Filename {} looks suspicious, ignoring".format(filename))
                    continue
                if filename in localJsonDigest:
                    if localJsonDigest[filename] == shahash:
                        self.nochange += 1
                        continue
                    else:
                        self.updated += 1
                else:
                    self.added += 1
                if not self.checkonly:
                    time.sleep(0.05)
                    localfile = os.path.join(d, filename)
                    fileurl = self.SAVESTATES_GITHUB_BASE_URL + Parse.quote(filename)
                    Request.urlretrieve(fileurl, localfile)
                    self.sigStatusMessage.emit('Downloaded {}'.format(localfile))
                    # remove config/games/<game>.fs
                    gamefs=os.path.abspath(os.path.join(d,"..","config","games",filename.replace("_ggpo.fs",".fs")))
                    if os.path.isfile(gamefs):
                        try:
                            os.remove(gamefs)
                        except:
                            pass
            if not self.checkonly:
                if not self.added and not self.updated:
                    #self.sigStatusMessage.emit('All files are up to date')
                    pass
                else:
                    writeLocalJsonDigest()
                    self.sigStatusMessage.emit(
                        '{} files are current, added {}, updated {}'.format(
                            self.nochange, self.added, self.updated))
        except Exception as ex:
            logdebug().error(str(ex))
        self.sigFinished.emit(self.added, self.updated, self.nochange)


# noinspection PyClassHasNoInit
class UnsupportedSavestates(QtCore.QObject):
    sigRemoteHasUpdates = QtCore.pyqtSignal(int, int, int)

    _thread = None
    _worker = None

    @classmethod
    def check(cls, mainWindow, statusMsgCallback=None, finishedCallback=None):
        cls.run(True, statusMsgCallback, finishedCallback)

    @classmethod
    def cleanup(cls, x, y, z):
        try:
            cls._thread.quit()
            cls._thread.wait()
        except:
            pass
        cls._thread = None
        cls._worker = None

    @classmethod
    def run(cls, checkonly, statusMsgCallback=None, finishedCallback=None):
        if cls._thread:
            logdebug().error('Already has a download thread running')
        cls._thread = QtCore.QThread()
        cls._worker = SyncWorker(checkonly)
        cls._worker.moveToThread(cls._thread)
        if finishedCallback:
            cls._worker.sigFinished.connect(finishedCallback)
        cls._worker.sigFinished.connect(cls.cleanup)
        if statusMsgCallback:
            cls._worker.sigStatusMessage.connect(statusMsgCallback)
        cls._thread.started.connect(cls._worker.download)
        cls._thread.start()

    @classmethod
    def sync(cls, statusMsgCallback=None, finishedCallback=None):
        cls.run(False, statusMsgCallback, finishedCallback)

