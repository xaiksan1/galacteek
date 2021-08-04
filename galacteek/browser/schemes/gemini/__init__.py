import ignition
from yarl import URL

from PyQt5.QtCore import QUrl

from galacteek import log
from galacteek.browser.schemes import BaseURLSchemeHandler
from galacteek.browser.schemes import SCHEME_GEMINI

from .gemtext import gemTextToHtml


class GeminiError(Exception):
    pass


class GeminiSchemeHandler(BaseURLSchemeHandler):
    """
    Simple Gemini URL scheme handler.

    Requests are made using the ignition library.
    """

    def geminiRequest(self, url: str):
        # Run in the thread executor
        try:
            response = ignition.request(url)
            data = response.data()
            return response, data
        except Exception as err:
            log.debug(f'Gemini request error for URL {url}: {err}')
            return None, None

    async def handleRequest(self, request, uid):
        rUrl = request.requestUrl()
        rInitiator = request.initiator()
        rMethod = bytes(request.requestMethod()).decode()
        host = rUrl.host()
        path = rUrl.path()

        if not host:
            return self.urlInvalid(request)

        # Build the URL, using the query params if present
        if rUrl.hasQuery():
            q = rUrl.query(QUrl.EncodeSpaces)
            url = ignition.url(
                f'{path}?{q}',
                f'//{host}'
            )
        else:
            url = ignition.url(path, f'//{host}')

        if not rInitiator.isEmpty():
            log.debug(f'{rMethod}: {url} (initiator: {rInitiator.toString()})')
        else:
            log.debug(f'{rMethod}: {url}')

        # Run the request in the app's executor
        response, data = await self.app.loop.run_in_executor(
            self.app.executor,
            self.geminiRequest,
            url
        )

        if not response or not data:
            return self.reqFailed(request)

        meta = response.meta

        if isinstance(data, bytes) and meta:
            # Raw file

            return self.serveContent(
                request.reqUid,
                request,
                meta,
                data
            )

        if response.is_a(ignition.InputResponse):
            # Gemini input, serve the form

            log.debug(f'{rMethod}: {url}: input requested')

            return await self.serveTemplate(
                request,
                'gemini_input.html',
                geminput=data,
                gemurl=url,
                title=url
            )
        elif response.is_a(ignition.RedirectResponse):
            # Redirects

            rInfo = data.strip()

            log.debug(f'{rMethod}: {url}: redirect spec is: {rInfo}')

            redirUrl = URL(rInfo)
            if not redirUrl.is_absolute():
                # Relative redirect

                if redirUrl.path.startswith('/'):
                    redirUrl = URL.build(
                        scheme=SCHEME_GEMINI,
                        host=host,
                        path=rInfo
                    )
                else:
                    redirUrl = URL(f'{url}/{rInfo}')

            log.debug(
                f'Gemini ({url}): redirecting to: {redirUrl}')

            return request.redirect(QUrl(str(redirUrl)))
        elif response.is_a(ignition.TempFailureResponse):
            return self.reqFailed(request)
        elif response.is_a(ignition.PermFailureResponse):
            return self.reqFailed(request)
        elif response.is_a(ignition.ClientCertRequiredResponse):
            return self.reqFailed(request)
        elif response.is_a(ignition.ErrorResponse):
            return self.reqFailed(request)

        try:
            if not response.success():
                raise GeminiError(
                    f'{response.url}: Invalid response: {response.status}')

            html, title = gemTextToHtml(data)

            if not html:
                raise GeminiError(f'{response.url}: gem2html failed')

            await self.serveTemplate(
                request,
                'gemini_capsule_render.html',
                gembody=html,
                gemurl=url,
                title=title if title else url
            )
        except Exception as err:
            log.debug(f'{rMethod}: {url}: error rendering capsule: {err}')

            return self.reqFailed(request)
