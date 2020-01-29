from selenium import webdriver
from lxml import html
try:
    import win32gui
except ImportError:
    win32gui = type('win32gui', (), {'__file__': None})

class FirefoxSession:
    """
    Wrapper for selenium driver that acts like a HTTP session
    """
    def __init__(self):
        self.driver = webdriver.Firefox()

    def get(self, url):
        self.driver.get(url)
        res = Response(url, self.driver.page_source)
        return res

    @property
    def current_response(self):
        return Response(self.driver.current_url, self.driver.page_source)

    @property
    def url(self):
        return self.driver.current_url

    def close(self):
        self.driver.close()

    def minimize(self):
        self.driver.minimize_window()

    def maximize(self):
        self.driver.maximize_window()

    def show(self, cmd_show=1):
        """
        Shows the window using the `cmd_show` style:

        cmd_show value : cmd_show constant name
        0: SW_HIDE
            Hides the window and activates another window.
        1: SW_SHOWNORMAL
            Activates and displays a window. If the window is minimized or
            maximized, the system restores it to its original size and
            position. An application should specify this flag when
            displaying the window for the first time.
        2: SW_SHOWMINIMIZED
            Activates the window and displays it as a minimized window.
        3: SW_MAXIMIZE
            Maximizes the specified window.
        3: SW_SHOWMAXIMIZED
            Activates the window and displays it as a maximized window.
        4: SW_SHOWNOACTIVATE
            Displays a window in its most recent size and position. This
            value is similar to SW_SHOWNORMAL, except that the window is not
            activated.
        5: SW_SHOW
            Activates the window and displays it in its current size and
            position.
        6: SW_MINIMIZE
            Minimizes the specified window and activates the next top-level
            window in the Z order.
        7: SW_SHOWMINNOACTIVE
            Displays the window as a minimized window. This value is similar
            to SW_SHOWMINIMIZED, except the window is not activated.
        8: SW_SHOWNA
            Displays the window in its current size and position. This value
            is similar to SW_SHOW, except that the window is not activated.
        9: SW_RESTORE
            Activates and displays the window. If the window is minimized or
            maximized, the system restores it to its original size and
            position. An application should specify this flag when restoring
            a minimized window.
        10: SW_SHOWDEFAULT
            Sets the show state based on the SW_ value specified in the
            STARTUPINFO structure passed to the CreateProcess function by
            the program that started the application.
        11: SW_FORCEMINIMIZE
            Minimizes a window, even if the thread that owns the window is
            not responding. This flag should only be used when minimizing
            windows from a different thread.
        """
        # handle other platforms...
        if not win32gui.__file__:
            self.maximize()
            return
            
        hwnd = win32gui.FindWindow(          # pylint: disable=no-member
            None, 
            self.driver.title + ' - Mozilla Firefox'
        )
        win32gui.ShowWindow(hwnd, cmd_show)  # pylint: disable=no-member
        win32gui.SetForegroundWindow(hwnd)   # pylint: disable=no-member

class Response:
    """
    Mimics an HTTP response object.
    """
    def __init__(self, url, content):
        self.url = url
        self.content = content
        self.lxml = html.fromstring(content)

    @property
    def html(self):
        HTML = type('html', (), {'lxml': self.lxml})
        HTML.lxml.url = self.url
        return HTML