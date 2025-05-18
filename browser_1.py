#!/usr/bin/env python3
import gi
import os
import subprocess
import json
import time
from pathlib import Path
from explorer import FileExplorer

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.0')
from gi.repository import Gtk, WebKit2, GLib, Gio, Gdk, GdkPixbuf


class Bookmark:
    def __init__(self, title, url, date_added=None):
        self.title = title
        self.url = url
        self.date_added = date_added or int(time.time())

    def to_dict(self):
        return {
            "title": self.title,
            "url": self.url,
            "date_added": self.date_added
        }

    @classmethod
    def from_dict(cls, data):
        return cls(data["title"], data["url"], data["date_added"])


class BookmarkManager:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.bookmark_file = os.path.join(data_dir, "bookmarks.json")
        self.bookmarks = []
        self.load_bookmarks()

    def load_bookmarks(self):
        try:
            if os.path.exists(self.bookmark_file):
                with open(self.bookmark_file, 'r') as f:
                    data = json.load(f)
                    self.bookmarks = [Bookmark.from_dict(item) for item in data]
        except Exception as e:
            print(f"Error loading bookmarks: {e}")
            self.bookmarks = []

    def save_bookmarks(self):
        try:
            with open(self.bookmark_file, 'w') as f:
                json.dump([b.to_dict() for b in self.bookmarks], f, indent=2)
        except Exception as e:
            print(f"Error saving bookmarks: {e}")

    def add_bookmark(self, title, url):
        # Check if bookmark with this URL already exists
        for bookmark in self.bookmarks:
            if bookmark.url == url:
                # Update the existing bookmark title
                bookmark.title = title
                self.save_bookmarks()
                return False  # Return False to indicate it was an update, not a new addition

        # If not found, add new bookmark
        bookmark = Bookmark(title, url)
        self.bookmarks.append(bookmark)
        self.save_bookmarks()
        return True  # Return True to indicate a new bookmark was added

    def remove_bookmark(self, url):
        before_count = len(self.bookmarks)
        self.bookmarks = [b for b in self.bookmarks if b.url != url]
        if len(self.bookmarks) < before_count:
            self.save_bookmarks()
            return True
        return False

    def get_all_bookmarks(self):
        return self.bookmarks

    def is_bookmarked(self, url):
        return any(b.url == url for b in self.bookmarks)

class WebBrowser(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="GTK Web Browser")
        self.set_default_size(1200, 800)
        #self.connect("destroy", Gtk.main_quit)
        self.fileView = False
        self.forceWeb = False
        self.scroll=1

        # Set up data directory
        self.data_dir = os.path.join(os.path.expanduser("~"), ".gtk-web-browser")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        # Initialize bookmark manager
        self.bookmark_manager = BookmarkManager(self.data_dir)

        # Context with optimizations and cookie support
        self.context = WebKit2.WebContext.get_default()

        # Enable disk cache for better performance
        cache_dir = os.path.join(self.data_dir, "cache")
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        self.context.set_disk_cache_directory(cache_dir)
        self.context.set_cache_model(WebKit2.CacheModel.WEB_BROWSER)

        # Cookie manager setup
        cookie_manager = self.context.get_cookie_manager()
        cookies_path = os.path.join(self.data_dir, "cookies.db")
        cookie_manager.set_persistent_storage(
            cookies_path,
            WebKit2.CookiePersistentStorage.SQLITE
        )
        cookie_manager.set_accept_policy(WebKit2.CookieAcceptPolicy.ALWAYS)

        # Enable transparency support for the window
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
            self.set_app_paintable(True)

        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)
        #vbox.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(1, 1, 1, 0.65))

        # Create WebView with optimized settings
        self.webview = self.create_optimized_webview()
        # Add this line after creating the webview
        #self.setup_memory_management()

        # Menu Bar
        self.create_menu_bar(vbox)

        # First Toolbar (Features)
        self.create_feature_toolbar(vbox)

        # Second Toolbar (Navigation)
        self.create_navigation_toolbar(vbox)



        # Set transparent background for webview
        #self.webview.set_background_color(Gdk.RGBA(0.05, 0.05, 0.05, 0.7))
        #self.webview.set_background_color(Gdk.RGBA(0.0, 1, 0.0, 0.8))
        self.webview.set_opacity(0.95)  # Set overall webview opacity

        # Connect to signals to maintain transparency
        self.webview.connect("load-changed", self.on_load_changed)
        self.webview.connect("create", self.on_create_window)

        # Enable transparency in the WebView settings
        settings = self.webview.get_settings()
        #settings.set_property("enable-transparent-background", True)

        # Custom CSS to make webpage background transparent
        self.inject_transparency_css()

        # ScrolledWindow for WebView
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.add(self.webview)
        self.allWeb = scrolled_window
        vbox.pack_start(scrolled_window, True, True, 0)

        # Status Bar
        self.statusbar = Gtk.Statusbar()
        self.statusbar_context = self.statusbar.get_context_id("status")

        toolbar_style_provider_full = Gtk.CssProvider()
        css_full = """
                * { /* Target the box directly */
                    background-color: white;
                    color: black
                }
                """
        toolbar_style_provider_full.load_from_data(css_full.encode())
        toolbar_context_full = self.statusbar.get_style_context()
        toolbar_context_full.add_provider(
            toolbar_style_provider_full,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


        vbox.pack_end(self.statusbar, False, False, 0)

        # Load default page
        self.webview.load_uri("https://www.google.com")
        self.set_icon_from_file("icon.png")

        # Bookmark button state (will update when page loads)
        self.bookmark_button = None

        start_path="/"
        self.win2 = FileExplorer(start_path, vbox, self.url_entry, self)
        self.prefetch_dns()
        self.setup_content_filters()
        self.setup_script_blocking()

    def pop_download(self, link, format_code):
        script_path = os.path.join(os.path.dirname(__file__), "youtube-download.sh")
        command = f'gnome-terminal -- bash -c "{script_path} \\"{link}\\" {format_code}; exec bash"'
        subprocess.run(command, shell=True)

    def pop_curl(self, link):
        if link.endswith((".com/",".org/",".pl/",".net/",".eu/",".de/")):
            link=link+"index.html"
        newName = link.replace("https://","")
        newName = newName.replace("http://","")
        newName = newName.replace("www.","")
        newName = newName.replace("index.html", "")
        newName = newName.replace("/","_")
        command = (
            f'gnome-terminal -- bash -c \''
            f'curl -O "{link}" && mv "$(basename \'{link}\')" "/home/sheeye/Videos/Download/CURL/{newName}_$(basename \'{link}\')"; '
            f'echo "Press any key to exit..."; read -n 1\''
        )
        subprocess.run(command, shell=True)

    def launch_download(self, button):
        url = self.url_entry.get_text()
        menu = Gtk.Menu()

        if url.__contains__("watch?v="):

            name_item = Gtk.RadioMenuItem(label="MP4 - 1080p")
            # name_item.set_active(self.sort_by == "name")
            name_item.connect("activate", lambda x: self.pop_download(url,0))
            menu.append(name_item)

            name_item = Gtk.RadioMenuItem(label="MP4 - 720p")
            # name_item.set_active(self.sort_by == "name")
            name_item.connect("activate", lambda x: self.pop_download(url,1))
            menu.append(name_item)

            name_item = Gtk.RadioMenuItem(label="MP4 - 480p")
            # name_item.set_active(self.sort_by == "name")
            name_item.connect("activate", lambda x: self.pop_download(url,2))
            menu.append(name_item)


            sort_sep = Gtk.SeparatorMenuItem()
            menu.append(sort_sep)

            name_item = Gtk.RadioMenuItem(label="MP3 - HIGH QUALITY")
            # name_item.set_active(self.sort_by == "name")
            name_item.connect("activate", lambda x: self.pop_download(url,3))
            menu.append(name_item)

            name_item = Gtk.RadioMenuItem(label="MP3 - LOW QUALITY")
            # name_item.set_active(self.sort_by == "name")
            name_item.connect("activate", lambda x: self.pop_download(url,4))
            menu.append(name_item)

            sort_sep = Gtk.SeparatorMenuItem()
            menu.append(sort_sep)

            name_item = Gtk.RadioMenuItem(label="WAV - HIGH QUALITY")
            # name_item.set_active(self.sort_by == "name")
            name_item.connect("activate", lambda x: self.pop_download(url, 5))
            menu.append(name_item)

            name_item = Gtk.RadioMenuItem(label="WAV - LOW QUALITY")
            # name_item.set_active(self.sort_by == "name")
            name_item.connect("activate", lambda x: self.pop_download(url, 6))
            menu.append(name_item)

            sort_sep = Gtk.SeparatorMenuItem()
            menu.append(sort_sep)

        name_item = Gtk.RadioMenuItem(label="CURL")
        # name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.pop_curl(url))
        menu.append(name_item)

        menu.show_all()
        menu.popup_at_pointer(None)

    def create_optimized_webview(self):
        # Create WebView with our context
        webview = WebKit2.WebView.new_with_context(self.context)

        # Connect signals
        webview.connect("load-changed", self.on_load_changed)
        webview.connect("decide-policy", self.on_decide_policy)
        webview.connect("notify::title", self.on_title_changed)


        # Get settings object
        settings = webview.get_settings()

        # Performance optimizations
        settings.set_property("enable-javascript", True)
        settings.set_property("enable-media-stream", True)
        settings.set_property("enable-mediasource", True)  # Important for YouTube
        settings.set_property("enable-accelerated-2d-canvas", True)
        settings.set_property("enable-smooth-scrolling", True)
        settings.set_property("enable-webgl", True)
        settings.set_property("hardware-acceleration-policy", WebKit2.HardwareAccelerationPolicy.ALWAYS)




        settings.set_property("allow-file-access-from-file-urls", True)
        settings.set_property("enable-developer-extras", True)  # Enable developer tools
        # Performance optimizations
        settings.set_property("enable-dns-prefetching", True)  # Enable DNS prefetching

        # Enable popup handling
        settings.set_property("javascript-can-open-windows-automatically", True)
        settings.set_property("allow-modal-dialogs", True)

        # Set mobile user agent
        mobile_user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
        settings.set_property("user-agent", mobile_user_agent)



        # Memory management
        settings.set_property("enable-page-cache", True)

        # Media playback optimizations
        settings.set_property("enable-webaudio", True)
        settings.set_property("media-playback-requires-user-gesture", False)
        settings.set_property("enable-media-capabilities", True)

        # Developer options
        settings.set_property("enable-developer-extras", True)
        settings.set_property("javascript-can-open-windows-automatically", True)

        # Additional optimization settings
        settings.set_property("enable-site-specific-quirks", True)
        settings.set_property("allow-file-access-from-file-urls", True)
        settings.set_property("allow-universal-access-from-file-urls", True)

        # Network optimizations
        self.context.set_process_model(WebKit2.ProcessModel.MULTIPLE_SECONDARY_PROCESSES)
        self.context.set_cache_model(WebKit2.CacheModel.WEB_BROWSER)

        webview.set_settings(settings)

        return webview
    
    def on_popup_toggled(self, widget):
        """Toggle popup blocking on/off"""
        settings = self.webview.get_settings()
        enable_popups = widget.get_active()
        settings.set_property("javascript-can-open-windows-automatically", enable_popups)

        if enable_popups:
            self.statusbar.push(self.statusbar_context, "Popups enabled")
        else:
            self.statusbar.push(self.statusbar_context, "Popups disabled")


    def prefetch_dns(self):
        """Pre-resolve common domains for faster future navigation"""
        common_domains = [
            "www.google.com",
            "www.youtube.com",
            "www.facebook.com",
            "www.wikipedia.org",
            "www.twitter.com",
            "www.x.com",
            "www.civitai.com",
            "www.inv.nadeko.net",
            "www.old.reddit.com"
        ]

        def resolve_domains():
            for domain in common_domains:
                self.context.prefetch_dns(domain)


    def create_menu_bar(self, vbox):
        menubar = Gtk.MenuBar()
        #menubar.override_background_color(Gtk.StateType.NORMAL,Gdk.RGBA(0,0,0,1))
        menubar.set_opacity(1)

        toolbar_style_provider_full = Gtk.CssProvider()
        css_full = """
        * { /* Target the box directly */
            background-color: white;
            color: black
        }
        """
        toolbar_style_provider_full.load_from_data(css_full.encode())
        toolbar_context_full = menubar.get_style_context()
        toolbar_context_full.add_provider(
             toolbar_style_provider_full,
             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


        vbox.pack_start(menubar, False, False, 0)

        # File Menu
        file_menu = Gtk.Menu()
        file_item = Gtk.MenuItem(label="File")
        file_item.set_submenu(file_menu)

        new_window = Gtk.MenuItem(label="New Window")
        new_window.connect("activate", self.on_new_window)
        file_menu.append(new_window)

        new_tab = Gtk.MenuItem(label="New Tab")
        new_tab.connect("activate", self.on_new_tab)
        file_menu.append(new_tab)

        separator = Gtk.SeparatorMenuItem()
        file_menu.append(separator)

        exit_item = Gtk.MenuItem(label="Exit")
        exit_item.connect("activate", Gtk.main_quit)
        file_menu.append(exit_item)

        menubar.append(file_item)

        # Edit Menu
        edit_menu = Gtk.Menu()
        edit_item = Gtk.MenuItem(label="Edit")
        edit_item.set_submenu(edit_menu)

        cut_item = Gtk.MenuItem(label="Cut")
        edit_menu.append(cut_item)

        copy_item = Gtk.MenuItem(label="Copy")
        edit_menu.append(copy_item)

        paste_item = Gtk.MenuItem(label="Paste")
        edit_menu.append(paste_item)

        separator2 = Gtk.SeparatorMenuItem()
        edit_menu.append(separator2)

        # Cookie Manager menu item
        cookie_manager_item = Gtk.MenuItem(label="Cookie Manager")
        cookie_manager_item.connect("activate", self.on_cookie_manager)
        edit_menu.append(cookie_manager_item)

        # Clear Cache menu item
        clear_cache_item = Gtk.MenuItem(label="Clear Cache")
        clear_cache_item.connect("activate", self.on_clear_cache)
        edit_menu.append(clear_cache_item)

        menubar.append(edit_item)

        # View Menu
        view_menu = Gtk.Menu()
        view_item = Gtk.MenuItem(label="View")
        view_item.set_submenu(view_menu)

        # Toggle Hardware Acceleration
        self.hw_accel_item = Gtk.CheckMenuItem(label="Hardware Acceleration")
        self.hw_accel_item.set_active(True)
        self.hw_accel_item.connect("toggled", self.on_toggle_hw_accel)
        view_menu.append(self.hw_accel_item)

        separator3 = Gtk.SeparatorMenuItem()
        view_menu.append(separator3)

        history_item = Gtk.MenuItem(label="History")
        history_item.connect("activate", self.on_history)
        view_menu.append(history_item)

        # Bookmarks Menu Item
        bookmarks_item = Gtk.MenuItem(label="Bookmarks")
        bookmarks_item.connect("activate", self.on_show_bookmarks)
        view_menu.append(bookmarks_item)

        view_menu.append(separator3)

        # User Agent submenu
        user_agent_menu = Gtk.Menu()
        user_agent_item = Gtk.MenuItem(label="User Agent")
        user_agent_item.set_submenu(user_agent_menu)

        # Mobile agent
        self.mobile_agent = Gtk.RadioMenuItem(label="Mobile")
        self.mobile_agent.connect("toggled", self.on_user_agent_toggled, "mobile")
        self.mobile_agent.set_active(True)  # Default to mobile
        user_agent_menu.append(self.mobile_agent)

        # Desktop agent
        self.desktop_agent = Gtk.RadioMenuItem.new_from_widget(self.mobile_agent)
        self.desktop_agent.set_label("Desktop")
        self.desktop_agent.connect("toggled", self.on_user_agent_toggled, "desktop")
        user_agent_menu.append(self.desktop_agent)

        view_menu.append(user_agent_item)

        # Popup options
        separator4 = Gtk.SeparatorMenuItem()
        view_menu.append(separator4)

        self.popup_checkbox = Gtk.CheckMenuItem(label="Enable Popups")
        self.popup_checkbox.set_active(True)  # Default to enabled
        self.popup_checkbox.connect("toggled", self.on_popup_toggled)
        view_menu.append(self.popup_checkbox)

        separator3 = Gtk.SeparatorMenuItem()
        view_menu.append(separator3)

        bookmarks_item = Gtk.MenuItem(label="Opacity 100%")
        bookmarks_item.connect("activate",  lambda x: self.set_opp(1))
        view_menu.append(bookmarks_item)
        bookmarks_item = Gtk.MenuItem(label="Opacity 95%")
        bookmarks_item.connect("activate",  lambda x: self.set_opp(0.95))
        view_menu.append(bookmarks_item)
        bookmarks_item = Gtk.MenuItem(label="Opacity 90%")
        bookmarks_item.connect("activate",  lambda x: self.set_opp(0.9))
        view_menu.append(bookmarks_item)
        bookmarks_item = Gtk.MenuItem(label="Opacity 80%")
        bookmarks_item.connect("activate",  lambda x: self.set_opp(0.8))
        view_menu.append(bookmarks_item)
        bookmarks_item = Gtk.MenuItem(label="Opacity 70%")
        bookmarks_item.connect("activate",  lambda x: self.set_opp(0.7))
        view_menu.append(bookmarks_item)
        bookmarks_item = Gtk.MenuItem(label="Opacity 50%")
        bookmarks_item.connect("activate",  lambda x: self.set_opp(0.5))
        view_menu.append(bookmarks_item)
        bookmarks_item = Gtk.MenuItem(label="Opacity 20%")
        bookmarks_item.connect("activate",  lambda x: self.set_opp(0.2))
        view_menu.append(bookmarks_item)
        bookmarks_item = Gtk.MenuItem(label="Opacity 0%")
        bookmarks_item.connect("activate",  lambda x: self.set_opp(0.))
        view_menu.append(bookmarks_item)

        menubar.append(view_item)

        # Bookmarks Menu
        bookmarks_menu = Gtk.Menu()
        bookmarks_menu_item = Gtk.MenuItem(label="Bookmarks")
        bookmarks_menu_item.set_submenu(bookmarks_menu)

        add_bookmark_item = Gtk.MenuItem(label="Add Bookmark")
        add_bookmark_item.connect("activate", self.on_add_bookmark)
        bookmarks_menu.append(add_bookmark_item)

        show_all_bookmarks_item = Gtk.MenuItem(label="Show All Bookmarks")
        show_all_bookmarks_item.connect("activate", self.on_show_bookmarks)
        bookmarks_menu.append(show_all_bookmarks_item)

        separator4 = Gtk.SeparatorMenuItem()
        bookmarks_menu.append(separator4)

        # Add dynamic bookmarks
        self.update_bookmarks_menu(bookmarks_menu)

        menubar.append(bookmarks_menu_item)

        # Tools Menu
        tools_menu = Gtk.Menu()
        tools_item = Gtk.MenuItem(label="Tools")
        tools_item.set_submenu(tools_menu)

        # Developer Tools
        dev_tools_item = Gtk.MenuItem(label="Developer Tools")
        dev_tools_item.connect("activate", self.on_developer_tools)
        tools_menu.append(dev_tools_item)

        menubar.append(tools_item)

        # View Menu - add after existing items
        separator4 = Gtk.SeparatorMenuItem()
        view_menu.append(separator4)

        # Ad blocking toggle
        self.ad_blocking = Gtk.CheckMenuItem(label="Block Ads & Tracking")
        self.ad_blocking.set_active(True)
        self.ad_blocking.connect("toggled", self.on_ad_blocking_toggled)
        view_menu.append(self.ad_blocking)

        # Help Menu
        help_menu = Gtk.Menu()
        help_item = Gtk.MenuItem(label="Help")
        help_item.set_submenu(help_menu)

        about_item = Gtk.MenuItem(label="About")
        about_item.connect("activate", self.on_about)
        help_menu.append(about_item)

        menubar.append(help_item)

    def update_bookmarks_menu(self, menu=None):
        if menu is None:
            # Find the bookmarks menu
            menubar = self.get_child().get_children()[0]
            for item in menubar.get_children():
                if item.get_label() == "Bookmarks":
                    menu = item.get_submenu()
                    break
            if menu is None:
                return

        # Remove existing bookmark entries
        children = menu.get_children()
        # Keep the first 3 items (Add Bookmark, Show All, Separator)
        if len(children) > 3:
            for child in children[3:]:
                menu.remove(child)

        # Add bookmarks
        for bookmark in self.bookmark_manager.get_all_bookmarks():
            item = Gtk.MenuItem(label=bookmark.title)
            item.connect("activate", self.on_bookmark_clicked, bookmark.url)
            menu.append(item)

        menu.show_all()


    def create_feature_toolbar(self, vbox):

        # Main container box for the toolbars (already a Box, keeping it)
        toolbar_main_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        toolbar_main_container.override_background_color(Gtk.StateType.NORMAL,Gdk.RGBA(1, 1, 1, 1))
        #toolbar_main_container.set_opacity(0.85)

        # --- Styling for the main container (Optional, if you want its background styled) ---
        toolbar_style_provider_full = Gtk.CssProvider()
        css_full = """
        box { /* Target the box directly */
            background-color: rgb(99,51,103); /* Example slightly different color */
        }
        """
        toolbar_style_provider_full.load_from_data(css_full.encode())
        toolbar_context_full = toolbar_main_container.get_style_context()
        toolbar_context_full.add_provider(
             toolbar_style_provider_full,
             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # --- Box for the "Blue" section ---
        toolbar_blue = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)  # Added spacing

        # Style Provider for the blue box
        toolbar_style_provider_blue = Gtk.CssProvider()
        css_blue = """
        /* Apply styles directly to the widget this provider is attached to */
        GtkBox {
            background-color: rgb(0, 102, 153);
            outline: none;
            border: none;
        }
        *, *:hover, *:focus, *:active {
            background-color: rgb(0, 102, 153);
            outline: none;
            border: none;
            margin-bottom:2px;

        }


        """
        toolbar_style_provider_blue.load_from_data(css_blue.encode())
        toolbar_context_blue = toolbar_blue.get_style_context()
        toolbar_context_blue.add_provider(
            toolbar_style_provider_blue,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Add the blue box to the main toolbar container
        toolbar_main_container.pack_start(toolbar_blue, False, False, 0)

        # --- Add Buttons to the "Blue" Box ---

        # New Window Button
        # Use convenient constructor for icon buttons
        self.url_entry = Gtk.Entry()
        new_window_button = Gtk.Button()

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file("read2.png")
            # Scale pixbuf if needed: pixbuf = pixbuf.scale_simple(16, 16, GdkPixbuf.InterpType.BILINEAR)
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            new_window_button.set_image(image)  # Set the image widget onto the button
        except GLib.Error as e:  # Catch file not found error
            print(f"Warning: Could not load history.png: {e}")
            new_tab_button.set_label("Hist")  # Fallback text

        button_context_green = new_window_button.get_style_context()
        button_context_green.add_provider(
            toolbar_style_provider_blue,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        new_window_button.set_tooltip_text("New Window")
        #new_window_button.connect("clicked", self.on_new_window)
        new_window_button.connect("clicked", self.on_read_toggled)
        toolbar_blue.pack_start(new_window_button, False, False, 0)

        # New Tab Button
        new_tab_button = Gtk.Button()
        new_tab_button.set_tooltip_text("New Tab")
        new_tab_button.connect("clicked", self.launch_download)
        toolbar_blue.pack_start(new_tab_button, False, False, 0)

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file("write2.png")
            # Scale pixbuf if needed: pixbuf = pixbuf.scale_simple(16, 16, GdkPixbuf.InterpType.BILINEAR)
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            new_tab_button.set_image(image)  # Set the image widget onto the button
        except GLib.Error as e:  # Catch file not found error
            print(f"Warning: Could not load history.png: {e}")
            new_tab_button.set_label("Hist")  # Fallback text

        button_context_green = new_tab_button.get_style_context()
        button_context_green.add_provider(
            toolbar_style_provider_blue,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Separator (Vertical because the box is horizontal)
        #separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        # Add separator directly to the main container to sit between blue and green boxes
        #toolbar_main_container.pack_start(separator, False, False, 5)  # Add some padding around separator

        # --- Box for the "Green" section ---
        toolbar_green = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)  # Added spacing

        # Style Provider for the green box
        toolbar_style_provider_green = Gtk.CssProvider()
        css_green = """
        /* Apply styles directly to the widget this provider is attached to */
        GtkBox {
            background-color: rgb(6, 99, 111);
            outline: none;
            border: none;
        }
        *, *:hover, *:focus, *:active {
            background-color: rgb(6, 99, 111);
            outline: none;
            border: none;
            margin-bottom:2px;

        }


        """
        toolbar_style_provider_green.load_from_data(css_green.encode())
        toolbar_context_green = toolbar_green.get_style_context()
        toolbar_context_green.add_provider(
            toolbar_style_provider_green,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Add the green box to the main toolbar container
        toolbar_main_container.pack_start(toolbar_green, False, False, 0)

        # --- Add Buttons to the "Green" Box ---

        # Add/Remove Bookmark Button (Using ToggleButton)
        self.bookmark_button = Gtk.ToggleButton()  # Use ToggleButton
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file("save2.png")
            # Scale pixbuf if needed
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            self.bookmark_button.set_image(image)
        except GLib.Error as e:
            print(f"Warning: Could not load save.png: {e}")
            self.bookmark_button.set_label("Save")  # Fallback text
        self.bookmark_button.set_tooltip_text("Add/Remove Bookmark")
        self.bookmark_button.connect("toggled", self.on_bookmark_button_toggled)

        button_context_green = self.bookmark_button.get_style_context()
        button_context_green.add_provider(
            toolbar_style_provider_green,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        toolbar_green.pack_start(self.bookmark_button, False, False, 0)


        # History Button
        history_button = Gtk.Button()  # Create a standard button
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file("history2.png")
            # Scale pixbuf if needed: pixbuf = pixbuf.scale_simple(16, 16, GdkPixbuf.InterpType.BILINEAR)
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            history_button.set_image(image)  # Set the image widget onto the button
        except GLib.Error as e:  # Catch file not found error
            print(f"Warning: Could not load history.png: {e}")
            history_button.set_label("Hist")  # Fallback text
        history_button.set_tooltip_text("History")
        history_button.connect("clicked", self.on_history)
        button_context_green = history_button.get_style_context()
        button_context_green.add_provider(
            toolbar_style_provider_green,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        toolbar_green.pack_start(history_button, False, False, 0)

        # Bookmarks Button
        bookmarks_button = Gtk.Button()
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file("bookmarks2.png")
            # Scale pixbuf if needed
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            bookmarks_button.set_image(image)
        except GLib.Error as e:
            print(f"Warning: Could not load bookmarks.png: {e}")
            bookmarks_button.set_label("Bkmk")  # Fallback text
        bookmarks_button.set_tooltip_text("Show Bookmarks")
        bookmarks_button.connect("clicked", self.on_show_bookmarks)

        button_context_green = bookmarks_button.get_style_context()
        button_context_green.add_provider(
            toolbar_style_provider_green,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        toolbar_green.pack_start(bookmarks_button, False, False, 0)



        toolbar_gray = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)  # Added spacing

        # Style Provider for the green box
        toolbar_style_provider_gray = Gtk.CssProvider()
        css_gray = """
        /* Apply styles directly to the widget this provider is attached to */
        GtkBox {
            background-color: rgb(0, 102, 153);
            outline: none;
            border: none;
        }
        *, *:hover, *:focus, *:active {
            background-color: rgb(99, 102, 153);
            outline: none;
            border: none;
            margin-bottom:2px;

        }


        """
        toolbar_style_provider_gray.load_from_data(css_gray.encode())
        toolbar_context_gray = toolbar_gray.get_style_context()
        toolbar_context_gray.add_provider(
            toolbar_style_provider_gray,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        toolbar_main_container.pack_start(toolbar_gray, False, False, 0)

        # Developer Tools Button
        dev_tools_button = Gtk.Button()

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file("internet2.png")
            # Scale pixbuf if needed: pixbuf = pixbuf.scale_simple(16, 16, GdkPixbuf.InterpType.BILINEAR)
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            dev_tools_button.set_image(image)  # Set the image widget onto the button
        except GLib.Error as e:  # Catch file not found error
            print(f"Warning: Could not load history.png: {e}")
            dev_tools_button.set_label("Hist")  # Fallback text

        button_context_gray = dev_tools_button.get_style_context()
        button_context_gray.add_provider(
            toolbar_style_provider_gray,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        dev_tools_button.set_tooltip_text("Developer Tools")
        dev_tools_button.connect("clicked", self.on_internet_clicked)
        toolbar_gray.pack_start(dev_tools_button, False, False, 0)




        # Developer Tools Button
        dev_tools_button = Gtk.Button()

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file("channels2.png")
            # Scale pixbuf if needed: pixbuf = pixbuf.scale_simple(16, 16, GdkPixbuf.InterpType.BILINEAR)
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            dev_tools_button.set_image(image)  # Set the image widget onto the button
        except GLib.Error as e:  # Catch file not found error
            print(f"Warning: Could not load history.png: {e}")
            dev_tools_button.set_label("Hist")  # Fallback text

        button_context_gray = dev_tools_button.get_style_context()
        button_context_gray.add_provider(
            toolbar_style_provider_gray,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        dev_tools_button.set_tooltip_text("Developer Tools")
        dev_tools_button.connect("clicked", self.on_show_channels)
        toolbar_gray.pack_start(dev_tools_button, False, False, 0)




        toolbar_purple = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)  # Added spacing

        # Style Provider for the green box
        toolbar_style_provider_purple = Gtk.CssProvider()
        css_purple = """
        /* Apply styles directly to the widget this provider is attached to */
        GtkBox {
            background-color: rgb(103,50,103);
            outline: none;
            border: none;
        }
        *{
            background-color: rgb(103,50,103);
            outline: none;
            border: none;
            margin-bottom:2px;
        }



        """
        toolbar_style_provider_purple.load_from_data(css_purple.encode())
        toolbar_context_purple = toolbar_purple.get_style_context()
        toolbar_context_purple.add_provider(
            toolbar_style_provider_purple,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        toolbar_main_container.pack_start(toolbar_purple, False, False, 0)


        for name in ["quotes2.png","perks2.png","weather2.png"]:
            # Developer Tools Button
            dev_tools_button = Gtk.Button()

            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(name)
                # Scale pixbuf if needed: pixbuf = pixbuf.scale_simple(16, 16, GdkPixbuf.InterpType.BILINEAR)
                image = Gtk.Image.new_from_pixbuf(pixbuf)
                dev_tools_button.set_image(image)  # Set the image widget onto the button
            except GLib.Error as e:  # Catch file not found error
                print(f"Warning: Could not load history.png: {e}")
                dev_tools_button.set_label("Hist")  # Fallback text

            button_context_purple = dev_tools_button.get_style_context()
            button_context_purple.add_provider(
                toolbar_style_provider_purple,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

            dev_tools_button.set_tooltip_text("Developer Tools")
            dev_tools_button.connect("clicked", self.on_developer_tools)
            toolbar_purple.pack_start(dev_tools_button, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar_main_container.pack_start(spacer, True, True, 0)

        anime = Gtk.Box()


        # Developer Tools Button
        self.load_button = Gtk.Button()

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file("loaded.png")
            # Scale pixbuf if needed: pixbuf = pixbuf.scale_simple(16, 16, GdkPixbuf.InterpType.BILINEAR)
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            self.load_button.set_image(image)  # Set the image widget onto the button
        except GLib.Error as e:  # Catch file not found error
            print(f"Warning: Could not load history.png: {e}")
            dev_tools_button.set_label("Hist")  # Fallback text

        button_context_purple = self.load_button.get_style_context()
        button_context_purple.add_provider(
            toolbar_style_provider_purple,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.load_button.set_tooltip_text("Developer Tools")
        self.load_button.connect("clicked", self.on_developer_tools)
        anime.pack_start(self.load_button, False, False, 0)

        toolbar_main_container.pack_start(anime,False,False,0)




        vbox.pack_start(toolbar_main_container,False,False,0)

    def on_ad_blocking_toggled(self, widget):
        """Toggle ad blocking on/off"""
        # When toggling, we need to recreate the WebView to clear/add filters
        scrolled_window = self.webview.get_parent()

        # Remove old webview
        scrolled_window.remove(self.webview)

        # Create new content manager and webview
        self.content_manager = WebKit2.UserContentManager()

        # Create a new WebView with the settings
        self.webview = WebKit2.WebView.new_with_user_content_manager(self.content_manager)

        # Apply same settings as original webview
        settings = self.webview.get_settings()
        settings.set_property("enable-javascript", True)
        settings.set_property("allow-file-access-from-file-urls", True)
        settings.set_property("enable-developer-extras", True)
        settings.set_property("enable-page-cache", True)
        settings.set_property("enable-dns-prefetching", True)

        # Mobile user agent if active
        if hasattr(self, 'mobile_agent') and self.mobile_agent.get_active():
            mobile_user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
            settings.set_property("user-agent", mobile_user_agent)

        # Connect signals
        self.webview.connect("load-changed", self.on_load_changed)
        self.webview.connect("decide-policy", self.on_decide_policy)

        # Add to container
        scrolled_window.add(self.webview)
        scrolled_window.show_all()

        # Apply ad blocking if enabled
        if widget.get_active():
            self.setup_content_filters()
            self.setup_script_blocking()
            self.statusbar.push(self.statusbar_context, "Ad blocking enabled")
        else:
            self.statusbar.push(self.statusbar_context, "Ad blocking disabled")

        # Navigate to current URL or home
        current_url = self.url_entry.get_text()
        if current_url:
            self.webview.load_uri(current_url)
        else:
            self.webview.load_uri("https://www.google.com")





        

        
    def on_internet_clicked(self, button):
        # Create a menu for sort optionshttps://en.wikipedia.org/wiki/Special:Random
        menu = Gtk.Menu()

        name_item = Gtk.RadioMenuItem(label="Youtube (VIDEO)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://yewtu.be"))
        menu.append(name_item)

        name_item = Gtk.RadioMenuItem(label="GryPl (GAMES)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://gry.pl"))
        menu.append(name_item)

        name_item = Gtk.RadioMenuItem(label="Aliexpress (SHOP)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://pl.aliexpress.com/"))
        menu.append(name_item)

        name_item = Gtk.RadioMenuItem(label="Overleaf (TEX)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://www.overleaf.com/project"))
        menu.append(name_item)

        name_item = Gtk.RadioMenuItem(label="Github (DEV)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://github.com/"))
        menu.append(name_item)

        # Separator in sort submenu
        sort_sep = Gtk.SeparatorMenuItem()
        menu.append(sort_sep)
        
        name_item = Gtk.RadioMenuItem(label="Wikipedia (INFO)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://en.wikipedia.org/wiki/Special:Random"))
        menu.append(name_item)

        name_item = Gtk.RadioMenuItem(label="LKML (INFO)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://lkml.org"))
        menu.append(name_item)

        sort_sep = Gtk.SeparatorMenuItem()
        menu.append(sort_sep)

        name_item = Gtk.RadioMenuItem(label="Pinterest (IMG)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://pl.pinterest.com/"))
        menu.append(name_item)

        name_item = Gtk.RadioMenuItem(label="Dan Booru (IMG)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://danbooru.donmai.us/posts"))
        menu.append(name_item)

        name_item = Gtk.RadioMenuItem(label="Civitai (IMG)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://civitai.com/home"))
        menu.append(name_item)

        sort_sep = Gtk.SeparatorMenuItem()
        menu.append(sort_sep)

        name_item = Gtk.RadioMenuItem(label="ChatGPT (AI)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://chatgpt.com/"))
        menu.append(name_item)

        name_item = Gtk.RadioMenuItem(label="Claude (AI)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://claude.ai/"))
        menu.append(name_item)

        name_item = Gtk.RadioMenuItem(label="Deepseek (AI)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://chat.deepseek.com/"))
        menu.append(name_item)


        # Separator in sort submenu
        sort_sep = Gtk.SeparatorMenuItem()
        menu.append(sort_sep)

        name_item = Gtk.RadioMenuItem(label="Translate (TOOL)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://www.google.com/search?q=google+translate"))
        menu.append(name_item)


        menu.show_all()
        menu.popup_at_pointer(None)


    def create_navigation_toolbar(self, vbox):
        toolbar = Gtk.Toolbar()
        toolbar.set_style(Gtk.ToolbarStyle.ICONS)
        labelToolbar = Gtk.Toolbar
        vbox.pack_start(toolbar, False, False, 0)

        # Back Button
        self.back_button = Gtk.ToolButton()
        #self.back_button.set_icon_name("history-back")

        pixbuf = GdkPixbuf.Pixbuf.new_from_file("left.png")
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.show()  # Important: make the image visible
        self.back_button.set_icon_widget(image)
        self.back_button.set_tooltip_text("Go Back")
        self.back_button.set_label(" Back")
        self.back_button.connect("clicked", self.on_back_clicked)
        toolbar.insert(self.back_button, -1)

        # Forward Button
        self.forward_button = Gtk.ToolButton()
        #self.forward_button.set_icon_name("history-forward")
        pixbuf = GdkPixbuf.Pixbuf.new_from_file("right.png")
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.show()  # Important: make the image visible
        self.forward_button.set_icon_widget(image)
        self.forward_button.set_tooltip_text("Go Forward")
        self.forward_button.connect("clicked", self.on_forward_clicked)
        toolbar.insert(self.forward_button, -1)

        # Refresh Button
        refresh_button = Gtk.ToolButton()
        #refresh_button.set_icon_name("document-refresh")

        pixbuf = GdkPixbuf.Pixbuf.new_from_file("refresh.png")
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.show()  # Important: make the image visible
        refresh_button.set_icon_widget(image)
        refresh_button.set_tooltip_text("Refresh")
        refresh_button.connect("clicked", self.on_refresh_clicked)
        toolbar.insert(refresh_button, -1)

        # Home Button
        home_button = Gtk.ToolButton()
        #home_button.set_icon_name("go-home")
        pixbuf = GdkPixbuf.Pixbuf.new_from_file("home.png")
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.show()  # Important: make the image visible
        home_button.set_icon_widget(image)
        home_button.set_tooltip_text("Home")
        home_button.connect("clicked", self.on_home_clicked)
        toolbar.insert(home_button, -1)

        # Separator
        separator = Gtk.SeparatorToolItem()
        toolbar.insert(separator, -1)

        # URL Entry
        self.url_entry = Gtk.Entry()
        self.url_entry.connect("activate", self.on_url_entry_activated)

        # Create a tool item to hold the entry and set it to expand
        entry_item = Gtk.ToolItem()
        entry_item.set_expand(True)
        entry_item.add(self.url_entry)
        toolbar.insert(entry_item, -1)

        self.url_entry.grab_focus()

        # Go Button
        go_button = Gtk.ToolButton()
        #go_button.set_icon_name("go-jump")

        pixbuf = GdkPixbuf.Pixbuf.new_from_file("go.png")
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.show()  # Important: make the image visible
        go_button.set_icon_widget(image)
        go_button.set_tooltip_text("Go to URL")
        go_button.connect("clicked", self.on_go_clicked)
        toolbar.insert(go_button, -1)



    def on_new_window(self, widget):
        browser = WebBrowser()
        browser.show_all()

    def on_new_tab(self, widget):
        self.statusbar.push(self.statusbar_context, "New Tab functionality not implemented")

    def on_history(self, widget):
        self.statusbar.push(self.statusbar_context, "History functionality not implemented")

    def on_cookie_manager(self, widget):
        # Simple cookie manager dialog
        dialog = Gtk.Dialog(
            title="Cookie Manager",
            parent=self,
            flags=0,
            buttons=(
                Gtk.STOCK_CLEAR, Gtk.ResponseType.APPLY,
                Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE
            )
        )
        dialog.set_default_size(400, 300)

        label = Gtk.Label(
            label="Cookies are being stored in SQLite format.\nYou can clear all cookies or close this dialog.")
        dialog.get_content_area().pack_start(label, True, True, 10)

        response = dialog.run()
        if response == Gtk.ResponseType.APPLY:
            # Clear all cookies
            cookie_manager = self.context.get_cookie_manager()
            cookie_manager.delete_all_cookies()
            self.statusbar.push(self.statusbar_context, "All cookies cleared")

        dialog.destroy()

    def on_clear_cache(self, widget):
        # Clear WebKit cache
        self.context.clear_cache()
        self.statusbar.push(self.statusbar_context, "Cache cleared")

    def on_toggle_hw_accel(self, widget):
        settings = self.webview.get_settings()
        if widget.get_active():
            settings.set_property("hardware-acceleration-policy",
                                  WebKit2.HardwareAccelerationPolicy.ALWAYS)
            self.statusbar.push(self.statusbar_context, "Hardware acceleration enabled")
        else:
            settings.set_property("hardware-acceleration-policy",
                                  WebKit2.HardwareAccelerationPolicy.NEVER)
            self.statusbar.push(self.statusbar_context, "Hardware acceleration disabled")

    def on_developer_tools(self, widget):
        # Open WebKit inspector
        self.webview.get_inspector().show()
        self.statusbar.push(self.statusbar_context, "Developer tools opened")

    def on_about(self, widget):
        about_dialog = Gtk.AboutDialog()
        about_dialog.set_program_name("GTK Web Browser")
        about_dialog.set_version("1.0")
        about_dialog.set_comments("A simple GTK-based web browser with bookmarks and performance optimizations")
        about_dialog.set_website("https://github.com")
        about_dialog.run()
        about_dialog.destroy()

    def on_back_clicked(self, widget):
        if not self.fileView:
            if self.webview.can_go_back():
                self.webview.go_back()
                self.load_url(self.win2.current_path)
                if False:
                    if self.url_entry.get_text().__contains__("file://"):
                        print("Yo")
                        self.fileView = True
                        self.on_bookmark_button_toggled(None)
        else:
            self.win2.go_back()

    def on_forward_clicked(self, widget):
        if not self.fileView:
            if self.webview.can_go_forward():
                self.webview.go_forward()
        # File manager
        else:
            if self.win2.history_pos < len(self.win2.history) - 1:
                self.win2.history_pos += 1
                path = self.win2.history[self.win2.history_pos]
                self.win2.load_directory(path)

    def on_refresh_clicked(self, widget):
        if not self.fileView:
            self.webview.reload()
        else:
            self.win2.load_directory(self.win2.current_path)


    def on_home_clicked(self, widget):
        if not self.fileView:
            self.webview.load_uri("https://www.google.com")
        else:
            home = os.path.expanduser("~")

            # Update history
            if self.win2.history_pos < len(self.win2.history) - 1:
                self.win2.history = self.win2.history[:self.win2.history_pos + 1]

            self.win2.history.append(home)
            self.win2.history_pos = len(self.win2.history) - 1

            self.win2.load_directory(home)
            #self.back_button.set_sensitive(len(self.win2.history) > 1)
            #self.forward_button.set_sensitive(self.win2.history_pos < len(self.win2.history) - 1)
        #self.webview.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(0, 0, 0, 0.65))

    def on_url_entry_activated(self, widget):
        if not self.fileView:
            url = self.url_entry.get_text()
            self.load_url(url)
        else:
            url = self.url_entry.get_text()
            self.win2.load_directory(url)


    def on_go_clicked(self, widget):
        if not self.fileView:
            url = self.url_entry.get_text()
            self.load_url(url)
        else:
            url = self.url_entry.get_text()
            self.win2.load_directory(url)


    def load_url(self, url):
        if url.startswith(("/")):
            url="file://"+url
        elif not url.startswith("file://"):
            if not url.startswith(("http://", "https://")):
                if True:
                    if not url.startswith("www."):
                        if url.find(".")!=-1:
                            url = "https://"+url
                        else:
                            url = url.replace("+","%2B")
                            url = "https://www.google.com/search?q="+url
                    else:
                        url = "https://" + url
                #url = "https://" + url
        if url.__contains__("reddit.com"):
            if not url.__contains__("old.reddit.com"):
                url = url.replace("reddit.com","old.reddit.com")
                url=url.replace("www.","")
        if url.__contains__("youtube.com"):
            url = url.replace("youtube.com", "inv.nadeko.net")
        if url.__contains__("yewtu.be"):
            url = url.replace("yewtu.be", "inv.nadeko.net")
        self.webview.load_uri(url)
        if url.startswith("file://") and (len(url)<6 or not url[len(url)-5:].__contains__(".")):
            self.fileView=True
        else:
            self.fileView=False
        if self.forceWeb:
            self.fileView=False
            self.forceWeb=False
        print(self.fileView)
        self.on_bookmark_button_toggled(None)

        #self.webview.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(0, 0, 0, 0.65))

    def update_bookmark_button_state(self):
        url = self.webview.get_uri()
        if url and self.bookmark_button:
            is_bookmarked = self.bookmark_manager.is_bookmarked(url)
            # Block the signal handler temporarily to prevent triggering the toggle event
            self.bookmark_button.handler_block_by_func(self.on_bookmark_button_toggled)
            self.bookmark_button.set_active(is_bookmarked)
            if is_bookmarked:
                self.bookmark_button.set_icon_name("user-bookmarks")
                self.bookmark_button.set_tooltip_text("Remove Bookmark")
            else:
                self.bookmark_button.set_icon_name("bookmark-new")
                self.bookmark_button.set_tooltip_text("Add Bookmark")
            self.bookmark_button.handler_unblock_by_func(self.on_bookmark_button_toggled)

    def on_load_changed(self, web_view, load_event):
        if load_event == WebKit2.LoadEvent.STARTED:
            pixbuf = GdkPixbuf.PixbufAnimation.new_from_file("aol_loading_image.gif")
            # pixbuf = pixbuf.scale_simple(38, 38, GdkPixbufAnimation.InterpType.BILINEAR)
            image = Gtk.Image.new_from_animation(pixbuf)
            self.load_button.set_image(image)

            self.statusbar.push(self.statusbar_context, "Loading...")
            self.statusbar.show_all()
        elif load_event == WebKit2.LoadEvent.COMMITTED:

            uri = web_view.get_uri()
            if uri:
                pixbuf = GdkPixbuf.PixbufAnimation.new_from_file("aol_loading_image.gif")
                # pixbuf = pixbuf.scale_simple(38, 38, GdkPixbufAnimation.InterpType.BILINEAR)
                image = Gtk.Image.new_from_animation(pixbuf)
                self.load_button.set_image(image)

                self.url_entry.set_text(uri)

                url = uri

                if url.__contains__("reddit.com"):
                    if not url.__contains__("old.reddit.com"):
                        url = url.replace("reddit.com", "old.reddit.com")
                        url = url.replace("www.", "")
                        self.load_url(url)
                if url.__contains__("youtube.com"):
                    url = url.replace("youtube.com", "inv.nadeko.net")
                    url = url.replace("www.", "")
                if url.__contains__("yewtu.be"):
                    url = url.replace("yewtu.be", "inv.nadeko.net")
                    url = url.replace("www.", "")

                self.url_entry.set_text(url)


                self.statusbar.push(self.statusbar_context, f"Loading: {uri}")
                self.statusbar.show_all()
                self.update_bookmark_button_state()
        elif load_event == WebKit2.LoadEvent.FINISHED:
            #self.webview.override_background_color(Gtk.Statetype.Normal,Gdk.RGBA(0.7,0.7,0.7,0.6))
            self.statusbar.push(self.statusbar_context, "Ready")
            pixbuf = GdkPixbuf.Pixbuf.new_from_file("loaded.png")
            self.statusbar.hide()
            # Scale pixbuf if needed: pixbuf = pixbuf.scale_simple(16, 16, GdkPixbuf.InterpType.BILINEAR)
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            self.load_button.set_image(image)  # Set the image widget onto the button
            self.update_bookmark_button_state()

        # Update navigation buttons
        if not self.fileView:
            self.back_button.set_sensitive(self.webview.can_go_back())
            self.forward_button.set_sensitive(self.webview.can_go_forward())



    def set_opp(self, opp):
        self.webview.set_opacity(opp)
        self.inject_transparency_css()


    def inject_transparency_css(self):
        """Inject custom CSS to maintain transparency while preserving text readability"""
        transparency_css = """
        html {
            background: rgba(0, 0, 0, 0) !important; 
        }
        body {
            background-color: rgba(0, 0, 0, 0) !important;
            background-image: none !important;
        }
        /* Preserve text contrast and readability */
        p, h1, h2, h3, h4, h5, h6, span, a, li, td, th {
            color: inherit !important;
            background-color: transparent !important;
            text-shadow: 0px 0px 3px rgba(0, 0, 0, 0.3);
        }
        /* Improve readability for light text on now-transparent backgrounds */
        body.light-text p, body.light-text h1, body.light-text span,
        .light-text, .light-bg p, .light-bg h1, .light-bg span {
            text-shadow: 0px 0px 4px rgba(0, 0, 0, 0.7) !important;
        }
        """
        js_code = f"""
        (function() {{
            // Add our custom CSS
            var style = document.createElement('style');
            style.textContent = `{transparency_css}`;
            document.head.appendChild(style);

            // Make background elements transparent
            document.documentElement.style.backgroundColor = 'transparent';
            document.body.style.backgroundColor = 'transparent';

            // Analyze the page to detect if it's light text on dark background
            // and add appropriate class for text shadow handling
            function analyzeAndApplyTextHandling() {{
                let bodyStyle = getComputedStyle(document.body);
                let bodyBgColor = bodyStyle.backgroundColor;
                let bodyTextColor = bodyStyle.color;

                // Convert colors to brightness value
                function getBrightness(color) {{
                    // Extract RGB values from color string
                    let rgb = color.match(/\\d+/g);
                    if (rgb) {{
                        return (parseInt(rgb[0]) * 299 + parseInt(rgb[1]) * 587 + parseInt(rgb[2]) * 114) / 1000;
                    }}
                    return 0;
                }}

                let bgBrightness = getBrightness(bodyBgColor);
                let textBrightness = getBrightness(bodyTextColor);

                // If light text on dark background
                if (textBrightness > bgBrightness) {{
                    document.body.classList.add('light-text');
                }}
            }}

            // Run analysis immediately and after a delay to catch dynamic content
            analyzeAndApplyTextHandling();
            setTimeout(analyzeAndApplyTextHandling, 1000);
        }})();
        """
        self.webview.run_javascript(js_code, None, None, None)

    def on_title_changed(self, web_view, param):
        # Update the window title with the page title
        title = web_view.get_title()
        if title:
            self.set_title(f"{title} - America Online")
        else:
            self.set_title("America Online")

    def on_decide_policy(self, web_view, decision, decision_type):
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            uri = decision.get_request().get_uri()
            self.statusbar.push(self.statusbar_context, f"Navigating to: {uri}")
        return False  # Allow the default behavior

    def on_add_bookmark(self, widget):
        uri = self.webview.get_uri()
        title = self.webview.get_title() or uri

        if uri:
            dialog = Gtk.Dialog(
                title="Add Bookmark",
                parent=self,
                flags=0,
                buttons=(
                    Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                    Gtk.STOCK_SAVE, Gtk.ResponseType.OK
                )
            )
            dialog.set_default_size(350, 150)

            box = dialog.get_content_area()
            box.set_spacing(6)

            # Title entry
            title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            title_label = Gtk.Label(label="Name:")
            title_entry = Gtk.Entry()
            title_entry.set_text(title)
            title_entry.set_activates_default(True)
            title_box.pack_start(title_label, False, False, 0)
            title_box.pack_start(title_entry, True, True, 0)
            box.pack_start(title_box, False, False, 0)

            # URL entry
            url_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            url_label = Gtk.Label(label="URL:")
            url_entry = Gtk.Entry()
            url_entry.set_text(uri)
            url_box.pack_start(url_label, False, False, 0)
            url_box.pack_start(url_entry, True, True, 0)
            box.pack_start(url_box, False, False, 0)

            dialog.set_default_response(Gtk.ResponseType.OK)
            dialog.show_all()

            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                new_title = title_entry.get_text()
                new_url = url_entry.get_text()
                if new_title and new_url:
                    is_new = self.bookmark_manager.add_bookmark(new_title, new_url)
                    if is_new:
                        self.statusbar.push(self.statusbar_context, f"Bookmark added: {new_title}")
                    else:
                        self.statusbar.push(self.statusbar_context, f"Bookmark updated: {new_title}")
                    self.update_bookmarks_menu()
                    self.update_bookmark_button_state()

            dialog.destroy()

    def on_read_toggled(self, widget):
        self.fileView = True
        self.back_button.set_sensitive(True)
        self.forward_button.set_sensitive(True)
        if self.fileView:
            self.win2.main_vertical_box.show_all()
            self.allWeb.hide()
            self.win2.load_directory("/home/sheeye/Videos/Download/")
            self.back_button.set_sensitive(True)
            self.forward_button.set_sensitive(True)


    def on_bookmark_button_toggled(self, widget):
        #self.fileView = not self.fileView
        if widget!=None:
            if self.fileView==False:
                self.load_url("file:///home/sheeye/")
                self.on_bookmark_button_toggled(None)
            else:
                self.load_url("www.google.com")
                self.on_bookmark_button_toggled(None)
            #self.fileView=not self.fileView
        self.back_button.set_sensitive(True)
        self.forward_button.set_sensitive(True)
        if self.fileView:
            self.win2.main_vertical_box.show_all()
            self.allWeb.hide()
            self.win2.load_directory(self.url_entry.get_text().replace("file://",""))
            self.back_button.set_sensitive(True)
            self.forward_button.set_sensitive(True)


        else:
            self.win2.main_vertical_box.hide()
            self.allWeb.show_all()
            #self.load_url(self.url_entry.get_text())
        if False:
            url = self.webview.get_uri()
            if not url:
                return
        if False:

            is_active = widget.get_active()
            is_bookmarked = self.bookmark_manager.is_bookmarked(url)

            if is_active and not is_bookmarked:
                # Add new bookmark
                self.on_add_bookmark(widget)
            elif not is_active and is_bookmarked:
                # Remove bookmark
                title = next((b.title for b in self.bookmark_manager.bookmarks if b.url == url), url)

                dialog = Gtk.MessageDialog(
                    transient_for=self,
                    flags=0,
                    message_type=Gtk.MessageType.QUESTION,
                    buttons=Gtk.ButtonsType.YES_NO,
                    text=f"Remove bookmark '{title}'?"
                )
                response = dialog.run()
                if response == Gtk.ResponseType.YES:
                    if self.bookmark_manager.remove_bookmark(url):
                        self.statusbar.push(self.statusbar_context, f"Bookmark removed: {title}")
                        self.update_bookmarks_menu()
                        self.update_bookmark_button_state()
                else:
                    # Revert the toggle button state since the user canceled
                    self.update_bookmark_button_state()
                dialog.destroy()

    def on_bookmark_clicked(self, widget, url):
        self.load_url(url)

    def on_show_channels(self, widget):
        bookmarks = self.bookmark_manager.get_all_bookmarks()

        dialog = Gtk.Dialog(
            title="Channels",
            parent=self,
            flags=0,
            buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        )
        dialog.set_default_size(500, 400)

        # Create a scrollable list
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_shadow_type(Gtk.ShadowType.ETCHED_IN)

        # Create liststore model for bookmark data
        # Columns: Title, URL, Date Added, (hidden) Bookmark Object
        liststore = Gtk.ListStore(str, str, str, object)

        bookmarks = [Bookmark("Absolute Terry Davis","https://yewtu.be/channel/UCuIUshnWOUD-a4d5Z54kj8A"),Bookmark("African Mann","https://inv.nadeko.net/channel/UCz2bxDAlwdvI8UKJS_W6CgQ"),Bookmark("Dhar Mann","https://inv.nadeko.net/channel/UC_hK9fOxyy_TM8FJGXIyG8Q"),Bookmark("Destiny","https://yewtu.be/channel/UC554eY5jNUfDq3yDOJYirOQ"),Bookmark("Shady Penguinn","https://yewtu.be/channel/UCU_mC__7H8NBJzX8ubMGY4Q"),Bookmark("No Text To Speech","https://inv.nadeko.net/channel/UCxaaULLk6UCnRl5VKRc7G0A")]

        # Fill the liststore with bookmarks
        for bookmark in bookmarks:
            date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(bookmark.date_added))
            liststore.append([bookmark.title, bookmark.url, date_str, bookmark])

        # Create TreeView
        treeview = Gtk.TreeView(model=liststore)
        treeview.set_headers_visible(True)

        # Create columns
        title_column = Gtk.TreeViewColumn("Title", Gtk.CellRendererText(), text=0)
        title_column.set_expand(True)
        title_column.set_sort_column_id(0)
        treeview.append_column(title_column)


        # Connect double-click signal
        treeview.connect("row-activated", self.on_bookmark_row_activated)

        # Set up context menu
        treeview.connect("button-press-event", self.on_bookmark_button_press)

        scrolled_window.add(treeview)
        dialog.get_content_area().pack_start(scrolled_window, True, True, 0)

        # Add toolbar buttons below the treeview
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_margin_top(6)
        button_box.set_margin_bottom(6)
        button_box.set_margin_start(6)
        button_box.set_margin_end(6)

        # Visit button
        visit_button = Gtk.Button.new_with_label("Visit")
        visit_button.connect("clicked", self.on_bookmark_dialog_visit, treeview)
        button_box.pack_end(visit_button, False, False, 0)

        dialog.get_content_area().pack_start(button_box, False, False, 0)

        dialog.show_all()
        response = dialog.run()
        dialog.destroy()

        # After dialog is closed, update the bookmarks menu
        self.update_bookmarks_menu()

    def on_show_bookmarks(self, widget):
        bookmarks = self.bookmark_manager.get_all_bookmarks()

        dialog = Gtk.Dialog(
            title="Bookmarks",
            parent=self,
            flags=0,
            buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        )
        dialog.set_default_size(500, 400)

        # Create a scrollable list
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_shadow_type(Gtk.ShadowType.ETCHED_IN)

        # Create liststore model for bookmark data
        # Columns: Title, URL, Date Added, (hidden) Bookmark Object
        liststore = Gtk.ListStore(str, str, str, object)

        # Fill the liststore with bookmarks
        for bookmark in bookmarks:
            date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(bookmark.date_added))
            liststore.append([bookmark.title, bookmark.url, date_str, bookmark])

        # Create TreeView
        treeview = Gtk.TreeView(model=liststore)
        treeview.set_headers_visible(True)

        # Create columns
        title_column = Gtk.TreeViewColumn("Title", Gtk.CellRendererText(), text=0)
        title_column.set_expand(True)
        title_column.set_sort_column_id(0)
        treeview.append_column(title_column)

        url_column = Gtk.TreeViewColumn("URL", Gtk.CellRendererText(), text=1)
        url_column.set_expand(True)
        treeview.append_column(url_column)

        date_column = Gtk.TreeViewColumn("Date Added", Gtk.CellRendererText(), text=2)
        date_column.set_sort_column_id(2)
        treeview.append_column(date_column)

        # Connect double-click signal
        treeview.connect("row-activated", self.on_bookmark_row_activated)

        # Set up context menu
        treeview.connect("button-press-event", self.on_bookmark_button_press)

        scrolled_window.add(treeview)
        dialog.get_content_area().pack_start(scrolled_window, True, True, 0)

        # Add toolbar buttons below the treeview
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_margin_top(6)
        button_box.set_margin_bottom(6)
        button_box.set_margin_start(6)
        button_box.set_margin_end(6)

        # Add button
        add_button = Gtk.Button.new_with_label("Add")
        add_button.connect("clicked", self.on_bookmark_dialog_add, liststore)
        button_box.pack_start(add_button, False, False, 0)

        # Edit button
        edit_button = Gtk.Button.new_with_label("Edit")
        edit_button.connect("clicked", self.on_bookmark_dialog_edit, treeview, liststore)
        button_box.pack_start(edit_button, False, False, 0)

        # Remove button
        remove_button = Gtk.Button.new_with_label("Remove")
        remove_button.connect("clicked", self.on_bookmark_dialog_remove, treeview, liststore)
        button_box.pack_start(remove_button, False, False, 0)

        # Visit button
        visit_button = Gtk.Button.new_with_label("Visit")
        visit_button.connect("clicked", self.on_bookmark_dialog_visit, treeview)
        button_box.pack_end(visit_button, False, False, 0)

        dialog.get_content_area().pack_start(button_box, False, False, 0)

        dialog.show_all()
        response = dialog.run()
        dialog.destroy()

        # After dialog is closed, update the bookmarks menu
        self.update_bookmarks_menu()

    def on_bookmark_button_press(self, treeview, event):
        # Check if right mouse button was pressed
        if event.button == 3:  # Right click
            x = int(event.x)
            y = int(event.y)
            time = event.time
            pthinfo = treeview.get_path_at_pos(x, y)

            if pthinfo is not None:
                path, col, cell_x, cell_y = pthinfo
                treeview.grab_focus()
                treeview.set_cursor(path, col, 0)

                # Create popup menu
                popup_menu = Gtk.Menu()

                # Visit item
                visit_item = Gtk.MenuItem(label="Visit")
                visit_item.connect("activate", self.on_bookmark_context_visit, treeview)
                popup_menu.append(visit_item)

                # Edit item
                edit_item = Gtk.MenuItem(label="Edit")
                edit_item.connect("activate", self.on_bookmark_context_edit, treeview, treeview.get_model())
                popup_menu.append(edit_item)

                # Remove item
                remove_item = Gtk.MenuItem(label="Remove")
                remove_item.connect("activate", self.on_bookmark_context_remove, treeview, treeview.get_model())
                popup_menu.append(remove_item)

                popup_menu.show_all()
                popup_menu.popup(None, None, None, None, event.button, time)
                return True
        return False

    def on_bookmark_row_activated(self, treeview, path, column):
        # Get the model and iter associated with the path
        model = treeview.get_model()
        iter = model.get_iter(path)
        # Get the URL from the selected row
        url = model.get_value(iter, 1)
        # Load the URL
        self.load_url(url)
        # Close the parent dialog
        treeview.get_toplevel().response(Gtk.ResponseType.CLOSE)

    def on_bookmark_dialog_add(self, button, liststore):
        dialog = Gtk.Dialog(
            title="Add Bookmark",
            parent=button.get_toplevel(),
            flags=0,
            buttons=(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                Gtk.STOCK_SAVE, Gtk.ResponseType.OK
            )
        )
        dialog.set_default_size(350, 150)

        box = dialog.get_content_area()
        box.set_spacing(6)

        # Title entry
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title_label = Gtk.Label(label="Name:")
        title_entry = Gtk.Entry()
        title_entry.set_activates_default(True)
        title_box.pack_start(title_label, False, False, 0)
        title_box.pack_start(title_entry, True, True, 0)
        box.pack_start(title_box, False, False, 0)

        # URL entry
        url_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        url_label = Gtk.Label(label="URL:")
        url_entry = Gtk.Entry()
        url_entry.set_text("https://")
        url_box.pack_start(url_label, False, False, 0)
        url_box.pack_start(url_entry, True, True, 0)
        box.pack_start(url_box, False, False, 0)

        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            title = title_entry.get_text()
            url = url_entry.get_text()
            if title and url:
                # Add to bookmark manager
                is_new = self.bookmark_manager.add_bookmark(title, url)

                # Add to liststore
                if is_new:
                    bookmark = next((b for b in self.bookmark_manager.bookmarks if b.url == url), None)
                    if bookmark:
                        date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(bookmark.date_added))
                        liststore.append([title, url, date_str, bookmark])
                        self.statusbar.push(self.statusbar_context, f"Bookmark added: {title}")

        dialog.destroy()

    def on_bookmark_dialog_edit(self, button, treeview, liststore):
        selection = treeview.get_selection()
        model, iter = selection.get_selected()

        if iter is not None:
            bookmark = model.get_value(iter, 3)

            dialog = Gtk.Dialog(
                title="Edit Bookmark",
                parent=button.get_toplevel(),
                flags=0,
                buttons=(
                    Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                    Gtk.STOCK_SAVE, Gtk.ResponseType.OK
                )
            )
            dialog.set_default_size(350, 150)

            box = dialog.get_content_area()
            box.set_spacing(6)

            # Title entry
            title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            title_label = Gtk.Label(label="Name:")
            title_entry = Gtk.Entry()
            title_entry.set_text(bookmark.title)
            title_entry.set_activates_default(True)
            title_box.pack_start(title_label, False, False, 0)
            title_box.pack_start(title_entry, True, True, 0)
            box.pack_start(title_box, False, False, 0)

            # URL entry
            url_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            url_label = Gtk.Label(label="URL:")
            url_entry = Gtk.Entry()
            url_entry.set_text(bookmark.url)
            url_box.pack_start(url_label, False, False, 0)
            url_box.pack_start(url_entry, True, True, 0)
            box.pack_start(url_box, False, False, 0)

            dialog.set_default_response(Gtk.ResponseType.OK)
            dialog.show_all()

            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                new_title = title_entry.get_text()
                new_url = url_entry.get_text()

                if new_title and new_url:
                    old_url = bookmark.url

                    # First, remove the old bookmark if URL is changing
                    if new_url != old_url:
                        self.bookmark_manager.remove_bookmark(old_url)

                    # Add the new/updated bookmark
                    self.bookmark_manager.add_bookmark(new_title, new_url)

                    # Update the list store
                    model.set_value(iter, 0, new_title)
                    model.set_value(iter, 1, new_url)

                    # Get updated bookmark object
                    updated_bookmark = next((b for b in self.bookmark_manager.bookmarks if b.url == new_url), None)
                    if updated_bookmark:
                        model.set_value(iter, 3, updated_bookmark)

                    self.statusbar.push(self.statusbar_context, f"Bookmark updated: {new_title}")

            dialog.destroy()

    def on_bookmark_dialog_remove(self, button, treeview, liststore):
        selection = treeview.get_selection()
        model, iter = selection.get_selected()

        if iter is not None:
            bookmark = model.get_value(iter, 3)
            title = bookmark.title

            dialog = Gtk.MessageDialog(
                transient_for=button.get_toplevel(),
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=f"Remove bookmark '{title}'?"
            )
            response = dialog.run()
            if response == Gtk.ResponseType.YES:
                # Remove from bookmark manager
                self.bookmark_manager.remove_bookmark(bookmark.url)

                # Remove from list store
                liststore.remove(iter)
                self.statusbar.push(self.statusbar_context, f"Bookmark removed: {title}")

            dialog.destroy()

    def on_bookmark_dialog_visit(self, button, treeview):
        selection = treeview.get_selection()
        model, iter = selection.get_selected()

        if iter is not None:
            url = model.get_value(iter, 1)
            self.load_url(url)
            treeview.get_toplevel().response(Gtk.ResponseType.CLOSE)

        # Context menu handlers

    def on_bookmark_context_visit(self, menuitem, treeview):
        selection = treeview.get_selection()
        model, iter = selection.get_selected()

        if iter is not None:
            url = model.get_value(iter, 1)
            self.load_url(url)
            treeview.get_toplevel().response(Gtk.ResponseType.CLOSE)

    def on_bookmark_context_edit(self, menuitem, treeview, liststore):
        self.on_bookmark_dialog_edit(menuitem, treeview, liststore)

    def on_bookmark_context_remove(self, menuitem, treeview, liststore):
        self.on_bookmark_dialog_remove(menuitem, treeview, liststore)

    def import_bookmarks(self, filename):
        """Import bookmarks from a JSON file"""
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                imported = 0
                for item in data:
                    if 'title' in item and 'url' in item:
                        self.bookmark_manager.add_bookmark(item['title'], item['url'])
                        imported += 1
                self.update_bookmarks_menu()
                return imported
        except Exception as e:
            print(f"Error importing bookmarks: {e}")
            return 0

    def export_bookmarks(self, filename):
        """Export bookmarks to a JSON file"""
        try:
            with open(filename, 'w') as f:
                json.dump([b.to_dict() for b in self.bookmark_manager.bookmarks], f, indent=2)
                return len(self.bookmark_manager.bookmarks)
        except Exception as e:
            print(f"Error exporting bookmarks: {e}")
            return 0

    def on_create_window(self, web_view, navigation_action):
        print(navigation_action.get_request().get_uri())
        browser = self.create_new_browser_window(navigation_action.get_request().get_uri())
        browser.show_all()
        browser.win2.main_vertical_box.hide()

        #self.webview.load_uri(navigation_action.get_request().get_uri())


    def on_user_agent_toggled(self, widget, agent_type):
        if not widget.get_active():
            return

        settings = self.webview.get_settings()
        if agent_type == "mobile":
            mobile_user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
            settings.set_property("user-agent", mobile_user_agent)
            self.statusbar.push(self.statusbar_context, "Using mobile user agent")
        else:
            # Default desktop user agent
            desktop_user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            settings.set_property("user-agent", desktop_user_agent)
            self.statusbar.push(self.statusbar_context, "Using desktop user agent")

        # Reload the current page with the new user agent
        self.webview.reload()  # !/usr/bin/env python3


    def create_new_browser_window(self, uri=None):
        """Create a new browser window and load the specified URI if provided"""
        browser = WebBrowser()
        #browser.webview = WebKit2.WebView.new_with_context(self.context)

        if uri:
            browser.load_url(uri)
        #browser.context=self.context

        return browser

    def on_authenticate(self, web_view, request):
        """Handle authentication requests"""
        # Get authentication data
        host = request.get_host()

        # Create authentication dialog
        dialog = Gtk.Dialog(
            title=f"Authentication Required - {host}",
            parent=self,
            flags=0,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        )
        dialog.set_default_size(350, 200)
        dialog.set_modal(True)

        # Create layout for username and password
        box = dialog.get_content_area()
        box.set_spacing(6)

        # Message
        label = Gtk.Label(label=f"The site {host} requires authentication")
        box.pack_start(label, False, False, 0)

        # Username field
        username_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        username_label = Gtk.Label(label="Username:")
        username_label.set_width_chars(12)
        username_entry = Gtk.Entry()
        username_box.pack_start(username_label, False, False, 0)
        username_box.pack_start(username_entry, True, True, 0)
        box.pack_start(username_box, False, False, 0)

        # Password field
        password_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        password_label = Gtk.Label(label="Password:")
        password_label.set_width_chars(12)
        password_entry = Gtk.Entry()
        password_entry.set_visibility(False)
        password_box.pack_start(password_label, False, False, 0)
        password_box.pack_start(password_entry, True, True, 0)
        box.pack_start(password_box, False, False, 0)

        # Show everything
        dialog.show_all()

        # Run dialog
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            username = username_entry.get_text()
            password = password_entry.get_text()
            credential = WebKit2.Credential.new(username, password, WebKit2.CredentialPersistence.FOR_SESSION)
            request.authenticate(credential)
            result = True
        else:
            request.cancel()
            result = False

        dialog.destroy()
        return result

    def setup_content_filters(self):
        """Set up content filters to block ads and tracking scripts using CSS"""
        # Get the user content manager
        content_manager = self.webview.get_user_content_manager()

        # CSS to hide common ad elements
        ad_blocking_css = """
            /* Ad containers */
            div[class*="ad-"],
            div[class*="ad_"],
            div[id*="ad-"],
            div[id*="ad_"],
            div[class*="ads-"],
            div[class*="ads_"],
            div[id*="ads-"],
            div[id*="ads_"],
            div[class*="advert"],
            div[id*="advert"],
            iframe[id*="ad_"],
            iframe[id*="ad-"],
            iframe[src*="ad_"],
            iframe[src*="ad-"],

            /* Banner containers */
            div[class*="banner"],
            div[id*="banner"],

            /* Other common ad containers */
            .advertisement,
            .advertising,
            .adsbygoogle,
            .adsbox,

            /* Cookie notices and popups */
            div[class*="cookie-banner"],
            div[class*="cookie-consent"],
            div[class*="cookie-notice"],
            div[class*="gdpr"],
            div[class*="consent"],
            div[class*="popup"],
            div[id*="popup"],
            div[class*="modal"][class*="overlay"],
            div[class*="lightbox"],

            /* Tracking pixels are usually hidden */
            img[width="1"][height="1"],
            iframe[width="1"][height="1"],

            /* Social tracking widgets */
            div[class*="share-buttons"],
            div[id*="share-buttons"],
            div[class*="social-buttons"],
            div[id*="social-buttons"],

            /* Newsletter signups and overlays */
            div[class*="newsletter"],
            div[id*="newsletter"],
            div[class*="subscribe"],
            div[id*="subscribe"],

            /* Common ad networks */
            iframe[src*="doubleclick.net"],
            iframe[src*="googleadservices"],
            iframe[src*="googlesyndication"],
            iframe[src*="adservice.google"],
            iframe[src*="amazon-adsystem"],
            img[src*="ad.doubleclick.net"],
            img[src*="googleadservices"],
            img[src*="googlesyndication"],
            img[src*="adservice.google"],
            img[src*="amazon-adsystem"]
            {
                display: none !important;
                opacity: 0 !important;
                pointer-events: none !important;
                height: 0 !important;
                position: absolute !important;
                z-index: -999 !important;
            }
        """

        # Add the CSS as a user style sheet
        content_manager.add_style_sheet(WebKit2.UserStyleSheet(
            ad_blocking_css,
            WebKit2.UserContentInjectedFrames.ALL_FRAMES,
            WebKit2.UserStyleLevel.USER,
            None,
            None
        ))

        self.statusbar.push(self.statusbar_context, "Ad blocking CSS enabled")

    def setup_script_blocking(self):
        """Set up script blocking for common tracking scripts"""
        content_manager = self.webview.get_user_content_manager()

        # Create script blocking rules
        script_block = """
        (function() {
            // Block common trackers by overriding their functions
            const blockObject = function(obj) {
                if (typeof obj === 'string') {
                    try {
                        // Handle dot notation by splitting
                        const parts = obj.split('.');
                        let current = window;

                        // Navigate to the parent object
                        for (let i = 0; i < parts.length - 1; i++) {
                            if (current[parts[i]] === undefined) {
                                return; // Object path doesn't exist
                            }
                            current = current[parts[i]];
                        }

                        // Replace the final property with a dummy function
                        const lastPart = parts[parts.length - 1];
                        if (current[lastPart]) {
                            current[lastPart] = function() { return false; };
                        }

                        // Also try to intercept via Object.defineProperty if possible
                        try {
                            Object.defineProperty(current, lastPart, {
                                get: function() { return function() { return false; }; },
                                set: function() { return false; }
                            });
                        } catch(e) {}
                    } catch(e) {}
                }
            };

            // Block these common trackers
            const trackers = [
                'ga', 'gaData', 'GoogleAnalyticsObject', 'gtag', 
                'fbq', 'fbevents', 'twttr.conversion', 'pintrk', 
                'snaptr', '_qevents', 'heap', 'mixpanel', 'plausible',
                '_hsq', 'hj', 'clarity'
            ];

            // Apply blocking
            trackers.forEach(blockObject);

            // Block common tracking URLs before they load
            const observer = new MutationObserver(function(mutations) {
                mutations.forEach(function(mutation) {
                    if (mutation.type === 'childList') {
                        mutation.addedNodes.forEach(function(node) {
                            if (node.tagName === 'SCRIPT' || node.tagName === 'IMG' || node.tagName === 'IFRAME') {
                                const src = node.src || '';
                                if (src.match(/analytics|tracker|pixel|beacon|doubleclick|googleadservices|facebook.*\/tr|ads/i)) {
                                    node.remove();
                                }
                            }
                        });
                    }
                });
            });

            // Start observing the document for tracking scripts
            observer.observe(document, { childList: true, subtree: true });
        })();
        """

        # Add the script blocking as a user script
        content_manager.add_script(WebKit2.UserScript(
            script_block,
            WebKit2.UserContentInjectedFrames.ALL_FRAMES,
            WebKit2.UserScriptInjectionTime.START,
            None,
            None
        ))

        self.statusbar.push(self.statusbar_context, "Script blocking enabled")

    # Add this function to the WebBrowser class:
    def setup_memory_management(self):
        """Setup advanced memory management for the browser"""
        # Connect to scroll events
        self.webview.connect("scroll-event", self.on_scroll_event)

        # Keep track of scroll position to detect when user has scrolled a lot
        self.last_cleanup_position = 0
        self.scroll_threshold = 5000  # Threshold for cleanup in pixels

        # Set up periodic cleanup timer (every 30 seconds)
        #GLib.timeout_add_seconds(30, self.perform_memory_cleanup)

        # Enable aggressive memory management settings
        settings = self.webview.get_settings()
        if hasattr(settings, "set_property"):
            # Limit JavaScript memory
            if hasattr(WebKit2.Settings, "set_javascript_memory_limit"):
                settings.set_javascript_memory_limit(128)  # Limit to 128MB

            # Disable site-specific quirks
            #settings.set_property("enable-site-specific-quirks", False)

            # Disable media playback when not visible
            #settings.set_property("media-playback-requires-user-gesture", True)

            # Free memory when page becomes inactive
            if hasattr(settings, "set_property"):
                settings.set_property("enable-write-console-messages-to-stdout", True)

        # Configure process model to conserve memory
        #if hasattr(self.context, "set_process_model"):
        #    self.context.set_process_model(WebKit2.ProcessModel.SHARED_SECONDARY_PROCESS)

    # Add this function to track scrolling
    def on_scroll_event(self, widget, event):
        """Track scroll events to trigger memory cleanup after significant scrolling"""
        # Get current scroll position
        self.scroll +=1
        print(self.scroll)
        if self.scroll==10:
            self.scroll=0
            #self.last_cleanup_position = y
            self.perform_memory_cleanup()
        return False  # Allow event propagation

    # Add this function to clean up memory after scrolling
    def cleanup_scrolled_content(self):
        """Clean up memory after significant scrolling"""
        # Run garbage collection
        try:
            # Request low-memory mode from WebKit
            if hasattr(self.webview, "send_message_to_page"):
                script = """
                // Remove hidden media elements
                observer = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (!entry.isIntersecting) {
                            elem = entry.target;
                            if (elem.tagName === 'VIDEO' || elem.tagName === 'IFRAME') {
                                elem.src = '';
                                elem.load();
                            } else if (elem.tagName === 'IMG') {
                                elem.src = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==';
                            }
                        }
                    });
                }, {rootMargin: '1000px'});

                // Observe media elements
                document.querySelectorAll('video, iframe, img').forEach(elem => {
                    observer.observe(elem);
                });

                // Force garbage collection where possible
                if (window.gc) { window.gc(); }

                // Clear some caches
                if (window.performance && window.performance.memory) {
                    console.log('Memory used:', window.performance.memory.usedJSHeapSize);
                }
                """
                self.webview.evaluate_javascript(script, -1, None, None, None)

            self.statusbar.push(self.statusbar_context, "Memory cleanup performed")
            print("nice")
        except Exception as e:
            print(f"Memory cleanup error: {e}")
        return False  # One-time execution

    # Add this function for periodic memory cleanup
    def perform_memory_cleanup(self):
        """Perform periodic memory cleanup"""
        # Only clean if the browser is still running
        if not self.get_realized():
            return False

        # Run a lighter memory cleanup
        script = """
        // Clear console
        console.clear();

        // Clear timeout and intervals that are no longer needed
        for (let i = 0; i < 1000; i++) {
            window.clearTimeout(i);
            window.clearInterval(i);
        }

        // Request garbage collection
        if (window.gc) { window.gc(); }
        """
        try:
            self.webview.evaluate_javascript(script, -1, None, None, None)
        except:
            pass

        return True  # Continue the timer

def main():
    # Enable GTK application to use X11 backend for hardware acceleration
    os.environ['GDK_BACKEND'] = 'x11'

    # Enable WebKit hardware acceleration
    os.environ['WEBKIT_FORCE_ACCELERATED_COMPOSITING'] = '1'

    # Initialize GTK
    Gtk.init(None)

    # Create and show the browser
    browser = WebBrowser()
    browser.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(0, 0, 0, 0.65))
    browser.show_all()
    browser.statusbar.hide()
    browser.win2.main_vertical_box.hide()

    Gtk.main()

if __name__ == "__main__":
    main()
