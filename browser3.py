import os
import sys
from PyQt5.QtCore import QUrl, Qt, QSize
from PyQt5.QtWidgets import (QApplication, QMainWindow, QToolBar, QAction,
                             QLineEdit, QProgressBar, QStatusBar, QMenu,
                             QShortcut, QTabWidget)
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage, QWebEngineSettings

# Set environment variables for better compatibility
os.environ[
    "QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-gpu --enable-media-stream --autoplay-policy=no-user-gesture-required"
os.environ["QT_QUICK_BACKEND"] = "software"  # Fallback for systems without full OpenGL


class WebEnginePage(QWebEnginePage):
    """Custom webpage to handle permission requests and errors"""

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # Optionally log JavaScript console messages for debugging
        pass

    def certificateError(self, error):
        # For development, we can ignore certificate errors
        # In production, handle this more securely
        return True


class WebEngineView(QWebEngineView):
    """Enhanced web view with basic features"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Configure settings for this view
        self.settings().setAttribute(QWebEngineSettings.PluginsEnabled, True)
        self.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        self.settings().setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        self.settings().setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)
        self.settings().setAttribute(QWebEngineSettings.WebGLEnabled, True)
        self.settings().setAttribute(QWebEngineSettings.AutoLoadImages, True)
        self.settings().setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)
        self.settings().setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        self.settings().setAttribute(QWebEngineSettings.AllowGeolocationOnInsecureOrigins, True)

        # Create a custom page with our page class
        #self.custom_page = WebEnginePage(self.profile(), self)
        #self.setPage(self.custom_page)

        # Connect signals
        #self.page().fullScreenRequested.connect(self.handle_fullscreen_request)

    def handle_fullscreen_request(self, request):
        request.accept()
        if request.toggleOn():
            self.parent().tabs.setTabsClosable(False)
            self.parent().showFullScreen()
        else:
            self.parent().tabs.setTabsClosable(True)
            self.parent().showNormal()

    def createWindow(self, window_type):
        return self.parent().add_new_tab()


class Browser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Enhanced PyQt Browser")
        self.setGeometry(100, 100, 1200, 800)

        # Create a custom global profile for the browser
        self.profile = QWebEngineProfile("browser_profile", self)

        # Set a modern user agent string to prevent website compatibility issues
        self.profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        # Set up tab widget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.tab_changed)
        self.setCentralWidget(self.tabs)

        # Initialize UI
        self.setup_ui()

        # Add first tab
        self.add_new_tab(QUrl("https://www.google.com"), "Home")

    def setup_ui(self):
        # Status bar with progress
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(120)
        self.progress_bar.setMaximumHeight(15)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

        # Navigation toolbar
        nav_toolbar = QToolBar("Navigation")
        nav_toolbar.setIconSize(QSize(16, 16))
        nav_toolbar.setMovable(False)
        self.addToolBar(nav_toolbar)

        # Back button
        back_btn = QAction("◀", self)
        back_btn.setStatusTip("Go back to previous page")
        back_btn.triggered.connect(lambda: self.current_browser().back())
        nav_toolbar.addAction(back_btn)

        # Forward button
        forward_btn = QAction("▶", self)
        forward_btn.setStatusTip("Go forward to next page")
        forward_btn.triggered.connect(lambda: self.current_browser().forward())
        nav_toolbar.addAction(forward_btn)

        # Reload button
        reload_btn = QAction("⟳", self)
        reload_btn.setStatusTip("Reload page")
        reload_btn.triggered.connect(lambda: self.current_browser().reload())
        nav_toolbar.addAction(reload_btn)

        # Home button
        home_btn = QAction("🏠", self)
        home_btn.setStatusTip("Go to home page")
        home_btn.triggered.connect(self.navigate_home)
        nav_toolbar.addAction(home_btn)

        # URL bar
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Enter URL or search term...")
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        nav_toolbar.addWidget(self.url_bar)

        # Add tab button
        new_tab_btn = QAction("+", self)
        new_tab_btn.setStatusTip("Open a new tab")
        new_tab_btn.triggered.connect(lambda: self.add_new_tab())
        nav_toolbar.addAction(new_tab_btn)

        # Keyboard shortcuts
        self.shortcut_new_tab = QShortcut(QKeySequence("Ctrl+T"), self)
        self.shortcut_new_tab.activated.connect(lambda: self.add_new_tab())

        self.shortcut_close_tab = QShortcut(QKeySequence("Ctrl+W"), self)
        self.shortcut_close_tab.activated.connect(lambda: self.close_tab(self.tabs.currentIndex()))

        self.shortcut_reload = QShortcut(QKeySequence("Ctrl+R"), self)
        self.shortcut_reload.activated.connect(lambda: self.current_browser().reload())

        self.shortcut_focus_url = QShortcut(QKeySequence("Ctrl+L"), self)
        self.shortcut_focus_url.activated.connect(lambda: self.url_bar.setFocus())

    def add_new_tab(self, qurl=None, label="New Tab"):
        if qurl is None:
            qurl = QUrl("https://www.google.com")

        # Create custom browser with our profile
        browser = WebEngineView(self)
        browser.page().profile().setHttpUserAgent(self.profile.httpUserAgent())

        # Connect browser signals
        browser.urlChanged.connect(lambda url, browser=browser: self.update_url(url, browser))
        browser.loadStarted.connect(lambda: self.load_started())
        browser.loadProgress.connect(lambda p: self.load_progress(p))
        browser.loadFinished.connect(lambda success: self.load_finished(success))
        browser.titleChanged.connect(lambda title, i=self.tabs.count():
                                     self.tabs.setTabText(i, title[:10] + "..." if len(title) > 10 else title))

        # Add browser to a new tab
        index = self.tabs.addTab(browser, label)
        self.tabs.setCurrentIndex(index)

        # Update URL bar when tab is shown
        browser.urlChanged.connect(self.update_current_url)

        return browser

    def tab_changed(self, index):
        if index >= 0:
            browser = self.current_browser()
            if browser:
                self.update_url(browser.url(), browser)

    def current_browser(self):
        return self.tabs.currentWidget()

    def close_tab(self, index):
        if self.tabs.count() > 1:
            self.tabs.widget(index).deleteLater()
            self.tabs.removeTab(index)
        else:
            self.close()

    def update_url(self, url, browser=None):
        if browser == self.current_browser():
            self.url_bar.setText(url.toString())
            self.url_bar.setCursorPosition(0)

    def update_current_url(self):
        browser = self.current_browser()
        if browser:
            self.url_bar.setText(browser.url().toString())
            self.url_bar.setCursorPosition(0)

    def navigate_to_url(self):
        url_text = self.url_bar.text()

        # Simple URL handling - add more robust parsing as needed
        if not url_text.startswith(('http://', 'https://')):
            # Check if it looks like a domain name
            if '.' in url_text and ' ' not in url_text:
                url_text = 'http://' + url_text
            else:
                # Treat as a search query
                url_text = 'https://www.google.com/search?q=' + url_text.replace(' ', '+')

        self.current_browser().setUrl(QUrl(url_text))

    def navigate_home(self):
        self.current_browser().setUrl(QUrl("https://www.google.com"))

    def load_started(self):
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

    def load_progress(self, progress):
        self.progress_bar.setValue(progress)

    def load_finished(self, success):
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Page loaded" if success else "Page failed to load", 3000)


if __name__ == "__main__":
    # Enable high DPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    window = Browser()
    window.show()
    sys.exit(app.exec_())