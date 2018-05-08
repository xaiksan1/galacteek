
import sys
import time
import os.path
import re

from PyQt5.QtWidgets import (QWidget, QFrame, QApplication, QMainWindow,
        QDialog, QLabel, QPushButton, QVBoxLayout, QAction,
        QMenu, QTabWidget, QInputDialog, QMessageBox, QToolButton, QFileDialog)

from PyQt5.QtPrintSupport import *

from PyQt5.QtCore import (QUrl, QIODevice, Qt, QCoreApplication, QObject,
    pyqtSignal, QMutex)
from PyQt5 import QtWebEngineWidgets, QtWebEngine, QtWebEngineCore
from PyQt5.QtWebEngineWidgets import QWebEngineDownloadItem
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt5.Qt import QByteArray
from PyQt5.QtGui import QClipboard, QPixmap, QIcon, QKeySequence

from yarl import URL
import cid

from galacteek.ipfs.wrappers import *

from . import ui_browsertab
from . import galacteek_rc
from .helpers import *
from .dialogs import *
from .bookmarks import *
from .i18n import *
from .widgets import *
from ..appsettings import *
from galacteek.ipfs import cidhelpers

SCHEME_DWEB = 'dweb'
SCHEME_FS = 'fs'

# i18n
def iOpenInTab():
    return QCoreApplication.translate('BrowserTabForm', 'Open link in tab')
def iOpenWith():
    return QCoreApplication.translate('BrowserTabForm', 'Open with')
def iDownload():
    return QCoreApplication.translate('BrowserTabForm', 'Download')
def iPin():
    return QCoreApplication.translate('BrowserTabForm', 'PIN')
def iPinThisPage():
    return QCoreApplication.translate('BrowserTabForm', 'PIN (this page)')
def iPinRecursive():
    return QCoreApplication.translate('BrowserTabForm', 'PIN (recursive)')
def iFollow():
    return QCoreApplication.translate('BrowserTabForm',
        'Follow IPNS resource')

def iEnterIpfsCID():
    return QCoreApplication.translate('BrowserTabForm', 'Enter an IPFS CID')

def iBrowseHomePage():
    return QCoreApplication.translate('BrowserTabForm',
        'Go to home page')

def iBrowseIpfsCID():
    return QCoreApplication.translate('BrowserTabForm',
        'Browse IPFS resource (CID)')

def iBrowseIpfsMultipleCID():
    return QCoreApplication.translate('BrowserTabForm',
        'Browse multiple IPFS resources (CID)')

def iEnterIpfsCIDDialog():
    return QCoreApplication.translate('BrowserTabForm',
        'Load IPFS CID dialog')

def iFollowIpnsDialog():
    return QCoreApplication.translate('BrowserTabForm',
        'IPNS add feed dialog')

def iBrowseIpnsHash():
    return QCoreApplication.translate('BrowserTabForm',
        'Browse IPNS resource from hash/name')

def iEnterIpns():
    return QCoreApplication.translate('BrowserTabForm',
        'Enter an IPNS hash/name')

def iEnterIpnsDialog():
    return QCoreApplication.translate('BrowserTabForm',
        'Load IPNS key dialog')

def iBookmarked(path):
    return QCoreApplication.translate('BrowserTabForm',
        'Bookmarked {0}').format(path)

def iBookmarkTitleDialog():
    return QCoreApplication.translate('BrowserTabForm',
        'Bookmark title')

def iInvalidUrl(text):
    return QCoreApplication.translate('BrowserTabForm',
        'Invalid URL')

def iInvalidCID(text):
    return QCoreApplication.translate('BrowserTabForm',
        '{0} is an invalid IPFS CID (Content IDentifier)').format(text)

def fsPath(path):
    return '{0}:{1}'.format(SCHEME_FS, path)
def isFsNs(url):
    return url.startswith('{0}:/'.format(SCHEME_FS))

class IPFSSchemeHandler(QtWebEngineCore.QWebEngineUrlSchemeHandler):
    def __init__(self, app, parent=None):
        QtWebEngineCore.QWebEngineUrlSchemeHandler.__init__(self, parent)
        self.app = app

    def requestStarted(self, request):
        gatewayUrl = self.app.gatewayUrl
        url = request.requestUrl()
        scheme = url.scheme()
        path = url.path()

        def redirectIpfs():
            yUrl = URL(url.toString())
            if len(yUrl.parts) < 3:
                messageBox(iInvalidUrl())
                return None

            newurl = QUrl("{0}/{1}".format(gatewayUrl, url.path()))
            return request.redirect(newurl)

        def redirectIpns():
            yUrl = URL(url.toString())
            if len(yUrl.parts) < 3:
                messageBox(iInvalidUrl())
                return None

            newurl = QUrl("{0}/{1}".format(gatewayUrl, url.path()))
            return request.redirect(newurl)

        if scheme == SCHEME_FS or scheme == SCHEME_DWEB:
            # Handle fs:/{ipfs,ipns}/path and dweb:/{ipfs,ipns}/path

            if path.startswith("/ipfs/"):
                return redirectIpfs()
            if path.startswith("/ipns/"):
                return redirectIpns()

class RequestInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl()

class WebView(QtWebEngineWidgets.QWebEngineView):
    def __init__(self, browserTab, parent = None):
        super(QtWebEngineWidgets.QWebEngineView, self).__init__(parent = parent)

        self.mutex = QMutex()
        self.browserTab = browserTab

    def contextMenuEvent(self, event):
        currentPage = self.page()
        contextMenuData = currentPage.contextMenuData()
        menu = self.page().createStandardContextMenu()
        actions = menu.actions()
        menu.addSeparator()

        act1 = menu.addAction(iOpenInTab(), lambda:
                self.openInTab(contextMenuData))
        act1 = menu.addAction(iDownload(), lambda:
                self.downloadLink(contextMenuData))
        ipfsMenu = QMenu('IPFS')
        ipfsMenu.setIcon(getIcon('ipfs-logo-128-black.png'))
        menu.addMenu(ipfsMenu)
        act = ipfsMenu.addAction(getIcon('pin.png'), iPin(), lambda:
                self.pinPage(contextMenuData))
        openWithMenu = QMenu(iOpenWith())
        openWithMenu.addAction('Media player', lambda:
                self.openWithMediaPlayer(contextMenuData))
        menu.addMenu(openWithMenu)

        menu.exec(event.globalPos())

    def openWithMediaPlayer(self, menudata):
        url = menudata.linkUrl()
        self.browserTab.gWindow.addMediaPlayerTab(url.path())

    def pinPage(self, menudata):
        url = menudata.linkUrl()
        path = url.path()
        self.browserTab.pinPath(path, recursive=False)

    def openInTab(self, menudata):
        url = menudata.linkUrl()
        tab = self.browserTab.gWindow.addBrowserTab()
        tab.enterUrl(url)

    def downloadLink(self, menudata):
        url = menudata.linkUrl()
        self.page().download(url, None)

    def createWindow(self, wtype):
        pass

class BrowserKeyFilter(QObject):
    bookmarkPressed = pyqtSignal()
    savePagePressed = pyqtSignal()

    def eventFilter(self,  obj,  event):
        if event.type() == QEvent.KeyPress:
            modifiers = event.modifiers()

            key = event.key()
            if modifiers & Qt.ControlModifier:
                if key == Qt.Key_B:
                    self.bookmarkPressed.emit()
                    return True
                if key == Qt.Key_S:
                    self.savePagePressed.emit()
                    return True
        return False

class BrowserTab(GalacteekTab):
    # signals
    ipfsPathVisited = pyqtSignal(str)

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.ui = ui_browsertab.Ui_BrowserTabForm()
        self.ui.setupUi(self)

        # Install scheme handler early on
        self.webProfile = QtWebEngineWidgets.QWebEngineProfile.defaultProfile()
        self.installIpfsSchemeHandler()

        self.ui.webEngineView = WebView(self)

        self.ui.vLayoutBrowser.addWidget(self.ui.webEngineView)

        self.ui.webEngineView.urlChanged.connect(self.onUrlChanged)
        self.ui.webEngineView.loadFinished.connect(self.onLoadFinished)
        self.ui.webEngineView.iconChanged.connect(self.onIconChanged)
        self.ui.webEngineView.loadProgress.connect(self.onLoadProgress)

        self.ui.urlZone.returnPressed.connect(self.onUrlEdit)
        self.ui.backButton.clicked.connect(self.backButtonClicked)
        self.ui.forwardButton.clicked.connect(self.forwardButtonClicked)
        self.ui.refreshButton.clicked.connect(self.refreshButtonClicked)
        self.ui.loadFromClipboardButton.clicked.connect(self.loadFromClipboardButtonClicked)
        self.ui.bookmarkPageButton.clicked.connect(self.onBookmarkPage)

        # Setup the tool button for browsing IPFS content
        self.loadIpfsMenu = QMenu()
        self.loadIpfsCIDAction = QAction(getIconIpfsIce(),
                iBrowseIpfsCID(),self,
                shortcut=QKeySequence('Ctrl+l'),
                triggered=self.onLoadIpfsCID)
        self.loadIpfsMultipleCIDAction = QAction(getIconIpfsIce(),
                iBrowseIpfsMultipleCID(), self,
                triggered=self.onLoadIpfsMultipleCID)
        self.loadIpnsAction = QAction(getIconIpfsWhite(),
                iBrowseIpnsHash(),self,
                triggered=self.onLoadIpns)
        self.followIpnsAction = QAction(getIconIpfsWhite(),
                iFollow(),self,
                triggered=self.onFollowIpns)
        self.loadHomeAction = QAction(getIcon('go-home.png'),
                iBrowseHomePage(),self,
                triggered=self.onLoadHome)

        self.loadIpfsMenu.addAction(self.loadIpfsCIDAction)
        self.loadIpfsMenu.addAction(self.loadIpfsMultipleCIDAction)
        self.loadIpfsMenu.addAction(self.loadIpnsAction)
        self.loadIpfsMenu.addAction(self.followIpnsAction)
        self.loadIpfsMenu.addAction(self.loadHomeAction)

        self.ui.loadIpfsButton.setMenu(self.loadIpfsMenu)
        self.ui.loadIpfsButton.setPopupMode(QToolButton.MenuButtonPopup)
        self.ui.loadIpfsButton.clicked.connect(self.onLoadIpfsCID)

        self.ui.pinAllButton.setCheckable(True)
        self.ui.pinAllButton.setAutoRaise(True)
        self.ui.pinAllButton.setChecked(self.gWindow.pinAllGlobalChecked)
        self.ui.pinAllButton.toggled.connect(self.onToggledPinAll)

        # Prepare the pin combo box
        iconPin = getIcon('pin.png')
        self.ui.actionComboBox.insertItem(0, iPinThisPage())
        self.ui.actionComboBox.setItemIcon(0, iconPin)
        self.ui.actionComboBox.insertItem(1, iPinRecursive())
        self.ui.actionComboBox.setItemIcon(1, iconPin)
        self.ui.actionComboBox.activated.connect(self.actionComboClicked)

        # Event filter
        evfilter = BrowserKeyFilter(self)
        evfilter.bookmarkPressed.connect(self.onBookmarkPage)
        self.installEventFilter(evfilter)

        self.ipfsPathVisited.connect(self.onPathVisited)

        self.currentUrl = None
        self.currentIpfsResource = None

    @property
    def webView(self):
        return self.ui.webEngineView

    @property
    def tabPage(self):
        return self.gWindow.ui.tabWidget.widget(self.tabPageIdx)

    @property
    def tabPageIdx(self):
        return self.gWindow.ui.tabWidget.indexOf(self)

    @property
    def gatewayAuthority(self):
        return self.app.gatewayAuthority

    @property
    def gatewayUrl(self):
        return self.app.gatewayUrl

    @property
    def pinAll(self):
        return self.ui.pinAllButton.isChecked()

    def installIpfsSchemeHandler(self):
        baFs   = QByteArray(b'fs')
        baDweb = QByteArray(b'dweb')

        for scheme in [baFs, baDweb]:
            eHandler = self.webProfile.urlSchemeHandler(scheme)
            if not eHandler:
                self.webProfile.installUrlSchemeHandler(scheme,
                    self.app.ipfsSchemeHandler)

    def onPathVisited(self, path):
        # Called after a new IPFS object has been loaded in this tab
        self.app.task(self.tsVisitPath, path)

    @ipfsStatOp
    async def tsVisitPath(self, ipfsop, path, stat):
        # If automatic pinning is checked we pin the object
        if self.pinAll is True:
            self.pinPath(path, recursive=False, notify=False)

    def onToggledPinAll(self, checked):
        pass

    def onSavePage(self):
        page = self.webView.page()

        result = QFileDialog.getSaveFileName(None,
            'Select file',
            self.app.settingsMgr.getSetting(CFG_SECTION_BROWSER,
                CFG_KEY_DLPATH), '(*.*)')
        if not result:
            return

        page.save(result[0], QWebEngineDownloadItem.CompleteHtmlSaveFormat)

    def onBookmarkPage(self):
        if self.currentIpfsResource:
            addBookmark(self.app.marksLocal,
                    self.currentIpfsResource,
                    self.currentPageTitle,
                    stats=self.app.ipfsCtx.objectStats.get(
                        self.currentIpfsResource, {}))

    def onPinSuccess(self, f):
        self.app.systemTrayMessage('PIN', iPinSuccess(f.result()))

    def pinPath(self, path, recursive=True, notify=True):
        async def pinCoro(client, path):
            pinner = self.app.pinner
            onSuccess = None
            if notify is True:
                onSuccess = self.onPinSuccess
            await pinner.enqueue(path, recursive, onSuccess)

        self.app.ipfsTask(pinCoro, path)

    def printButtonClicked(self):
        # TODO: reinstate the printing button
        printer = QPrinter()
        dialog = QPrintDialog(printer, self)
        dialog.setModal(True)

        def success(ok):
            return ok

        if dialog.exec_() == QDialog.Accepted:
            currentPage = self.ui.webEngineView.page()
            currentPage.print(printer, success)

    def actionComboClicked(self, idx):
        if not self.currentIpfsResource:
            return
        if idx == 0:
            self.pinPath(self.currentIpfsResource, recursive=False)
        if idx == 1:
            self.pinPath(self.currentIpfsResource, recursive=True)

    def loadFromClipboardButtonClicked(self):
        clipboardSelection = self.app.clipboard().text(QClipboard.Selection)
        if not cidhelpers.cidValid(clipboardSelection):
            return messageBox(iInvalidCID(clipboardSelection))
        self.browseIpfsHash(clipboardSelection)

    def onLoadIpfsCID(self):
        def onValidated(d):
            self.browseIpfsHash(d.getHash())

        runDialog(IPFSCIDInputDialog, title=iEnterIpfsCIDDialog(),
            accepted=onValidated)

    def onLoadIpfsMultipleCID(self):
        def onValidated(dlg):
            # Open a tab for every CID
            cids = dlg.getCIDs()
            for cid in cids:
                self.gWindow.addBrowserTab().browseIpfsHash(cid)

        runDialog(IPFSMultipleCIDInputDialog,
            title=iEnterIpfsCIDDialog(),
            accepted=onValidated)

    def onLoadIpns(self):
        text, ok = QInputDialog.getText(self,
                iEnterIpnsDialog(),
                iEnterIpns())
        if ok:
            self.browseIpnsHash(text)

    def onFollowIpns(self):
        runDialog(AddFeedDialog, self.app.marksLocal,
            self.currentIpfsResource,
            title=iFollowIpnsDialog())

    def onLoadHome(self):
        self.loadHomePage()

    def loadHomePage(self):
        homeUrl = self.app.settingsMgr.getSetting(CFG_SECTION_BROWSER,
            CFG_KEY_HOMEURL)
        self.enterUrl(QUrl(homeUrl))

    def refreshButtonClicked(self):
        self.ui.webEngineView.reload()

    def backButtonClicked(self):
        currentPage = self.ui.webEngineView.page()
        currentPage.history().back()

    def forwardButtonClicked(self):
        currentPage = self.ui.webEngineView.page()
        currentPage.history().forward()

    def onUrlChanged(self, url):
        if url.authority() == self.gatewayAuthority:
            self.currentIpfsResource = url.path()
            self.ui.urlZone.clear()
            # Content loaded from IPFS gateway, this is IPFS content
            self.ui.urlZone.insert(fsPath(url.path()))
            self.ipfsPathVisited.emit(self.currentIpfsResource)

            # Activate the follow action if this is IPNS
            # todo: better check on ipns path validity
            if self.currentIpfsResource.startswith('/ipns/'):
                self.followIpnsAction.setEnabled(True)
            else:
                self.followIpnsAction.setEnabled(False)
        else:
            self.ui.urlZone.clear()
            self.ui.urlZone.insert(url.toString())

    def onLoadFinished(self, ok):
        currentPageTitle = self.ui.webEngineView.page().title()
        if currentPageTitle.startswith(self.gatewayAuthority):
            currentPageTitle = 'No title'

        self.currentPageTitle = currentPageTitle

        idx = self.gWindow.ui.tabWidget.indexOf(self)
        self.gWindow.ui.tabWidget.setTabText(idx, currentPageTitle)

    def onIconChanged(self, icon):
        self.gWindow.ui.tabWidget.setTabIcon(self.tabPageIdx, icon)

    def onLoadProgress(self, progress):
        self.ui.progressBar.setValue(progress)

    def browseFsPath(self, path):
        self.enterUrl(QUrl('{0}:{1}'.format(SCHEME_FS, path)))

    def browseIpfsHash(self, ipfsHash):
        if not cidhelpers.cidValid(ipfsHash):
            return messageBox(iInvalidCID(ipfsHash))

        self.browseFsPath('/ipfs/{0}'.format(ipfsHash))

    def browseIpnsHash(self, ipnshash):
        self.browseFsPath('/ipns/{0}'.format(ipnshash))

    def enterUrl(self, url):
        self.ui.urlZone.clear()
        self.ui.urlZone.insert(url.toString())
        self.ui.webEngineView.load(url)

    def onUrlEdit(self):
        inputStr = self.ui.urlZone.text().strip()

        if cidhelpers.cidValid(inputStr):
            return self.browseIpfsHash(inputStr)

        if not inputStr.startswith(SCHEME_DWEB) and \
           not inputStr.startswith(SCHEME_FS):
            # Browse through ipns
            inputStr = '{0}:/ipns/{1}'.format(SCHEME_FS, inputStr)

        if isFsNs(inputStr):
            self.enterUrl(QUrl(inputStr))
