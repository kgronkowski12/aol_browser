#!/usr/bin/env python3
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.0')
from gi.repository import Gtk, WebKit2, GLib, Gio, Pango


class BrowserTab(Gtk.Box):
    def __init__(self, browser):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self.browser = browser

        # WebView
        self.webview = WebKit2.WebView()
        self.webview.connect("load-changed", self.on_load_changed)
        self.webview.connect("decide-policy", self.on_decide_policy)
        #self.webview.connect("title-changed", self.on_title_changed)

        # ScrolledWindow for WebView
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.add(self.webview)
        self.pack_start(scrolled_window, True, True, 0)

        # Default title
        self.title = "New Tab"

    def load_uri(self, uri):
        if not uri.startswith(("http://", "https://")):
            uri = "https://" + uri
        self.webview.load_uri(uri)

    def on_load_changed(self, web_view, load_event):
        if load_event == WebKit2.LoadEvent.STARTED:
            self.browser.statusbar.push(self.browser.statusbar_context, "Loading...")
        elif load_event == WebKit2.LoadEvent.COMMITTED:
            uri = web_view.get_uri()
            if uri:
                if self.browser.get_current_tab() == self:
                    self.browser.url_entry.set_text(uri)
                self.browser.statusbar.push(self.browser.statusbar_context, f"Loading: {uri}")
        elif load_event == WebKit2.LoadEvent.FINISHED:
            self.browser.statusbar.push(self.browser.statusbar_context, "Ready")

        # Update navigation buttons if this is the current tab
        if self.browser.get_current_tab() == self:
            self.update_navigation_buttons()

    def on_decide_policy(self, web_view, decision, decision_type):
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            uri = decision.get_request().get_uri()
            self.browser.statusbar.push(self.browser.statusbar_context, f"Navigating to: {uri}")
        return False  # Allow the default behavior

    def on_title_changed(self, web_view, title):
        self.title = title if title else "New Tab"
        # Update the tab label if this tab exists in the notebook
        page_num = self.browser.notebook.page_num(self)
        if page_num != -1:
            self.browser.update_tab_label(self, page_num)

    def update_navigation_buttons(self):
        self.browser.back_button.set_sensitive(self.webview.can_go_back())
        self.browser.forward_button.set_sensitive(self.webview.can_go_forward())


class WebBrowser(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="GTK Web Browser")
        self.set_default_size(1200, 800)
        self.connect("destroy", Gtk.main_quit)

        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # Menu Bar
        self.create_menu_bar(vbox)

        # First Toolbar (Features)
        self.create_feature_toolbar(vbox)

        # Second Toolbar (Navigation)
        self.create_navigation_toolbar(vbox)

        # Notebook (tab container)
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.connect("switch-page", self.on_tab_switch)
        vbox.pack_start(self.notebook, True, True, 0)

        # Status Bar
        self.statusbar = Gtk.Statusbar()
        self.statusbar_context = self.statusbar.get_context_id("status")
        vbox.pack_end(self.statusbar, False, False, 0)

        # Create the first tab
        self.add_new_tab("https://www.google.com")

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

        close_tab = Gtk.MenuItem(label="Close Tab")
        close_tab.connect("activate", self.on_close_tab)
        file_menu.append(close_tab)

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

        menubar.append(edit_item)

        # View Menu
        view_menu = Gtk.Menu()
        view_item = Gtk.MenuItem(label="View")
        view_item.set_submenu(view_menu)

        history_item = Gtk.MenuItem(label="History")
        history_item.connect("activate", self.on_history)
        view_menu.append(history_item)

        bookmarks_item = Gtk.MenuItem(label="Bookmarks")
        view_menu.append(bookmarks_item)

        menubar.append(view_item)

        # Help Menu
        help_menu = Gtk.Menu()
        help_item = Gtk.MenuItem(label="Help")
        help_item.set_submenu(help_menu)

        about_item = Gtk.MenuItem(label="About")
        about_item.connect("activate", self.on_about)
        help_menu.append(about_item)

        menubar.append(help_item)

    def create_feature_toolbar(self, vbox):
        toolbar = Gtk.Toolbar()
        toolbar.set_style(Gtk.ToolbarStyle.ICONS)
        vbox.pack_start(toolbar, False, False, 0)

        # New Window Button
        new_window_button = Gtk.ToolButton()
        new_window_button.set_icon_name("window-new")
        new_window_button.set_tooltip_text("New Window")
        new_window_button.connect("clicked", self.on_new_window)
        toolbar.insert(new_window_button, -1)

        # New Tab Button
        new_tab_button = Gtk.ToolButton()
        new_tab_button.set_icon_name("tab-new")
        new_tab_button.set_tooltip_text("New Tab")
        new_tab_button.connect("clicked", self.on_new_tab)
        toolbar.insert(new_tab_button, -1)

        # Close Tab Button
        close_tab_button = Gtk.ToolButton()
        close_tab_button.set_icon_name("window-close")
        close_tab_button.set_tooltip_text("Close Tab")
        close_tab_button.connect("clicked", self.on_close_tab_clicked)
        toolbar.insert(close_tab_button, -1)

        # Separator
        separator = Gtk.SeparatorToolItem()
        toolbar.insert(separator, -1)

        # History Button
        history_button = Gtk.ToolButton()
        history_button.set_icon_name("document-open-recent")
        history_button.set_tooltip_text("History")
        history_button.connect("clicked", self.on_history)
        toolbar.insert(history_button, -1)

        # Bookmarks Button
        bookmarks_button = Gtk.ToolButton()
        bookmarks_button.set_icon_name("user-bookmarks")
        bookmarks_button.set_tooltip_text("Bookmarks")
        toolbar.insert(bookmarks_button, -1)

    def create_navigation_toolbar(self, vbox):
        toolbar = Gtk.Toolbar()
        vbox.pack_start(toolbar, False, False, 0)

        # Back Button
        self.back_button = Gtk.ToolButton()
        self.back_button.set_icon_name("go-previous")
        self.back_button.set_tooltip_text("Go Back")
        self.back_button.connect("clicked", self.on_back_clicked)
        toolbar.insert(self.back_button, -1)

        # Forward Button
        self.forward_button = Gtk.ToolButton()
        self.forward_button.set_icon_name("go-next")
        self.forward_button.set_tooltip_text("Go Forward")
        self.forward_button.connect("clicked", self.on_forward_clicked)
        toolbar.insert(self.forward_button, -1)

        # Refresh Button
        refresh_button = Gtk.ToolButton()
        refresh_button.set_icon_name("view-refresh")
        refresh_button.set_tooltip_text("Refresh")
        refresh_button.connect("clicked", self.on_refresh_clicked)
        toolbar.insert(refresh_button, -1)

        # Home Button
        home_button = Gtk.ToolButton()
        home_button.set_icon_name("go-home")
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

        # Go Button
        go_button = Gtk.ToolButton()
        go_button.set_icon_name("go-jump")
        go_button.set_tooltip_text("Go to URL")
        go_button.connect("clicked", self.on_go_clicked)
        toolbar.insert(go_button, -1)

    def on_new_window(self, widget):
        browser = WebBrowser()
        browser.show_all()

    def add_new_tab(self, url=None):
        # Create a new tab
        tab = BrowserTab(self)

        # Create a tab label with a close button
        tab_label = self.create_tab_label(tab)

        # Add the tab to the notebook
        page_num = self.notebook.append_page(tab, tab_label)
        self.notebook.set_current_page(page_num)
        self.notebook.show_all()

        # Load the URL if provided
        if url:
            tab.load_uri(url)

        return tab

    def create_tab_label(self, tab):
        # Create a horizontal box for the tab label
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        # Create a label for the tab title
        label = Gtk.Label(label=tab.title)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(20)
        hbox.pack_start(label, True, True, 0)

        # Create a close button
        close_button = Gtk.Button()
        close_button.set_relief(Gtk.ReliefStyle.NONE)
        close_button.set_focus_on_click(False)
        close_image = Gtk.Image.new_from_icon_name("window-close", Gtk.IconSize.MENU)
        close_button.add(close_image)
        close_button.connect("clicked", self.on_tab_close_clicked, tab)
        hbox.pack_start(close_button, False, False, 0)

        hbox.show_all()
        return hbox

    def update_tab_label(self, tab, page_num):
        # Get the current tab label box
        tab_label = self.notebook.get_tab_label(tab)

        # Find the label widget in the box (it's the first child)
        for child in tab_label.get_children():
            if isinstance(child, Gtk.Label):
                child.set_text(tab.title)
                break

    def on_new_tab(self, widget):
        tab = self.add_new_tab("https://www.google.com")
        tab.show_all()

    def on_close_tab(self, widget):
        page_num = self.notebook.get_current_page()
        if page_num != -1:
            self.notebook.remove_page(page_num)

            # If all tabs are closed, create a new one
            if self.notebook.get_n_pages() == 0:
                self.add_new_tab("https://www.google.com")

    def on_close_tab_clicked(self, widget):
        self.on_close_tab(widget)

    def on_tab_close_clicked(self, button, tab):
        page_num = self.notebook.page_num(tab)
        if page_num != -1:
            self.notebook.remove_page(page_num)

            # If all tabs are closed, create a new one
            if self.notebook.get_n_pages() == 0:
                self.add_new_tab("https://www.google.com")

    def on_tab_switch(self, notebook, page, page_num):
        # Get the current tab
        tab = self.get_current_tab()
        if tab:
            # Update the URL entry with the current tab's URL
            uri = tab.webview.get_uri()
            if uri:
                self.url_entry.set_text(uri)

            # Update navigation buttons
            tab.update_navigation_buttons()

    def get_current_tab(self):
        page_num = self.notebook.get_current_page()
        if page_num != -1:
            return self.notebook.get_nth_page(page_num)
        return None

    def on_history(self, widget):
        self.statusbar.push(self.statusbar_context, "History functionality not implemented")

    def on_about(self, widget):
        about_dialog = Gtk.AboutDialog()
        about_dialog.set_program_name("GTK Web Browser")
        about_dialog.set_version("1.0")
        about_dialog.set_comments("A simple GTK-based web browser with tabbed browsing")
        about_dialog.set_website("https://github.com")
        about_dialog.run()
        about_dialog.destroy()

    def on_back_clicked(self, widget):
        tab = self.get_current_tab()
        if tab and tab.webview.can_go_back():
            tab.webview.go_back()

    def on_forward_clicked(self, widget):
        tab = self.get_current_tab()
        if tab and tab.webview.can_go_forward():
            tab.webview.go_forward()

    def on_refresh_clicked(self, widget):
        tab = self.get_current_tab()
        if tab:
            tab.webview.reload()

    def on_home_clicked(self, widget):
        tab = self.get_current_tab()
        if tab:
            tab.load_uri("https://www.google.com")

    def on_url_entry_activated(self, widget):
        url = self.url_entry.get_text()
        self.load_url(url)

    def on_go_clicked(self, widget):
        url = self.url_entry.get_text()
        self.load_url(url)

    def load_url(self, url):
        tab = self.get_current_tab()
        if tab:
            tab.load_uri(url)


def main():
    browser = WebBrowser()
    browser.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()