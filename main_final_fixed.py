import flet as ft
from flet import *
import os
import sqlite3
import mimetypes
from datetime import datetime
import shutil
from pathlib import Path
import asyncio
from appwrite.client import Client
from appwrite.services.storage import Storage
from appwrite.services.databases import Databases
from appwrite.id import ID
from appwrite.input_file import InputFile
from appwrite.query import Query

# Configuration
APP_NAME = "DocVault"
DB_NAME = "docvault.db"
LOCAL_VAULT_DIR = "docvault_files"
SYNC_INTERVAL = 300  # 5 minutes in seconds

class DocumentVault:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = APP_NAME
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 20
        
        # State variables
        self.current_folder = "root"
        self.selected_tags = []
        self.search_query = ""
        self.last_sync_time = 0
        self.online = False
        self.sync_in_progress = False
        
        # Initialize databases and directories
        self.init_local_storage()
        self.init_appwrite_client()
        
        # UI Components
        self.create_ui()
        
        # Initial load
        self.check_connection()
        self.load_folders()
        self.load_tags()
        self.load_files()
        
        # Periodic sync
        self.page.run_task(self.periodic_sync)
    
    # Replace your init_local_storage method with this thread-safe version:
    def init_local_storage(self):
        """Initialize local SQLite database and storage directory"""
        # Create local vault directory
        self.local_vault_path = Path(LOCAL_VAULT_DIR)
        self.local_vault_path.mkdir(exist_ok=True)
        
        # Initialize SQLite database with check_same_thread=False
        self.local_db = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = self.local_db.cursor()
        
        # Create tables if they don't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT,
                size INTEGER,
                folder TEXT,
                tags TEXT,
                uploaded_at TEXT,
                local_path TEXT,
                cloud_id TEXT,
                sync_status TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS folders (
                name TEXT PRIMARY KEY
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                name TEXT PRIMARY KEY
            )
        ''')
        
        self.local_db.commit()
    
    def init_appwrite_client(self):
        """Initialize Appwrite client (optional if offline)"""
        try:
            self.client = Client()
            self.client.set_endpoint('https://fra.cloud.appwrite.io/v1')
            self.client.set_project('6829cc6a001a39af7849') 
            self.client.set_key('your key')
            
            self.storage = Storage(self.client)
            self.databases = Databases(self.client)
            self.online = True
        except Exception as e:
            print(f"Appwrite initialization failed: {e}. Continuing in offline mode.")
            self.online = False
    
    
    def create_ui(self):
        """Create the main UI components"""
        self.connection_status = ft.Icon(
            name=ft.Icons.CLOUD_QUEUE,
            color=ft.Colors.GREY_500,
            tooltip="Connection status"
        )

        self.search_field = ft.TextField(
            hint_text="Search documents...",
            expand=True,
            on_change=self.handle_search,
            suffix=ft.IconButton(
                icon=ft.Icons.SEARCH,
                on_click=lambda _: self.load_files()
            )
        )

        self.tag_chips = ft.Row(wrap=True, spacing=8)
        self.folder_tree = ft.Column(spacing=5, scroll=ft.ScrollMode.AUTO)
        self.file_list = ft.ListView(expand=True, spacing=10, padding=10)

        self.upload_button = ft.FloatingActionButton(
            icon=ft.Icons.UPLOAD_FILE,
            on_click=self.upload_file,
            tooltip="Upload files"
        )

        self.sync_button = ft.IconButton(
            icon=ft.Icons.SYNC,
            on_click=self.manual_sync,
            tooltip="Sync with cloud",
            disabled=not self.online
        )

        self.page.add(
            ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            self.connection_status,
                            ft.Text(APP_NAME, size=24, weight=ft.FontWeight.BOLD),
                            ft.Container(expand=True),
                            self.sync_button
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER
                    ),
                    ft.Divider(),
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Column(
                                    controls=[
                                        ft.Text("Folders", weight=ft.FontWeight.BOLD),
                                        ft.Card(
                                            content=ft.Container(
                                                content=self.folder_tree,
                                                padding=10,
                                            ),
                                            elevation=2,
                                        ),
                                        ft.Divider(),
                                        ft.Text("Tags", weight=ft.FontWeight.BOLD),
                                        ft.Container(
                                        expand=True,
                                        content=ft.Card(
                                            expand=True,
                                            content=ft.Container(
                                                expand=True,
                                                content=self.file_list,
                                                padding=10
                                            )
                                        )
                                    ),
                                    ],
                                    spacing=10
                                ),
                                width=250,
                            ),
                            ft.VerticalDivider(width=10),
                            ft.Container(expand=True, content=
                                ft.Column(
                                    controls=[
                                        ft.Row([self.search_field]),
                                        ft.Divider(),
                                        ft.Container(
                                            expand=True,
                                            content=ft.Card(
                                                expand=True,
                                                content=ft.Container(
                                                    expand=True,
                                                    content=self.file_list,
                                                    padding=10
                                                )
                                            )
                                        )

                                    ],
                                    spacing=10
                                )
                            )
                        ],
                        expand=True
                    )
                ],
                expand=True,
                spacing=20
            ),
            self.upload_button
        )

    def handle_search(self, e):
        self.search_query = e.control.value
    
    def upload_file(self, e):
        file_picker = ft.FilePicker()
        self.page.overlay.append(file_picker)
        self.page.update()
        
        def on_files_selected(e: ft.FilePickerResultEvent):
            if e.files:
                for f in e.files:
                    self.add_file_to_vault(f.path)
                self.load_files()
            self.page.overlay.remove(file_picker)
            self.page.update()
        
        file_picker.on_result = on_files_selected
        file_picker.pick_files(allow_multiple=True)
    
    def add_file_to_vault(self, file_path):
        """Add a file to the local vault and queue for sync"""
        try:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            file_type, _ = mimetypes.guess_type(file_path)
            file_id = str(datetime.now().timestamp())
            
            # Create local copy
            local_path = self.local_vault_path / f"{file_id}_{file_name}"
            shutil.copy2(file_path, local_path)
            
            # Add to local database
            cursor = self.local_db.cursor()
            cursor.execute('''
                INSERT INTO files (id, name, type, size, folder, tags, uploaded_at, local_path, cloud_id, sync_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_id,
                file_name,
                file_type,
                file_size,
                self.current_folder,
                ",".join(self.selected_tags),
                datetime.now().isoformat(),
                str(local_path),
                None,  # No cloud ID yet
                "new" if self.online else "offline"
            ))
            self.local_db.commit()
            
            # If online, try to sync immediately
            if self.online:
                self.sync_new_files()
            
            self.page.snack_bar = ft.SnackBar(ft.Text(f"Added {file_name} to vault"))
            self.page.snack_bar.open = True
        except Exception as e:
            self.page.snack_bar = ft.SnackBar(ft.Text(f"Error adding file: {str(e)}"))
            self.page.snack_bar.open = True
        finally:
            self.page.update()
    
    # main_final_fixed.py
    def load_files(self):
        """Load files from local database with current filters"""
        self.file_list.controls.clear()

        try:
            cursor = self.local_db.cursor()

            # Build query
            query = "SELECT * FROM files WHERE folder = ?"
            params = [self.current_folder]

            if self.search_query:
                query += " AND name LIKE ?"
                params.append(f"%{self.search_query}%")

            if self.selected_tags:
                tag_conditions = []
                for tag in self.selected_tags:
                    tag_conditions.append("tags LIKE ?")
                    params.append(f"%{tag}%")
                query += " AND (" + " OR ".join(tag_conditions) + ")"

            cursor.execute(query, params)
            files = cursor.fetchall()

            rows = []
            for file in files:
                file_id, name, file_type, size, folder, tags, uploaded_at, local_path, cloud_id, sync_status = file

                icon = self.get_file_icon(file_type)
                sync_icon = self.get_sync_icon(sync_status)

                rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Icon(icon)),
                            ft.DataCell(ft.Text(name)),
                            ft.DataCell(ft.Text(file_type or "Unknown")),
                            ft.DataCell(ft.Text(self.format_size(size))),
                            ft.DataCell(sync_icon),
                            ft.DataCell(
                                ft.Row(
                                    controls=[
                                        ft.IconButton(
                                            icon=ft.Icons.OPEN_IN_NEW,
                                            tooltip="Open",
                                            on_click=lambda e, path=local_path: self.open_file(path)
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.DOWNLOAD,
                                            tooltip="Download",
                                            on_click=lambda e, path=local_path, fname=name: self.download_file(path, fname)
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.DELETE,
                                            tooltip="Delete",
                                            on_click=lambda e, fid=file_id: self.delete_file(fid)
                                        )
                                    ],
                                    spacing=5
                                )
                            ),
                        ]
                    )
                )

            data_table = ft.DataTable(
                columns=[
                    ft.DataColumn(label=ft.Text("Type")),
                    ft.DataColumn(label=ft.Text("Name")),
                    ft.DataColumn(label=ft.Text("MIME")),
                    ft.DataColumn(label=ft.Text("Size")),
                    ft.DataColumn(label=ft.Text("Sync")),
                    ft.DataColumn(label=ft.Text("Actions")),
                ],
                rows=rows
            )

            self.file_list.controls.append(data_table)
            self.page.update()

        except Exception as e:
            print(f"Error loading files: {e}")

    
    def get_file_icon(self, file_type):
        """Get appropriate icon based on file type"""
        if not file_type:
            return ft.Icons.INSERT_DRIVE_FILE
        
        file_type = file_type.lower()
        if "pdf" in file_type:
            return ft.Icons.PICTURE_AS_PDF
        elif "image" in file_type:
            return ft.Icons.IMAGE
        elif "word" in file_type:
            return ft.Icons.DESCRIPTION
        elif "excel" in file_type:
            return ft.Icons.TABLE_CHART
        elif "powerpoint" in file_type:
            return ft.Icons.SLIDESHOW
        elif "text" in file_type or "plain" in file_type:
            return ft.Icons.TEXT_SNIPPET
        elif "zip" in file_type or "compressed" in file_type:
            return ft.Icons.ARCHIVE
        else:
            return ft.Icons.INSERT_DRIVE_FILE
    
    def get_sync_icon(self, sync_status):
        """Get icon indicating sync status"""
        if sync_status == "synced":
            return ft.Icon(ft.Icons.CLOUD_DONE, color=ft.Colors.GREEN)
        elif sync_status == "modified":
            return ft.Icon(ft.Icons.CLOUD_SYNC, color=ft.Colors.ORANGE)
        elif sync_status == "new":
            return ft.Icon(ft.Icons.CLOUD_UPLOAD, color=ft.Colors.BLUE)
        else:  # offline
            return ft.Icon(ft.Icons.CLOUD_OFF, color=ft.Colors.GREY)
    
    def open_file(self, file_path):
        """Open file using system default application"""
        try:
            os.startfile(file_path)  # Windows
        except:
            try:
                os.system(f'xdg-open "{file_path}"')  # Linux
            except:
                try:
                    os.system(f'open "{file_path}"')  # macOS
                except:
                    self.page.snack_bar = ft.SnackBar(ft.Text("Could not open file"))
                    self.page.snack_bar.open = True
                    self.page.update()
    
    def download_file(self, file_path, file_name):
        """Handle file download (in a real app, this would save to downloads)"""
        self.page.snack_bar = ft.SnackBar(ft.Text(f"File ready: {file_name}"))
        self.page.snack_bar.open = True
        self.page.update()
    
    def delete_file(self, file_id):
        """Delete file from local and cloud storage"""
        try:
            cursor = self.local_db.cursor()
            
            # Get file info
            cursor.execute("SELECT local_path, cloud_id FROM files WHERE id = ?", (file_id,))
            result = cursor.fetchone()
            
            if result:
                local_path, cloud_id = result
                
                # Delete local file
                if local_path and os.path.exists(local_path):
                    os.remove(local_path)
                
                # Delete from cloud if online and has cloud ID
                if self.online and cloud_id:
                    try:
                        self.storage.delete_file(bucket_id='documents', file_id=cloud_id)
                        self.databases.delete_document(
                            database_id='vault',
                            collection_id='files',
                            document_id=file_id
                        )
                    except Exception as cloud_err:
                        print(f"Error deleting from cloud: {cloud_err}")
                
                # Delete from local database
                cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
                self.local_db.commit()
                
                self.load_files()
                self.page.snack_bar = ft.SnackBar(ft.Text("File deleted"))
                self.page.snack_bar.open = True
        except Exception as e:
            self.page.snack_bar = ft.SnackBar(ft.Text(f"Error deleting file: {str(e)}"))
            self.page.snack_bar.open = True
        finally:
            self.page.update()
    
    def load_folders(self):
        """Load folders from local database"""
        try:
            cursor = self.local_db.cursor()
            cursor.execute("SELECT name FROM folders ORDER BY name")
            folders = [row[0] for row in cursor.fetchall()]
            
            # Ensure we have at least the root folder
            if not folders:
                folders = ["root"]
                cursor.execute("INSERT INTO folders (name) VALUES (?)", ("root",))
                self.local_db.commit()
            
            def on_folder_click(e):
                self.current_folder = e.control.text
                self.load_files()
                self.page.update()
            
            self.folder_tree.controls.clear()
            for folder in folders:
                self.folder_tree.controls.append(
                    ft.TextButton(
                        text=folder,
                        on_click=on_folder_click,
                        style=ft.ButtonStyle(
                            color=ft.Colors.BLUE if self.current_folder == folder else None
                        )
                    )
                )
            
            self.page.update()
            
        except Exception as e:
            print(f"Error loading folders: {e}")
    
    def load_tags(self):
        """Load tags from local database"""
        try:
            cursor = self.local_db.cursor()
            cursor.execute("SELECT name FROM tags ORDER BY name")
            tags = [row[0] for row in cursor.fetchall()]
            
            def on_tag_click(e, tag):
                if tag in self.selected_tags:
                    self.selected_tags.remove(tag)
                else:
                    self.selected_tags.append(tag)
                self.load_files()
                self.page.update()
            
            self.tag_chips.controls.clear()
            for tag in tags:
                self.tag_chips.controls.append(
                    ft.Chip(
                        label=ft.Text(tag),
                        on_select=lambda e, tag=tag: on_tag_click(e, tag),
                        selected=tag in self.selected_tags
                    )
                )
            
            self.page.update()
            
        except Exception as e:
            print(f"Error loading tags: {e}")
    
    def check_connection(self):
        """Check if we have an internet connection and Appwrite is reachable"""
        try:
            # Simple check by trying to list buckets
            self.storage.list_buckets()
            self.online = True
            self.connection_status.name = ft.Icons.CLOUD
            self.connection_status.color = ft.Colors.GREEN
            self.sync_button.disabled = False
        except:
            self.online = False
            self.connection_status.name = ft.Icons.CLOUD_OFF
            self.connection_status.color = ft.Colors.RED
            self.sync_button.disabled = True
        
        self.connection_status.tooltip = "Online" if self.online else "Offline"
        self.page.update()
    
    def manual_sync(self, e):
        """Manual sync trigger"""
        self.page.snack_bar = ft.SnackBar(ft.Text("Starting sync..."))
        self.page.snack_bar.open = True
        self.page.update()
        
        self.sync_data()
    
            
    async def periodic_sync(self):
        """Periodic sync task"""
        while True:
            if self.online and datetime.now().timestamp() - self.last_sync_time > SYNC_INTERVAL:
                self.sync_data()
            await asyncio.sleep(30)  # Check every 30 seconds
    
    def sync_data(self):
        """Sync local changes with cloud"""
        if not self.online or self.sync_in_progress:
            return
            
        self.sync_in_progress = True
        try:
            # Sync new files
            self.sync_new_files()
            
            # Sync modified files
            self.sync_modified_files()
            
            # Download changes from cloud
            self.download_cloud_changes()
            
            self.last_sync_time = datetime.now().timestamp()
            self.page.snack_bar = ft.SnackBar(ft.Text("Sync complete"))
            self.page.snack_bar.open = True
        except Exception as e:
            self.page.snack_bar = ft.SnackBar(ft.Text(f"Sync error: {str(e)}"))
            self.page.snack_bar.open = True
        finally:
            self.sync_in_progress = False
            self.load_files()  # Refresh UI
            self.page.update()
    
    def sync_new_files(self):
        """Upload new files to cloud"""
        cursor = self.local_db.cursor()
        cursor.execute("SELECT * FROM files WHERE sync_status = 'new'")
        new_files = cursor.fetchall()
        
        for file in new_files:
            file_id, name, file_type, size, folder, tags, uploaded_at, local_path, _, _ = file
            
            try:
                # Upload to Appwrite Storage
                with open(local_path, 'rb') as f:
                    result = self.storage.create_file(
                        bucket_id='documents',
                        file_id=ID.unique(),
                        file=InputFile.from_bytes(f.read(), filename=name)
                    )
                
                # Add metadata to database
                self.databases.create_document(
                    database_id='vault',
                    collection_id='files',
                    document_id=file_id,
                    data={
                        'name': name,
                        'type': file_type,
                        'size': size,
                        'folder': folder,
                        'tags': tags.split(",") if tags else [],
                        'uploaded_at': uploaded_at,
                        'storage_id': result['$id']
                    }
                )
                
                # Update local record
                cursor.execute('''
                    UPDATE files 
                    SET cloud_id = ?, sync_status = 'synced'
                    WHERE id = ?
                ''', (result['$id'], file_id))
                self.local_db.commit()
                
            except Exception as e:
                print(f"Error syncing new file {name}: {e}")
                # Mark as offline if sync failed
                cursor.execute('''
                    UPDATE files 
                    SET sync_status = 'offline'
                    WHERE id = ?
                ''', (file_id,))
                self.local_db.commit()
    
    def sync_modified_files(self):
        """Sync files marked as modified"""
        # Similar to sync_new_files but for updates
        pass
    
    def download_cloud_changes(self):
        """Download changes from cloud to local"""
        if not self.online:
            return
            
        try:
            # Get latest changes from cloud
            cloud_files = self.databases.list_documents(
                database_id='vault',
                collection_id='files',
                queries=[Query.greaterThan('$updatedAt', self.last_sync_time)]
            )
            
            for doc in cloud_files['documents']:
                # Check if we have this file locally
                cursor = self.local_db.cursor()
                cursor.execute("SELECT 1 FROM files WHERE id = ?", (doc['$id'],))
                exists = cursor.fetchone()
                
                if not exists:
                    # Download new file from cloud
                    file_content = self.storage.get_file_download(
                        bucket_id='documents',
                        file_id=doc['storage_id']
                    )
                    
                    # Save locally
                    local_path = self.local_vault_path / f"{doc['$id']}_{doc['name']}"
                    with open(local_path, 'wb') as f:
                        f.write(file_content)
                    
                    # Add to local database
                    cursor.execute('''
                        INSERT INTO files (id, name, type, size, folder, tags, uploaded_at, local_path, cloud_id, sync_status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        doc['$id'],
                        doc['name'],
                        doc['type'],
                        doc['size'],
                        doc['folder'],
                        ",".join(doc.get('tags', [])),
                        doc['$createdAt'],
                        str(local_path),
                        doc['storage_id'],
                        "synced"
                    ))
                    self.local_db.commit()
        except Exception as e:
            print(f"Error downloading cloud changes: {e}")
    
    @staticmethod
    def format_size(size):
        """Convert bytes to human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

def main(page: ft.Page):
    DocumentVault(page)

ft.app(target=main)
