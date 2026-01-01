# This extension adds support for .app bundles in Nautilus file manager.
# Looks at the .desktop file inside the .app bundle to get the executable and icon.
# Shows custom icon for .app bundles.
# Adds a context menu item "Launch Application" for .app bundles.
# Prompts the user to install the app on first launch.
# Installation copies the .app bundle to ~/Applications/ and creates
#  a .desktop file in ~/.local/share/applications/.

from typing import List, Dict, Optional
import gi
import os
import shutil
import configparser
gi.require_version('Gtk', '4.0')
from gi.repository import GObject, Adw, Gtk, Nautilus, Gio

# Track which apps have been prompted for installation
PROMPTED_APPS_FILE = os.path.expanduser("~/.config/nautilus-app-bundle-prompted.txt")

def get_prompted_apps():
    """Get the set of apps that have already been prompted"""
    if not os.path.exists(PROMPTED_APPS_FILE):
        return set()
    with open(PROMPTED_APPS_FILE, 'r') as f:
        return set(line.strip() for line in f.readlines())


def mark_app_prompted(app_path: str):
    """Mark an app as having been prompted"""
    os.makedirs(os.path.dirname(PROMPTED_APPS_FILE), exist_ok=True)
    with open(PROMPTED_APPS_FILE, 'a') as f:
        f.write(app_path + '\n')


def is_app_bundle(file: Nautilus.FileInfo) -> bool:
    """Check if a file is an .app bundle"""
    if not file.is_directory() or not file.get_name().endswith('.app'):
        return False
    
    # Check if .desktop file exists
    app_path = file.get_location().get_path()
    desktop_file = get_desktop_file_path(app_path)
    return desktop_file is not None


def get_desktop_file_path(app_path: str) -> Optional[str]:
    """Get the .desktop file path inside the app bundle"""
    # Look for .desktop files in the app bundle
    if not os.path.isdir(app_path):
        return None
    
    for filename in os.listdir(app_path):
        if filename.endswith('.desktop'):
            return os.path.join(app_path, filename)
    return None


def parse_desktop_file(app_path: str) -> Optional[Dict[str, str]]:
    """Parse the .desktop file and return relevant fields"""
    desktop_file = get_desktop_file_path(app_path)
    if not desktop_file:
        return None
    
    try:
        config = configparser.ConfigParser()
        config.read(desktop_file)
        
        if 'Desktop Entry' not in config:
            return None
        
        entry = config['Desktop Entry']
        return {
            'Name': entry.get('Name', ''),
            'Exec': entry.get('Exec', ''),
            'Icon': entry.get('Icon', ''),
            'Terminal': entry.get('Terminal', 'false'),
            'Categories': entry.get('Categories', 'Application;'),
            'Type': entry.get('Type', 'Application'),
            'StartupNotify': entry.get('StartupNotify', 'true'),
        }
    except Exception:
        return None


def get_app_icon_path(file: Nautilus.FileInfo) -> Optional[str]:
    """Get the icon path for an app bundle from .desktop file"""
    app_path = file.get_location().get_path()
    desktop_info = parse_desktop_file(app_path)
    
    if not desktop_info or not desktop_info['Icon']:
        return None
    
    icon_path = desktop_info['Icon']
    # If relative path, make it absolute
    if not os.path.isabs(icon_path):
        icon_path = os.path.join(app_path, icon_path)
    
    if os.path.exists(icon_path):
        return icon_path
    return None


def get_app_exec_path(app_path: str) -> Optional[str]:
    """Get the executable path for an app bundle from .desktop file"""
    desktop_info = parse_desktop_file(app_path)
    
    if not desktop_info or not desktop_info['Exec']:
        return None
    
    exec_path = desktop_info['Exec']
    # If relative path, make it absolute
    if not os.path.isabs(exec_path):
        exec_path = os.path.join(app_path, exec_path)
    
    return exec_path


def message_alert(heading: str, body: str, dismiss_label: str = 'Dismiss', parent: Adw.Dialog = None):
    """Show an alert dialog"""
    dialog = Adw.AlertDialog(
        heading=heading,
        body=body,
    )
    dialog.add_response(
        id=dismiss_label,
        label=dismiss_label,
    )
    dialog.present(parent)


def launch_app_bundle(file: Nautilus.FileInfo):
    """Launch the app bundle binary"""
    app_path = file.get_location().get_path()
    exec_path = get_app_exec_path(app_path)
    
    if not exec_path or not os.path.exists(exec_path):
        message_alert(
            heading="Launch Error",
            body=f"Executable not found in .app bundle",
        )
        return
    
    # Make binary executable
    try:
        os.chmod(exec_path, 0o755)
    except Exception as e:
        message_alert(
            heading="Launch Error",
            body=f"Failed to make binary executable: {e}",
        )
        return
    
    # Check if this is the first time launching
    prompted_apps = get_prompted_apps()
    
    if app_path not in prompted_apps:
        # Show installation dialog
        InstallDialog(file).present()
    else:
        # Just launch the app
        import subprocess
        try:
            subprocess.Popen([exec_path], cwd=os.path.dirname(exec_path))
        except Exception as e:
            message_alert(
                heading="Launch Error",
                body=f"Failed to launch application: {e}",
            )


def install_app_bundle(file: Nautilus.FileInfo):
    """Install the app bundle by copying to ~/Applications/ and creating .desktop file"""
    source_app_path = file.get_location().get_path()
    app_name = file.get_name()
    
    # Parse the .desktop file from the source
    desktop_info = parse_desktop_file(source_app_path)
    if not desktop_info:
        message_alert(
            heading="Installation Error",
            body="Failed to read .desktop file from app bundle",
        )
        return False
    
    try:
        # Create ~/Applications/ directory if it doesn't exist
        applications_dir = os.path.expanduser("~/Applications")
        os.makedirs(applications_dir, exist_ok=True)
        
        # Copy the entire .app bundle to ~/Applications/
        dest_app_path = os.path.join(applications_dir, app_name)
        
        # If destination exists, remove it first
        if os.path.exists(dest_app_path):
            shutil.rmtree(dest_app_path)
        
        shutil.copytree(source_app_path, dest_app_path)
        
        # Create .desktop file in ~/.local/share/applications/ with absolute paths
        # Use the original .desktop filename from the bundle
        original_desktop_file = get_desktop_file_path(source_app_path)
        desktop_file_name = os.path.basename(original_desktop_file)
        desktop_file_path = os.path.expanduser(f"~/.local/share/applications/{desktop_file_name}")
        
        # Convert relative paths to absolute
        exec_path = desktop_info['Exec']
        if not os.path.isabs(exec_path):
            exec_path = os.path.join(dest_app_path, exec_path)
        
        icon_path = desktop_info['Icon']
        if icon_path and not os.path.isabs(icon_path):
            icon_path = os.path.join(dest_app_path, icon_path)
        elif not icon_path:
            icon_path = 'application-x-executable'
        
        # Create the .desktop file content
        desktop_content = f"""[Desktop Entry]
Type={desktop_info['Type']}
Name={desktop_info['Name']}
Exec={exec_path}
Icon={icon_path}
Terminal={desktop_info['Terminal']}
Categories={desktop_info['Categories']}
StartupNotify={desktop_info['StartupNotify']}
"""
        
        os.makedirs(os.path.dirname(desktop_file_path), exist_ok=True)
        with open(desktop_file_path, 'w') as f:
            f.write(desktop_content)
        
        # Make the executable executable (in case it wasn't)
        if os.path.exists(exec_path):
            os.chmod(exec_path, 0o755)
        
        return True
    except Exception as e:
        message_alert(
            heading="Installation Error",
            body=f"Failed to install application: {e}",
        )
        return False


class InstallDialog(Adw.Dialog):
    def __init__(self, file: Nautilus.FileInfo):
        super().__init__()
        
        self.file = file
        self.app_path = file.get_location().get_path()
        self.app_name = file.get_name()[:-4]
        
        # Set up the dialog
        self.set_title('Install Application')
        self.set_content_width(400)
        
        root = Adw.ToolbarView()
        header_bar = Adw.HeaderBar()
        header_bar.set_decoration_layout(':close')
        root.add_top_bar(header_bar)
        
        body = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            hexpand=True,
            spacing=16,
            margin_top=16,
            margin_bottom=16,
            margin_start=16,
            margin_end=16,
        )
        root.set_content(body)
        
        # Message
        message = Gtk.Label(
            label=f"Do you want to install '{self.app_name}'?\n\nThis will create a launcher in your applications menu.",
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        body.append(message)
        
        # Buttons
        button_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.CENTER,
        )
        body.append(button_box)
        
        no_button = Gtk.Button(
            label='No',
            css_classes=['pill'],
        )
        no_button.connect('clicked', lambda *_: self.on_no_clicked())
        button_box.append(no_button)
        
        yes_button = Gtk.Button(
            label='Yes, Install',
            css_classes=['pill', 'suggested-action'],
        )
        yes_button.connect('clicked', lambda *_: self.on_yes_clicked())
        button_box.append(yes_button)
        
        self.set_child(root)
    
    def on_yes_clicked(self):
        # Install the app bundle
        if install_app_bundle(self.file):
            mark_app_prompted(self.app_path)
            # Launch the installed app
            self.launch_installed_app()
        self.close()
    
    def on_no_clicked(self):
        # Mark as prompted but don't install
        mark_app_prompted(self.app_path)
        # Launch the app
        self.launch_app()
        self.close()
    
    def launch_app(self):
        """Launch the app from the original location"""
        import subprocess
        exec_path = get_app_exec_path(self.app_path)
        if exec_path and os.path.exists(exec_path):
            try:
                os.chmod(exec_path, 0o755)
                subprocess.Popen([exec_path], cwd=os.path.dirname(exec_path))
            except Exception as e:
                message_alert(
                    heading="Launch Error",
                    body=f"Failed to launch application: {e}",
                )
    
    def launch_installed_app(self):
        """Launch the app from the installed location"""
        import subprocess
        installed_app_path = os.path.expanduser(f"~/Applications/{self.file.get_name()}")
        exec_path = get_app_exec_path(installed_app_path)
        if exec_path and os.path.exists(exec_path):
            try:
                os.chmod(exec_path, 0o755)
                subprocess.Popen([exec_path], cwd=os.path.dirname(exec_path))
            except Exception as e:
                message_alert(
                    heading="Launch Error",
                    body=f"Failed to launch application: {e}",
                )


class AppBundleMenuProvider(GObject.GObject, Nautilus.MenuProvider):
    def get_file_items(self, files: List[Nautilus.FileInfo]) -> List[Nautilus.MenuItem]:
        if len(files) != 1:
            return []
        
        file = files[0]
        if not is_app_bundle(file):
            return []
        
        # Create "Launch Application" menu item
        launch_item = Nautilus.MenuItem(
            name="AppBundleMenuProvider::Launch",
            label="Launch Application",
            tip="Launch this application bundle",
        )
        launch_item.connect(
            "activate",
            lambda *_: launch_app_bundle(file),
        )
        
        return [launch_item]


class AppBundleInfoProvider(GObject.GObject, Nautilus.InfoProvider):
    def update_file_info(self, file: Nautilus.FileInfo) -> Nautilus.OperationResult:
        if not is_app_bundle(file):
            return Nautilus.OperationResult.COMPLETE
        
        # Set custom icon if exists
        icon_path = get_app_icon_path(file)
        if icon_path and os.path.exists(icon_path):
            try:
                # Set the custom icon using Gio metadata
                gfile = file.get_location()
                file_info = gfile.query_info('metadata::custom-icon', Gio.FileQueryInfoFlags.NONE, None)
                file_info.set_attribute_string('metadata::custom-icon', f'file://{icon_path}')
                gfile.set_attributes_from_info(file_info, Gio.FileQueryInfoFlags.NONE, None)
            except:
                pass
        
        return Nautilus.OperationResult.COMPLETE
