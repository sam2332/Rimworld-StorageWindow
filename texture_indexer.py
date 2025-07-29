#!/usr/bin/env python3
"""
Texture File Indexer and Search Tool
====================================

A comprehensive tool to index and search texture files from the RimWorld art assets.
Supports indexing, searching, thumbnail generation, and metadata extraction.

Author: ProgrammerLily
"""

import os
import json
import sqlite3
import hashlib
import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import threading

@dataclass
class TextureInfo:
    """Container for texture file metadata"""
    path: str
    filename: str
    category: str  # RimWorld, Biotech, Ideology, etc.
    subcategory: str  # extracted from folder structure
    file_size: int
    width: int
    height: int
    format: str
    hash_md5: str
    created_date: str
    modified_date: str

class TextureIndexer:
    """Main indexer class for texture files"""
    
    def __init__(self, base_path: str, db_path: str = "texture_index.db"):
        self.base_path = Path(base_path)
        self.db_path = db_path
        self.supported_formats = {'.png', '.jpg', '.jpeg', '.bmp', '.tga', '.psd'}
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database for texture index"""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        
        # Create tables
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS textures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT,
                file_size INTEGER,
                width INTEGER,
                height INTEGER,
                format TEXT,
                hash_md5 TEXT,
                created_date TEXT,
                modified_date TEXT,
                indexed_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes for faster searching
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_filename ON textures(filename)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON textures(category)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_subcategory ON textures(subcategory)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_format ON textures(format)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_dimensions ON textures(width, height)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_size ON textures(file_size)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_filename_category ON textures(filename, category)')
        
        # Enable WAL mode for better performance
        self.cursor.execute('PRAGMA journal_mode=WAL')
        self.cursor.execute('PRAGMA synchronous=NORMAL')
        self.cursor.execute('PRAGMA cache_size=10000')
        self.cursor.execute('PRAGMA temp_store=memory')
        
        self.conn.commit()
    
    def get_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of file"""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception:
            return ""
    
    def get_image_dimensions(self, file_path: Path) -> Tuple[int, int]:
        """Get image dimensions using PIL"""
        try:
            with Image.open(file_path) as img:
                return img.size
        except Exception:
            return (0, 0)
    
    def extract_category_info(self, file_path: Path) -> Tuple[str, str]:
        """Extract category and subcategory from file path"""
        relative_path = file_path.relative_to(self.base_path)
        parts = relative_path.parts
        
        if len(parts) == 0:
            return "Unknown", ""
        
        # Extract main category (RimWorld, Biotech, etc.)
        category = "Unknown"
        if "RimWorld" in parts[0]:
            category = "RimWorld"
        elif "Biotech" in parts[0]:
            category = "Biotech"
        elif "Ideology" in parts[0]:
            category = "Ideology"
        elif "Royalty" in parts[0]:
            category = "Royalty"
        elif "Anomaly" in parts[0]:
            category = "Anomaly"
        elif "Odyssey" in parts[0]:
            category = "Odyssey"
        
        # Extract subcategory (folder structure) - remove art source prefixes
        if len(parts) > 2:
            subcategory_parts = list(parts[1:-1])  # Skip first and last (filename)
            
            # Remove art source folder names to match game paths
            art_source_prefixes = [
                "RimWorldArtSource",
                "BiotechArtSource", 
                "IdeologyArtSource",
                "RoyaltyArtSource",
                "AnomalyArtSource",
                "OdysseyArtSource"
            ]
            
            # Remove the first part if it's an art source folder
            if subcategory_parts and subcategory_parts[0] in art_source_prefixes:
                subcategory_parts = subcategory_parts[1:]
            
            subcategory = "/".join(subcategory_parts)
        else:
            subcategory = ""
        
        return category, subcategory
    
    def index_file(self, file_path: Path) -> Optional[TextureInfo]:
        """Index a single texture file"""
        try:
            if file_path.suffix.lower() not in self.supported_formats:
                return None
            
            stat = file_path.stat()
            category, subcategory = self.extract_category_info(file_path)
            width, height = self.get_image_dimensions(file_path)
            file_hash = self.get_file_hash(file_path)
            
            texture_info = TextureInfo(
                path=str(file_path),
                filename=file_path.name,
                category=category,
                subcategory=subcategory,
                file_size=stat.st_size,
                width=width,
                height=height,
                format=file_path.suffix.lower(),
                hash_md5=file_hash,
                created_date=datetime.fromtimestamp(stat.st_ctime).isoformat(),
                modified_date=datetime.fromtimestamp(stat.st_mtime).isoformat()
            )
            
            return texture_info
            
        except Exception as e:
            print(f"Error indexing {file_path}: {e}")
            return None
    
    def index_directory(self, progress_callback=None):
        """Index all texture files in the base directory"""
        print(f"Starting indexing of {self.base_path}")
        
        # Get all texture files
        texture_files = []
        for ext in self.supported_formats:
            texture_files.extend(self.base_path.rglob(f"*{ext}"))
        
        total_files = len(texture_files)
        print(f"Found {total_files} texture files to index")
        
        indexed_count = 0
        skipped_count = 0
        
        for i, file_path in enumerate(texture_files):
            if progress_callback:
                progress_callback(i, total_files, file_path.name)
            
            # Check if file is already indexed and up to date
            existing = self.get_texture_by_path(str(file_path))
            if existing:
                file_modified = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                if existing['modified_date'] == file_modified:
                    skipped_count += 1
                    continue
            
            texture_info = self.index_file(file_path)
            if texture_info:
                self.save_texture_info(texture_info)
                indexed_count += 1
            
            if (i + 1) % 100 == 0:
                self.conn.commit()
                print(f"Processed {i + 1}/{total_files} files...")
        
        self.conn.commit()
        print(f"Indexing complete! Indexed: {indexed_count}, Skipped: {skipped_count}")
    
    def save_texture_info(self, texture_info: TextureInfo):
        """Save texture info to database"""
        self.cursor.execute('''
            INSERT OR REPLACE INTO textures 
            (path, filename, category, subcategory, file_size, width, height, 
             format, hash_md5, created_date, modified_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            texture_info.path, texture_info.filename, texture_info.category,
            texture_info.subcategory, texture_info.file_size, texture_info.width,
            texture_info.height, texture_info.format, texture_info.hash_md5,
            texture_info.created_date, texture_info.modified_date
        ))
    
    def get_texture_by_path(self, path: str) -> Optional[Dict]:
        """Get texture info by file path"""
        self.cursor.execute('SELECT * FROM textures WHERE path = ?', (path,))
        row = self.cursor.fetchone()
        if row:
            columns = [desc[0] for desc in self.cursor.description]
            return dict(zip(columns, row))
        return None
    
    def search_textures(self, 
                       filename_pattern: str = "",
                       category: str = "",
                       subcategory: str = "",
                       min_width: int = 0,
                       max_width: int = 999999,
                       min_height: int = 0,
                       max_height: int = 999999,
                       format_filter: str = "",
                       limit: int = 1000) -> List[Dict]:
        """Search textures with various filters"""
        
        query = "SELECT * FROM textures WHERE 1=1"
        params = []
        
        if filename_pattern:
            query += " AND filename LIKE ?"
            params.append(f"%{filename_pattern}%")
        
        if category:
            query += " AND category = ?"
            params.append(category)
        
        if subcategory:
            query += " AND subcategory LIKE ?"
            params.append(f"%{subcategory}%")
        
        if min_width > 0:
            query += " AND width >= ?"
            params.append(min_width)
        
        if max_width < 999999:
            query += " AND width <= ?"
            params.append(max_width)
        
        if min_height > 0:
            query += " AND height >= ?"
            params.append(min_height)
        
        if max_height < 999999:
            query += " AND height <= ?"
            params.append(max_height)
        
        if format_filter:
            query += " AND format = ?"
            params.append(format_filter)
        
        query += f" ORDER BY filename LIMIT {limit}"
        
        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()
        columns = [desc[0] for desc in self.cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    def get_statistics(self) -> Dict:
        """Get index statistics"""
        stats = {}
        
        # Total count
        self.cursor.execute('SELECT COUNT(*) FROM textures')
        stats['total_textures'] = self.cursor.fetchone()[0]
        
        # By category
        self.cursor.execute('SELECT category, COUNT(*) FROM textures GROUP BY category')
        stats['by_category'] = dict(self.cursor.fetchall())
        
        # By format
        self.cursor.execute('SELECT format, COUNT(*) FROM textures GROUP BY format')
        stats['by_format'] = dict(self.cursor.fetchall())
        
        # Size statistics
        self.cursor.execute('SELECT AVG(width), AVG(height), AVG(file_size) FROM textures')
        avg_stats = self.cursor.fetchone()
        stats['avg_width'] = round(avg_stats[0] or 0, 2)
        stats['avg_height'] = round(avg_stats[1] or 0, 2)
        stats['avg_file_size'] = round(avg_stats[2] or 0, 2)
        
        return stats
    
    def export_search_results(self, results: List[Dict], output_file: str):
        """Export search results to JSON"""
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Exported {len(results)} results to {output_file}")
    
    def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            self.conn.close()

class TextureSearchGUI:
    """GUI application for texture searching"""
    
    def __init__(self, indexer: TextureIndexer):
        self.indexer = indexer
        self.root = tk.Tk()
        self.root.title("RimWorld Texture Search Tool")
        self.root.geometry("1200x800")
        
        self.current_results = []
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the GUI interface"""
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Search frame
        search_frame = ttk.LabelFrame(main_frame, text="Search Filters", padding=10)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Search controls
        row = 0
        
        # Filename search
        ttk.Label(search_frame, text="Filename:").grid(row=row, column=0, sticky=tk.W, padx=(0, 5))
        self.filename_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.filename_var, width=30).grid(row=row, column=1, sticky=tk.W, padx=(0, 20))
        
        # Category filter
        ttk.Label(search_frame, text="Category:").grid(row=row, column=2, sticky=tk.W, padx=(0, 5))
        self.category_var = tk.StringVar()
        category_combo = ttk.Combobox(search_frame, textvariable=self.category_var, width=15)
        category_combo['values'] = ('', 'RimWorld', 'Biotech', 'Ideology', 'Royalty', 'Anomaly', 'Odyssey')
        category_combo.grid(row=row, column=3, sticky=tk.W)
        
        row += 1
        
        # Subcategory search
        ttk.Label(search_frame, text="Subcategory:").grid(row=row, column=0, sticky=tk.W, padx=(0, 5))
        self.subcategory_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.subcategory_var, width=30).grid(row=row, column=1, sticky=tk.W, padx=(0, 20))
        
        # Format filter
        ttk.Label(search_frame, text="Format:").grid(row=row, column=2, sticky=tk.W, padx=(0, 5))
        self.format_var = tk.StringVar()
        format_combo = ttk.Combobox(search_frame, textvariable=self.format_var, width=15)
        format_combo['values'] = ('', '.png', '.jpg', '.jpeg', '.bmp', '.tga', '.psd')
        format_combo.grid(row=row, column=3, sticky=tk.W)
        
        row += 1
        
        # Size filters
        ttk.Label(search_frame, text="Min Width:").grid(row=row, column=0, sticky=tk.W, padx=(0, 5))
        self.min_width_var = tk.StringVar(value="0")
        ttk.Entry(search_frame, textvariable=self.min_width_var, width=10).grid(row=row, column=1, sticky=tk.W, padx=(0, 20))
        
        ttk.Label(search_frame, text="Max Width:").grid(row=row, column=2, sticky=tk.W, padx=(0, 5))
        self.max_width_var = tk.StringVar(value="999999")
        ttk.Entry(search_frame, textvariable=self.max_width_var, width=10).grid(row=row, column=3, sticky=tk.W)
        
        row += 1
        
        ttk.Label(search_frame, text="Min Height:").grid(row=row, column=0, sticky=tk.W, padx=(0, 5))
        self.min_height_var = tk.StringVar(value="0")
        ttk.Entry(search_frame, textvariable=self.min_height_var, width=10).grid(row=row, column=1, sticky=tk.W, padx=(0, 20))
        
        ttk.Label(search_frame, text="Max Height:").grid(row=row, column=2, sticky=tk.W, padx=(0, 5))
        self.max_height_var = tk.StringVar(value="999999")
        ttk.Entry(search_frame, textvariable=self.max_height_var, width=10).grid(row=row, column=3, sticky=tk.W)
        
        row += 1
        
        # Search and export buttons
        button_frame = ttk.Frame(search_frame)
        button_frame.grid(row=row, column=0, columnspan=4, pady=(10, 0))
        
        ttk.Button(button_frame, text="Search", command=self.perform_search).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Clear", command=self.clear_search).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Export Results", command=self.export_results).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Show Statistics", command=self.show_statistics).pack(side=tk.LEFT)
        
        # Results frame
        results_frame = ttk.LabelFrame(main_frame, text="Search Results", padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True)
        
        # Results treeview
        columns = ('filename', 'category', 'subcategory', 'format', 'width', 'height', 'size')
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show='tree headings')
        
        # Configure columns
        self.results_tree.column('#0', width=0, stretch=False)
        self.results_tree.column('filename', width=200, anchor=tk.W)
        self.results_tree.column('category', width=100, anchor=tk.CENTER)
        self.results_tree.column('subcategory', width=150, anchor=tk.W)
        self.results_tree.column('format', width=80, anchor=tk.CENTER)
        self.results_tree.column('width', width=80, anchor=tk.CENTER)
        self.results_tree.column('height', width=80, anchor=tk.CENTER)
        self.results_tree.column('size', width=100, anchor=tk.E)
        
        # Configure headings
        self.results_tree.heading('filename', text='Filename')
        self.results_tree.heading('category', text='Category')
        self.results_tree.heading('subcategory', text='Subcategory')
        self.results_tree.heading('format', text='Format')
        self.results_tree.heading('width', text='Width')
        self.results_tree.heading('height', text='Height')
        self.results_tree.heading('size', text='Size (KB)')
        
        # Add scrollbars
        tree_scroll_y = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        tree_scroll_x = ttk.Scrollbar(results_frame, orient=tk.HORIZONTAL, command=self.results_tree.xview)
        self.results_tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        
        # Pack treeview and scrollbars
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind double-click to open file
        self.results_tree.bind('<Double-1>', self.open_selected_file)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(10, 0))
    
    def perform_search(self):
        """Perform texture search with current filters"""
        try:
            # Get filter values
            filename = self.filename_var.get().strip()
            category = self.category_var.get().strip()
            subcategory = self.subcategory_var.get().strip()
            format_filter = self.format_var.get().strip()
            
            min_width = int(self.min_width_var.get() or 0)
            max_width = int(self.max_width_var.get() or 999999)
            min_height = int(self.min_height_var.get() or 0)
            max_height = int(self.max_height_var.get() or 999999)
            
            self.status_var.set("Searching...")
            self.root.update()
            
            # Perform search
            results = self.indexer.search_textures(
                filename_pattern=filename,
                category=category,
                subcategory=subcategory,
                min_width=min_width,
                max_width=max_width,
                min_height=min_height,
                max_height=max_height,
                format_filter=format_filter,
                limit=2000
            )
            
            self.current_results = results
            self.populate_results(results)
            
            self.status_var.set(f"Found {len(results)} textures")
            
        except Exception as e:
            messagebox.showerror("Search Error", f"Error performing search: {e}")
            self.status_var.set("Search failed")
    
    def populate_results(self, results: List[Dict]):
        """Populate the results treeview"""
        # Clear existing results
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # Add new results
        for result in results:
            size_kb = round(result['file_size'] / 1024, 1)
            self.results_tree.insert('', tk.END, values=(
                result['filename'],
                result['category'],
                result['subcategory'] or '',
                result['format'],
                result['width'],
                result['height'],
                f"{size_kb} KB"
            ))
    
    def clear_search(self):
        """Clear all search filters"""
        self.filename_var.set("")
        self.category_var.set("")
        self.subcategory_var.set("")
        self.format_var.set("")
        self.min_width_var.set("0")
        self.max_width_var.set("999999")
        self.min_height_var.set("0")
        self.max_height_var.set("999999")
        
        # Clear results
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        self.current_results = []
        self.status_var.set("Search cleared")
    
    def export_results(self):
        """Export current search results"""
        if not self.current_results:
            messagebox.showwarning("No Results", "No search results to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                self.indexer.export_search_results(self.current_results, filename)
                messagebox.showinfo("Export Complete", f"Exported {len(self.current_results)} results to {filename}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Error exporting results: {e}")
    
    def show_statistics(self):
        """Show index statistics"""
        try:
            stats = self.indexer.get_statistics()
            
            stats_window = tk.Toplevel(self.root)
            stats_window.title("Index Statistics")
            stats_window.geometry("400x300")
            
            text_widget = tk.Text(stats_window, wrap=tk.WORD, padx=10, pady=10)
            text_widget.pack(fill=tk.BOTH, expand=True)
            
            stats_text = f"""Texture Index Statistics
=========================

Total Textures: {stats['total_textures']:,}

By Category:
"""
            for category, count in stats['by_category'].items():
                stats_text += f"  {category}: {count:,}\n"
            
            stats_text += f"\nBy Format:\n"
            for format_type, count in stats['by_format'].items():
                stats_text += f"  {format_type}: {count:,}\n"
            
            stats_text += f"""
Average Dimensions:
  Width: {stats['avg_width']} px
  Height: {stats['avg_height']} px
  File Size: {stats['avg_file_size']:,.0f} bytes
"""
            
            text_widget.insert(tk.END, stats_text)
            text_widget.config(state=tk.DISABLED)
            
        except Exception as e:
            messagebox.showerror("Statistics Error", f"Error generating statistics: {e}")
    
    def open_selected_file(self, event):
        """Open selected file in default application"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = self.results_tree.item(selection[0])
        filename = item['values'][0]
        
        # Find the full path from current results
        for result in self.current_results:
            if result['filename'] == filename:
                try:
                    os.startfile(result['path'])
                except Exception as e:
                    messagebox.showerror("Open Error", f"Could not open file: {e}")
                break
    
    def run(self):
        """Start the GUI application"""
        # Show initial statistics
        self.perform_search()  # Show all textures initially
        self.root.mainloop()

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="RimWorld Texture Indexer and Search Tool")
    parser.add_argument("--base-path", default=r"D:\Ludeon public art assets\Game art source",
                       help="Base path to texture files")
    parser.add_argument("--db-path", default="texture_index.db",
                       help="Path to SQLite database file")
    parser.add_argument("--index", action="store_true",
                       help="Rebuild the texture index")
    parser.add_argument("--gui", action="store_true", default=True,
                       help="Launch GUI application")
    parser.add_argument("--search", help="Search for textures matching pattern")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--stats", action="store_true",
                       help="Show index statistics")
    
    args = parser.parse_args()
    
    # Initialize indexer
    indexer = TextureIndexer(args.base_path, args.db_path)
    
    try:
        if args.index:
            print("Rebuilding texture index...")
            indexer.index_directory()
        
        if args.stats:
            stats = indexer.get_statistics()
            print("\nTexture Index Statistics:")
            print(f"Total textures: {stats['total_textures']:,}")
            print(f"Average dimensions: {stats['avg_width']:.0f}x{stats['avg_height']:.0f}")
            print("Categories:")
            for category, count in stats['by_category'].items():
                print(f"  {category}: {count:,}")
        
        if args.search:
            results = indexer.search_textures(
                filename_pattern=args.search,
                category=args.category or ""
            )
            print(f"\nFound {len(results)} matching textures:")
            for result in results[:20]:  # Show first 20
                print(f"  {result['filename']} ({result['category']}/{result['subcategory']})")
            if len(results) > 20:
                print(f"  ... and {len(results) - 20} more")
        
        if args.gui:
            print("Launching GUI...")
            gui = TextureSearchGUI(indexer)
            gui.run()
    
    finally:
        indexer.close()

if __name__ == "__main__":
    main()
