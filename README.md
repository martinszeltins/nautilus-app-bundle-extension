# App Bundle Nautlus Extension

This extension adds support for .app bundles in Nautilus file manager.

- Looks at the .desktop file inside the .app bundle to get the executable and icon.
- Shows custom icon for .app bundles.
- Adds a context menu item "Launch Application" for .app bundles.
- Prompts the user to install the app on first launch.
- Installation copies the .app bundle to ~/Applications/ and creates a .desktop file in ~/.local/share/applications/.

## Installation

```bash
sudo apt update
sudo apt install -y git curl python3-nautilus python3-charset-normalizer at python3-polib

cp app-bundle-nautilus-extension.py ~/.local/share/nautilus-python/extensions/
nautilus -q
```
