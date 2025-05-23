#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path
import mimetypes
import re
import shutil
import hashlib
import stat
import time
import gi
import cv2
import tempfile

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf, Gdk, Gio, GLib


class FileExplorer(Gtk.Window):
    def __init__(self, start_path, window, nav_bar,transient):
        if window==0:
            Gtk.Window.__init__(self, title="File Explorer")
            self.set_default_size(1100, 800)

            # Use the system theme
            settings = Gtk.Settings.get_default()
            settings.set_property("gtk-application-prefer-dark-theme", False)

        # Initialize variables
        self.trans = transient
        self.current_path = os.path.expanduser("~") if not start_path else start_path
        self.history = [self.current_path]
        self.history_pos = 0

        self.show_hidden = True
        self.show_backup = False
        self.showthumbnails = True
        # self.icon_size = 64
        self.icon_size = 48
        self.columns = 18
        self.sort_by = "type"  # Options: name, size, type, modified
        self.sort_reverse = False
        # Create main vertical box to contain everything
        self.main_vertical_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        if window==0:
            self.add(self.main_vertical_box)
        else:
            window.pack_start(self.main_vertical_box, True, True, 0)

        # Create and add toolbar (now spans the entire window width)
        # This also creates the path bar
        #self.create_toolbar()
        self.path_bar = nav_bar

        # Now create a horizontal box to contain sidebar and content area
        self.horizontal_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.main_vertical_box.pack_start(self.horizontal_box, True, True, 0)

        # Create sidebar (on the left)
        self.create_sidebar()

        # Main layout for file content
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.horizontal_box.pack_start(self.main_box, True, True, 0)

        self.create_custom_status_bar()

        if window==0:
            screen = self.get_screen()
            visual = screen.get_rgba_visual()
            if visual and screen.is_composited():
                self.set_visual(visual)
                self.set_app_paintable(True)

        # Create scrolled window with transparency
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)

        # Make scrolled window paintable
        #scrolled_window.set_app_paintable(True)

        # Connect draw signal for scrolled window transparency
        #scrolled_window.connect("draw", self.on_scrolled_draw)




        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.main_box.pack_start(scrolled_window, True, True, 0)
        self.main_box.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(0,0,0,0.65))



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
        css_provider = Gtk.CssProvider()
        css = """
        flowbox {
            color: white;
        }
        """
        css_provider.load_from_data(css.encode())

        # Apply CSS
        context = self.flow_box.get_style_context()
        context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        #scrolled_window.add(self.flow_box)

        # Set the background color to white for the flow box
        #self.flow_box.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(1,1,1,0.7))
        self.flow_box.set_vexpand(True)
        self.flow_box.set_size_request(800,900)
        self.transient = transient



        if window==0:
            # Connect key press event
            self.connect("key-press-event", self.on_key_press)
        else:
            transient.connect("key-press-event", self.on_key_press)
            #transient.connect("button-press-event", self.on_button_press)

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

        self.setup_drag_and_drop()

        self.is_refresh = False  # Initialize refresh flag

        self.status_box.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(1,1,1,0.9))

        # Load initial directory
        self.load_directory(self.current_path)

    def on_scrolled_draw(self, widget, cairo):
        # Draw semi-transparent background for scrolled window
        #cairo.set_source_rgba(1,1,1, 0.7)  # Adjust the last value (0.7) for opacity
        cairo.set_operator(1)  # OPERATOR_OVER
        cairo.paint()
        return False


    def get_system_drives(self):
        """Get all available drives in the system with Windows-style naming, minimum size 1GB"""
        drives = []
        all_devices = []

        try:
            # Get all block devices with their sizes - use a slightly different lsblk format
            result = subprocess.run(
                ["lsblk", "-b", "-n", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,LABEL"],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')

                for line in lines:
                    parts = line.split()
                    if len(parts) < 3:
                        continue  # Skip lines with insufficient information

                    # Get the basic device info
                    name = parts[0].strip()
                    # Clean up the name - remove any non-alphanumeric characters except digits and known prefixes
                    name = ''.join(c for c in name if c.isalnum() or c in '-')

                    size = int(parts[1])
                    device_type = parts[2]

                    # Get mount point and label if available
                    mount_point = None
                    label = None

                    if len(parts) >= 4 and parts[3] != "":
                        mount_point = parts[3]

                    if len(parts) >= 5:
                        label = " ".join(parts[4:])

                    # Include only partitions of at least 1GB (ignoring whole disks as they're not directly mountable)
                    if device_type == 'part' and size >= 1024 * 1024 * 1024:  # 1GB
                        device_path = f"/dev/{name}"
                        all_devices.append({
                            'device': device_path,
                            'size': size,
                            'type': device_type,
                            'mount_point': mount_point,
                            'label': label
                        })

            # If we didn't get any valid partitions from lsblk, try an alternative approach
            if not all_devices:
                # Use fdisk to list partitions
                try:
                    result = subprocess.run(
                        ["sudo", "fdisk", "-l"],
                        capture_output=True,
                        text=True,
                        check=False
                    )

                    if result.returncode == 0:
                        # Parse fdisk output to get partitions
                        for line in result.stdout.split('\n'):
                            if '/dev/' in line and 'Linux' in line:
                                parts = line.split()
                                device_path = parts[0]
                                # Try to get size in bytes
                                size_bytes = 0
                                for i, part in enumerate(parts):
                                    if part == 'GB':
                                        try:
                                            size_bytes = int(float(parts[i - 1]) * 1024 * 1024 * 1024)
                                            break
                                        except:
                                            pass

                                if size_bytes >= 1024 * 1024 * 1024:  # 1GB
                                    all_devices.append({
                                        'device': device_path,
                                        'size': size_bytes,
                                        'type': 'part',
                                        'mount_point': None,
                                        'label': None
                                    })
                except:
                    pass

            # Assign drive letters starting from C:
            drive_letter = 68  # ASCII for 'C'

            new_drives = []

            # Process the devices
            for device_info in all_devices:
                device = device_info['device']
                if device!="/dev/sda6":
                    is_mounted = device_info['mount_point'] is not None and len(device_info['mount_point'])>=2
                    mount_point = device_info['mount_point']

                    # Determine drive name
                    if device_info['label']:
                        drive_name = device_info['label']
                        print(drive_name)
                    elif mount_point == '/':
                        drive_name = "System Drive"
                    elif mount_point and len(os.path.basename(mount_point).capitalize())<20:
                        drive_name = os.path.basename(mount_point).capitalize()
                    else:
                        # If no label or mount point, use a generic name based on size
                        size_gb = device_info['size'] / (1024 * 1024 * 1024)
                        if size_gb < 10:
                            drive_name = f"{size_gb:.1f} GB Volume"
                        else:
                            drive_name = f"{int(size_gb)} GB Volume"

                    # Generate Windows-style drive name
                    drive_letter_str = chr(drive_letter)
                    if drive_name!= "System Drive":
                        drive_letter += 1
                        # Add to list of drives
                        drives.append({
                            'letter': drive_letter_str,
                            'name': drive_name,
                            'device': device,
                            'is_mounted': is_mounted,
                            'mount_point': mount_point,
                            'size': device_info['size']
                        })
                    else:
                        drive_letter_str = chr(67)
                        new_drives.append({
                            'letter': drive_letter_str,
                            'name': drive_name,
                            'device': device,
                            'is_mounted': is_mounted,
                            'mount_point': mount_point,
                            'size': device_info['size']
                        })

        except Exception as e:
            print(f"Error getting system drives: {str(e)}")

        for driv in drives:
            new_drives.append(driv)

        return new_drives

    def mount_drive(self, device_path):
        """Attempt to mount a drive, asking for sudo password if needed"""
        try:
            # Clean up device path
            device_path = device_path.replace('├─', '').replace('└─', '')

            # Check if already mounted
            result = subprocess.run(
                ["findmnt", "-S", device_path],
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                # Already mounted, get mount point
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    mount_point = lines[1].split()[0]
                    return mount_point

            # Need to mount it
            # Create a temporary mount point in /media
            drive_name = os.path.basename(device_path)
            mount_dir = f"/media/{os.getenv('USER', 'user')}/{drive_name}"

            # Make sure the mount point exists
            try:
                os.makedirs(mount_dir, exist_ok=True)
            except:
                # If we can't create in /media, try /mnt
                mount_dir = f"/mnt/{drive_name}"
                try:
                    os.makedirs(mount_dir, exist_ok=True)
                except:
                    # Last resort - use /tmp
                    mount_dir = f"/tmp/{drive_name}"
                    os.makedirs(mount_dir, exist_ok=True)

            # Try different mounting methods

            # Method 1: Try with udisksctl (no password needed, best option)
            try:
                print(f"Trying to mount {device_path} with udisksctl...")
                result = subprocess.run(
                    ["udisksctl", "mount", "-b", device_path],
                    capture_output=True,
                    text=True,
                    check=False
                )

                print(f"udisksctl result: {result}")

                if result.returncode == 0 and "Mounted" in result.stdout:
                    # Extract mount point from output
                    mount_point = result.stdout.split("at")[1].strip()
                    return mount_point
            except Exception as e:
                print(f"udisksctl failed: {str(e)}")

            # Method 2: Try with pkexec (graphical password prompt)
            try:
                print(f"Trying to mount {device_path} with pkexec...")
                subprocess.run(
                    ["pkexec", "mount", device_path, mount_dir],
                    check=True
                )
                return mount_dir
            except Exception as e:
                print(f"pkexec failed: {str(e)}")

            # Method 3: Use a GTK password dialog with sudo
            try:
                # Create a simple password dialog
                dialog = Gtk.MessageDialog(
                    parent=self.trans,
                    flags=0,
                    message_type=Gtk.MessageType.QUESTION,
                    buttons=Gtk.ButtonsType.OK_CANCEL,
                    text=f"Authentication required to mount {device_path}"
                )

                # Add password entry
                password_entry = Gtk.Entry()
                password_entry.set_visibility(False)  # Hide password
                password_entry.set_invisible_char('*')
                password_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)

                # Add to dialog
                content_area = dialog.get_content_area()
                content_area.add(Gtk.Label(label="Password:"))
                content_area.add(password_entry)
                dialog.show_all()

                response = dialog.run()

                if response == Gtk.ResponseType.OK:
                    password = password_entry.get_text()
                    dialog.destroy()

                    # Use echo to pipe password to sudo (be careful with shell=True)
                    mount_command = f"echo '{password}' | sudo -S mount '{device_path}' '{mount_dir}'"
                    result = subprocess.run(
                        mount_command,
                        shell=True,
                        capture_output=True,
                        text=True
                    )

                    if result.returncode == 0:
                        return mount_dir
                    else:
                        print(f"sudo mount failed: {result.stderr}")
                else:
                    dialog.destroy()
                    return None
            except Exception as e:
                print(f"Password dialog failed: {str(e)}")

            return None

        except Exception as e:
            print(f"Error mounting drive {device_path}: {str(e)}")
            return None

    def on_drive_clicked(self, button):
        """Handle when a drive is clicked in the Devices panel"""
        drive_info = button.device_info
        print(drive_info)

        if drive_info['is_mounted'] and drive_info['mount_point'] and drive_info['mount_point'][0]=='/':
            # Drive is already mounted, just navigate to it
            self.load_directory(drive_info['mount_point'])
        else:
            # Need to mount the drive first
            self.update_status(f"Mounting {drive_info['letter']}: {drive_info['name']}...")

            # Try to mount the drive
            mount_point = self.mount_drive(drive_info['device'])

            if mount_point:
                self.update_status(f"Mounted {drive_info['letter']}: {drive_info['name']}")
                # Navigate to the mount point
                self.load_directory(mount_point)
            else:
                self.show_error_dialog(
                    "Mount Error",
                    f"Could not mount drive {drive_info['letter']}: {drive_info['name']}"
                )

    def setup_drag_and_drop(self):
        # Set up drag source (for dragging items out)
        self.flow_box.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [Gtk.TargetEntry.new("text/uri-list", 0, 0)],
            Gdk.DragAction.MOVE  # Default to MOVE instead of COPY
        )

        # Connect drag signals for source
        self.flow_box.connect("drag-data-get", self.on_drag_data_get)
        self.flow_box.connect("drag-begin", self.on_drag_begin)
        self.flow_box.connect("drag-end", self.on_drag_end)

        # Set up drop targets for the flow box
        self.flow_box.drag_dest_set(
            Gtk.DestDefaults.DROP | Gtk.DestDefaults.HIGHLIGHT,
            [Gtk.TargetEntry.new("text/uri-list", 0, 0)],
            Gdk.DragAction.MOVE  # Default to MOVE
        )

        # Connect drag signals for destination
        self.flow_box.connect("drag-data-received", self.on_drag_data_received)
        self.flow_box.connect("drag-motion", self.on_drag_motion)

        # Store the last highlighted folder child during drag
        self.last_highlighted_child = None
        self.last_highlight_css = None

        # For tracking whether we're the source of the drag
        self.is_drag_source = False
        self.dragged_path = None

        # Flag to track if directory load is due to refresh or navigation
        self.is_refresh = False

    def on_drag_begin(self, widget, context):
        # Mark that we're the source of this drag operation
        self.is_drag_source = True

        # Get selected items
        selected_children = self.flow_box.get_selected_children()
        if not selected_children:
            return False

        # Get the path of the dragged item
        child = selected_children[0]
        box = child.get_child()

        if hasattr(box, 'path'):
            self.dragged_path = box.path

            # Find the image widget in the box for drag icon
            for child_widget in box.get_children():
                if isinstance(child_widget, Gtk.Image):
                    pixbuf = child_widget.get_pixbuf()
                    if pixbuf:
                        Gtk.drag_set_icon_pixbuf(context, pixbuf, 0, 0)
                        break

    def on_drag_end(self, widget, context):
        # If we were dragging to outside our window, refresh to reflect changes
        if self.is_drag_source and self.dragged_path:
            # Check if the file still exists at the original location
            if not os.path.exists(self.dragged_path):
                # File was moved elsewhere, refresh
                self.is_refresh = True  # Mark as refresh to prevent sound
                self.load_directory(self.current_path)
                self.is_refresh = False

        # Reset drag tracking variables
        self.is_drag_source = False
        self.dragged_path = None

        # Reset any folder highlighting
        if self.last_highlighted_child:
            self.unhighlight_child(self.last_highlighted_child)
            self.last_highlighted_child = None

    def on_drag_data_get(self, widget, drag_context, data, info, time):
        selected_children = self.flow_box.get_selected_children()
        if not selected_children:
            return

        # Get selected item path
        child = selected_children[0]
        box = child.get_child()

        if hasattr(box, 'path'):
            file_path = box.path
            # Convert to URI format
            uri = GLib.filename_to_uri(file_path, None)
            # Set the URI as drag data
            data.set_uris([uri])

    def on_drag_motion(self, widget, drag_context, x, y, time):
        # Reset highlight on previously highlighted child
        if self.last_highlighted_child:
            self.unhighlight_child(self.last_highlighted_child)
            self.last_highlighted_child = None

        # Find the item under the pointer
        child = self.flow_box.get_child_at_pos(x, y)

        if child:
            box = child.get_child()
            if hasattr(box, 'path') and box.is_dir:
                # If it's a directory, allow drop and highlight it
                self.highlight_child(child)
                self.last_highlighted_child = child
                # Use MOVE as default action
                Gdk.drag_status(drag_context, Gdk.DragAction.MOVE, time)
                return True

        # Allow drop into the current directory with MOVE
        Gdk.drag_status(drag_context, Gdk.DragAction.MOVE, time)
        return True

    def highlight_child(self, child):
        # Apply highlight to indicate drop target
        css_provider = Gtk.CssProvider()
        css = """
        flowboxchild {
            background-color: rgba(100, 149, 237, 0.3);
            border: 1px solid #6495ED;
        }
        """
        css_provider.load_from_data(css.encode())

        style_context = child.get_style_context()
        style_context.add_provider(
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        # Store the provider for later removal
        self.last_highlight_css = css_provider

    def unhighlight_child(self, child):
        # Remove highlight
        style_context = child.get_style_context()
        if self.last_highlight_css:
            style_context.remove_provider(self.last_highlight_css)
            self.last_highlight_css = None

    def on_drag_data_received(self, widget, drag_context, x, y, data, info, time):
        # Reset any highlight
        if self.last_highlighted_child:
            self.unhighlight_child(self.last_highlighted_child)
            self.last_highlighted_child = None

        # Process the dropped data
        if data and data.get_uris():
            uris = data.get_uris()
            drop_target = self.current_path

            # Check if dropped on a folder
            child = self.flow_box.get_child_at_pos(x, y)
            if child:
                box = child.get_child()
                if hasattr(box, 'path') and box.is_dir:
                    drop_target = box.path

            # Always use MOVE action unless CTRL key is pressed (for copy)
            action = Gdk.DragAction.COPY if (
                    drag_context.get_actions() & Gdk.DragAction.COPY# and
                    #drag_context.get_device().get_state(widget.get_window())[1] & Gdk.ModifierType.CONTROL_MASK
            ) else Gdk.DragAction.MOVE

            # Process the dropped files
            success = False
            for uri in uris:
                if uri.startswith('file://'):
                    source_path = GLib.filename_from_uri(uri)[0]
                    if os.path.exists(source_path):  # Make sure source exists
                        if self.handle_drop(source_path, drop_target, action):
                            success = True

            # Finish the drag operation
            drag_context.finish(success, action == Gdk.DragAction.MOVE, time)

            # Refresh the directory view
            self.is_refresh = True  # Mark as refresh to prevent sound
            self.load_directory(self.current_path)
            self.is_refresh = False

    def handle_drop(self, source_path, target_dir, action):
        try:
            # Validate that we're not trying to move/copy to itself
            if os.path.normpath(source_path) == os.path.normpath(target_dir):
                return False

            # Validate that we're not trying to move a parent into its child
            if target_dir.startswith(source_path + os.sep):
                self.show_error_dialog("Invalid Operation",
                                       "Cannot move a folder into its own subfolder")
                return False

            basename = os.path.basename(source_path)
            dest_path = os.path.join(target_dir, basename)

            # Check if destination exists
            if os.path.exists(dest_path):
                name, ext = os.path.splitext(basename)
                i = 1
                while os.path.exists(dest_path):
                    new_name = f"{name}_{i}{ext}"
                    dest_path = os.path.join(target_dir, new_name)
                    i += 1

            # Copy or move based on the action
            if action == Gdk.DragAction.COPY:
                if os.path.isdir(source_path):
                    shutil.copytree(source_path, dest_path)
                else:
                    shutil.copy2(source_path, dest_path)
                self.update_status(f"Copied: {basename} to {os.path.basename(target_dir)}")

                # Also update system clipboard for interoperability
                self.set_system_clipboard([dest_path], "copy")
                return True

            elif action == Gdk.DragAction.MOVE:
                shutil.move(source_path, dest_path)
                self.update_status(f"Moved: {basename} to {os.path.basename(target_dir)}")

                # Also update system clipboard for interoperability
                self.set_system_clipboard([dest_path], "cut")
                return True
            return False
        except Exception as e:
            self.show_error_dialog("Drop Error", str(e))
            return False

    def set_system_clipboard(self, file_paths, operation="copy"):
        """Set files in system clipboard in a simple text format"""
        # Convert paths to URIs
        uris = [GLib.filename_to_uri(path, None) for path in file_paths]

        # Create a text representation that includes the operation type
        # This is our own custom format that our app will understand
        text_data = f"{operation}\n" + "\n".join(uris)

        # Get clipboard and set text
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text_data, -1)

        # Store in our application clipboard too (as a fallback)
        self.clipboard_operation = operation
        self.clipboard_path = file_paths[0] if file_paths else None

    def get_from_system_clipboard(self):
        """Try to get file paths from system clipboard"""
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

        # Try to get text from clipboard
        text = clipboard.wait_for_text()
        if text:
            lines = text.strip().split("\n")
            if len(lines) > 1:
                operation = lines[0].strip().lower()
                if operation in ["copy", "cut"]:
                    uris = lines[1:]
                    paths = []
                    for uri in uris:
                        if uri.startswith('file://'):
                            try:
                                path = GLib.filename_from_uri(uri)[0]
                                if os.path.exists(path):
                                    paths.append(path)
                            except:
                                pass

                    if paths:
                        return paths, operation

        # Fall back to internal clipboard
        if hasattr(self, 'clipboard_path') and hasattr(self, 'clipboard_operation'):
            if os.path.exists(self.clipboard_path):
                return [self.clipboard_path], self.clipboard_operation

        return None, None

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
                line = 1
                while len(filename) >= 19*line:
                    filename = filename[0:19*line] + "\n" + filename[19*line:]
                    line+=1
                self.file_name_label.set_markup(f"<b>Name:</b>\n{filename}")

                # Get file type
                content_type, encoding = mimetypes.guess_type(file_path)
                if content_type:
                    if len(content_type) >= 20:
                        content_type = content_type[0:20] + "\n" + content_type[20:]
                        if len(content_type)>=40:
                            content_type=content_type[0:37]+"..."

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
                    if len(default_app) >= 20:
                        default_app = default_app[0:17] + "..."
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
        #self.status_box.set_border_width(0)

        # Style the status bar to look like a traditional status bar
        # context = self.status_box.get_style_context()
        # context.add_class(Gtk.STYLE_CLASS_STATUSBAR)

        self.status_box.set_size_request(-1, 30)
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

        if not is_dir:
            open_with_item = Gtk.MenuItem(label="Open with...")
            open_with_item.connect("activate", lambda x: self.show_open_with_dialog(path))
            menu.append(open_with_item)

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

    def show_open_with_dialog(self, file_path):
        """Show dialog to choose application to open a file"""
        try:

            # Get file content type
            content_type, _ = mimetypes.guess_type(file_path)
            if content_type:
                # Set content type if available
                # Create dialog
                dialog = Gtk.AppChooserDialog(
                    title="Open with",
                    parent=self.trans,
                    content_type=content_type,
                    flags=0
                )
            else:
                dialog = Gtk.AppChooserDialog(
                    title="Open with",
                    parent=self.trans,
                    content_type=None,
                    flags=0
                )


            # Run dialog
            response = dialog.run()

            if response == Gtk.ResponseType.OK:
                app_info = dialog.get_app_info()
                if app_info:
                    files = [Gio.File.new_for_path(file_path)]
                    app_info.launch(files, None)

            dialog.destroy()
        except Exception as e:
            self.show_error_dialog("Error", f"Could not open file: {str(e)}")

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
            font-size: 14px;
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
        label.set_margin_top(4)
        label.set_margin_bottom(5)
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
        section.pack_start(palces, False, False, 0)

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
            font-size: 13px;
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
            margin-top: 3px;
            margin-bottom: 2px;
            text-shadow: none;
        }

        button:hover, button:active, button:checked, button:selected {
            background-image: none;
            background-color: transparent;
            font-size: 14px;
            margin-top: 2px;
            margin-bottom: 2px;
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
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

            # Add folder icon
            icon_theme = Gtk.IconTheme.get_default()
            try:
                folder_icon = icon_theme.load_icon("folder", 16, 0)
                if name == "Documents":
                    folder_icon = icon_theme.load_icon("folder-documents", 16, 0)
                if name == "Music":
                    folder_icon = icon_theme.load_icon("folder-music", 16, 0)
                if name == "Videos":
                    folder_icon = icon_theme.load_icon("folder-videos", 16, 0)
                if name == "Desktop":
                    folder_icon = icon_theme.load_icon("user-desktop", 16, 0)
                if name == "Trash":
                    folder_icon = icon_theme.load_icon("user-trash", 16, 0)
                image = Gtk.Image.new_from_pixbuf(folder_icon)
                button_box.pack_start(image, False, False, 0)
            except:
                pass  # If icon loading fails, continue without icon

            # Add the label, left-aligned
            label = Gtk.Label(label=name)
            label.set_halign(Gtk.Align.START)
            label.set_margin_start(6)
            button_box.pack_start(label, True, True, 0)

            button = Gtk.Button()
            button.add(button_box)
            # button.set_halign(Gtk.Align.FILL)
            button.set_relief(Gtk.ReliefStyle.NONE)
            # Add margins to the button
            # button.set_margin_start(18)
            button.set_margin_start(6)
            if name == "Trash":
                button.set_margin_bottom(6)
            # button.set_margin_end(8)
            button.connect("clicked", lambda btn, p=path: self.load_directory(p))
            button_context = button.get_style_context()
            button_context.add_provider(sidebar_style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            section.pack_start(button, False, True, 0)
            # sidebar.pack_start(button, False, True, 0)

        sidebar.pack_start(section, False, True, 0)

        # Add Devices panel
        section = self.make_section("Devices")

        # Get list of drives
        drives = self.get_system_drives()

        if drives:
            count = 0
            for drive in drives:
                # Create a box to hold icon and label
                button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

                # Add drive icon
                icon_theme = Gtk.IconTheme.get_default()
                try:
                    # Select appropriate icon based on drive characteristics
                    if "System Drive" in drive['name']:
                        drive_icon = icon_theme.load_icon("drive-harddisk-system", 16, 0)
                    elif drive['is_mounted'] and "/media" in (drive['mount_point'] or ""):
                        drive_icon = icon_theme.load_icon("drive-removable-media", 16, 0)
                    elif "GB Volume" in drive['name'] and drive['size'] < 64 * 1024 * 1024 * 1024:
                        # Smaller drives likely to be USB drives
                        drive_icon = icon_theme.load_icon("drive-removable-media", 16, 0)
                    else:
                        drive_icon = icon_theme.load_icon("drive-harddisk", 16, 0)

                    image = Gtk.Image.new_from_pixbuf(drive_icon)
                    button_box.pack_start(image, False, False, 0)
                except:
                    # Fallback if icon not found
                    try:
                        drive_icon = icon_theme.load_icon("drive-harddisk", 16, 0)
                        image = Gtk.Image.new_from_pixbuf(drive_icon)
                        button_box.pack_start(image, False, False, 0)
                    except:
                        pass  # If all icon loading fails, continue without icon

                # Add the label, left-aligned (with Windows-style formatting)
                label = Gtk.Label(label=f"{drive['letter']}:\\ {drive['name']}")
                label.set_margin_start(6)
                label.set_halign(Gtk.Align.START)
                button_box.pack_start(label, True, True, 0)

                button = Gtk.Button()
                button.add(button_box)
                button.set_relief(Gtk.ReliefStyle.NONE)
                button.set_margin_start(6)
                count+=1
                if count==len(drives):
                    label.set_margin_bottom(6)

                # Store device info in the button for later use
                button.device_info = drive

                button.connect("clicked", self.on_drive_clicked)
                button_context = button.get_style_context()
                button_context.add_provider(sidebar_style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                section.pack_start(button, False, True, 0)
        else:
            # No drives found or user doesn't have permission to view drives
            label = Gtk.Label(label="No drives detected")
            label.set_halign(Gtk.Align.START)
            label.set_margin_start(6)
            label.set_margin_bottom(6)
            section.pack_start(label, False, False, 2)


        self.devices = section
        sidebar.pack_start(section, False, True, 0)


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
        new_window_button.set_margin_bottom(1)
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
        # share_folder_button.set_margin_end(8)
        share_folder_button.set_margin_bottom(1)
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

        sidebar.pack_start(section, False, True, 0)

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
        #toolbar_box.set_size_request(1080, -1)

        # Second toolbar with icons only
        icon_toolbar = Gtk.Toolbar()
        icon_toolbar.set_style(Gtk.ToolbarStyle.ICONS)
        #icon_toolbar.set_hexpand(True)
        #icon_toolbar.set_size_request(1080, -1)

        toolbar = Gtk.Toolbar()
        toolbar.set_style(Gtk.ToolbarStyle.BOTH_HORIZ)
        #toolbar.set_size_request(140, -1)

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

        b = Gtk.ToolButton()
        b.set_hexpand(True)
        icon_toolbar.insert(b,-1)


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
        toolbar_box.pack_start(toolbar, False, True, 0)
        toolbar_box.pack_start(icon_toolbar, False, True, 0)
        self.main_vertical_box.pack_start(toolbar_box, False, True, 0)
        self.main_vertical_box.pack_start(toolbar2, False, True, 0)

    def on_new_window_clicked(self, button):
        # Open a new window with the current directory
        try:
            subprocess.Popen(["/home/sheeye/Desktop/Explorer.sh", self.current_path])
        except Exception as e:
            self.show_error_dialog("Error opening new window", str(e))

    def load_directory(self, path):
        self.file_details_box.hide()
        path = path.replace("file://","")
        path=path.replace("%20"," ")
        splot = path.split("/")
        splot = splot[len(splot)-1]
        if len(splot)>=2 and splot[0]!="." and splot.__contains__("."):
            parts = path.split("/")
            new_path=""
            for c in range(len(parts)-1):
                new_path+=parts[c]+"/"
            path=new_path
        if (path == self.current_path or path+"/"==self.current_path or path == self.current_path+"/" ) and not self.is_refresh:
            return
        if not self.is_refresh:
            print("LOAD DIRECTORY ",self.current_path,path)
            self.current_path=path
            self.transient.on_uri_changed(self.transient.webview,"")
            newHist = []
            if False:
                transient = self.trans
                for c in range(len(transient.history)):
                    if c == 0 or (transient.history[c] != transient.history[c - 1] and transient.history[c]+"/" != transient.history[c - 1] and transient.history[c] != transient.history[c - 1]+"/"):
                        newHist.append(transient.history[c])
                transient.history = newHist


        if not path.startswith(("/","~","file://")):
            #path="/home/sheeye/"
            self.trans.fileView=False
            return
        if False:
            if path.__contains__(".") and not path.__contains__("/.") and not path.endswith("/"):
                c = path.split("/")
                newpath="/"
                for r in range(len(c)-1):
                    newpath+=c[r]+"/"
                path=newpath


        for child in self.flow_box.get_children():
            self.flow_box.remove(child)

        self.file_details_box.hide()
        #self.devices.hide()
        if path=="/":
            self.devices.show_all()


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
            self.trans.skipHistory = True
            self.transient.webview.load_uri("file://"+path)
            self.path_bar.set_text(self.current_path)

            # Play the folder opened sound only if this is not a refresh
            if not self.is_refresh:
                if self.trans.skipHistory:
                    self.trans.skipHistory = False
                else:
                    self.trans.history.insert(len(self.trans.history) - self.trans.histPoint,  path)
                try:
                    subprocess.Popen(["aplay", "folder_opened.wav"], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                except:
                    # If aplay doesn't work, try paplay (PulseAudio)
                    try:
                        subprocess.Popen(["paplay", "folder_opened.wav"], stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
                    except:
                        pass  # Silently fail if the sound can't be played

            # Get directory contents
            items = []
            while not os.path.isdir(path):
                parts = path.split("/")
                new_path=""
                for c in range(length(parts)-1):
                    new_path+="/"+c
                path = new_path
            for item in os.listdir(path):
                full_path = os.path.join(path, item)
                if (not os.path.basename(full_path).startswith('.') or self.show_hidden) and (not os.path.basename(full_path).endswith('~') or self.show_backup):  # Hide hidden files
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
                # Sort by type first, then by name alphabetically as secondary sort
                items.sort(key=lambda x: (not os.path.isdir(x[1]), x[4], x[0].lower()), reverse=self.sort_reverse)
            elif self.sort_by == "modified":
                items.sort(key=lambda x: (not os.path.isdir(x[1]), x[3]), reverse=self.sort_reverse)

            # Add items to the flow box
            b = 0
            for name, full_path, _, _, _ in items:
                self.add_item(name, full_path)
                self.flow_box.show_all()
                self.update_status(f"{b}/{len(items)} items loaded")
                b+=1
                while Gtk.events_pending():
                    Gtk.main_iteration()

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
        self.is_refresh = False

    def is_animated_webp(self, path):
        """Check if a WebP file contains animation frames."""
        try:
            with open(path, 'rb') as f:
                # WebP file header check (simplified)
                header = f.read(12)
                if header[0:4] != b'RIFF' or header[8:12] != b'WEBP':
                    return False

                # Look for ANIM chunk
                f.seek(0)
                data = f.read(2048)  # Read a reasonable chunk to check for ANIM
                return b'ANIM' in data
        except Exception:
            return False  # Helper method to convert various formats to GIF

    def convert_to_gif(self, path):
        """Convert video or animated image to a GIF for preview."""

        file_size = os.path.getsize(path)
        file_hash = hashlib.md5(path.encode()).hexdigest()
        test_path = os.path.join("/home/sheeye/Videos/Cache", f"preview_{file_hash}_{self.icon_size}.lck")
        if file_size > 300 * 1024 * 1024:  # 100MB
            # Skip animation for large files and use static thumbnail
            print(f"Large video file detected ({file_size / (1024 * 1024):.1f} MB): using static thumbnail")
            return None

        size=file_size
        fps = 10
        secs = 6
        if size> 56 * 1024 * 1024:
            fps=5
            secs=6

        if size> 100 * 1024 * 1024:
            fps=4
            secs=5

        if size> 138 * 1024 * 1024:
            fps=3
            secs=4

        if size> 183 * 1024 * 1024:
            fps=3
            secs=3

        if size> 220 * 1024 * 1024:
            fps=2
            secs=3

        if size > 245 * 1024 * 1024:
            fps = 1
            secs = 3

        if size > 275 * 1024 * 1024:
            fps = 1
            secs = 2

        #fps=10 t=3
        secs = str(secs)

        try:
            # Create a unique hash for the file to avoid name collisions
            #file_hash = hashlib.md5(path.encode()).hexdigest()
            gif_path = os.path.join("/home/sheeye/Videos/Cache", f"preview_{file_hash}_{self.icon_size}.gif")

            # Check if we already have a cached version
            if os.path.exists(gif_path) and os.path.getmtime(gif_path) > os.path.getmtime(path):
                # Verify the GIF is actually animated before returning it
                try:
                    anim = GdkPixbuf.PixbufAnimation.new_from_file(gif_path)
                    if not anim.is_static_image():
                        print("donzo",gif_path)
                        return gif_path
                    # If it's static, we'll recreate it
                except Exception:
                    pass
            if os.path.exists(test_path):
                print("Already tried, exiting...")
                return None

            print("making file")
            t = open(test_path, "w+")
            t.close()

            content_type, _ = mimetypes.guess_type(path)



            # For debugging
            print(f"Converting {path} to animated GIF...")

            # Set up FFmpeg command based on file type
            if content_type and content_type.startswith("video/"):
                # For videos, extract a short segment and convert to GIF
                # Two-step process for better quality
                palette_path = os.path.join("/home/sheeye/Videos/Cache", f"palette_{file_hash}.png")

                # Step 1: Generate palette for better quality
                palette_cmd = [
                    "ffmpeg", "-y", "-i", path,
                    "-t", secs,  # 3 seconds of video
                    "-vf", f"fps={fps},scale={self.icon_size}:-1:flags=lanczos,palettegen",
                    palette_path
                ]

                print("1")

                subprocess.run(
                    palette_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=20
                )

                print("2")

                # Step 2: Create GIF using the palette
                if os.path.exists(palette_path):
                    gif_cmd = [
                        "ffmpeg", "-y",
                        "-i", path,
                        "-i", palette_path,
                        "-t", secs,  # 3 seconds of video
                        "-filter_complex", f"fps={fps},scale={self.icon_size}:-1:flags=lanczos[x];[x][1:v]paletteuse",
                        gif_path
                    ]

                    result = subprocess.run(
                        gif_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=25
                    )

                    print("2")

                    # For debugging
                    if result.returncode != 0:
                        print(f"FFmpeg error: {result.stderr.decode()}")

                    # Clean up palette
                    try:
                        os.remove(palette_path)
                    except:
                        pass
                else:
                    # Fallback to simpler method if palette generation fails
                    simple_cmd = [
                        "ffmpeg", "-y", "-i", path,
                        "-t", "3",
                        "-vf", f"fps=10,scale={self.icon_size}:-1:flags=lanczos",
                        gif_path
                    ]
                    result = subprocess.run(simple_cmd, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL, timeout=10)

                print("3")
            elif content_type == "image/webp" and self.is_animated_webp(path):
                # For animated WebP files
                cmd = [
                    "ffmpeg", "-y", "-i", path,
                    "-vf", f"scale={self.icon_size}:-1:flags=lanczos",
                    gif_path
                ]
                result = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, timeout=10)
            else:
                # Unsupported format
                return None

            # Verify the GIF is actually animated
            if os.path.exists(gif_path):
                try:
                    anim = GdkPixbuf.PixbufAnimation.new_from_file(gif_path)
                    if not anim.is_static_image():
                        print(f"Successfully created animated GIF: {gif_path}")
                        return gif_path
                    else:
                        print(f"Generated GIF is static, not animated: {gif_path}")
                except Exception as e:
                    print(f"Error checking if GIF is animated: {e}")
            else:
                print(f"GIF was not created at path: {gif_path}")

        except Exception as e:
            print(f"Error converting to GIF: {e}")

        return None

    def convert_to_gif2(self, path):
        """Convert video or animated image to a GIF for preview."""
        try:
            # Create a unique hash for the file to avoid name collisions
            file_hash = hashlib.md5(path.encode()).hexdigest()
            icon_size = self.icon_size
            gif_path = os.path.join("/home/sheeye/Videos/Cache", f"preview_{file_hash}_{icon_size}.gif")
            lck_path = os.path.join("/home/sheeye/Videos/Cache", f"preview_{file_hash}_{icon_size}.lck")

            # Check if we already have a cached version
            if os.path.exists(gif_path) and os.path.getmtime(gif_path) > os.path.getmtime(path):
                # Verify the GIF is actually animated before returning it
                try:
                    anim = GdkPixbuf.PixbufAnimation.new_from_file(gif_path)
                    if not anim.is_static_image():
                        return gif_path
                    # If it's static, we'll recreate it
                except Exception:
                    pass
            if os.path.exists(lck_path):
                print("Locked")
                return None

            c = open(lck_path,"w+")
            c.close()


            content_type, _ = mimetypes.guess_type(path)

            # For debugging
            print(f"Converting {path} to animated GIF...")

            # Set up FFmpeg command based on file type
            if content_type and content_type.startswith("video/"):
                # Use the fast method first - this drastically speeds up processing
                # by only reading the start of the file
                fast_cmd = [
                    "ffmpeg", "-y",
                    "-ss", "0",  # Start from the beginning
                    "-i", path,  # Input file
                    "-t", "5",   # Only process 2 seconds
                    "-vf", f"fps=10,scale={self.icon_size}:-1:flags=lanczos",
                    "-an",       # No audio
                    gif_path
                ]

                try:
                    # Set a short timeout to avoid hanging on large files
                    result = subprocess.run(
                        fast_cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=3  # Short timeout for fast processing
                    )

                    # Check if we got a valid animated GIF
                    if result.returncode == 0 and os.path.exists(gif_path):
                        anim = GdkPixbuf.PixbufAnimation.new_from_file(gif_path)
                        if not anim.is_static_image():
                            print(f"Fast method successful: {gif_path}")
                            return gif_path
                except subprocess.TimeoutExpired:
                    print("Fast method timed out, trying fallback...")
                except Exception as e:
                    print(f"Fast method failed: {e}")

                # Fallback: Create a simple animated GIF from a few frames
                # This approach manually extracts frames and combines them
                try:
                    # Create a temporary directory for the frames
                    temp_dir = os.path.join(tempfile.gettempdir(), f"frames_{file_hash}")
                    os.makedirs(temp_dir, exist_ok=True)

                    # Extract 3 frames at 1-second intervals
                    for i in range(3):
                        frame_path = os.path.join(temp_dir, f"frame_{i}.png")
                        frame_cmd = [
                            "ffmpeg", "-y",
                            "-ss", str(i),  # Skip to second i
                            "-i", path,
                            "-vframes", "1",  # Extract exactly one frame
                            "-vf", f"scale={self.icon_size}:-1:flags=lanczos",
                            "-q:v", "2",  # High quality
                            frame_path
                        ]

                        subprocess.run(
                            frame_cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=2  # Short timeout per frame
                        )

                    # Check if we got at least 2 frames
                    frames = [f for f in os.listdir(temp_dir) if f.endswith('.png')]
                    if len(frames) >= 2:
                        # Combine frames into a GIF
                        frames_pattern = os.path.join(temp_dir, "frame_%d.png")
                        combine_cmd = [
                            "ffmpeg", "-y",
                            "-framerate", "1",  # 1 FPS (1 second per frame)
                            "-i", frames_pattern,
                            "-loop", "0",  # Loop forever
                            gif_path
                        ]

                        subprocess.run(
                            combine_cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=3
                        )

                        # Clean up the frames
                        shutil.rmtree(temp_dir, ignore_errors=True)

                        # Verify it's animated
                        if os.path.exists(gif_path):
                            anim = GdkPixbuf.PixbufAnimation.new_from_file(gif_path)
                            if not anim.is_static_image():
                                print(f"Frame-based method successful: {gif_path}")
                                return gif_path
                except Exception as e:
                    print(f"Frame-based method failed: {e}")
                    # Clean up any temporary directory
                    if 'temp_dir' in locals():
                        shutil.rmtree(temp_dir, ignore_errors=True)

            elif content_type == "image/webp" and self.is_animated_webp(path):
                # For animated WebP files - use simpler command
                cmd = [
                    "ffmpeg", "-y", "-i", path,
                    "-vf", f"scale={self.icon_size}:-1:flags=lanczos",
                    gif_path
                ]
                result = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=3)

                # Verify it's animated
                if result.returncode == 0 and os.path.exists(gif_path):
                    anim = GdkPixbuf.PixbufAnimation.new_from_file(gif_path)
                    if not anim.is_static_image():
                        return gif_path
            else:
                # Unsupported format
                return None

        except Exception as e:
            print(f"Error converting to GIF: {e}")

        return None

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
        content_type, _ = mimetypes.guess_type(path)

        if self.showthumbnails and content_type and (
                content_type.startswith("image/") or content_type.startswith("video/")):
            # Create thumbnail for images and videos
            try:
                if os.path.exists(path) and os.path.isfile(path):
                    if content_type.startswith("image/"):
                        # Check if it's an animated image format (GIF, WebP, etc.)
                        if content_type == "image/gif":
                            # GIF - direct support
                            pixbuf_anim = GdkPixbuf.PixbufAnimation.new_from_file(path)
                            image = Gtk.Image.new_from_animation(pixbuf_anim)
                        elif content_type == "image/webp" and self.is_animated_webp(path):
                            # Animated WebP - convert to GIF
                            gif_path = self.convert_to_gif2(path)
                            if gif_path:
                                pixbuf_anim = GdkPixbuf.PixbufAnimation.new_from_file(gif_path)
                                image = Gtk.Image.new_from_animation(pixbuf_anim)
                            else:
                                # Fallback to static preview if conversion fails
                                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, self.icon_size, self.icon_size)
                                image = Gtk.Image.new_from_pixbuf(pixbuf)
                        else:
                            # Static image
                            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, self.icon_size, self.icon_size)
                            image = Gtk.Image.new_from_pixbuf(pixbuf)
                    elif content_type.startswith("video/"):
                        # Convert video to animated GIF for preview
                        gif_path = self.convert_to_gif2(path)
                        if gif_path:
                            try:
                                pixbuf_anim = GdkPixbuf.PixbufAnimation.new_from_file(gif_path)
                                image = Gtk.Image.new_from_animation(pixbuf_anim)
                                print("Done gif for ",path)
                            except Exception as e:
                                print(f"Error loading animation from converted GIF: {e}")
                        else:

                            # Fall back to static thumbnail if GIF conversion failed
                            thumbnail_path = os.path.join(tempfile.gettempdir(), f"thumb_{hash(path)}.png")
                            try:
                                subprocess.run(
                                    ["ffmpegthumbnailer", "-i", path, "-o", thumbnail_path,
                                     "-s", str(self.icon_size), "-t", "10", "-c", "png"],
                                    check=True, timeout=5, stderr=subprocess.DEVNULL
                                )
                                if os.path.exists(thumbnail_path):
                                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                                        thumbnail_path, self.icon_size, self.icon_size)
                                    image = Gtk.Image.new_from_pixbuf(pixbuf)
                            except (subprocess.SubprocessError, subprocess.TimeoutExpired):
                                # Fall back to default icon if thumbnail generation fails
                                pass
            except Exception as e:
                print(f"Error creating thumbnail for {path}: {e}")



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
            print("DEB A")
            self.load_directory(path)
        else:
            # Open file with default application
            try:
                self.trans.fileView = False
                self.trans.forceWeb = True
                self.trans.load_url("file://"+path)
                #self.trans.histPoint+=1
                #subprocess.Popen(["xdg-open", path])
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

    # Modify copy_item and cut_item to use the system clipboard
    def copy_item(self, path):
        self.clipboard_operation = "copy"
        self.clipboard_path = path
        self.set_system_clipboard([path], "copy")
        self.update_status(f"Copied: {os.path.basename(path)}")

    def cut_item(self, path):
        self.clipboard_operation = "cut"
        self.clipboard_path = path
        self.set_system_clipboard([path], "cut")
        self.update_status(f"Cut: {os.path.basename(path)}")

    # Modify paste_item to check system clipboard first
    def paste_item(self):
        # First try to get from system clipboard
        paths, operation = self.get_from_system_clipboard()

        if paths and operation:
            source_path = paths[0]  # Just use the first path for now
            self.clipboard_path = source_path
            self.clipboard_operation = operation
        elif not hasattr(self, 'clipboard_path') or not hasattr(self, 'clipboard_operation'):
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
                self.update_status(f"Copied: {basename} to {self.current_path}")
            elif self.clipboard_operation == "cut":
                shutil.move(source_path, dest_path)
                # Clear clipboard after move
                delattr(self, 'clipboard_path')
                delattr(self, 'clipboard_operation')
                self.update_status(f"Moved: {basename} to {self.current_path}")

            # Mark as refresh to prevent sound
            self.is_refresh = True
            self.load_directory(self.current_path)
            self.is_refresh = False
        except Exception as e:
            self.show_error_dialog("Paste Error", str(e))

    def delete_item(self, path):
        basename = os.path.basename(path)
        is_dir = os.path.isdir(path)

        # Create confirmation dialog
        item_type = "folder" if is_dir else "file"
        dialog = Gtk.MessageDialog(
            parent=self.trans,
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
                self.on_refresh_clicked(None)
            except Exception as e:
                self.show_error_dialog("Delete Error", str(e))

    def rename_dialog(self, path, current_name):
        dialog = Gtk.Dialog(
            title="Rename",
            parent=self.trans,
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
                    #self.load_directory(self.current_path)
                    self.on_refresh_clicked(None)
                except Exception as e:
                    self.show_error_dialog("Rename Error", str(e))

        dialog.destroy()

    def create_folder_dialog(self):
        dialog = Gtk.Dialog(
            title="New Folder",
            parent=self.trans,
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
                    #self.load_directory(self.current_path)
                    self.on_refresh_clicked(None)
                except FileExistsError:
                    self.show_error_dialog("Error", f"A folder named '{folder_name}' already exists")
                except Exception as e:
                    self.show_error_dialog("Error creating folder", str(e))

        dialog.destroy()

    def create_file_dialog(self):
        dialog = Gtk.Dialog(
            title="New File",
            parent=self.trans,
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
                    self.on_refresh_clicked(None)
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
                parent=self.trans,
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
        self.on_refresh_clicked(None)

    def toggle_sort_reverse(self, widget):
        self.sort_reverse = widget.get_active()
        self.on_refresh_clicked(None)

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
        self.is_refresh = True
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
        self.on_refresh_clicked(None)

    def on_button_press(self, widget, event):
        button_num = event.button

        if button_num == 8:
            self.transient.on_back_clicked(None)
            return True
        elif button_num == 9:
            self.transient.on_forward_clicked(None)
            return True

        return False

    def on_key_press(self, widget, event):
        print(event.keyval)
        button_num = event.keyval
        if self.transient.changed>0:
            if button_num == 65470:
                print("changed")
                self.transient.webview = self.transient.webview_org
                self.transient.normie_view.show_all()
                for c in self.transient.tabs_views:
                    c.hide()
                self.transient.update_tab_names()
                self.transient.tab_menu.show_all()
                self.transient.fileViewSwitch()
                return True
            elif button_num > 65470 and button_num <= 65473:
                print("changed")
                for c in self.transient.tabs_views:
                    c.hide()
                self.transient.normie_view.hide()
                self.transient.webview = self.transient.tabs[button_num-65471]
                self.transient.tabs_views[button_num-65471].show_all()
                self.transient.update_tab_names()
                self.transient.tab_menu.show_all()
                self.transient.fileViewSwitch()
                return True
        if not self.transient.fileView and event.keyval == Gdk.KEY_Tab:
            if self.transient.webview==self.transient.webview_org:
                self.transient.changed*=-1
                if self.transient.changed<0:
                    self.transient.embed_view.show_all()
                    self.transient.nav_bar.hide()
                    self.transient.menu_bar.hide()
                    self.transient.full_tool.hide()
                    self.transient.tab_menu.hide()
                    self.transient.normie_view.hide()
                else:
                    self.transient.embed_view.hide()
                    self.transient.normie_view.show_all()
                    self.transient.nav_bar.show_all()
                    self.transient.menu_bar.show_all()
                    self.transient.full_tool.show_all()
                    self.transient.tab_menu.show_all()
        if not self.transient.fileView:
            return False

        if event.keyval == Gdk.KEY_BackSpace:
            self.on_up_clicked(None)
            return True

        if event.keyval == Gdk.KEY_Delete:
            selected_children = self.flow_box.get_selected_children()
            if selected_children:
                child = selected_children[0]
                box = child.get_child()
                if hasattr(box, 'path'):
                    self.delete_without_confirmation(box.path)
                self.on_refresh_clicked(None)
                return True
        if event.keyval == Gdk.KEY_Tab:
            print("hi")
            self.open_terminal(self.current_path)
            return True
        if event.keyval == Gdk.keyval_from_name("bracketleft"):
            self.icon_size/=2
            self.on_refresh_clicked(None)
            #self.load_directory(self.current_path)
            return True
        if event.keyval == Gdk.keyval_from_name("bracketright"):
            self.icon_size*=2
            #self.load_directory(self.current_path)
            self.on_refresh_clicked(None)
            return True
        if event.keyval == 65474:
            self.on_refresh_clicked(None)
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

    def delete_without_confirmation(self, path):
        """Delete file or folder without showing confirmation dialog"""
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.unlink(path)
            self.on_refresh_clicked(None)
        except Exception as e:
            self.show_error_dialog("Delete Error", str(e))

    def show_error_dialog(self, title, message):
        dialog = Gtk.MessageDialog(
            parent=self.trans,
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
        potential_path = potential_path.replace("file://", "")
        if os.path.isdir(potential_path):
            start_path = os.path.abspath(potential_path)
        elif potential_path == ".":
            start_path = os.getcwd()

    # Create and run application
    win = FileExplorer(start_path,0)
    win2 = FileExplorer(start_path,win.main_vertical_box)
    win.connect("destroy", Gtk.main_quit)

    win.show_all()
    #win2.show_all()
    win.file_details_box.hide()
    #win.devices.hide()
    Gtk.main()
