
import sys
import time
import os.path

from PyQt5.QtWidgets import (QFileDialog, QDialog, QLabel, QAction)
from PyQt5.QtWidgets import QMessageBox

from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import QUrl, Qt, pyqtSlot

from . import ui_settings
from ..appsettings import *

class SettingsDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)

        self.app = app
        self.sManager = self.app.settingsMgr

        self.ui = ui_settings.Ui_SettingsDialogForm()
        self.ui.setupUi(self)
        self.ui.groupBoxDaemon.toggled.connect(self.onDaemonToggle)
        self.ui.changeDownloadsPathButton.clicked.connect(self.onChangeDownloadsPath)

        self.loadSettings()

    def enableGroupDaemon(self):
        self.ui.groupBoxIpfsConn.setEnabled(False)
        self.ui.groupBoxDaemon.setEnabled(True)
        self.ui.groupBoxDaemon.setChecked(True)

    def enableGroupCustom(self):
        self.ui.groupBoxIpfsConn.setEnabled(True)
        self.ui.groupBoxDaemon.setChecked(False)

    def onChangeDownloadsPath(self):
        result = QFileDialog.getExistingDirectory(None,
            self.tr('Select directory'), os.getenv('HOME'),
            QFileDialog.ShowDirsOnly)
        if result:
            self.ui.downloadsLocation.setText(result)
            self.setS(CFG_SECTION_BROWSER, CFG_KEY_DLPATH, result)

    def onDaemonToggle(self, on):
        if on:
            self.enableGroupDaemon()
        else:
            self.enableGroupCustom()

    def getS(self, section, key, type=None):
        return self.sManager.getSetting(section, key, type=type)

    def isChecked(self, w):
        return w.checkState() == Qt.Checked

    def setChecked(self, w, bVal):
        if bVal is True:
            w.setCheckState(Qt.Checked)
        else:
            w.setCheckState(Qt.Unchecked)

    def setS(self, section, key, value):
        return self.sManager.setSetting(section, key, value)

    def loadSettings(self):
        # IPFSD
        section = CFG_SECTION_IPFSD
        ipfsdEnabled = self.sManager.isTrue(section, CFG_KEY_ENABLED)

        if ipfsdEnabled:
            self.enableGroupDaemon()
        else:
            self.enableGroupCustom()

        self.ui.ipfsdSwarmPort.setValue(
                self.getS(section, CFG_KEY_SWARMPORT, int))
        self.ui.ipfsdApiPort.setValue(
                self.getS(section, CFG_KEY_APIPORT, int))
        self.ui.ipfsdGwPort.setValue(
                self.getS(section, CFG_KEY_HTTPGWPORT, int))
        self.ui.swarmMinConns.setValue(
                self.getS(section, CFG_KEY_SWARMLOWWATER, int))
        self.ui.swarmMaxConns.setValue(
                self.getS(section, CFG_KEY_SWARMHIGHWATER, int))
        self.ui.storageMax.setValue(
                self.getS(section, CFG_KEY_STORAGEMAX, int))

        # IPFS connection
        section = CFG_SECTION_IPFSCONN1
        self.ui.customIpfsHost.setText(
                self.getS(section, CFG_KEY_HOST, str))
        self.ui.customIpfsApiPort.setValue(
                self.getS(section, CFG_KEY_APIPORT, int))
        self.ui.customIpfsGwPort.setValue(
                self.getS(section, CFG_KEY_HTTPGWPORT, int))

        # Browser
        section = CFG_SECTION_BROWSER
        self.ui.home.setText(
                self.getS(section, CFG_KEY_HOMEURL, str))
        self.ui.downloadsLocation.setText(
                self.getS(section, CFG_KEY_DLPATH, str))
        self.setChecked(self.ui.goToHomePageOnOpen,
                self.sManager.isTrue(section, CFG_KEY_GOTOHOME))

	# UI
        section = CFG_SECTION_UI
        self.setChecked(self.ui.wrapFiles,
                self.sManager.isTrue(section, CFG_KEY_WRAPSINGLEFILES))
        self.setChecked(self.ui.wrapDirectories,
                self.sManager.isTrue(section, CFG_KEY_WRAPDIRECTORIES))
        self.setChecked(self.ui.hideHashes,
                self.sManager.isTrue(section, CFG_KEY_HIDEHASHES))

    def accept(self):
        section = CFG_SECTION_IPFSD

        if self.ui.groupBoxDaemon.isChecked():
            self.sManager.setTrue(section, CFG_KEY_ENABLED)
        else:
            self.sManager.setFalse(section, CFG_KEY_ENABLED)

        self.setS(section, CFG_KEY_SWARMPORT, self.ui.ipfsdSwarmPort.text())
        self.setS(section, CFG_KEY_APIPORT, self.ui.ipfsdApiPort.text())
        self.setS(section, CFG_KEY_HTTPGWPORT, self.ui.ipfsdGwPort.text())
        self.setS(section, CFG_KEY_SWARMLOWWATER, self.ui.swarmMinConns.text())
        self.setS(section, CFG_KEY_SWARMHIGHWATER, self.ui.swarmMaxConns.text())
        self.setS(section, CFG_KEY_STORAGEMAX, self.ui.storageMax.text())

        section = CFG_SECTION_IPFSCONN1
        self.setS(section, CFG_KEY_HOST, self.ui.customIpfsHost.text())
        self.setS(section, CFG_KEY_APIPORT, self.ui.customIpfsApiPort.text())
        self.setS(section, CFG_KEY_HTTPGWPORT, self.ui.customIpfsGwPort.text())

        section = CFG_SECTION_BROWSER
        self.setS(section, CFG_KEY_HOMEURL, self.ui.home.text())
        self.sManager.setBoolFrom(section, CFG_KEY_GOTOHOME,
                self.isChecked(self.ui.goToHomePageOnOpen))

        section = CFG_SECTION_UI
        self.sManager.setBoolFrom(section, CFG_KEY_WRAPSINGLEFILES,
                self.isChecked(self.ui.wrapFiles))
        self.sManager.setBoolFrom(section, CFG_KEY_WRAPDIRECTORIES,
                self.isChecked(self.ui.wrapDirectories))
        self.sManager.setBoolFrom(section, CFG_KEY_HIDEHASHES,
                self.isChecked(self.ui.hideHashes))

        self.sManager.sync()
        self.done(1)

    def reject(self):
        self.done(0)
