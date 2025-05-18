

---

````markdown
# 📁 DocVault – Personal Document Vault with Offline and Cloud Sync

**DocVault** is a cross-platform document management system built using [Flet](https://flet.dev). It allows you to store, organize, and manage files locally, with optional synchronization to the cloud using Appwrite. Designed with an intuitive UI, it includes folder/tag management, offline-first syncing, and a built-in file viewer.

---

## 🚀 Features

- 📂 **Folder & Tag-based File Organization**
- 🔍 **Search and Filter** documents by name or tag
- 💾 **Offline-first with SQLite** and local storage
- ☁️ **Cloud Sync** with Appwrite Storage & Database
- 📥 Upload, 🔄 Sync, 📤 Download, ❌ Delete operations
- 📊 **DataTable UI** for clean horizontal file layout
- 🌐 Cross-platform (Linux, Windows, macOS)
- ⚡ Built with Python + Flet (Flutter-based UI engine)

---

## 📦 Tech Stack

| Layer        | Tech Used         |
|--------------|-------------------|
| Language     | Python 3.9+       |
| UI Framework | [Flet](https://flet.dev) |
| Database     | SQLite (Local), Appwrite DB (Cloud) |
| Cloud Sync   | Appwrite SDK      |
| File Storage | Local Disk + Appwrite Storage |
| UI Elements  | DataTable, Icons, ListViews, Snackbars |

---

## 🖥️ UI Preview

- Folder list and tag filters on the left
- Search bar at the top
- Table listing for files with actions (open, download, delete)
- Floating Upload button
- Cloud sync status indicator

---

## ⚙️ Setup Instructions

### 1. 🔧 Prerequisites

- Python 3.9+
- Appwrite instance (or skip if offline-only)
- `pip install` the dependencies

```bash
pip install flet appwrite
````

---

### 2. 📁 Run the App

```bash
python main_final_fixed.py
```

The Flet UI will launch in your browser or native window.

---

### 3. 🌐 Configure Appwrite (Optional)

Edit the following in `main_final_fixed.py`:

```python
self.client.set_endpoint('<your-appwrite-endpoint>')
self.client.set_project('<your-project-id>')
self.client.set_key('<your-api-key>')
```

You should also have:

* A `documents` storage bucket
* A `vault` database with a `files` collection

---

## 📄 File Structure

```
.
├── main_final_fixed.py    # Main application script
├── docvault.db            # SQLite DB (auto-created)
├── docvault_files/        # Folder for locally stored files
```

---

## 🧠 Key Concepts

* **Offline-first Design**: Works fully offline using SQLite and file system.
* **Sync Model**: Tracks new, modified, and deleted files, syncing them when online.
* **Cross-platform File Handling**: Uses `os.startfile`, `xdg-open`, or `open` based on OS.

---

## 🛡 Known Limitations

* `os.startfile()` is Windows-specific – fallback logic is implemented for Linux/macOS.
* Appwrite Python SDK is not guaranteed to work on Android mobile devices.
* File picker behavior may vary slightly across platforms.

---

## 📬 Contact

Maintained by **Sharath DHD**
📧 [Reach me on GitHub](https://github.com/sharathDHD)

---
