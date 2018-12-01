import os.path
import uuid
import pkg_resources
from os import urandom
from datetime import datetime
from io import BytesIO

import aiofiles
import aioipfs
import asyncio

from PyQt5.QtCore import QObject, pyqtSignal

from galacteek import log, logUser, ensure
from galacteek.ipfs.mutable import MutableIPFSJson, CipheredIPFSJson
from galacteek.ipfs.dag import EvolvingDAG
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.encrypt import IpfsRSAAgent
from galacteek.core.asynclib import asyncReadFile
from galacteek.web import render


class UserInfos(CipheredIPFSJson):
    GENDER_MALE = 0
    GENDER_FEMALE = 1
    GENDER_UNSPECIFIED = -1

    def initObj(self):
        uid = str(uuid.uuid4())

        return {
            'userinfo': {
                'username': uid,
                'firstname': '',
                'lastname': '',
                'altname': '',
                'nickname': '',
                'gender': -1,
                'org': '',
                'email': '',
                'country': {
                    'code': '',
                    'name': '',
                },
                'city': '',
                'birthdate': '',
                'birthplace': '',
                'occupation': '',
                'telephone': '',
                'langs': [],
                'avatar': {
                    'cid': '',
                },
                'bio': '',
                'motto': '',
                'crypto': {
                    'rsa': {},
                    'gpg': {},
                },
                'resources': [],
                'peerid': '',
                'date': {
                    'created': datetime.now().isoformat(' ', 'seconds'),
                    'modified': datetime.now().isoformat(' ', 'seconds'),
                },
                'uid': uid,
                'locked': False,
                'schemav': 1,
            }
        }

    @property
    def uid(self):
        return self.parser.traverse('userinfo.uid')

    @property
    def peerid(self):
        return self.parser.traverse('userinfo.peerid')

    @property
    def avatarCid(self):
        return self.parser.traverse('userinfo.avatar.cid')

    @property
    def bio(self):
        return self.parser.traverse('userinfo.bio')

    @property
    def username(self):
        return self.parser.traverse('userinfo.username')

    @property
    def firstname(self):
        return self.parser.traverse('userinfo.firstname')

    @property
    def lastname(self):
        return self.parser.traverse('userinfo.lastname')

    @property
    def email(self):
        return self.parser.traverse('userinfo.email')

    @property
    def gender(self):
        return self.parser.traverse('userinfo.gender')

    @property
    def org(self):
        return self.parser.traverse('userinfo.org')

    @property
    def city(self):
        return self.parser.traverse('userinfo.city')

    @property
    def countryName(self):
        return self.parser.traverse('userinfo.country.name')

    @property
    def countryCode(self):
        return self.parser.traverse('userinfo.country.code')

    @property
    def locked(self):
        return self.parser.traverse('userinfo.locked')

    @property
    def identToken(self):
        return self.parser.traverse('userinfo.identtoken')

    @property
    def schemaVersion(self):
        return self.parser.traverse('userinfo.schemav')

    @property
    def objHash(self):
        if self.curEntry:
            return self.curEntry['Hash']

    def setAvatarCid(self, cid):
        if self.locked:
            return
        self.root['userinfo']['avatar']['cid'] = cid
        self.updateModifiedDate()
        self.changed.emit()

    def setCountryInfo(self, name, code):
        if self.locked:
            return
        sec = self.root['userinfo']['country']
        sec['name'] = name
        sec['code'] = code
        self.updateModifiedDate()
        self.changed.emit()

    def setInfos(self, **kw):
        if self.locked:
            return
        for key, val in kw.items():
            if key not in self.root['userinfo'].keys():
                continue
            self.root['userinfo'][key] = val
        self.updateModifiedDate()
        self.changed.emit()

    def updateModifiedDate(self):
        self.root['userinfo']['date']['modified'] = datetime.now().isoformat(
            ' ', 'seconds')

    def updateIdentToken(self):
        token = self.root['userinfo'].get('identtoken', None)
        if not token:
            self.root['userinfo']['identtoken'] = urandom(128).hex()
            self.changed.emit()

    def setLock(self, lock=False):
        self.root['userinfo']['locked'] = lock
        self.changed.emit()

    def valid(self):
        return True


class UserDAG(EvolvingDAG):
    def initDag(self):
        return {
            'index.html': 'Blank',
            'media': {
                'images': {},
            },
            'board': {
                'messages': []
            }
        }


class UserApp(QObject):
    def __init__(self, profile):
        super(UserApp, self).__init__(profile)

        self._profile = profile
        self.cssEntry = None

    @property
    def profile(self):
        return self._profile

    @property
    def dagRoot(self):
        return self.profile.dagUser.root

    def debug(self, msg):
        return self.profile.debug(msg)

    @ipfsOp
    async def postMessage(self, op, title, msg):
        async with self.profile.dagUser as dag:
            board = dag.dagRoot['board']
            newMsg = {
                'content': msg,
                'title': title,
                'date': datetime.now().isoformat(' ', 'minutes'),
            }
            board['messages'].append(newMsg)

        await self.update()

    @ipfsOp
    async def init(self, op):
        cssPath = pkg_resources.resource_filename('galacteek.templates',
                                                  'public/css')
        self.cssEntry = await op.addPath(cssPath, recursive=True)

    @ipfsOp
    async def update(self, op):
        homeIndex = await self.profile.tmplRender(
            'public/userhome.html',
            boardMessages=list(reversed(self.dagRoot['board']['messages'])),
            loop=self.profile.ctx.loop
        )

        async with self.profile.dagUser as dag:
            dag.root['index.html'] = dag.mkLink(homeIndex)
            if self.cssEntry:
                dag.root['css'] = dag.mkLink(self.cssEntry)

            if self.profile.userInfo.avatarCid != '':
                dag.root['media']['images']['avatar'] = dag.mkLink(
                    self.profile.userInfo.avatarCid)

            if self.profile.ctx.hasRsc('ipfs-cube-64'):
                dag.root['media']['images']['ipfs-cube.png'] = dag.mkLink(
                    self.profile.ctx.resources['ipfs-cube-64'])


class ProfileError(Exception):
    pass


class UserProfile(QObject):
    """ User profile object """

    P_FILES = 'files'

    def __init__(self, ctx, name, rootDir):
        super(UserProfile, self).__init__()

        self._ctx = ctx
        self._name = name
        self._rootDir = rootDir
        self._initialized = False

        self.keyRoot = 'galacteek.{}.root'.format(self.name)
        self.keyRootId = None

        self._rsaPrivKeyPath = os.path.join(
            self.ctx.app.cryptoDataLocation,
            'rsa_{0}_priv.key'.format(
                self.name))
        self._rsaPubKeyPath = os.path.join(self.ctx.app.cryptoDataLocation,
                                           'rsa_{0}_pub.key'.format(self.name))
        self._rsaPubKey = None

        self._filesModel = None

        self._dagUser = None
        self.userInfo = None

        self.rsaAgent = None

    def debug(self, msg):
        log.debug('Profile {0}: {1}'.format(self.name, msg))

    def userLogInfo(self, msg):
        logUser.info('profile ({0}): {1}'.format(self.name, msg))

    @property
    def initialized(self):
        return self._initialized

    @property
    def rsaExec(self):
        return self.ctx.rsaExec

    @property
    def rsaPrivKeyPath(self):
        return self._rsaPrivKeyPath

    @property
    def rsaPubKeyPath(self):
        return self._rsaPubKeyPath

    @property
    def rsaPubKey(self):
        return self._rsaPubKey

    @rsaPubKey.setter
    def rsaPubKey(self, key):
        self._rsaPubKey = key

    @property
    def dagUser(self):
        return self._dagUser  # the DAG for this user

    @property
    def root(self):
        return self._rootDir  # profile's root dir in the MFS

    @property
    def ctx(self):
        return self._ctx  # IPFS context

    @property
    def name(self):
        return self._name

    @property
    def filesModel(self):
        return self._filesModel

    @property
    def tree(self):
        # Profile's filesystem tree list
        return [
            self.pathFiles,
            self.pathHome,
            self.pathMedia,
            self.pathData,
            self.pathPlaylists,
            self.pathPictures,
            self.pathVideos,
            self.pathDocuments,
            self.pathMusic,
            self.pathCode,
        ]

    @property
    def pathFiles(self):
        return os.path.join(self.root, self.P_FILES)

    @property
    def pathHome(self):
        return os.path.join(self.pathFiles, 'home')

    @property
    def pathDocuments(self):
        return os.path.join(self.pathFiles, 'documents')

    @property
    def pathMedia(self):
        return os.path.join(self.pathFiles, 'multimedia')

    @property
    def pathPictures(self):
        return os.path.join(self.pathMedia, 'pictures')

    @property
    def pathVideos(self):
        return os.path.join(self.pathMedia, 'videos')

    @property
    def pathMusic(self):
        return os.path.join(self.pathMedia, 'music')

    @property
    def pathCode(self):
        return os.path.join(self.pathFiles, 'code')

    @property
    def pathWebsites(self):
        return os.path.join(self.pathFiles, 'websites')

    @property
    def pathEtc(self):
        return os.path.join(self.root, 'etc')

    @property
    def pathData(self):
        return os.path.join(self.root, 'data')

    @property
    def pathPlaylists(self):
        return os.path.join(self.pathData, 'playlists')

    @property
    def pathUserInfo(self):
        return os.path.join(self.pathData, 'userinfo.json.enc')

    @property
    def pathUserDagMeta(self):
        return os.path.join(self.pathData, 'dag.main')

    def setFilesModel(self, model):
        self._filesModel = model

    @ipfsOp
    async def init(self, ipfsop):
        """
        Initialize the profile's filesystem
        """

        self.userLogInfo('Initializing filesystem')

        await ipfsop.filesMkdir(self.root)

        for directory in self.tree:
            await ipfsop.filesMkdir(directory)

        self.userLogInfo('Initializing crypto')

        if not await self.cryptoInit():
            self.userLogInfo('Error while initializing crypto')
            raise ProfileError('Crypto init failed')

        keysNames = await ipfsop.keysNames()

        if self.keyRoot not in keysNames:
            self.userLogInfo('Generating main IPNS key')
            await ipfsop.keyGen(self.keyRoot)

        key = await ipfsop.keyFind(self.keyRoot)
        if key is not None:
            self.keyRootId = key.get('Id', None)

        self.debug('IPNS key({0}): {1}'.format(self.keyRoot, self.keyRootId))

        if self.userInfo.avatarCid == '' and self.ctx.hasRsc('ipfs-logo-ice'):
            self.userInfo.setAvatarCid(
                self.ctx.resources['ipfs-logo-ice']['Hash'])

        if self.userInfo.peerid == '':
            self.userInfo.root['userinfo']['peerid'] = self.ctx.node.id
            self.userInfo.changed.emit()

        if await ipfsop.hasDagCommand():
            self.userLogInfo('Loading DAG ..')
            self._dagUser = UserDAG(self.pathUserDagMeta, loop=self.ctx.loop)

            ensure(self.dagUser.load())
            await self.dagUser.loaded

            self.dagUser.changed.connect(self.onDagChange)

            self.app = UserApp(self)
            await self.app.init()
            ensure(self.update())
            self.userLogInfo('Loaded')
        else:
            self.debug('DAG api not available !')

        self._initialized = True
        self.userLogInfo('Initialization complete')
        self.userInfo.changed.connect(self.onUserInfoChanged)

    @ipfsOp
    async def cryptoInit(self, op):
        if not os.path.isfile(self.rsaPrivKeyPath) and \
                not os.path.isfile(self.rsaPubKeyPath):
            self.userLogInfo('Creating RSA keypair')

            privKey, pubKey = await self.rsaExec.genKeys()
            if privKey is None or pubKey is None:
                self.debug('RSA: keygen failed')
                return False

            try:
                async with aiofiles.open(self.rsaPrivKeyPath, 'w+b') as fd:
                    await fd.write(privKey)

                async with aiofiles.open(self.rsaPubKeyPath, 'w+b') as fd:
                    await fd.write(pubKey)
            except Exception as err:
                self.debug('RSA: could not save keys: {}'.format(str(err)))
                self.userLogInfo('Error while saving RSA keys!')
                return False
            else:
                self.userLogInfo('Successfully created RSA keypair')

        if not await self.cryptoRegisterKeys():
            self.debug('RSA: failed to register keys')
            return False

        return True

    @ipfsOp
    async def cryptoRegisterKeys(self, op):
        self.userLogInfo('Registering keys')
        try:
            pubKey = await asyncReadFile(self.rsaPubKeyPath)
            if pubKey is None:
                self.debug('RSA: could not read public key')
                raise Exception('pubkey error')
            self.rsaPubKey = pubKey
        except Exception as e:
            self.debug('RSA: error while importing keys {}'.format(str(e)))
            return False
        else:
            #
            # Tough decision here .. first mechanism tried for publishing the
            # peer's public key payload was to import the PEM key in the
            # repository and transmit the CID, which is neat and handy (other
            # peers just pin/fetch the key..) ATM embedding the key's payload
            # in the userinfo offers some advantages and we can always use
            # another system later on
            #
            self.rsaAgent = IpfsRSAAgent(self.rsaExec,
                                         self.rsaPubKey,
                                         self.rsaPrivKeyPath)

            self.userLogInfo('Loading user information')
            self.userInfo = UserInfos(self.pathUserInfo, self.rsaAgent)

            ensure(self.userInfo.load())
            await self.userInfo.evLoaded.wait()
            self.userInfo.updateIdentToken()

            rsaSection = self.userInfo.root['userinfo']['crypto'].setdefault(
                'rsa', {})
            prevPem = rsaSection.get('pubkeypem', None)
            rsaSection['pubkeypem'] = self.rsaPubKey.decode()

            if rsaSection['pubkeypem'] != prevPem:
                self.userInfo.changed.emit()

            return True

    @ipfsOp
    async def rsaEncryptSelf(self, op, data):
        return await self.rsaAgent.storeSelf(data)

    @ipfsOp
    async def rsaDecryptIpfsObj(self, op, cid):
        return await self.rsaAgent.decryptIpfsObject(cid)

    async def __rsaReadPrivateKey(self):
        log.debug('RSA: reading private key')
        return await asyncReadFile(self.rsaPrivKeyPath)

    def onUserInfoChanged(self):
        ensure(self.update())

    def onDagChange(self):
        ensure(self.publishDag())

    @ipfsOp
    async def publishDag(self, op):
        result = await op.publish(self.dagUser.dagCid, key=self.keyRoot)

        if result is None:
            self.debug('DAG publish failed: {}'.format(result))

    async def tmplRender(self, tmpl, **kw):
        """
        Render an HTML template (jinja), passing it the profile, ipfs context
        and the DAG
        """
        return await render.ipfsRender(tmpl,
                                       profile=self,
                                       ipfsCtx=self.ctx,
                                       dag=self.dagUser.dagRoot,
                                       **kw)

    @ipfsOp
    async def update(self, op):
        """
        Update the user's DAG
        """

        await self.dagUser.loaded
        await self.app.update()
