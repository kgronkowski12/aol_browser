#!/usr/bin/env python3
import gi
import os
import json
import time
from pathlib import Path

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
        self.connect("destroy", Gtk.main_quit)

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

        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Menu Bar
        self.create_menu_bar(vbox)

        # First Toolbar (Features)
        self.create_feature_toolbar(vbox)

        # Second Toolbar (Navigation)
        self.create_navigation_toolbar(vbox)

        # Create WebView with optimized settings
        self.webview = self.create_optimized_webview()

        # ScrolledWindow for WebView
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.add(self.webview)
        vbox.pack_start(scrolled_window, True, True, 0)

        # Status Bar
        self.statusbar = Gtk.Statusbar()
        self.statusbar_context = self.statusbar.get_context_id("status")
        vbox.pack_end(self.statusbar, False, False, 0)


        # Load default page
        self.webview.load_uri("https://www.google.com")
        self.set_icon_from_file("icon.png")

        # Bookmark button state (will update when page loads)
        self.bookmark_button = None



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
        self.context.set_web_process_count_limit(128)  # Limit the number of processes

        webview.set_settings(settings)

        return webview

    def create_menu_bar(self, vbox):
        menubar = Gtk.MenuBar()
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
        new_window_button.connect("clicked", self.on_new_window)
        toolbar_blue.pack_start(new_window_button, False, False, 0)

        # New Tab Button
        new_tab_button = Gtk.Button()
        new_tab_button.set_tooltip_text("New Tab")
        new_tab_button.connect("clicked", self.on_new_tab)
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

    def on_internet_clicked(self, button):
        # Create a menu for sort optionshttps://en.wikipedia.org/wiki/Special:Random
        menu = Gtk.Menu()

        name_item = Gtk.RadioMenuItem(label="Youtube (VIDEO)")
        #name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.webview.load_uri("https://inv.nadeko.netkernel "))
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
        if self.webview.can_go_back():
            self.webview.go_back()

    def on_forward_clicked(self, widget):
        if self.webview.can_go_forward():
            self.webview.go_forward()

    def on_refresh_clicked(self, widget):
        self.webview.reload()

    def on_home_clicked(self, widget):
        self.webview.load_uri("https://www.google.com")

    def on_url_entry_activated(self, widget):
        url = self.url_entry.get_text()
        self.load_url(url)

    def on_go_clicked(self, widget):
        url = self.url_entry.get_text()
        self.load_url(url)

    def load_url(self, url):
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
        self.webview.load_uri(url)

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
                self.statusbar.push(self.statusbar_context, f"Loading: {uri}")
                self.statusbar.show_all()
                self.update_bookmark_button_state()
        elif load_event == WebKit2.LoadEvent.FINISHED:
            self.statusbar.push(self.statusbar_context, "Ready")
            pixbuf = GdkPixbuf.Pixbuf.new_from_file("loaded.png")
            self.statusbar.hide()
            # Scale pixbuf if needed: pixbuf = pixbuf.scale_simple(16, 16, GdkPixbuf.InterpType.BILINEAR)
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            self.load_button.set_image(image)  # Set the image widget onto the button
            self.update_bookmark_button_state()

        # Update navigation buttons
        self.back_button.set_sensitive(self.webview.can_go_back())
        self.forward_button.set_sensitive(self.webview.can_go_forward())

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

    def on_bookmark_button_toggled(self, widget):
        url = self.webview.get_uri()
        if not url:
            return

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

        bookmarks = [Bookmark("Absolute Terry Davis","https://inv.nadeko.net/channel/UCuIUshnWOUD-a4d5Z54kj8A"),Bookmark("Destiny","https://inv.nadeko.net/channel/UC554eY5jNUfDq3yDOJYirOQ"),Bookmark("Shady Penguinn","https://inv.nadeko.net/channel/UCU_mC__7H8NBJzX8ubMGY4Q")]

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

def main():
    # Enable GTK application to use X11 backend for hardware acceleration
    os.environ['GDK_BACKEND'] = 'x11'

    # Enable WebKit hardware acceleration
    os.environ['WEBKIT_FORCE_ACCELERATED_COMPOSITING'] = '1'

    # Initialize GTK
    Gtk.init(None)

    # Create and show the browser
    browser = WebBrowser()
    browser.show_all()
    #browser.statusbar.hide()

    Gtk.main()

if __name__ == "__main__":
    main()