#!/usr/bin/env python3
"""
Archive Studio Qt - PyQt6 Version
Modern UI for historical document processing with AI integration
"""

import sys
import os
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, 
    QHBoxLayout, QSplitter, QTextEdit, QGraphicsView, QGraphicsScene,
    QToolBar, QStatusBar, QProgressBar, QLabel, QPushButton,
    QFileDialog, QMessageBox, QScrollArea, QFrame, QGraphicsPixmapItem,
    QComboBox, QCheckBox, QGroupBox, QDialog, QLineEdit, QFormLayout
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QRectF
from PyQt6.QtGui import QAction, QPixmap, QFont, QIcon, QPainter, QTextCharFormat, QColor
import pandas as pd

# Import existing backend modules (preserving all functionality)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from util.Settings import Settings
    from util.DataOperations import DataOperations
    from util.APIHandler import APIHandler
    from util.ProjectIO import ProjectIO
    from util.ImageHandler import ImageHandler
    from util.ExportFunctions import ExportManager
    from util.AIFunctions import AIFunctionsHandler
    from util.ErrorLogger import log_error
    from util.SettingsWindow import SettingsWindow
except ImportError as e:
    print(f"Warning: Could not import backend modules: {e}")
    print("Running in demo mode...")

class AIProcessingThread(QThread):
    """Background thread for AI processing operations"""
    
    # Signals for communication with main thread
    progress_updated = pyqtSignal(int, int, str)  # current, total, status
    processing_complete = pyqtSignal(str)  # result message
    error_occurred = pyqtSignal(str)  # error message
    
    def __init__(self, operation_type, data, api_handler, main_window=None):
        super().__init__()
        self.operation_type = operation_type
        self.data = data
        self.api_handler = api_handler
        self.main_window = main_window
        self.is_cancelled = False
    
    def run(self):
        """Execute the AI processing operation"""
        try:
            if self.operation_type == "htr_all":
                self.process_htr_all()
            elif self.operation_type == "correct_text":
                self.process_text_correction()
            elif self.operation_type == "translate":
                self.process_translation()
            elif self.operation_type == "extract_metadata":
                self.process_metadata_extraction()
        except Exception as e:
            self.error_occurred.emit(f"Processing error: {str(e)}")
    
    def process_htr_all(self):
        """Process HTR for all pages using concurrent execution (like original version)"""
        if not hasattr(self, 'data') or self.data is None or self.data.empty:
            self.error_occurred.emit("No data available for processing")
            return
        
        total_pages = len(self.data)
        batch_size = 50  # Same as original version
        
        try:
            processed_count = 0
            
            # Use ThreadPoolExecutor for concurrent processing (same as original)
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                # Submit all pages for concurrent processing
                future_to_page = {}
                
                for i in range(total_pages):
                    if self.is_cancelled:
                        break
                    
                    page_data = self.data.iloc[i]
                    future = executor.submit(self.process_single_page_htr, page_data, i)
                    future_to_page[future] = i
                
                # Process results as they complete
                for future in as_completed(future_to_page):
                    if self.is_cancelled:
                        break
                        
                    page_index = future_to_page[future]
                    try:
                        success = future.result()
                        if success:
                            processed_count += 1
                        
                        # Update progress
                        self.progress_updated.emit(processed_count, total_pages, 
                                                 f"Completed page {page_index + 1}")
                        
                    except Exception as e:
                        print(f"❌ Error processing page {page_index}: {e}")
            
            if not self.is_cancelled:
                self.processing_complete.emit(f"HTR processing completed: {processed_count}/{total_pages} pages processed")
                # Sync the dataframe changes back to the main window
                self.sync_dataframe_to_main_window()
            else:
                self.processing_complete.emit(f"HTR processing cancelled: {processed_count}/{total_pages} pages processed")
                    
        except Exception as e:
            self.error_occurred.emit(f"HTR processing failed: {str(e)}")
    
    def process_single_page_htr(self, page_data, page_index):
        """Process a single page for HTR using real AI API"""
        try:
            # Get the image path
            image_path = page_data.get('Image_Path', '')
            if not image_path:
                print(f"❌ Page {page_index}: No image path")
                return False
            
            # Convert to absolute path if needed
            if hasattr(self.main_window, 'get_full_path'):
                image_path = self.main_window.get_full_path(image_path)
            
            # Check if image exists
            if not os.path.exists(image_path):
                print(f"❌ Page {page_index}: Image not found: {image_path}")
                return False
            
            print(f"📸 Page {page_index}: Processing image: {image_path}")
            
            # Get HTR settings from the main window
            settings = getattr(self.main_window, 'settings', None)
            if not settings:
                print(f"❌ Page {page_index}: No settings available")
                return False
            
            # Find HTR function preset
            htr_preset = None
            for preset in settings.function_presets:
                if preset.get('name') == 'HTR':
                    htr_preset = preset
                    break
            
            if not htr_preset:
                print(f"❌ Page {page_index}: No HTR preset found")
                return False
            
            print(f"🔧 Page {page_index}: Using preset: {htr_preset.get('name')} with model: {htr_preset.get('model')}")
            
            # Call the API handler directly (thread-safe)
            result = self.call_ai_api_thread_safe(
                image_path=image_path,
                preset=htr_preset,
                page_index=page_index
            )
            
            if result and result.strip():
                print(f"✅ Page {page_index}: HTR result: {result[:100]}...")
                # Update the dataframe with the result
                # This is thread-safe because we're only modifying data, not UI
                self.data.loc[page_index, 'Original_Text'] = result
                self.data.loc[page_index, 'Text_Toggle'] = 'Original_Text'
                return True
            else:
                print(f"❌ Page {page_index}: No result from API")
            
            return False
            
        except Exception as e:
            print(f"❌ Error processing page {page_index}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def call_ai_api_thread_safe(self, image_path, preset, page_index, text_to_process=""):
        """Call AI API in a thread-safe manner"""
        try:
            import asyncio
            
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Call the API handler directly
                result = loop.run_until_complete(
                    self.api_handler.route_api_call(
                        engine=preset.get('model', 'gemini-1.5-pro'),
                        system_prompt=preset.get('general_instructions', ''),
                        user_prompt=preset.get('specific_instructions', ''),
                        temp=float(preset.get('temperature', '0.3')),
                        image_data=image_path if image_path and os.path.exists(image_path) else None,
                        text_to_process=text_to_process,
                        val_text=preset.get('val_text', ''),
                        index=page_index,
                        is_base64=False,
                        job_type=preset.get('name', 'HTR')
                    )
                )
                
                # Extract the text result
                if isinstance(result, tuple) and len(result) >= 2:
                    return result[0]  # The actual text result
                elif isinstance(result, str):
                    return result
                else:
                    return ""
                    
            finally:
                loop.close()
                
        except Exception as e:
            print(f"API call failed for page {page_index}: {e}")
            return ""
    
    def process_text_correction(self):
        """Process text correction using real AI API calls"""
        if not hasattr(self, 'data') or self.data is None or self.data.empty:
            self.error_occurred.emit("No data available for processing")
            return
        
        total_pages = len(self.data)
        
        try:
            # Process each page with real AI text correction
            processed_count = 0
            
            for i in range(total_pages):
                if self.is_cancelled:
                    break
                    
                self.progress_updated.emit(i + 1, total_pages, f"Correcting text for page {i + 1}")
                
                # Get the current page data
                page_data = self.data.iloc[i]
                
                # Only process if there's original text
                if page_data.get('Original_Text', '').strip():
                    success = self.process_single_page_correction(page_data, i)
                    if success:
                        processed_count += 1
            
            if not self.is_cancelled:
                self.processing_complete.emit(f"Text correction completed: {processed_count}/{total_pages} pages processed")
                # Sync the dataframe changes back to the main window
                self.sync_dataframe_to_main_window()
            else:
                self.processing_complete.emit(f"Text correction cancelled: {processed_count}/{total_pages} pages processed")
                    
        except Exception as e:
            self.error_occurred.emit(f"Text correction failed: {str(e)}")
    
    def process_single_page_correction(self, page_data, page_index):
        """Process a single page for text correction using real AI API"""
        try:
            # Get the original text and image path
            original_text = page_data.get('Original_Text', '')
            image_path = page_data.get('Image_Path', '')
            
            if not original_text.strip():
                return False
                
            # Convert to absolute path if needed
            if image_path and hasattr(self.main_window, 'get_full_path'):
                image_path = self.main_window.get_full_path(image_path)
            
            # Get text correction settings from the main window
            settings = getattr(self.main_window, 'settings', None)
            if not settings:
                return False
            
            # Find text correction function preset
            correction_preset = None
            for preset in settings.function_presets:
                if preset.get('name') == 'Correct_Text':
                    correction_preset = preset
                    break
            
            if not correction_preset:
                return False
            
            # Call the API handler directly (thread-safe)
            result = self.call_ai_api_thread_safe(
                image_path=image_path,
                preset=correction_preset,
                page_index=page_index,
                text_to_process=original_text
            )
            
            if result and result.strip():
                # Update the dataframe with the result
                self.data.loc[page_index, 'Corrected_Text'] = result
                self.data.loc[page_index, 'Text_Toggle'] = 'Corrected_Text'
                return True
            
            return False
            
        except Exception as e:
            print(f"Error correcting text for page {page_index}: {e}")
            return False
    
    def process_translation(self):
        """Process translation"""
        total_items = 8  # Simulate number of translation segments
        
        for i in range(total_items):
            if self.is_cancelled:
                break
                
            self.progress_updated.emit(i + 1, total_items, f"Translating segment {i + 1}")
        
        if not self.is_cancelled:
            self.processing_complete.emit("Translation completed")
    
    def process_metadata_extraction(self):
        """Process metadata extraction"""
        total_items = 15  # Simulate number of metadata extractions
        
        for i in range(total_items):
            if self.is_cancelled:
                break
                
            self.progress_updated.emit(i + 1, total_items, f"Extracting metadata from page {i + 1}")
        
        if not self.is_cancelled:
            self.processing_complete.emit("Metadata extraction completed")
    
    def cancel(self):
        """Cancel the processing operation"""
        self.is_cancelled = True
    
    def sync_dataframe_to_main_window(self):
        """Sync the modified dataframe back to the main window"""
        try:
            if hasattr(self, 'main_window') and self.main_window:
                # Update the main window's dataframe
                self.main_window.main_df = self.data.copy()
                
                # Update the data operations dataframe if it exists
                if hasattr(self.main_window, 'data_operations'):
                    self.main_window.data_operations.main_df = self.data.copy()
                    
                print("✅ Dataframe synced to main window")
        except Exception as e:
            print(f"❌ Error syncing dataframe: {e}")

class PDFImportThread(QThread):
    """Background thread for PDF import operations"""
    
    # Signals for communication with main thread
    progress_updated = pyqtSignal(int, int, str)  # current, total, status
    import_complete = pyqtSignal(str)  # completion message
    import_error = pyqtSignal(str)  # error message
    
    def __init__(self, pdf_path, main_window):
        super().__init__()
        self.pdf_path = pdf_path
        self.main_window = main_window
        self.is_cancelled = False
    
    def run(self):
        """Execute the PDF import operation"""
        try:
            import fitz
            import os
            import pandas as pd
            
            # Open PDF document
            pdf_document = fitz.open(self.pdf_path)
            total_pages = len(pdf_document)
            
            self.progress_updated.emit(0, total_pages, "Starting PDF import...")
            
            # Ensure images directory exists
            if not hasattr(self.main_window, 'images_directory') or not self.main_window.images_directory:
                self.main_window.images_directory = os.path.join(
                    os.path.dirname(self.pdf_path), "images"
                )
            os.makedirs(self.main_window.images_directory, exist_ok=True)
            
            # Get starting index for new entries
            start_index = len(self.main_window.main_df)
            new_rows_list = []
            
            # Process pages in batches to avoid memory issues
            batch_size = 5  # Process 5 pages at a time
            
            for batch_start in range(0, total_pages, batch_size):
                if self.is_cancelled:
                    break
                    
                batch_end = min(batch_start + batch_size, total_pages)
                
                # Process batch
                for page_num in range(batch_start, batch_end):
                    if self.is_cancelled:
                        break
                        
                    self.progress_updated.emit(
                        page_num + 1, total_pages, 
                        f"Processing page {page_num + 1} of {total_pages}"
                    )
                    
                    page = pdf_document[page_num]
                    
                    # Extract image at moderate resolution to save memory
                    dpi = 150
                    mat = fitz.Matrix(dpi/72, dpi/72)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    
                    # Calculate paths
                    new_index = start_index + page_num
                    new_page_num_str = f"{new_index+1:04d}_p{new_index+1:03d}"
                    image_filename = f"{new_page_num_str}.jpg"
                    image_path_abs = os.path.join(self.main_window.images_directory, image_filename)
                    
                    # Save image
                    pix.save(image_path_abs)
                    
                    # Get relative path for storage
                    if hasattr(self.main_window, 'get_relative_path'):
                        image_path_rel = self.main_window.get_relative_path(image_path_abs)
                    else:
                        image_path_rel = os.path.relpath(image_path_abs, os.path.dirname(self.pdf_path))
                    
                    # Extract text
                    text_content = page.get_text("text")
                    
                    # Create row data
                    new_row_data = {
                        "Index": new_index,
                        "Page": new_page_num_str,
                        "Original_Text": text_content if text_content and text_content.strip() else "",
                        "Corrected_Text": "",
                        "Formatted_Text": "",
                        "Separated_Text": "",
                        "Translation": "",
                        "Image_Path": image_path_rel,
                        "Text_Path": "",
                        "Text_Toggle": "Original_Text" if text_content and text_content.strip() else "None",
                        "Relevance": "",
                    }
                    
                    # Add other columns that exist in main_df
                    for col in self.main_window.main_df.columns:
                        if col not in new_row_data:
                            new_row_data[col] = ""
                    
                    new_rows_list.append(new_row_data)
                
                # Force garbage collection after each batch
                import gc
                gc.collect()
            
            pdf_document.close()
            
            if not self.is_cancelled and new_rows_list:
                # Add new rows to DataFrame
                new_rows_df = pd.DataFrame(new_rows_list)
                self.main_window.main_df = pd.concat([self.main_window.main_df, new_rows_df], ignore_index=True)
                
                # Update page counter
                self.main_window.page_counter = start_index
                
                self.import_complete.emit(f"PDF import completed: {len(new_rows_list)} pages imported")
            elif self.is_cancelled:
                self.import_error.emit("Import cancelled by user")
            else:
                self.import_error.emit("No pages were imported")
                
        except Exception as e:
            self.import_error.emit(f"Import error: {str(e)}")
    
    def cancel(self):
        """Cancel the import operation"""
        self.is_cancelled = True

class ProjectTab(QWidget):
    """PROJECT tab - Import, organize, batch operations"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Header
        header = QLabel("📁 PROJECT MANAGEMENT")
        header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Quick Actions Frame
        actions_frame = QFrame()
        actions_frame.setFrameStyle(QFrame.Shape.Box)
        actions_layout = QHBoxLayout()
        
        # Import buttons
        import_pdf_btn = QPushButton("📄 Import PDF")
        import_pdf_btn.clicked.connect(self.import_pdf)
        actions_layout.addWidget(import_pdf_btn)
        
        import_images_btn = QPushButton("🖼️ Import Images")
        import_images_btn.clicked.connect(self.import_images)
        actions_layout.addWidget(import_images_btn)
        
        # Project management
        new_project_btn = QPushButton("🆕 New Project")
        new_project_btn.clicked.connect(self.new_project)
        actions_layout.addWidget(new_project_btn)
        
        open_project_btn = QPushButton("📂 Open Project")
        open_project_btn.clicked.connect(self.open_project)
        actions_layout.addWidget(open_project_btn)
        
        actions_layout.addStretch()
        actions_frame.setLayout(actions_layout)
        layout.addWidget(actions_frame)
        
        # Project status area
        status_label = QLabel("Ready to import documents...")
        layout.addWidget(status_label)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def import_pdf(self):
        """Import PDF file with progress feedback"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import PDF", "", "PDF Files (*.pdf)"
        )
        if file_path and hasattr(self.main_window, 'project_io'):
            # Check PDF size first
            try:
                import fitz
                import os
                file_size = os.path.getsize(file_path)
                pdf_document = fitz.open(file_path)
                page_count = len(pdf_document)
                pdf_document.close()
                
                # Show confirmation for large files
                if file_size > 50 * 1024 * 1024:  # 50MB
                    reply = QMessageBox.question(
                        self, "Large PDF Import", 
                        f"This PDF is {file_size / (1024*1024):.1f} MB with {page_count} pages.\n\n"
                        f"Import may take several minutes. Continue?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.No:
                        return
                
                # Start import in background thread
                self.start_pdf_import(file_path)
                
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to analyze PDF: {str(e)}")
                self.main_window.status_bar.showMessage(f"Import failed: {str(e)}")
    
    def start_pdf_import(self, file_path):
        """Start PDF import in background thread"""
        # Create and start the PDF import thread
        self.pdf_import_thread = PDFImportThread(file_path, self.main_window)
        self.pdf_import_thread.progress_updated.connect(self.update_import_progress)
        self.pdf_import_thread.import_complete.connect(self.on_import_complete)
        self.pdf_import_thread.import_error.connect(self.on_import_error)
        self.pdf_import_thread.start()
        
        # Show progress in status bar
        self.main_window.status_bar.showMessage(f"Importing PDF: {Path(file_path).name}...")
    
    def update_import_progress(self, current, total, message):
        """Update import progress"""
        self.main_window.status_bar.showMessage(f"Importing: {message} ({current}/{total})")
        # Update progress bar if available (skip for now as it's causing issues)
        # if hasattr(self.main_window, 'progress_bar') and self.main_window.progress_bar:
        #     self.main_window.progress_bar.setValue(int(100 * current / total))
    
    def on_import_complete(self, message):
        """Handle successful import completion"""
        self.main_window.status_bar.showMessage(message)
        
        # Switch to REVIEW tab to see the imported content
        self.main_window.tabs.setCurrentIndex(2)  # Switch to REVIEW tab
        
        # Update the review tab to show new data
        if hasattr(self.main_window.review_tab, 'update_page_display'):
            self.main_window.review_tab.update_page_display()
    
    def on_import_error(self, error_message):
        """Handle import error"""
        QMessageBox.critical(self, "Import Error", f"Failed to import PDF: {error_message}")
        self.main_window.status_bar.showMessage(f"Import failed: {error_message}")
    
    def import_images(self):
        """Import image folder"""
        folder_path = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if folder_path:
            try:
                # Use existing backend functionality - open_folder with "Images without Text"
                self.main_window.open_folder(folder_path, "Images without Text")
                self.main_window.status_bar.showMessage(f"Imported images from: {Path(folder_path).name}")
                
                # Switch to REVIEW tab to see the imported content
                self.main_window.tabs.setCurrentIndex(2)  # Switch to REVIEW tab
                
                # Update the review tab to show new data
                if hasattr(self.main_window.review_tab, 'update_page_display'):
                    self.main_window.review_tab.update_page_display()
                    
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to import images: {str(e)}")
                self.main_window.status_bar.showMessage(f"Import failed: {str(e)}")
    
    def new_project(self):
        """Create new project"""
        if hasattr(self.main_window, 'project_io'):
            self.main_window.project_io.create_new_project()
        self.main_window.status_bar.showMessage("Created new project")
    
    def open_project(self):
        """Open existing project"""
        if hasattr(self.main_window, 'project_io'):
            self.main_window.project_io.open_project()
        self.main_window.status_bar.showMessage("Opened project")

class ProcessTab(QWidget):
    """PROCESS tab - AI transcription, correction, analysis"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.current_thread = None
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Header
        header = QLabel("📄 AI PROCESSING")
        header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Quick Actions Frame
        actions_frame = QFrame()
        actions_frame.setFrameStyle(QFrame.Shape.Box)
        actions_layout = QHBoxLayout()
        
        # AI processing buttons
        self.htr_btn = QPushButton("🔍 HTR All Pages")
        self.htr_btn.clicked.connect(self.htr_all_pages)
        actions_layout.addWidget(self.htr_btn)
        
        self.correct_btn = QPushButton("✏️ Correct Text")
        self.correct_btn.clicked.connect(self.correct_text)
        actions_layout.addWidget(self.correct_btn)
        
        self.translate_btn = QPushButton("🌍 Translate")
        self.translate_btn.clicked.connect(self.translate_text)
        actions_layout.addWidget(self.translate_btn)
        
        self.analyze_btn = QPushButton("📊 Extract Metadata")
        self.analyze_btn.clicked.connect(self.extract_metadata)
        actions_layout.addWidget(self.analyze_btn)
        
        # Cancel button (initially hidden)
        self.cancel_btn = QPushButton("❌ Cancel")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setVisible(False)
        actions_layout.addWidget(self.cancel_btn)
        
        actions_layout.addStretch()
        actions_frame.setLayout(actions_layout)
        layout.addWidget(actions_frame)
        
        # AI Provider Selection
        provider_frame = QFrame()
        provider_layout = QHBoxLayout()
        provider_layout.addWidget(QLabel("AI Provider:"))
        
        # Provider dropdown
        self.provider_combo = QComboBox()
        self.provider_combo.addItems([
            "Document AI (Fastest, cheapest)",
            "Gemini Pro (Balanced)",
            "Claude Sonnet 4 (Best quality)",
            "GPT-4 (General purpose)"
        ])
        provider_layout.addWidget(self.provider_combo)
        
        # Quality setting
        provider_layout.addWidget(QLabel("Quality:"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["High", "Standard", "Fast"])
        provider_layout.addWidget(self.quality_combo)
        
        provider_layout.addStretch()
        
        # Cost estimate
        self.cost_label = QLabel("Est. cost: $0.25 for 45 pages")
        provider_layout.addWidget(self.cost_label)
        
        provider_frame.setLayout(provider_layout)
        layout.addWidget(provider_frame)
        
        # Progress area
        progress_group = QGroupBox("Processing Status")
        progress_layout = QVBoxLayout()
        
        self.progress_label = QLabel("Ready to process documents...")
        progress_layout.addWidget(self.progress_label)
        
        # Progress bar
        self.local_progress = QProgressBar()
        self.local_progress.setVisible(False)
        progress_layout.addWidget(self.local_progress)
        
        # Status details
        self.status_details = QLabel("")
        self.status_details.setStyleSheet("color: #666; font-size: 11px;")
        progress_layout.addWidget(self.status_details)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # Results summary
        results_group = QGroupBox("Recent Results")
        results_layout = QVBoxLayout()
        
        self.results_label = QLabel("No processing completed yet.")
        results_layout.addWidget(self.results_label)
        
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def start_ai_processing(self, operation_type):
        """Start AI processing in background thread"""
        if self.current_thread and self.current_thread.isRunning():
            QMessageBox.warning(self, "Processing", "Another operation is already running. Please wait or cancel it first.")
            return
        
        # Get data to process (would be actual document data in real implementation)
        data = getattr(self.main_window, 'main_df', None)
        api_handler = getattr(self.main_window, 'api_handler', None)
        
        # Create and start processing thread
        self.current_thread = AIProcessingThread(operation_type, data, api_handler, self.main_window)
        self.current_thread.progress_updated.connect(self.on_progress_updated)
        self.current_thread.processing_complete.connect(self.on_processing_complete)
        self.current_thread.error_occurred.connect(self.on_error_occurred)
        
        # Update UI for processing state
        self.set_processing_state(True)
        
        # Start the thread
        self.current_thread.start()
    
    def set_processing_state(self, is_processing):
        """Enable/disable UI elements during processing"""
        self.htr_btn.setEnabled(not is_processing)
        self.correct_btn.setEnabled(not is_processing)
        self.translate_btn.setEnabled(not is_processing)
        self.analyze_btn.setEnabled(not is_processing)
        self.cancel_btn.setVisible(is_processing)
        self.local_progress.setVisible(is_processing)
        
        if is_processing:
            self.local_progress.setRange(0, 100)
            self.local_progress.setValue(0)
    
    def on_progress_updated(self, current, total, status):
        """Handle progress updates from processing thread"""
        if total > 0:
            progress_percent = int((current / total) * 100)
            self.local_progress.setValue(progress_percent)
            self.main_window.show_progress(current, total)
        
        self.progress_label.setText(f"🔄 {status}")
        self.status_details.setText(f"Progress: {current}/{total} ({progress_percent}%)")
    
    def on_processing_complete(self, message):
        """Handle processing completion"""
        self.set_processing_state(False)
        self.progress_label.setText("✅ Processing complete!")
        self.status_details.setText(message)
        self.results_label.setText(f"✅ {message}")
        self.main_window.status_bar.showMessage(message)
        self.main_window.show_progress(0, 0)  # Hide progress bar
        
        # Show completion message
        QMessageBox.information(self, "Processing Complete", message)
    
    def on_error_occurred(self, error_message):
        """Handle processing errors"""
        self.set_processing_state(False)
        self.progress_label.setText("❌ Processing failed")
        self.status_details.setText(error_message)
        self.results_label.setText(f"❌ {error_message}")
        self.main_window.status_bar.showMessage(f"Error: {error_message}")
        self.main_window.show_progress(0, 0)  # Hide progress bar
        
        # Show error message
        QMessageBox.critical(self, "Processing Error", error_message)
    
    def cancel_processing(self):
        """Cancel current processing operation"""
        if self.current_thread and self.current_thread.isRunning():
            self.current_thread.cancel()
            self.current_thread.wait()  # Wait for thread to finish
            
            self.set_processing_state(False)
            self.progress_label.setText("⏹️ Processing cancelled")
            self.status_details.setText("Operation was cancelled by user")
            self.main_window.status_bar.showMessage("Processing cancelled")
            self.main_window.show_progress(0, 0)
    
    def htr_all_pages(self):
        """Start HTR processing for all pages"""
        self.start_ai_processing("htr_all")
    
    def correct_text(self):
        """Start text correction"""
        self.start_ai_processing("correct_text")
    
    def translate_text(self):
        """Start translation"""
        self.start_ai_processing("translate")
    
    def extract_metadata(self):
        """Extract metadata"""
        self.start_ai_processing("extract_metadata")

class EnhancedImageViewer(QGraphicsView):
    """Enhanced image viewer with smooth zoom and pan"""
    
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        
        # Enable smooth zooming and panning
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        # Current image item
        self.image_item = None
        
        # Zoom limits
        self.min_zoom = 0.1
        self.max_zoom = 10.0
        self.zoom_factor = 1.15
        
    def load_image(self, image_path):
        """Load and display an image"""
        try:
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                # Clear previous image
                self.scene.clear()
                
                # Add new image
                self.image_item = QGraphicsPixmapItem(pixmap)
                self.scene.addItem(self.image_item)
                
                # Fit image to view
                self.fitInView(self.image_item, Qt.AspectRatioMode.KeepAspectRatio)
                
                return True
        except Exception as e:
            print(f"Error loading image: {e}")
        return False
    
    def wheelEvent(self, event):
        """Handle mouse wheel for zooming"""
        # Check zoom limits
        current_scale = self.transform().m11()
        
        if event.angleDelta().y() > 0:
            # Zoom in
            if current_scale < self.max_zoom:
                self.scale(self.zoom_factor, self.zoom_factor)
        else:
            # Zoom out
            if current_scale > self.min_zoom:
                self.scale(1.0 / self.zoom_factor, 1.0 / self.zoom_factor)
    
    def fit_to_window(self):
        """Fit image to window"""
        if self.image_item:
            self.fitInView(self.image_item, Qt.AspectRatioMode.KeepAspectRatio)
    
    def zoom_to_actual_size(self):
        """Zoom to 100% actual size"""
        if self.image_item:
            self.resetTransform()

class EnhancedTextEditor(QTextEdit):
    """Enhanced text editor with highlighting and diff support"""
    
    def __init__(self):
        super().__init__()
        self.init_highlighting()
    
    def init_highlighting(self):
        """Initialize text highlighting formats"""
        # Define highlighting formats
        self.highlight_formats = {
            'name': QTextCharFormat(),
            'place': QTextCharFormat(), 
            'change': QTextCharFormat(),
            'error': QTextCharFormat(),
            'suggestion': QTextCharFormat()
        }
        
        # Configure highlight colors
        self.highlight_formats['name'].setBackground(QColor(173, 216, 230))  # Light blue
        self.highlight_formats['place'].setBackground(QColor(245, 222, 179))  # Wheat
        self.highlight_formats['change'].setBackground(QColor(144, 238, 144))  # Light green
        self.highlight_formats['error'].setBackground(QColor(255, 182, 193))  # Light pink
        self.highlight_formats['suggestion'].setBackground(QColor(255, 255, 0))  # Yellow
    
    def highlight_text(self, start_pos, length, highlight_type):
        """Highlight text at specified position"""
        if highlight_type in self.highlight_formats:
            cursor = self.textCursor()
            cursor.setPosition(start_pos)
            cursor.setPosition(start_pos + length, cursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(self.highlight_formats[highlight_type])
    
    def clear_highlights(self):
        """Clear all highlighting"""
        cursor = self.textCursor()
        cursor.select(cursor.SelectionType.Document)
        cursor.setCharFormat(QTextCharFormat())  # Reset to default format
    
    def show_diff(self, original_text, corrected_text):
        """Show differences between original and corrected text"""
        # This would integrate with existing AdvancedDiffHighlighting
        self.setPlainText(corrected_text)
        # TODO: Implement actual diff highlighting

class ReviewTab(QWidget):
    """REVIEW tab - Edit, validate, compare versions"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.current_page = 0
        self.total_pages = 0
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Header
        header = QLabel("✏️ REVIEW & EDIT")
        header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Controls row
        controls_layout = QHBoxLayout()
        
        # Text display options
        display_group = QGroupBox("Display Options")
        display_layout = QHBoxLayout()
        
        display_layout.addWidget(QLabel("Show:"))
        self.text_type_combo = QComboBox()
        self.text_type_combo.addItems([
            "Original Text", "Corrected Text", "Translation", 
            "Formatted Text", "Separated Text"
        ])
        self.text_type_combo.currentTextChanged.connect(self.on_text_type_changed)
        display_layout.addWidget(self.text_type_combo)
        
        # Highlighting options
        self.highlight_names = QCheckBox("Names")
        self.highlight_places = QCheckBox("Places") 
        self.highlight_changes = QCheckBox("Changes")
        self.highlight_errors = QCheckBox("Errors")
        
        display_layout.addWidget(self.highlight_names)
        display_layout.addWidget(self.highlight_places)
        display_layout.addWidget(self.highlight_changes)
        display_layout.addWidget(self.highlight_errors)
        
        display_group.setLayout(display_layout)
        controls_layout.addWidget(display_group)
        controls_layout.addStretch()
        
        layout.addLayout(controls_layout)
        
        # Main editing area - split view
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Document viewer side
        viewer_widget = QWidget()
        viewer_layout = QVBoxLayout()
        
        viewer_header = QHBoxLayout()
        viewer_header.addWidget(QLabel("📖 Document Viewer"))
        viewer_header.addStretch()
        
        # Image controls
        fit_btn = QPushButton("Fit to Window")
        fit_btn.clicked.connect(self.fit_image_to_window)
        viewer_header.addWidget(fit_btn)
        
        actual_size_btn = QPushButton("100%")
        actual_size_btn.clicked.connect(self.zoom_to_actual_size)
        viewer_header.addWidget(actual_size_btn)
        
        viewer_layout.addLayout(viewer_header)
        
        # Enhanced image viewer with hardware acceleration
        self.image_viewer = EnhancedImageViewer()
        self.image_viewer.setMinimumSize(400, 400)
        viewer_layout.addWidget(self.image_viewer)
        
        # Navigation controls
        nav_layout = QHBoxLayout()
        
        self.prev_page_btn = QPushButton("◀◀")
        self.prev_page_btn.clicked.connect(lambda: self.navigate_pages(-10))
        nav_layout.addWidget(self.prev_page_btn)
        
        self.prev_btn = QPushButton("◀")
        self.prev_btn.clicked.connect(lambda: self.navigate_pages(-1))
        nav_layout.addWidget(self.prev_btn)
        
        self.page_label = QLabel("Page 0 / 0")
        nav_layout.addWidget(self.page_label)
        
        self.next_btn = QPushButton("▶")
        self.next_btn.clicked.connect(lambda: self.navigate_pages(1))
        nav_layout.addWidget(self.next_btn)
        
        self.next_page_btn = QPushButton("▶▶")
        self.next_page_btn.clicked.connect(lambda: self.navigate_pages(10))
        nav_layout.addWidget(self.next_page_btn)
        
        nav_layout.addStretch()
        viewer_layout.addLayout(nav_layout)
        
        viewer_widget.setLayout(viewer_layout)
        splitter.addWidget(viewer_widget)
        
        # Text editor side
        editor_widget = QWidget()
        editor_layout = QVBoxLayout()
        
        editor_header = QHBoxLayout()
        editor_header.addWidget(QLabel("✍️ Text Editor"))
        editor_header.addStretch()
        
        # Word count
        self.word_count_label = QLabel("Words: 0")
        editor_header.addWidget(self.word_count_label)
        
        editor_layout.addLayout(editor_header)
        
        # Enhanced text editor with highlighting
        self.text_editor = EnhancedTextEditor()
        self.text_editor.setPlainText("Original transcribed text will appear here...\n\nUse the controls above to switch between different text versions.\n\nHighlighting options help identify names, places, changes, and potential errors.")
        self.text_editor.setMinimumSize(400, 400)
        self.text_editor.textChanged.connect(self.update_word_count)
        editor_layout.addWidget(self.text_editor)
        
        # Edit controls
        edit_controls = QHBoxLayout()
        
        find_replace_btn = QPushButton("🔍 Find & Replace")
        find_replace_btn.clicked.connect(self.open_find_replace)
        edit_controls.addWidget(find_replace_btn)
        
        suggestions_btn = QPushButton("💡 Show Suggestions")
        suggestions_btn.clicked.connect(self.show_suggestions)
        edit_controls.addWidget(suggestions_btn)
        
        compare_btn = QPushButton("📊 Compare Versions")
        compare_btn.clicked.connect(self.compare_versions)
        edit_controls.addWidget(compare_btn)
        
        clear_highlights_btn = QPushButton("🧹 Clear Highlights")
        clear_highlights_btn.clicked.connect(self.text_editor.clear_highlights)
        edit_controls.addWidget(clear_highlights_btn)
        
        edit_controls.addStretch()
        editor_layout.addLayout(edit_controls)
        
        editor_widget.setLayout(editor_layout)
        splitter.addWidget(editor_widget)
        
        # Set equal split initially
        splitter.setSizes([500, 500])
        layout.addWidget(splitter)
        
        self.setLayout(layout)
        
        # Load sample image for demo
        self.load_sample_image()
    
    def load_sample_image(self):
        """Load a sample image for demonstration"""
        # Try to load an image from the project if available
        # For now, create a placeholder
        sample_text = "📖 Document Image\n\nImage viewer ready.\nDrop PDF or images in PROJECT tab\nto see documents here."
        
    def navigate_pages(self, direction):
        """Navigate between document pages"""
        self.refresh_page_data()  # Update page data first
        
        if self.total_pages > 0:
            self.current_page = max(0, min(self.current_page + direction, self.total_pages - 1))
        
        self.update_page_display()
    
    def refresh_page_data(self):
        """Refresh page data from main dataframe"""
        if hasattr(self.main_window, 'main_df') and not self.main_window.main_df.empty:
            self.total_pages = len(self.main_window.main_df)
            # Initialize current_page if not set
            if not hasattr(self, 'current_page'):
                self.current_page = 0
            # Ensure current_page is within bounds
            self.current_page = max(0, min(self.current_page, self.total_pages - 1))
        else:
            self.current_page = 0
            self.total_pages = 0
    
    def update_page_display(self):
        """Update page counter and load current page"""
        # Refresh page data first
        self.refresh_page_data()
        
        self.page_label.setText(f"Page {self.current_page + 1} / {self.total_pages}")
        
        # Enable/disable navigation buttons
        self.prev_btn.setEnabled(self.current_page > 0)
        self.prev_page_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < self.total_pages - 1)
        self.next_page_btn.setEnabled(self.current_page < self.total_pages - 1)
        
        # Load current page data
        self.load_current_page()
    
    def load_current_page(self):
        """Load current page image and text"""
        if (hasattr(self.main_window, 'main_df') and 
            not self.main_window.main_df.empty and 
            self.current_page < len(self.main_window.main_df)):
            
            # Load image if available
            row = self.main_window.main_df.iloc[self.current_page]
            if 'Image_Path' in row and row['Image_Path']:
                # Convert relative path to absolute path
                image_path = row['Image_Path']
                if hasattr(self.main_window, 'get_full_path'):
                    image_path = self.main_window.get_full_path(image_path)
                self.image_viewer.load_image(image_path)
            
            # Load text based on selected type
            self.load_current_text()
    
    def load_current_text(self):
        """Load text for current page based on selected type"""
        text_type = self.text_type_combo.currentText()
        
        if (hasattr(self.main_window, 'main_df') and 
            not self.main_window.main_df.empty and 
            self.current_page < len(self.main_window.main_df)):
            
            row = self.main_window.main_df.iloc[self.current_page]
            
            # Map display names to column names
            column_map = {
                "Original Text": "Original_Text",
                "Corrected Text": "Corrected_Text", 
                "Translation": "Translation",
                "Formatted Text": "Formatted_Text",
                "Separated Text": "Separated_Text"
            }
            
            column_name = column_map.get(text_type, "Original_Text")
            
            if column_name in row and not pd.isna(row[column_name]):
                self.text_editor.setPlainText(str(row[column_name]))
            else:
                self.text_editor.setPlainText(f"No {text_type.lower()} available for this page.")
        else:
            self.text_editor.setPlainText("No document loaded. Import documents in PROJECT tab.")
        
        self.update_word_count()
    
    def on_text_type_changed(self):
        """Handle text type selection change"""
        self.load_current_text()
    
    def fit_image_to_window(self):
        """Fit image to viewer window"""
        self.image_viewer.fit_to_window()
    
    def zoom_to_actual_size(self):
        """Zoom image to actual size"""
        self.image_viewer.zoom_to_actual_size()
    
    def update_word_count(self):
        """Update word count display"""
        text = self.text_editor.toPlainText()
        word_count = len(text.split()) if text.strip() else 0
        self.word_count_label.setText(f"Words: {word_count}")
    
    def open_find_replace(self):
        """Open find and replace dialog"""
        # This would integrate with existing FindReplace functionality
        self.main_window.status_bar.showMessage("Find & Replace dialog would open here")
    
    def show_suggestions(self):
        """Show AI suggestions for current text"""
        # Highlight potential improvements
        text = self.text_editor.toPlainText()
        if text.strip():
            # Demo highlighting - in real version would use AI analysis
            self.text_editor.highlight_text(0, 10, 'suggestion')
            self.main_window.status_bar.showMessage("Showing AI suggestions (demo)")
    
    def compare_versions(self):
        """Compare different text versions"""
        # This would integrate with existing diff highlighting
        self.main_window.status_bar.showMessage("Version comparison would open here")

class ExportTab(QWidget):
    """EXPORT tab - Output formats, sharing, archival"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Header
        header = QLabel("📤 EXPORT & SHARE")
        header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # Export options frame
        export_frame = QFrame()
        export_frame.setFrameStyle(QFrame.Shape.Box)
        export_layout = QHBoxLayout()
        
        # Export format buttons
        export_txt_btn = QPushButton("📄 Export as TXT")
        export_txt_btn.clicked.connect(self.export_txt)
        export_layout.addWidget(export_txt_btn)
        
        export_pdf_btn = QPushButton("📋 Export as PDF")
        export_pdf_btn.clicked.connect(self.export_pdf)
        export_layout.addWidget(export_pdf_btn)
        
        export_csv_btn = QPushButton("📊 Export as CSV")
        export_csv_btn.clicked.connect(self.export_csv)
        export_layout.addWidget(export_csv_btn)
        
        export_layout.addStretch()
        export_frame.setLayout(export_layout)
        layout.addWidget(export_frame)
        
        # Export status
        status_label = QLabel("Ready to export processed documents...")
        layout.addWidget(status_label)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def export_txt(self):
        """Export as text files"""
        if hasattr(self.main_window, 'export_manager'):
            try:
                # Use existing backend functionality
                self.main_window.export_manager.export_txt()
                self.main_window.status_bar.showMessage("Exported as TXT files")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export TXT: {str(e)}")
        else:
            QMessageBox.information(self, "Export", "Export system not available")
    
    def export_pdf(self):
        """Export as PDF"""
        if hasattr(self.main_window, 'export_manager'):
            try:
                # Check if export_pdf method exists
                if hasattr(self.main_window.export_manager, 'export_pdf'):
                    self.main_window.export_manager.export_pdf()
                else:
                    QMessageBox.information(self, "Export", "PDF export not yet implemented")
                self.main_window.status_bar.showMessage("Exported as PDF")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export PDF: {str(e)}")
        else:
            QMessageBox.information(self, "Export", "Export system not available")
    
    def export_csv(self):
        """Export as CSV"""
        if hasattr(self.main_window, 'export_manager'):
            try:
                # Check if export_csv method exists
                if hasattr(self.main_window.export_manager, 'export_csv'):
                    self.main_window.export_manager.export_csv()
                else:
                    # Fallback: export main_df as CSV
                    file_path, _ = QFileDialog.getSaveFileName(
                        self, "Export CSV", "", "CSV Files (*.csv)"
                    )
                    if file_path and hasattr(self.main_window, 'main_df'):
                        self.main_window.main_df.to_csv(file_path, index=False)
                        QMessageBox.information(self, "Export Complete", f"Data exported to {file_path}")
                self.main_window.status_bar.showMessage("Exported as CSV")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export CSV: {str(e)}")
        else:
            QMessageBox.information(self, "Export", "Export system not available")

class SimpleSettingsDialog(QDialog):
    """Simple PyQt6 settings dialog for API keys"""
    
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings - API Keys")
        self.setModal(True)
        self.setMinimumSize(500, 300)
        
        layout = QVBoxLayout()
        
        # Form layout for API keys
        form_layout = QFormLayout()
        
        # OpenAI API Key
        self.openai_key_input = QLineEdit()
        self.openai_key_input.setText(getattr(settings, 'openai_api_key', ''))
        self.openai_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("OpenAI API Key:", self.openai_key_input)
        
        # Anthropic API Key
        self.anthropic_key_input = QLineEdit()
        self.anthropic_key_input.setText(getattr(settings, 'anthropic_api_key', ''))
        self.anthropic_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Anthropic API Key:", self.anthropic_key_input)
        
        # Google API Key
        self.google_key_input = QLineEdit()
        self.google_key_input.setText(getattr(settings, 'google_api_key', ''))
        self.google_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Google API Key:", self.google_key_input)
        
        # Document AI Section
        form_layout.addRow("", QLabel(""))  # Spacer
        form_layout.addRow("Document AI Settings:", QLabel(""))
        
        # Document AI Project ID
        self.doc_ai_project_input = QLineEdit()
        self.doc_ai_project_input.setText(getattr(settings, 'document_ai_project_id', ''))
        self.doc_ai_project_input.setPlaceholderText("your-project-id")
        form_layout.addRow("Document AI Project ID:", self.doc_ai_project_input)
        
        # Document AI Credentials (JSON)
        self.doc_ai_credentials_input = QTextEdit()
        self.doc_ai_credentials_input.setText(getattr(settings, 'document_ai_credentials', ''))
        self.doc_ai_credentials_input.setPlaceholderText("Paste your service account JSON credentials here...")
        self.doc_ai_credentials_input.setMaximumHeight(100)
        form_layout.addRow("Document AI Credentials:", self.doc_ai_credentials_input)
        
        layout.addLayout(form_layout)
        
        # Instructions
        instructions = QLabel("""
🔑 API Key Setup Instructions:

• OpenAI: Get your key from https://platform.openai.com/api-keys
• Anthropic: Get your key from https://console.anthropic.com/settings/keys  
• Google: Get your key from https://aistudio.google.com/app/apikey

🏛️ Document AI Setup (Optional):
• Create a Google Cloud project at https://console.cloud.google.com
• Enable Document AI API
• Create a service account and download JSON credentials
• Copy the entire JSON content into the credentials field above

💡 You need at least one API key for AI processing to work.
🔒 Keys are stored locally and never shared.
        """)
        instructions.setWordWrap(True)
        instructions.setStyleSheet("background-color: #f0f8ff; padding: 10px; border-radius: 5px;")
        layout.addWidget(instructions)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        save_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        button_layout.addWidget(save_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def save_settings(self):
        """Save API keys to settings"""
        try:
            # Update settings object
            self.settings.openai_api_key = self.openai_key_input.text().strip()
            self.settings.anthropic_api_key = self.anthropic_key_input.text().strip()
            self.settings.google_api_key = self.google_key_input.text().strip()
            
            # Update Document AI settings
            self.settings.document_ai_project_id = self.doc_ai_project_input.text().strip()
            self.settings.document_ai_credentials = self.doc_ai_credentials_input.toPlainText().strip()
            
            # Save to file
            if hasattr(self.settings, 'save_settings'):
                self.settings.save_settings()
                
            # Initialize Document AI if credentials are provided
            if (self.settings.document_ai_credentials and 
                self.settings.document_ai_project_id):
                try:
                    from util.DocumentAIHandler import document_ai_handler
                    if document_ai_handler:
                        success = document_ai_handler.setup_credentials(
                            self.settings.document_ai_credentials,
                            self.settings.document_ai_project_id,
                            self.settings.document_ai_location,
                            self.settings.document_ai_processor_id
                        )
                        if success:
                            print("✅ Document AI configured successfully")
                        else:
                            print("❌ Document AI configuration failed")
                except Exception as e:
                    print(f"❌ Document AI setup error: {e}")
            
            # Check if at least one key is provided
            has_key = any([
                self.settings.openai_api_key,
                self.settings.anthropic_api_key,
                self.settings.google_api_key
            ])
            
            if not has_key:
                reply = QMessageBox.question(
                    self, "No API Keys", 
                    "No API keys were provided. AI processing will not work.\n\nContinue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
            
            QMessageBox.information(self, "Settings Saved", "API keys have been saved successfully!")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save settings: {str(e)}")

class ArchiveStudioQt(QMainWindow):
    """Main application window with PyQt6"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Archive Studio 2.0 - PyQt6")
        self.setGeometry(100, 100, 1400, 900)
        
        # Initialize backend modules (preserve existing functionality)
        self.init_backend()
        
        # Initialize modern UI
        self.init_ui()
        
        # Apply styling
        self.apply_styles()
    
    def init_backend(self):
        """Initialize all existing backend modules"""
        try:
            # Core settings and data
            self.settings = Settings()
            self.data_operations = DataOperations(self)
            
            # Initialize main dataframe
            if hasattr(self.data_operations, 'initialize_main_df'):
                self.data_operations.initialize_main_df()
                # The DataOperations class sets self.app.main_df, so it's already set
                # Just create a reference for easier access
                if hasattr(self, 'main_df'):
                    self.data_operations.main_df = self.main_df  # Create reverse reference
            
            # Initialize required attributes for compatibility
            self.page_counter = 0
            self.temp_directory = self.settings.temp_directory if hasattr(self.settings, 'temp_directory') else None
            
            # Set project_directory to temp_directory if not already set (following original pattern)
            if not hasattr(self, 'project_directory') or not self.project_directory:
                self.project_directory = self.temp_directory
            
            self.images_directory = None
            
            # API and processing handlers
            self.api_handler = APIHandler(
                self.settings.openai_api_key,
                self.settings.anthropic_api_key, 
                self.settings.google_api_key,
                self
            )
            
            # File and project management
            self.project_io = ProjectIO(self)
            self.export_manager = ExportManager(self)
            
            # AI functions
            self.ai_functions_handler = AIFunctionsHandler(self)
            
            # Initialize progress bar compatibility layer AFTER UI is created
            # This will be set up in init_ui after the status bar exists
            
            print("✅ Backend modules initialized successfully")
            
        except Exception as e:
            print(f"⚠️ Warning: Could not initialize all backend modules: {e}")
            print("Some functionality may be limited.")
    
    def reset_application(self):
        """Reset application state - needed for backend compatibility"""
        if hasattr(self, 'data_operations'):
            self.data_operations.initialize_main_df()
            self.main_df = self.data_operations.main_df
        self.page_counter = 0
    
    def get_full_path(self, path):
        """Resolves a potentially relative path to an absolute path based on the project directory."""
        # If the path isn't a string or is empty, return it as is.
        if not isinstance(path, str) or not path.strip():
            return path
        # If it's already absolute, return it.
        if os.path.isabs(path):
            return path
        # If a project is open, join with the project directory.
        # Use self.project_directory if it exists, otherwise use temp_directory as a fallback base
        base_dir = getattr(self, 'project_directory', None) or getattr(self, 'temp_directory', None)
        if base_dir:
            # Normalize both base_dir and path to handle mixed slashes before joining
            normalized_base = os.path.normpath(base_dir)
            normalized_path = os.path.normpath(path)
            full_path = os.path.join(normalized_base, normalized_path)
            return os.path.abspath(full_path) # Ensure it's truly absolute

        # Fallback: return the absolute path relative to the current working directory (less ideal)
        return os.path.abspath(os.path.normpath(path))
    
    def error_logging(self, message, level="INFO"):
        """Error logging for backend compatibility"""
        print(f"[{level}] {message}")
        
    def enable_drag_and_drop(self):
        """Enable drag and drop - placeholder for compatibility"""
        print("Drag and drop enabled (PyQt6 implementation pending)")
        
    def counter_update(self):
        """Update counters - needed for backend compatibility"""
        if hasattr(self, 'review_tab'):
            self.review_tab.update_page_display()
    
    def update_idletasks(self):
        """PyQt6 compatibility for Tkinter update_idletasks"""
        QApplication.processEvents()
    
    def toggle_button_state(self):
        """Toggle button states during AI processing - needed for backend compatibility"""
        # In PyQt6, we can disable tabs or show processing state
        # For now, just update the status bar to show processing state
        if hasattr(self, 'status_bar'):
            current_message = self.status_bar.currentMessage()
            if "Processing" in current_message:
                self.status_bar.showMessage("Processing completed")
            else:
                self.status_bar.showMessage("Processing...")
        
        # Could also disable/enable specific buttons or tabs here if needed
        # For example:
        # if hasattr(self, 'tabs'):
        #     self.tabs.setEnabled(not self.tabs.isEnabled())
    
    class CompatibleProgressBar:
        """Progress bar compatibility layer for Tkinter-based backend"""
        def __init__(self, main_window):
            self.main_window = main_window
            self.current_progress = None
            
        def create_progress_window(self, title):
            """Create progress window - returns compatible objects"""
            self.current_progress = QProgressBar()
            
            # Show progress in status bar
            self.main_window.status_bar.showMessage(f"{title} - Starting...")
            self.main_window.status_progress_bar.setVisible(True)
            self.main_window.status_progress_bar.setRange(0, 100)
            
            # Return mock objects that have the expected interface
            class MockLabel:
                def config(self, text=None):
                    if text:
                        self.main_window.status_bar.showMessage(text)
            
            return None, self.main_window.status_progress_bar, MockLabel()
        
        def update_progress(self, current, total):
            """Update progress bar"""
            if total > 0:
                percent = int((current / total) * 100)
                self.main_window.status_progress_bar.setValue(percent)
                self.main_window.status_bar.showMessage(f"Processing: {current}/{total} ({percent}%)")
        
        def set_total_steps(self, total):
            """Set total steps for progress"""
            self.main_window.status_progress_bar.setRange(0, total)
        
        def close_progress_window(self):
            """Close progress window"""
            self.main_window.status_progress_bar.setVisible(False)
            self.main_window.status_bar.showMessage("Processing complete")
    
    def open_folder(self, directory, toggle):
        """Open folder and load files - adapted from original"""
        if directory:
            # Use an absolute path for the project directory
            self.project_directory = os.path.abspath(directory)
            # Make sure images directory is relative to project or temp
            self.images_directory = os.path.join(self.project_directory, "images")
            os.makedirs(self.images_directory, exist_ok=True)

            # Reset application state.
            self.reset_application() # This resets main_df and page_counter

            if toggle == "Images without Text":
                self.load_files_from_folder_no_text()
            else:
                self.load_files_from_folder()
            self.enable_drag_and_drop()
    
    def load_files_from_folder_no_text(self):
        """Load image files without text - adapted from original"""
        if not self.project_directory:
            QMessageBox.critical(self, "Error", "No directory selected.")
            return

        # Get lists of image files from the project_directory
        try:
            image_files = [f for f in os.listdir(self.project_directory) 
                          if f.lower().endswith((".jpg", ".jpeg", ".png", ".tiff", ".tif"))]

            if not image_files:
                QMessageBox.information(self, "No Files", "No image files found in the selected directory.")
                return

            # Sort image files naturally
            from util.DataOperations import natural_sort_key
            image_files.sort(key=natural_sort_key)

            new_rows_list = []
            # Populate the DataFrame with all image files
            for i, image_file in enumerate(image_files):
                image_path_abs = os.path.join(self.project_directory, image_file)
                image_path_rel = self.get_relative_path(image_path_abs)
                
                new_row = {
                    'Page': i + 1,
                    'Image_Path': image_path_rel,
                    'Text': "",
                    'Text_Toggle': "None",
                    'Corrected_Text': "",
                    'Translation': "",
                    'Formatted_Text': "",
                    'Separated_Text': "",
                    'Names': "",
                    'Places': "",
                    'Metadata': "",
                    'Relevance': ""
                }
                new_rows_list.append(new_row)

            # Create new DataFrame and update
            if new_rows_list:
                self.main_df = pd.DataFrame(new_rows_list)
                self.data_operations.main_df = self.main_df
                self.page_counter = 0
                print(f"✅ Loaded {len(new_rows_list)} image files")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load files: {str(e)}")
    
    def get_relative_path(self, absolute_path):
        """Convert absolute path to relative - needed for backend compatibility"""
        if not absolute_path or not self.project_directory:
            return absolute_path
        try:
            return os.path.relpath(absolute_path, self.project_directory)
        except ValueError:
            return absolute_path
    
    def init_ui(self):
        """Initialize the modern tabbed interface"""
        
        # Create central tab widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # Create the four main tabs
        self.project_tab = ProjectTab(self)
        self.process_tab = ProcessTab(self)
        self.review_tab = ReviewTab(self)
        self.export_tab = ExportTab(self)
        
        # Add tabs to widget
        self.tabs.addTab(self.project_tab, "📁 PROJECT")
        self.tabs.addTab(self.process_tab, "📄 PROCESS")
        self.tabs.addTab(self.review_tab, "✏️ REVIEW")
        self.tabs.addTab(self.export_tab, "📤 EXPORT")
        
        # Create toolbar
        self.create_toolbar()
        
        # Create status bar
        self.create_status_bar()
        
        # Set default tab
        self.tabs.setCurrentIndex(0)  # Start with PROJECT tab
        
        # Initialize progress bar compatibility layer
        self.progress_bar = self.CompatibleProgressBar(self)
    
    def create_toolbar(self):
        """Create quick actions toolbar"""
        toolbar = QToolBar("Quick Actions")
        self.addToolBar(toolbar)
        
        # File operations
        new_action = QAction("🆕 New", self)
        new_action.triggered.connect(self.project_tab.new_project)
        toolbar.addAction(new_action)
        
        open_action = QAction("📂 Open", self)
        open_action.triggered.connect(self.project_tab.open_project)
        toolbar.addAction(open_action)
        
        toolbar.addSeparator()
        
        # Quick processing
        htr_action = QAction("🔍 HTR", self)
        htr_action.triggered.connect(self.process_tab.htr_all_pages)
        toolbar.addAction(htr_action)
        
        correct_action = QAction("✏️ Correct", self)
        correct_action.triggered.connect(self.process_tab.correct_text)
        toolbar.addAction(correct_action)
        
        toolbar.addSeparator()
        
        # Settings
        settings_action = QAction("⚙️ Settings", self)
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)
    
    def create_status_bar(self):
        """Create status bar with progress indicator"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Progress bar (hidden by default)
        self.status_progress_bar = QProgressBar()
        self.status_progress_bar.setVisible(False)
        self.status_progress_bar.setMaximumWidth(200)
        self.status_bar.addPermanentWidget(self.status_progress_bar)
        
        # Status message
        self.status_bar.showMessage("Archive Studio 2.0 Ready")
    
    def apply_styles(self):
        """Apply modern styling to the application"""
        style = """
        QMainWindow {
            background-color: #f8f9fa;
        }
        
        QTabWidget::pane {
            border: 1px solid #c0c0c0;
            background-color: white;
        }
        
        QTabWidget::tab-bar {
            alignment: left;
        }
        
        QTabBar::tab {
            background-color: #e9ecef;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        
        QTabBar::tab:selected {
            background-color: white;
            border: 1px solid #c0c0c0;
            border-bottom-color: white;
        }
        
        QPushButton {
            background-color: #007bff;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }
        
        QPushButton:hover {
            background-color: #0056b3;
        }
        
        QPushButton:pressed {
            background-color: #004085;
        }
        
        QFrame[frameShape="4"] {
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 10px;
        }
        
        QToolBar {
            background-color: #343a40;
            color: white;
            spacing: 3px;
        }
        
        QStatusBar {
            background-color: #343a40;
            color: white;
        }
        """
        
        self.setStyleSheet(style)
    
    def open_settings(self):
        """Open settings dialog"""
        try:
            if hasattr(self, 'settings'):
                # Create simple PyQt6 settings dialog
                settings_dialog = SimpleSettingsDialog(self, self.settings)
                if settings_dialog.exec() == QDialog.DialogCode.Accepted:
                    self.status_bar.showMessage("Settings updated")
                    # Reinitialize API handler with new keys
                    self.api_handler = APIHandler(
                        self.settings.openai_api_key,
                        self.settings.anthropic_api_key, 
                        self.settings.google_api_key,
                        self
                    )
                    self.ai_functions_handler = AIFunctionsHandler(self)
            else:
                QMessageBox.information(self, "Settings", "Settings system not initialized")
        except Exception as e:
            QMessageBox.critical(self, "Settings Error", f"Could not open settings: {str(e)}")
    
    def show_progress(self, current, total):
        """Show progress bar with current status"""
        if total > 0:
            self.status_progress_bar.setMaximum(total)
            self.status_progress_bar.setValue(current)
            self.status_progress_bar.setVisible(True)
            self.status_bar.showMessage(f"Processing: {current}/{total}")
        else:
            self.status_progress_bar.setVisible(False)
    
    def closeEvent(self, event):
        """Handle application close"""
        reply = QMessageBox.question(
            self, 'Close Archive Studio', 
            'Are you sure you want to exit?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("Archive Studio")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("Archive Studio Team")
    
    # Create and show main window
    window = ArchiveStudioQt()
    window.show()
    
    print("🚀 Archive Studio 2.0 (PyQt6) launched successfully!")
    print("📁 Start with the PROJECT tab to import documents")
    print("📄 Use PROCESS tab for AI operations")
    print("✏️ REVIEW tab for editing and validation")
    print("📤 EXPORT tab for final output")
    
    # Start the application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()