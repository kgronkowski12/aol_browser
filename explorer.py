#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path
import mimetypes
import re
import shutil
import stat
import time
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf, Gdk, Gio, GLib


class FileExplorer(Gtk.Window):
    def __init__(self, start_path):
        Gtk.Window.__init__(self, title="File Explorer")
        self.set_default_size(930, 600)

        # Use the system theme
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme", False)

        # Initialize variables
        self.current_path = os.path.expanduser("~") if not start_path else start_path
        self.history = [self.current_path]
        self.history_pos = 0
        #self.icon_size = 64
        self.icon_size=48
        self.columns = 18
        self.sort_by = "type"  # Options: name, size, type, modified
        self.sort_reverse = False
        # Create main vertical box to contain everything
        self.main_vertical_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.main_vertical_box)

        # Create and add toolbar (now spans the entire window width)
        # This also creates the path bar
        self.create_toolbar()

        # Now create a horizontal box to contain sidebar and content area
        self.horizontal_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.main_vertical_box.pack_start(self.horizontal_box, True, True, 0)

        # Create sidebar (on the left)
        self.create_sidebar()

        # Main layout for file content
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.horizontal_box.pack_start(self.main_box, True, True, 0)

        self.create_custom_status_bar()

        # Scrolled window for file display
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.main_box.pack_start(scrolled_window, True, True, 0)

        self.flow_box = Gtk.FlowBox()
        self.flow_box.set_valign(Gtk.Align.START)
        self.flow_box.set_max_children_per_line(self.columns)
        self.flow_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flow_box.set_homogeneous(True)
        # Change to double-click activation instead of single-click
        self.flow_box.set_activate_on_single_click(False)
        self.flow_box.connect("child-activated", self.on_item_activated)
        # Connect button-press-event to the flow box for right-click detection
        self.flow_box.connect("button-press-event", self.on_flow_box_button_press)
        scrolled_window.add(self.flow_box)
        





        scrolled_window.add(self.flow_box)

        # Set the background color to white for the flow box
        self.flow_box.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(1.0, 1.0, 1.0, 1.0))

        # Style container to ensure the background is always white
        css_provider = Gtk.CssProvider()
        css = b"""
        flowbox {
            background-color: white;
            min-height: 10800px;
        }
        """
        css_provider.load_from_data(css)
        self.flow_box.get_style_context().add_provider(
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


        # Connect key press event
        self.connect("key-press-event", self.on_key_press)

        # Try to import Pango
        try:
            gi.require_version('Pango', '1.0')
            from gi.repository import Pango
            self.has_pango = True
        except:
            self.has_pango = False

        # Add selection changed handler
        self.flow_box.connect("selected-children-changed", self.on_selection_changed)

        # Initialize variables for file details
        self.selected_file_path = None

        # Load initial directory
        self.load_directory(self.current_path)


    def on_selection_changed(self, flow_box):
        selected_children = flow_box.get_selected_children()

        if not selected_children:
            # No selection - hide file details
            self.file_details_box.hide()

            # Reset sidebar background
            sidebar_style_provider = Gtk.CssProvider()
            css = """
            box {
                background-image: url('gradient.png');
                background-repeat: repeat-y;
            }
            """
            sidebar_style_provider.load_from_data(css.encode())
            sidebar_context = self.sidebar.get_style_context()
            sidebar_context.add_provider(
                sidebar_style_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

            self.selected_file_path = None
            return

        # Get selected item's box
        child = selected_children[0]
        box = child.get_child()

        if hasattr(box, 'path'):
            file_path = box.path
            self.selected_file_path = file_path

            # Change sidebar background if it's a file (not a directory)
            if not box.is_dir:
                self.file_details_box.show_all()
                
                # Update file details
                filename = os.path.basename(file_path)
                file_ext = os.path.splitext(filename)[1]

                # Format filename with extension highlighted
                if len(filename)>=27:
                    filename = filename[0:23]+"..."
                self.file_name_label.set_markup(f"<b>Name:</b>\n{filename}")

                # Get file type
                content_type, encoding = mimetypes.guess_type(file_path)
                if content_type:
                    if len(content_type) >= 27:
                        content_type = content_type[0:23] + "..."
                    self.file_type_label.set_markup(f"<b>Type:</b>\n{content_type}")
                else:
                    self.file_type_label.set_markup(f"<b>Type:</b>\nunknown")

                # Get file size
                try:
                    size = os.path.getsize(file_path)
                    self.file_size_label.set_markup(f"<b>Size:</b>\n{self.format_size(size)}")
                except:
                    self.file_size_label.set_markup("<b>Size:</b>\nunknown")

                # Get default application
                self.file_app_label.set_markup(f"<b>Opens with:</b>\nunknown")
                default_app = self.get_default_app(file_path, content_type)
                if default_app:
                    if len(default_app) >= 27:
                        default_app = default_app[0:23] + "..."
                    self.file_app_label.set_markup(f"<b>Opens with:</b>\n{default_app}")

                # Show file details section
                self.file_details_box.show_all()
            else:
                # It's a directory - hide file details
                self.file_details_box.hide()

                # Reset sidebar background
                sidebar_style_provider = Gtk.CssProvider()
                css = """
                box {
                    background-image: url('gradient.png');
                    background-repeat: repeat-y;
                }
                """
                sidebar_style_provider.load_from_data(css.encode())
                sidebar_context = self.sidebar.get_style_context()
                sidebar_context.add_provider(
                    sidebar_style_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )

    def get_default_app(self, file_path, content_type=None):
        """Get the default application name for a file"""
        try:
            if not content_type:
                content_type, _ = mimetypes.guess_type(file_path)

            if not content_type:
                return None

            # Use GTK to get the default app
            app_info = Gio.AppInfo.get_default_for_type(content_type, False)
            if app_info:
                return app_info.get_display_name()

            # Fallback: try to get from xdg-mime
            try:
                result = subprocess.run(
                    ["xdg-mime", "query", "default", content_type],
                    capture_output=True, text=True, check=False
                )
                if result.returncode == 0 and result.stdout.strip():
                    desktop_file = result.stdout.strip()
                    # Extract app name from desktop file
                    app_name = desktop_file.split('.')[0]
                    return app_name.capitalize()
            except:
                pass

            return None
        except:
            return None

    def create_custom_status_bar(self):
        # Create a horizontal box for the status bar
        self.status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.status_box.set_border_width(0)

        # Style the status bar to look like a traditional status bar
        #context = self.status_box.get_style_context()
        #context.add_class(Gtk.STYLE_CLASS_STATUSBAR)

        self.status_box.set_size_request(-1, 10)
        self.status_box.set_margin_start(0)

        # Create a label for displaying file count and other status messages
        self.status_label = Gtk.Label()
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_margin_start(4)
        self.status_label.set_margin_end(4)
        self.status_label.set_margin_bottom(4)

        # Add the label to the status box
        self.status_box.pack_start(self.status_label, True, True, 0)

        # Create an optional second label for additional info (like free space)
        self.status_extra_label = Gtk.Label()
        self.status_extra_label.set_halign(Gtk.Align.END)
        self.status_box.pack_end(self.status_extra_label, False, False, 4)

        # Add the status box to the main box
        self.main_box.pack_end(self.status_box, False, True, 0)

    def update_status(self, message):
        """Update the main status message"""
        self.status_label.set_text(message)

    def update_extra_status(self, message):
        """Update the extra status information (optional)"""
        self.status_extra_label.set_text(message)
        
    def on_flow_box_button_press(self, widget, event):
        """
        Handle button press events in the flow box (both items and background)
        """
        # Get pointer coordinates
        x, y = event.get_coords()

        # Check if click is on an item
        child = self.flow_box.get_child_at_pos(x, y)

        # Handle right-click (button 3)
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
            if child is not None:
                # Right-click on an item

                # First, select the item that was right-clicked if it's not already selected
                self.flow_box.select_child(child)

                # Get the box widget inside the flow box child
                box = child.get_child()
                if hasattr(box, 'path'):
                    # Show context menu for the item
                    self.show_item_context_menu(box, event)
                    return True
            else:
                # Right-click on empty space
                self.show_background_context_menu(event)
                return True

        # Handle left-click for selection
        elif event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
            if child is None:
                # Clear selection when clicking on empty space
                self.flow_box.unselect_all()

        return False

    def show_item_context_menu(self, box, event):
        """Display context menu for a file/folder item"""
        path = box.path
        is_dir = box.is_dir
        name = box.name

        # Create context menu
        menu = Gtk.Menu()

        # Open option
        open_item = Gtk.MenuItem(label="Open")
        open_item.connect("activate", lambda x: self.open_item(path, is_dir))
        menu.append(open_item)

        if is_dir:
            # Open terminal here option
            terminal_item = Gtk.MenuItem(label="Open Terminal Here")
            terminal_item.connect("activate", lambda x: self.open_terminal(path))
            menu.append(terminal_item)

        # Add a separator
        separator = Gtk.SeparatorMenuItem()
        menu.append(separator)

        # Copy path option
        copy_item = Gtk.MenuItem(label="Copy Path")
        copy_item.connect("activate", lambda x: self.copy_to_clipboard(path))
        menu.append(copy_item)

        # Cut option
        cut_item = Gtk.MenuItem(label="Cut")
        cut_item.connect("activate", lambda x: self.cut_item(path))
        menu.append(cut_item)

        # Copy option
        copy_file_item = Gtk.MenuItem(label="Copy")
        copy_file_item.connect("activate", lambda x: self.copy_item(path))
        menu.append(copy_file_item)

        # Add a separator
        separator2 = Gtk.SeparatorMenuItem()
        menu.append(separator2)

        # Rename option
        rename_item = Gtk.MenuItem(label="Rename")
        rename_item.connect("activate", lambda x: self.rename_dialog(path, name))
        menu.append(rename_item)

        # Delete option
        delete_item = Gtk.MenuItem(label="Delete")
        delete_item.connect("activate", lambda x: self.delete_item(path))
        menu.append(delete_item)

        # Add a separator
        separator3 = Gtk.SeparatorMenuItem()
        menu.append(separator3)

        # Properties option
        properties_item = Gtk.MenuItem(label="Properties")
        properties_item.connect("activate", lambda x: self.show_properties(path))
        menu.append(properties_item)

        # Show menu
        menu.show_all()
        menu.popup_at_pointer(event)

    def show_background_context_menu(self, event):
        """Display context menu for empty area in the flow box"""
        # Create context menu for empty area
        menu = Gtk.Menu()

        # Refresh option
        refresh_item = Gtk.MenuItem(label="Refresh")
        refresh_item.connect("activate", lambda x: self.on_refresh_clicked(None))
        menu.append(refresh_item)

        # Separator
        separator = Gtk.SeparatorMenuItem()
        menu.append(separator)

        # New folder option
        new_folder_item = Gtk.MenuItem(label="New Folder")
        new_folder_item.connect("activate", lambda x: self.create_folder_dialog())
        menu.append(new_folder_item)

        # New file option
        new_file_item = Gtk.MenuItem(label="New File")
        new_file_item.connect("activate", lambda x: self.create_file_dialog())
        menu.append(new_file_item)

        # Paste option if clipboard has path
        paste_item = Gtk.MenuItem(label="Paste")
        paste_item.connect("activate", lambda x: self.paste_item())
        menu.append(paste_item)

        # Separator
        separator2 = Gtk.SeparatorMenuItem()
        menu.append(separator2)

        # Terminal option
        terminal_item = Gtk.MenuItem(label="Open Terminal Here")
        terminal_item.connect("activate", lambda x: self.open_terminal(self.current_path))
        menu.append(terminal_item)

        # Share folder option (copy current path)
        share_folder_item = Gtk.MenuItem(label="Share Folder")
        share_folder_item.connect("activate", lambda x: self.on_share_folder_clicked(None))
        menu.append(share_folder_item)

        # Sorting submenu
        sort_item = Gtk.MenuItem(label="Sort By")
        sort_submenu = Gtk.Menu()
        sort_item.set_submenu(sort_submenu)

        # Sorting options
        name_item = Gtk.RadioMenuItem(label="Name")
        name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.set_sort_method("name"))
        sort_submenu.append(name_item)

        size_item = Gtk.RadioMenuItem.new_with_label_from_widget(name_item, "Size")
        size_item.set_active(self.sort_by == "size")
        size_item.connect("activate", lambda x: self.set_sort_method("size"))
        sort_submenu.append(size_item)

        type_item = Gtk.RadioMenuItem.new_with_label_from_widget(name_item, "Type")
        type_item.set_active(self.sort_by == "type")
        type_item.connect("activate", lambda x: self.set_sort_method("type"))
        sort_submenu.append(type_item)

        modified_item = Gtk.RadioMenuItem.new_with_label_from_widget(name_item, "Modified Date")
        modified_item.set_active(self.sort_by == "modified")
        modified_item.connect("activate", lambda x: self.set_sort_method("modified"))
        sort_submenu.append(modified_item)

        # Separator in sort submenu
        sort_sep = Gtk.SeparatorMenuItem()
        sort_submenu.append(sort_sep)

        # Reverse sort option
        reverse_item = Gtk.CheckMenuItem(label="Reverse Order")
        reverse_item.set_active(self.sort_reverse)
        reverse_item.connect("toggled", self.toggle_sort_reverse)
        sort_submenu.append(reverse_item)

        menu.append(sort_item)

        # Properties option
        properties_item = Gtk.MenuItem(label="Properties")
        properties_item.connect("activate", lambda x: self.show_properties(self.current_path))
        menu.append(properties_item)

        # Show menu
        menu.show_all()
        menu.popup_at_pointer(event)

    def make_section(self, name):

        # Set up CSS styling for buttons to remove hover/active effects
        new_style_provider = Gtk.CssProvider()
        css = """
        box {
            background-image: url('box.png');
            background-size: 100% 100%;
        }


        button {
            background-image: url('title.png');
            background-size: 100% 100%;
            font-size: 14px;
            border: none;
            box-shadow: none;
            text-shadow: none;
        }
        
        button:hover, button:active, button:checked, button:selected {
            background-image: url('title.png');
            font-size: 14px;
            border: none;
            box-shadow: none;
            text-shadow: none;
        }
        """
        new_style_provider.load_from_data(css.encode())

        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        section.set_margin_start(10)
        section.set_margin_end(10)
        section.set_margin_top(12)
        section_context = section.get_style_context()
        section_context.add_provider(new_style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        label = Gtk.Label(label=name)
        label.set_margin_start(6)
        label.set_margin_top(2)
        label.set_margin_bottom(3)
        label.set_markup(f"<b>{name}</b>")
        label.set_halign(Gtk.Align.START)
        button_box.pack_start(label, False, True, 0)

        palces = Gtk.Button()
        palces.add(button_box)
        palces.set_margin_start(2)
        palces.set_margin_end(3)
        palces.set_relief(Gtk.ReliefStyle.NONE)
        palces_context = palces.get_style_context()
        palces_context.add_provider(new_style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        section.pack_start(palces,False,False,0)

        return section


    def create_sidebar(self):
        # Create a sidebar with background image
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.set_size_request(200, -1)

        # Set background image
        sidebar_style_provider = Gtk.CssProvider()
        css = """
        box {
            background-image: url('gradient.png');
            background-repeat: repeat-y;
        }
        """
        sidebar_style_provider.load_from_data(css.encode())
        sidebar_context = sidebar.get_style_context()
        sidebar_context.add_provider(
            sidebar_style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        # Set up CSS styling for buttons to remove hover/active effects
        new_style_provider = Gtk.CssProvider()
        css = """
        box {
            background-image: url('box.png');
            background-size: 100% 100%;
        }


        button {
            background-image: url('title.png');
            background-size: 100% 100%;
            font-size: 14px;
        }
        """
        new_style_provider.load_from_data(css.encode())



        # Set up CSS styling for buttons to remove hover/active effects
        sidebar_style_provider = Gtk.CssProvider()
        css = """
        box {
            background-image: url('gradient.png');
            background-repeat: repeat-y;
        }

        button {
            background-image: none;
            background-color: transparent;
            border: none;
            box-shadow: none;
            font-size: 13px;
            margin-top: 1px;
            text-shadow: none;
        }

        button:hover, button:active, button:checked, button:selected {
            background-image: none;
            background-color: transparent;
            font-size: 14px;
            margin-top: 0px;
            border: none;
            box-shadow: none;
            text-shadow: none;
        }
        """
        sidebar_style_provider.load_from_data(css.encode())
        sidebar_context = sidebar.get_style_context()
        sidebar_context.add_provider(
            sidebar_style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


        section = self.make_section("Places")

        # Places items
        places = [
            ("Desktop", os.path.expanduser("~/Desktop")),
            ("Downloads", os.path.expanduser("~/Downloads")),
            ("Documents", os.path.expanduser("~/Documents")),
            ("Music", os.path.expanduser("~/Music")),
            ("Videos", os.path.expanduser("~/Videos")),
            ("Trash", os.path.expanduser("~/.local/share/Trash")),
        ]

        for name, path in places:
            # Create a box to hold icon and label
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

            # Add folder icon
            icon_theme = Gtk.IconTheme.get_default()
            try:
                folder_icon = icon_theme.load_icon("folder", 16, 0)
                if name=="Documents":
                    folder_icon = icon_theme.load_icon("folder-documents", 16, 0)
                if name=="Music":
                    folder_icon = icon_theme.load_icon("folder-music", 16, 0)
                if name=="Videos":
                    folder_icon = icon_theme.load_icon("folder-videos", 16, 0)
                if name=="Desktop":
                    folder_icon = icon_theme.load_icon("user-desktop", 16, 0)
                if name=="Trash":
                    folder_icon = icon_theme.load_icon("user-trash", 16, 0)
                image = Gtk.Image.new_from_pixbuf(folder_icon)
                button_box.pack_start(image, False, False, 0)
            except:
                pass  # If icon loading fails, continue without icon

            # Add the label, left-aligned
            label = Gtk.Label(label=name)
            label.set_halign(Gtk.Align.START)
            button_box.pack_start(label, True, True, 1)

            button = Gtk.Button()
            button.add(button_box)
            #button.set_halign(Gtk.Align.FILL)
            button.set_relief(Gtk.ReliefStyle.NONE)
            # Add margins to the button
            #button.set_margin_start(18)
            button.set_margin_start(6)
            if name=="Trash":
                button.set_margin_bottom(6)
            #button.set_margin_end(8)
            button.connect("clicked", lambda btn, p=path: self.load_directory(p))
            button_context = button.get_style_context()
            button_context.add_provider(sidebar_style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            section.pack_start(button,False,True,2)
            #sidebar.pack_start(button, False, True, 0)


        sidebar.pack_start(section,False,True, 0)




        section = self.make_section("Actions")


        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Add folder icon
        icon_theme = Gtk.IconTheme.get_default()
        try:
            folder_icon = icon_theme.load_icon("application-x-executable", 16, 0)
            image = Gtk.Image.new_from_pixbuf(folder_icon)
            button_box.pack_start(image, False, False, 0)
        except:
            pass  # If icon loading fails, continue without icon

        # New window action

        label = Gtk.Label(label="New Window")
        label.set_halign(Gtk.Align.START)
        button_box.pack_start(label, True, True, 0)

        new_window_button = Gtk.Button()
        new_window_button.add(button_box)
        new_window_button.set_halign(Gtk.Align.FILL)
        new_window_button.set_relief(Gtk.ReliefStyle.NONE)
        # Add margins to the button
        new_window_button.set_margin_start(6)
        new_window_button.set_margin_bottom(3)
        new_window_button.connect("clicked", self.on_new_window_clicked)
        button_context = new_window_button.get_style_context()
        button_context.add_provider(sidebar_style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        section.pack_start(new_window_button, False, True, 0)





        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Add folder icon
        icon_theme = Gtk.IconTheme.get_default()
        try:
            folder_icon = icon_theme.load_icon("folder-publicshare", 16, 0)
            image = Gtk.Image.new_from_pixbuf(folder_icon)
            button_box.pack_start(image, False, False, 0)
        except:
            pass  # If icon loading fails, continue without icon

        # New window action

        label = Gtk.Label(label="Share Folder")
        label.set_halign(Gtk.Align.START)
        button_box.pack_start(label, True, True, 0)

        share_folder_button = Gtk.Button()
        share_folder_button.add(button_box)
        share_folder_button.set_halign(Gtk.Align.FILL)
        share_folder_button.set_relief(Gtk.ReliefStyle.NONE)
        # Add margins to the button
        share_folder_button.set_margin_start(6)
        #share_folder_button.set_margin_end(8)
        share_folder_button.set_margin_bottom(3)
        button_context = share_folder_button.get_style_context()
        button_context.add_provider(sidebar_style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


        share_folder_button.connect("clicked", self.on_share_folder_clicked)
        section.pack_start(share_folder_button, False, True, 0)






        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Add folder icon
        icon_theme = Gtk.IconTheme.get_default()
        try:
            folder_icon = icon_theme.load_icon("network-workgroup", 16, 0)
            image = Gtk.Image.new_from_pixbuf(folder_icon)
            button_box.pack_start(image, False, False, 0)
        except:
            pass  # If icon loading fails, continue without icon

        # New window action


        label = Gtk.Label(label="Network Folder")
        label.set_halign(Gtk.Align.START)
        button_box.pack_start(label, True, True, 0)

        network_folder_button = Gtk.Button()
        network_folder_button.add(button_box)
        network_folder_button.set_halign(Gtk.Align.FILL)
        network_folder_button.set_relief(Gtk.ReliefStyle.NONE)
        # Add margins to the button
        network_folder_button.set_margin_start(6)
        network_folder_button.set_margin_bottom(6)
        network_folder_button.connect("clicked", self.on_network_folder_clicked)
        section.pack_start(network_folder_button, False, True, 0)
        button_context = network_folder_button.get_style_context()
        button_context.add_provider(sidebar_style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        sidebar.pack_start(section,False,True,0)





        self.file_details_box = self.make_section("File Details")


        # Create labels for file details
        self.file_name_label = Gtk.Label()
        self.file_name_label.set_halign(Gtk.Align.START)
        self.file_name_label.set_margin_start(6)
        self.file_name_label.set_margin_end(6)
        self.file_name_label.set_line_wrap(False)
        self.file_name_label.set_selectable(True)
        self.file_details_box.pack_start(self.file_name_label, False, False, 0)

        self.file_type_label = Gtk.Label()
        self.file_type_label.set_halign(Gtk.Align.START)
        self.file_type_label.set_margin_start(6)
        self.file_type_label.set_margin_end(6)
        self.file_details_box.pack_start(self.file_type_label, False, False, 0)

        self.file_size_label = Gtk.Label()
        self.file_size_label.set_halign(Gtk.Align.START)
        self.file_size_label.set_margin_start(6)
        self.file_size_label.set_margin_end(6)
        self.file_details_box.pack_start(self.file_size_label, False, False, 0)

        self.file_app_label = Gtk.Label()
        self.file_app_label.set_halign(Gtk.Align.START)
        self.file_app_label.set_margin_start(6)
        self.file_app_label.set_margin_end(6)
        self.file_app_label.set_margin_bottom(7)
        self.file_details_box.pack_start(self.file_app_label, False, False, 0)



        # Add the file details box to the sidebar (initially hidden)
        sidebar.pack_start(self.file_details_box, False, False, 0)
        self.file_details_box.hide()












        # Add the sidebar to the horizontal box (at the beginning, so it's on the left)
        self.horizontal_box.pack_start(sidebar, False, False, 0)
        self.sidebar = sidebar


        
    def on_share_folder_clicked(self, button):
        # Copy current directory path to clipboard
        self.copy_to_clipboard(self.current_path)
        self.update_status(f"Path copied to clipboard: {self.current_path}")


    def create_toolbar(self):


        toolbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)


        # Second toolbar with icons only
        icon_toolbar = Gtk.Toolbar()
        icon_toolbar.set_style(Gtk.ToolbarStyle.ICONS)
        icon_toolbar.set_size_request(1080, -1)

        toolbar = Gtk.Toolbar()
        toolbar.set_style(Gtk.ToolbarStyle.BOTH_HORIZ)
        toolbar.set_size_request(140, -1)

        # Back button
        back_button = Gtk.ToolButton()
        back_button.set_icon_name("history-back")
        back_button.set_tooltip_text("Back")
        back_button.set_label("Back")
        back_button.set_is_important(True)
        back_button.connect("clicked", self.on_back_clicked)
        toolbar.insert(back_button, -1)

        # Forward button
        forward_button = Gtk.ToolButton()
        forward_button.set_icon_name("history-forward")
        forward_button.set_tooltip_text("Forward")
        forward_button.connect("clicked", self.on_forward_clicked)
        toolbar.insert(forward_button, -1)

        # Up button
        up_button = Gtk.ToolButton()
        up_button.set_icon_name("go-parent-directory")
        up_button.set_tooltip_text("Up")
        up_button.connect("clicked", self.on_up_clicked)
        icon_toolbar.insert(up_button, -1)

        # Home button
        home_button = Gtk.ToolButton()
        home_button.set_icon_name("go-home")
        home_button.set_tooltip_text("Home")
        home_button.connect("clicked", self.on_home_clicked)
        icon_toolbar.insert(home_button, -1)

        # Refresh button
        refresh_button = Gtk.ToolButton()
        refresh_button.set_icon_name("document-refresh")
        refresh_button.set_tooltip_text("Refresh")
        refresh_button.connect("clicked", self.on_refresh_clicked)
        icon_toolbar.insert(refresh_button, -1)

        # Add a separator
        separator = Gtk.SeparatorToolItem()
        icon_toolbar.insert(separator, -1)

        # New folder button
        new_folder_button = Gtk.ToolButton()
        new_folder_button.set_icon_name("folder-new")
        new_folder_button.set_tooltip_text("New Folder")
        new_folder_button.connect("clicked", lambda x: self.create_folder_dialog())
        icon_toolbar.insert(new_folder_button, -1)

        # New file button
        new_file_button = Gtk.ToolButton()
        new_file_button.set_icon_name("document-new")
        new_file_button.set_tooltip_text("New File")
        new_file_button.connect("clicked", lambda x: self.create_file_dialog())
        icon_toolbar.insert(new_file_button, -1)

        # Terminal button
        terminal_button = Gtk.ToolButton()
        terminal_button.set_icon_name("utilities-terminal")
        terminal_button.set_tooltip_text("Open Terminal Here")
        terminal_button.connect("clicked", lambda x: self.open_terminal(self.current_path))
        icon_toolbar.insert(terminal_button, -1)

        # Add a separator
        separator3 = Gtk.SeparatorToolItem()
        icon_toolbar.insert(separator3, -1)

        # Sort button
        sort_button = Gtk.ToolButton()
        sort_button.set_icon_name("view-sort-ascending")
        sort_button.set_tooltip_text("Change Sort Order")
        sort_button.connect("clicked", self.on_sort_clicked)
        icon_toolbar.insert(sort_button, -1)

        # View options
        view_button = Gtk.ToolButton()
        view_button.set_icon_name("view-grid")
        view_button.set_tooltip_text("Change View")
        view_button.connect("clicked", self.on_view_clicked)
        icon_toolbar.insert(view_button, -1)


        toolbar2 = Gtk.Toolbar()
        toolbar2.set_style(Gtk.ToolbarStyle.ICONS)

        # Add "Address:" label
        address_label_item = Gtk.ToolItem()
        address_label = Gtk.Label(label="Address: ")
        address_label_item.add(address_label)
        toolbar2.insert(address_label_item, -1)

        # Add path entry field
        path_entry_item = Gtk.ToolItem()
        self.path_bar = Gtk.Entry()
        self.path_bar.set_text(self.current_path)
        self.path_bar.connect("activate", self.on_path_changed)
        # Make the path bar expand to fill available space
        path_entry_item.set_expand(True)
        self.path_bar.set_margin_start(5)
        self.path_bar.set_margin_end(5)
        path_entry_item.add(self.path_bar)
        toolbar2.insert(path_entry_item, -1)

        # Add navigate/go button
        go_button = Gtk.ToolButton()
        go_button.set_icon_name("system-search")  # or "system-search" or "edit-find"
        go_button.set_tooltip_text("Navigate to this location")
        go_button.connect("clicked", lambda x: self.on_path_changed(self.path_bar))
        toolbar2.insert(go_button, -1)

        # Add toolbar to the main vertical box at the top
        toolbar_box.pack_start(toolbar, False, False, 0)
        toolbar_box.pack_start(icon_toolbar, False, False, 0)
        self.main_vertical_box.pack_start(toolbar_box, False, True, 0)
        self.main_vertical_box.pack_start(toolbar2, False, True, 0)

    def on_new_window_clicked(self, button):
        # Open a new window with the current directory
        try:
            subprocess.Popen(["/home/sheeye/Desktop/Explorer.sh", self.current_path])
        except Exception as e:
            self.show_error_dialog("Error opening new window", str(e))

    def load_directory(self, path):
        # Clear existing items
        for child in self.flow_box.get_children():
            self.flow_box.remove(child)

        self.file_details_box.hide()

        sidebar_style_provider = Gtk.CssProvider()
        css = """
        box {
            background-image: url('gradient.png');
            background-repeat: repeat-y;
        }
        """
        sidebar_style_provider.load_from_data(css.encode())
        sidebar_context = self.sidebar.get_style_context()
        sidebar_context.add_provider(
            sidebar_style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Make sure the flowbox is empty
        while self.flow_box.get_child_at_index(0) is not None:
            self.flow_box.remove(self.flow_box.get_child_at_index(0))

        try:
            # Update path
            self.current_path = path
            self.path_bar.set_text(self.current_path)

            # Play the folder opened sound
            try:
                subprocess.Popen(["aplay", "folder_opened.wav"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except:
                # If aplay doesn't work, try paplay (PulseAudio)
                try:
                    subprocess.Popen(["paplay", "folder_opened.wav"], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                except:
                    pass  # Silently fail if the sound can't be played

            # Get directory contents
            items = []
            for item in os.listdir(path):
                full_path = os.path.join(path, item)
                if not os.path.basename(full_path).startswith('.'):  # Hide hidden files
                    # Get file stats for sorting
                    try:
                        stat_info = os.stat(full_path)
                        size = stat_info.st_size
                        modified = stat_info.st_mtime
                    except:
                        size = 0
                        modified = 0

                    # Get file type
                    if os.path.isdir(full_path):
                        file_type = "folder"
                    else:
                        content_type, _ = mimetypes.guess_type(full_path)
                        file_type = content_type if content_type else "unknown"

                    items.append((item, full_path, size, modified, file_type))

            # Sort items
            if self.sort_by == "name":
                # Always sort with folders first, then by the chosen method
                items.sort(key=lambda x: (not os.path.isdir(x[1]), x[0].lower()), reverse=self.sort_reverse)
            elif self.sort_by == "size":
                items.sort(key=lambda x: (not os.path.isdir(x[1]), x[2]), reverse=self.sort_reverse)
            elif self.sort_by == "type":
                items.sort(key=lambda x: (not os.path.isdir(x[1]), x[4]), reverse=self.sort_reverse)
            elif self.sort_by == "modified":
                items.sort(key=lambda x: (not os.path.isdir(x[1]), x[3]), reverse=self.sort_reverse)

            # Add items to the flow box
            for name, full_path, _, _, _ in items:
                self.add_item(name, full_path)

            # Show all the widgets
            self.flow_box.show_all()

            # Update status bar
            self.update_status(f"{len(items)} items")

        except PermissionError:
            self.show_error_dialog("Permission denied", f"Cannot access {path}")
            self.go_back()
        except FileNotFoundError:
            self.show_error_dialog("Directory not found", f"The directory {path} does not exist")
            self.go_back()
        except Exception as e:
            self.show_error_dialog("Error", str(e))
            self.go_back()

    def add_item(self, name, path):
        is_dir = os.path.isdir(path)

        # Create box for the item
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.START)

        # Get icon for the item
        if is_dir:
            icon_name = "folder"
        else:
            # Determine file type icon
            mimetypes.add_type("application/x-desktop", ".desktop")
            mimetypes.add_type("image/webp", ".webp")
            mimetypes.add_type("backup", ".png~")
            content_type, _ = mimetypes.guess_type(path)

            if path.endswith(("~", ".bak", ".backup")):
                icon_name = "text-x-preview"  # Adjust icon as needed
            elif content_type is None:
                icon_name = "text-x-generic"
            elif "pdf" in (content_type or ""):
                icon_name = "application-pdf"
            elif content_type and any(x in content_type for x in ["zip", "tar", "gzip"]):
                icon_name = "application-zip"
            elif content_type and any(x in content_type for x in ["rar"]):
                icon_name = "application-x-tarz"
            elif content_type and any(x in content_type for x in ["webp"]):
                icon_name = "image-png"
            elif "desktop" in (content_type or ""):
                icon_name = "application-x-executable"
            elif content_type and any(x in content_type for x in ["deb"]):
                icon_name = "drive-optical"
            elif content_type and any(x in content_type for x in ["zip", "tar", "gzip", "x-compressed"]):
                icon_name = "package-x-generic"
            elif content_type and any(x in content_type for x in ["executable", "x-shellscript"]):
                icon_name = "application-x-executable"

            # GPT START

            elif content_type and any(x in content_type for x in [
                "msword", "vnd.openxmlformats-officedocument.wordprocessingml", "application/rtf"
            ]):
                icon_name = "x-office-document"

            elif content_type and any(x in content_type for x in [
                "vnd.ms-excel", "vnd.openxmlformats-officedocument.spreadsheetml"
            ]):
                icon_name = "x-office-spreadsheet"

            elif content_type and any(x in content_type for x in [
                "vnd.ms-powerpoint", "vnd.openxmlformats-officedocument.presentationml"
            ]):
                icon_name = "x-office-presentation"

            elif content_type and any(x in content_type for x in [
                "x-python", "x-javascript", "x-java", "x-csrc", "x-c++src", "x-shellscript", "x-perl", "x-ruby", "x-php"
            ]):
                icon_name = "text-x-script"

            elif content_type and any(x in content_type for x in [
                "sh", "shell", "bash", "bat", "batch", "x-shellscript", "x-shell", "x-bash", "x-php"
            ]):
                icon_name = "application-x-shellscript"

            elif content_type and any(x in content_type for x in [
                "ttf", "utf"
            ]):
                icon_name = "font-ttf"

            elif content_type and any(x in content_type for x in [
                "otf", "utf"
            ]):
                icon_name = "font-otf"


            elif content_type and any(x in content_type for x in [
                "x-executable", "x-msdownload", "x-sharedlib", "octet-stream"
            ]):
                icon_name = "application-x-executable"

            elif content_type and "json" in content_type:
                icon_name = "text-x-script"

            elif content_type and "xml" in content_type:
                icon_name = "text-xml"

            elif content_type and "html" in content_type:
                icon_name = "text-html"

            elif content_type and "csv" in content_type:
                icon_name = "text-csv"
            # GPT END

            elif content_type.startswith("image/"):
                icon_name = "image-x-generic"
            elif content_type.startswith("text/"):
                icon_name = "text-x-generic"
            elif content_type.startswith("video/"):
                icon_name = "video-x-generic"
            elif content_type.startswith("audio/"):
                icon_name = "audio-x-generic"
            else:
                icon_name = "text-x-preview"

        # Create icon
        icon_theme = Gtk.IconTheme.get_default()
        try:
            icon = icon_theme.load_icon(icon_name, self.icon_size, 0)
        except GLib.Error:
            try:
                # Fallback to a generic icon
                icon = icon_theme.load_icon("text-x-generic", self.icon_size, 0)
            except:
                # Last resort fallback
                icon = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, self.icon_size, self.icon_size)
                icon.fill(0x00000000)  # Transparent

        image = Gtk.Image.new_from_pixbuf(icon)
        box.pack_start(image, False, False, 0)

        # Create label
        display_name = self.truncate_text(name, 15)
        label = Gtk.Label(label=display_name)
        label.set_line_wrap(True)
        label.set_max_width_chars(15)
        label.set_justify(Gtk.Justification.CENTER)
        label.set_lines(2)

        if self.has_pango:
            from gi.repository import Pango
            label.set_ellipsize(Pango.EllipsizeMode.END)

        box.pack_start(label, False, False, 0)

        # Store the full path as data
        box.path = path
        box.is_dir = is_dir
        box.name = name

        # Add to flow box
        flow_box_child = Gtk.FlowBoxChild()
        flow_box_child.add(box)
        flow_box_child.show_all()
        self.flow_box.add(flow_box_child)


    def truncate_text(self, text, max_length):
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."

    def on_item_activated(self, flow_box, child):
        box = child.get_child()
        path = box.path

        if box.is_dir:
            # Update history
            if self.history_pos < len(self.history) - 1:
                self.history = self.history[:self.history_pos + 1]

            self.history.append(path)
            self.history_pos = len(self.history) - 1

            # Navigate to directory
            self.load_directory(path)
        else:
            # Open file with default application
            try:
                subprocess.Popen(["xdg-open", path])
            except Exception as e:
                self.show_error_dialog("Error opening file", str(e))

    def open_item(self, path, is_dir):
        if is_dir:
            self.load_directory(path)
        else:
            try:
                subprocess.Popen(["xdg-open", path])
            except Exception as e:
                self.show_error_dialog("Error opening file", str(e))

    def open_terminal(self, path):
        try:
            # Try common terminal emulators
            for terminal in ["xfce4-terminal", "gnome-terminal", "konsole", "xterm"]:
                try:
                    subprocess.Popen([terminal, "--working-directory", path])
                    return
                except FileNotFoundError:
                    continue

            # If we get here, none of the terminals worked
            self.show_error_dialog("Terminal Error", "Could not find a terminal emulator")
        except Exception as e:
            self.show_error_dialog("Error opening terminal", str(e))


    def on_network_folder_clicked(self, button):
        try:
            subprocess.Popen(["thunar", self.current_path])
            return
        except FileNotFoundError:
            print("mef")

    def copy_to_clipboard(self, text):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)

    def cut_item(self, path):
        self.clipboard_operation = "cut"
        self.clipboard_path = path
        self.update_status(f"Cut: {os.path.basename(path)}")

    def copy_item(self, path):
        self.clipboard_operation = "copy"
        self.clipboard_path = path
        self.update_status(f"Copied: {os.path.basename(path)}")

    def paste_item(self):
        if not hasattr(self, 'clipboard_path') or not hasattr(self, 'clipboard_operation'):
            self.show_error_dialog("Paste Error", "No item in clipboard")
            return

        source_path = self.clipboard_path
        if not os.path.exists(source_path):
            self.show_error_dialog("Paste Error", "Source item no longer exists")
            return

        basename = os.path.basename(source_path)
        dest_path = os.path.join(self.current_path, basename)

        # If destination exists, add a suffix
        if os.path.exists(dest_path):
            name, ext = os.path.splitext(basename)
            i = 1
            while os.path.exists(dest_path):
                new_name = f"{name}_{i}{ext}"
                dest_path = os.path.join(self.current_path, new_name)
                i += 1

        try:
            if self.clipboard_operation == "copy":
                if os.path.isdir(source_path):
                    shutil.copytree(source_path, dest_path)
                else:
                    shutil.copy2(source_path, dest_path)
            elif self.clipboard_operation == "cut":
                shutil.move(source_path, dest_path)
                delattr(self, 'clipboard_path')
                delattr(self, 'clipboard_operation')

            self.load_directory(self.current_path)
        except Exception as e:
            self.show_error_dialog("Paste Error", str(e))

    def delete_item(self, path):
        basename = os.path.basename(path)
        is_dir = os.path.isdir(path)

        # Create confirmation dialog
        item_type = "folder" if is_dir else "file"
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete {item_type}"
        )
        dialog.format_secondary_text(f"Are you sure you want to delete '{basename}'?")
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            try:
                if is_dir:
                    shutil.rmtree(path)
                else:
                    os.unlink(path)
                self.load_directory(self.current_path)
            except Exception as e:
                self.show_error_dialog("Delete Error", str(e))

    def rename_dialog(self, path, current_name):
        dialog = Gtk.Dialog(
            title="Rename",
            parent=self,
            flags=0,
            buttons=(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                Gtk.STOCK_OK, Gtk.ResponseType.OK
            )
        )
        dialog.set_default_size(300, 100)

        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        label = Gtk.Label(label="New name:")
        box.add(label)

        entry = Gtk.Entry()
        entry.set_text(current_name)
        entry.set_activates_default(True)
        box.add(entry)

        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            new_name = entry.get_text()
            if new_name and new_name != current_name:
                new_path = os.path.join(os.path.dirname(path), new_name)
                try:
                    os.rename(path, new_path)
                    self.load_directory(self.current_path)
                except Exception as e:
                    self.show_error_dialog("Rename Error", str(e))

        dialog.destroy()

    def create_folder_dialog(self):
        dialog = Gtk.Dialog(
            title="New Folder",
            parent=self,
            flags=0,
            buttons=(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                Gtk.STOCK_OK, Gtk.ResponseType.OK
            )
        )
        dialog.set_default_size(300, 100)

        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        label = Gtk.Label(label="Folder name:")
        box.add(label)

        entry = Gtk.Entry()
        entry.set_text("New Folder")
        entry.set_activates_default(True)
        box.add(entry)

        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            folder_name = entry.get_text()
            if folder_name:
                folder_path = os.path.join(self.current_path, folder_name)
                try:
                    os.makedirs(folder_path, exist_ok=False)
                    self.load_directory(self.current_path)
                except FileExistsError:
                    self.show_error_dialog("Error", f"A folder named '{folder_name}' already exists")
                except Exception as e:
                    self.show_error_dialog("Error creating folder", str(e))

        dialog.destroy()

    def create_file_dialog(self):
        dialog = Gtk.Dialog(
            title="New File",
            parent=self,
            flags=0,
            buttons=(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                Gtk.STOCK_OK, Gtk.ResponseType.OK
            )
        )
        dialog.set_default_size(300, 100)

        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        label = Gtk.Label(label="File name:")
        box.add(label)

        entry = Gtk.Entry()
        entry.set_text("New File.txt")
        entry.set_activates_default(True)
        box.add(entry)

        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            file_name = entry.get_text()
            if file_name:
                file_path = os.path.join(self.current_path, file_name)
                try:
                    # Create empty file
                    with open(file_path, 'w') as f:
                        pass
                    self.load_directory(self.current_path)
                except FileExistsError:
                    self.show_error_dialog("Error", f"A file named '{file_name}' already exists")
                except Exception as e:
                    self.show_error_dialog("Error creating file", str(e))

        dialog.destroy()

    def show_properties(self, path):
        try:
            # Get file info
            stat_info = os.stat(path)
            is_dir = os.path.isdir(path)
            name = os.path.basename(path)

            # Calculate size
            if is_dir:
                size = self.get_dir_size(path)
            else:
                size = stat_info.st_size

            # Format size
            size_str = self.format_size(size)

            # Format dates
            import datetime
            modified = datetime.datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            accessed = datetime.datetime.fromtimestamp(stat_info.st_atime).strftime('%Y-%m-%d %H:%M:%S')
            # Get permissions
            perm = stat.filemode(stat_info.st_mode)

            # Create dialog
            dialog = Gtk.Dialog(
                title=f"Properties of {name}",
                parent=self,
                flags=0,
                buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
            )
            dialog.set_default_size(400, 300)

            # Create a grid for properties
            grid = Gtk.Grid()
            grid.set_column_spacing(10)
            grid.set_row_spacing(10)
            grid.set_margin_top(20)
            grid.set_margin_bottom(20)
            grid.set_margin_start(20)
            grid.set_margin_end(20)

            # Add properties to grid
            labels = [
                ("Name:", name),
                ("Type:", "Directory" if is_dir else "File"),
                ("Location:", os.path.dirname(path)),
                ("Size:", size_str),
                ("Modified:", modified),
                ("Accessed:", accessed),
                ("Permissions:", perm)
            ]

            for i, (prop, value) in enumerate(labels):
                prop_label = Gtk.Label(label=prop)
                prop_label.set_halign(Gtk.Align.START)
                grid.attach(prop_label, 0, i, 1, 1)

                value_label = Gtk.Label(label=value)
                value_label.set_halign(Gtk.Align.START)
                value_label.set_selectable(True)
                grid.attach(value_label, 1, i, 1, 1)

            # Add grid to dialog
            content_area = dialog.get_content_area()
            content_area.add(grid)
            dialog.show_all()

            # Run dialog
            dialog.run()
            dialog.destroy()

        except Exception as e:
            self.show_error_dialog("Error showing properties", str(e))

    def get_dir_size(self, path):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total_size += os.path.getsize(fp)
                except:
                    pass
        return total_size

    def format_size(self, size_bytes):
        # Convert size to human-readable format
        if size_bytes < 1024:
            return f"{size_bytes} bytes"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def set_sort_method(self, method):
        self.sort_by = method
        self.load_directory(self.current_path)

    def toggle_sort_reverse(self, widget):
        self.sort_reverse = widget.get_active()
        self.load_directory(self.current_path)

    def on_path_changed(self, entry):
        path = entry.get_text()
        if os.path.isdir(os.path.expanduser(path)):
            path = os.path.expanduser(path)

            # Update history
            if self.history_pos < len(self.history) - 1:
                self.history = self.history[:self.history_pos + 1]

            self.history.append(path)
            self.history_pos = len(self.history) - 1

            self.load_directory(path)
        else:
            self.show_error_dialog("Invalid Path", f"The path '{path}' is not a valid directory")
            self.path_bar.set_text(self.current_path)

    def on_back_clicked(self, button):
        self.go_back()

    def go_back(self):
        if self.history_pos > 0:
            self.history_pos -= 1
            path = self.history[self.history_pos]
            self.load_directory(path)

    def on_forward_clicked(self, button):
        if self.history_pos < len(self.history) - 1:
            self.history_pos += 1
            path = self.history[self.history_pos]
            self.load_directory(path)

    def on_up_clicked(self, button):
        parent = os.path.dirname(self.current_path)
        if parent and parent != self.current_path:
            # Update history
            if self.history_pos < len(self.history) - 1:
                self.history = self.history[:self.history_pos + 1]

            self.history.append(parent)
            self.history_pos = len(self.history) - 1

            self.load_directory(parent)

    def on_home_clicked(self, button):
        home = os.path.expanduser("~")

        # Update history
        if self.history_pos < len(self.history) - 1:
            self.history = self.history[:self.history_pos + 1]

        self.history.append(home)
        self.history_pos = len(self.history) - 1

        self.load_directory(home)

    def on_refresh_clicked(self, button):
        self.load_directory(self.current_path)

    def on_sort_clicked(self, button):
        # Create a menu for sort options
        menu = Gtk.Menu()

        name_item = Gtk.RadioMenuItem(label="Name")
        name_item.set_active(self.sort_by == "name")
        name_item.connect("activate", lambda x: self.set_sort_method("name"))
        menu.append(name_item)

        size_item = Gtk.RadioMenuItem.new_with_label_from_widget(name_item, "Size")
        size_item.set_active(self.sort_by == "size")
        size_item.connect("activate", lambda x: self.set_sort_method("size"))
        menu.append(size_item)

        type_item = Gtk.RadioMenuItem.new_with_label_from_widget(name_item, "Type")
        type_item.set_active(self.sort_by == "type")
        type_item.connect("activate", lambda x: self.set_sort_method("type"))
        menu.append(type_item)

        modified_item = Gtk.RadioMenuItem.new_with_label_from_widget(name_item, "Modified Date")
        modified_item.set_active(self.sort_by == "modified")
        modified_item.connect("activate", lambda x: self.set_sort_method("modified"))
        menu.append(modified_item)

        # Separator in sort submenu
        sort_sep = Gtk.SeparatorMenuItem()
        menu.append(sort_sep)

        # Reverse sort option
        reverse_item = Gtk.CheckMenuItem(label="Reverse Order")
        reverse_item.set_active(self.sort_reverse)
        reverse_item.connect("toggled", self.toggle_sort_reverse)
        menu.append(reverse_item)

        menu.show_all()
        menu.popup_at_pointer(None)

    def on_view_clicked(self, button):
        # Cycle through different icon sizes
        sizes = [48, 64, 96, 128]
        current_index = sizes.index(self.icon_size) if self.icon_size in sizes else 0
        next_index = (current_index + 1) % len(sizes)
        self.icon_size = sizes[next_index]

        # Adjust columns based on icon size
        self.columns = 12 if self.icon_size == 48 else 8 if self.icon_size == 64 else 6 if self.icon_size == 96 else 4
        self.flow_box.set_max_children_per_line(self.columns)

        # Reload directory
        self.load_directory(self.current_path)

    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_BackSpace:
            self.on_up_clicked(None)
            return True

        if event.state & Gdk.ModifierType.CONTROL_MASK:
            if event.keyval == Gdk.KEY_h:
                self.on_home_clicked(None)
                return True
            elif event.keyval == Gdk.KEY_r:
                self.on_refresh_clicked(None)
                return True
            elif event.keyval == Gdk.KEY_Left:
                self.on_back_clicked(None)
                return True
            elif event.keyval == Gdk.KEY_Right:
                self.on_forward_clicked(None)
                return True
            elif event.keyval == Gdk.KEY_t:
                self.open_terminal(self.current_path)
                return True
            elif event.keyval == Gdk.KEY_n and event.state & Gdk.ModifierType.SHIFT_MASK:
                self.create_folder_dialog()
                return True
            elif event.keyval == Gdk.KEY_n:
                self.create_file_dialog()
                return True

        return False

    def show_error_dialog(self, title, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()


if __name__ == "__main__":
    # Initialize GTK
    try:
        gi.require_version('Pango', '1.0')
        from gi.repository import Pango
    except:
        print("Pango not available, ellipsizing text may not work properly")

    # Set up mime types
    mimetypes.init()

    # Process command line arguments to get starting path

    print(sys.argv)
    start_path = None
    if len(sys.argv) > 1:
        potential_path = sys.argv[1]
        potential_path = potential_path.replace("file://","")
        if os.path.isdir(potential_path):
            start_path = os.path.abspath(potential_path)
        elif potential_path == ".":
            start_path = os.getcwd()

    # Create and run application
    win = FileExplorer(start_path)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    win.file_details_box.hide()
    Gtk.main()
