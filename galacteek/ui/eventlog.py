
import time
import json
import asyncio

from PyQt5.QtWidgets import (QTextEdit, QVBoxLayout, QHBoxLayout,
        QCheckBox, QPushButton)
from PyQt5.QtCore import QCoreApplication, Qt, QSaveFile, QIODevice

from galacteek import log
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ui.widgets import GalacteekTab
from galacteek.ui.helpers import *
from galacteek.core import jtraverse, asynclib

class EventLogWidget(GalacteekTab):
    """
    Widget to display IPFS log events
    """

    def __init__(self, gWindow):
        super().__init__(gWindow)

        self.logZone = QTextEdit()
        self.logZone.setReadOnly(True)

        self.saveButton = QPushButton('Save')
        self.saveButton.clicked.connect(self.onSave)
        self.clearButton = QPushButton('Clear')
        self.clearButton.clicked.connect(lambda: self.logZone.clear())

        layout = QVBoxLayout(self)
        hLayout = QHBoxLayout(self)

        self.checkCore = QCheckBox('Core events')
        self.checkCore.setCheckState(Qt.Checked)
        self.checkDht = QCheckBox('DHT events')
        self.checkBitswap = QCheckBox('Bitswap events')
        self.checkAll = QCheckBox('All events')

        hLayout.addWidget(self.checkCore)
        hLayout.addWidget(self.checkDht)
        hLayout.addWidget(self.checkBitswap)
        hLayout.addWidget(self.checkAll)
        hLayout.addWidget(self.clearButton)
        hLayout.addWidget(self.saveButton)

        layout.addLayout(hLayout)
        layout.addWidget(self.logZone)

        self.tskLog = self.app.task(self.logWatch)

    def onSave(self):
        fPath = saveFileSelect()
        if fPath:
            file = QSaveFile(fPath)

            if not file.open(QIODevice.WriteOnly):
                return messageBox('Cannot open file for writing')

            file.write(self.logZone.toPlainText().encode())
            file.commit()

    def displayEvent(self, event):
        self.logZone.append(json.dumps(event, indent=4))

    @ipfsOp
    async def logWatch(self, op):
        try:
            await op.client.log.level('all', 'info')

            async for event in op.client.log.tail():
                display = False
                parser = jtraverse.traverseParser(event)

                systems = [ parser.traverse('system'),
                    parser.traverse('Tags.system') ]

                if ('core' in systems or 'addrutil' in systems) and \
                        self.checkCore.isChecked():
                    display = True
                elif 'dht' in systems and self.checkDht.isChecked():
                    display = True
                elif 'bitswap' in systems and self.checkBitswap.isChecked():
                    display = True

                if self.checkAll.isChecked():
                    display = True

                if display is True:
                    self.displayEvent(event)

                await op.sleep()

        except asyncio.CancelledError as err:
            return
        except Exception as err:
            log.debug('Unknown error ocurred while reading ipfs log')

    def onClose(self):
        self.tskLog.cancel()
        return True