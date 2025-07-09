#!/usr/bin/env python3
"""
Test real HTR processing functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from archive_studio_qt import ArchiveStudioQt
import pandas as pd

def test_real_htr():
    """Test real HTR processing functionality"""
    print("🧪 Testing real HTR processing...")
    
    app = QApplication(sys.argv)
    window = ArchiveStudioQt()
    
    # Check if we have API keys
    has_openai = bool(getattr(window.settings, 'openai_api_key', ''))
    has_anthropic = bool(getattr(window.settings, 'anthropic_api_key', ''))
    has_google = bool(getattr(window.settings, 'google_api_key', ''))
    
    print(f"🔑 API Keys:")
    print(f"   OpenAI: {'✅' if has_openai else '❌'}")
    print(f"   Anthropic: {'✅' if has_anthropic else '❌'}")
    print(f"   Google: {'✅' if has_google else '❌'}")
    
    if not any([has_openai, has_anthropic, has_google]):
        print("❌ No API keys found. Cannot test real HTR processing.")
        return False
    
    # Set up proper directory structure (following original backend pattern)
    images_dir = "/Users/jimclifford/Library/CloudStorage/GoogleDrive-cljim22@gmail.com/My Drive/transcription/images"
    base_dir = "/Users/jimclifford/Library/CloudStorage/GoogleDrive-cljim22@gmail.com/My Drive/transcription"
    
    # Set the project directory to the base directory containing the images folder
    window.project_directory = base_dir
    window.images_directory = images_dir
    
    # Mock some data with real image paths (relative to project directory)
    image_files = []
    
    if os.path.exists(images_dir):
        for filename in os.listdir(images_dir):
            if filename.endswith('.jpg') and len(image_files) < 3:
                image_files.append(f"images/{filename}")  # Relative path
    
    if not image_files:
        print("❌ No image files found for testing")
        return False
    
    print(f"📸 Found {len(image_files)} image files for testing")
    
    # Create test dataframe
    test_data = []
    for i, image_path in enumerate(image_files):
        test_data.append({
            'Index': i,
            'Page': f'000{i+1}_p00{i+1}',
            'Original_Text': '',
            'Corrected_Text': '',
            'Image_Path': image_path,
            'Text_Toggle': 'None'
        })
    
    window.main_df = pd.DataFrame(test_data)
    
    print(f"✅ Test data created: {len(window.main_df)} pages")
    
    # Use default HTR preset (now with Gemini 2.5 Pro)
    for preset in window.settings.function_presets:
        if preset.get('name') == 'HTR':
            print(f"🔧 Using HTR preset with model: {preset['model']}")
            break
    
    # Test real HTR processing
    print("\n🔄 Starting real HTR processing...")
    
    def on_htr_complete(message):
        print(f"✅ HTR completed: {message}")
        
        # Check if text was actually extracted
        if hasattr(window, 'main_df') and not window.main_df.empty:
            for i, row in window.main_df.iterrows():
                original_text = row.get('Original_Text', '')
                if original_text.strip():
                    print(f"📝 Page {i+1} extracted text: {original_text[:100]}...")
                else:
                    print(f"📝 Page {i+1}: No text extracted")
        
        app.quit()
    
    def on_htr_error(message):
        print(f"❌ HTR error: {message}")
        app.quit()
    
    def on_htr_progress(current, total, status):
        print(f"📈 Progress: {current}/{total} - {status}")
    
    try:
        process_tab = window.process_tab
        
        # Start HTR processing
        process_tab.start_ai_processing("htr_all")
        
        if hasattr(process_tab, 'current_thread'):
            process_tab.current_thread.processing_complete.connect(on_htr_complete)
            process_tab.current_thread.error_occurred.connect(on_htr_error)
            process_tab.current_thread.progress_updated.connect(on_htr_progress)
        
        # Set timeout
        QTimer.singleShot(60000, app.quit)  # 1 minute timeout
        
        print("⏳ Processing started...")
        app.exec()
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing HTR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_real_htr()
    print("🎉 HTR testing completed!" if success else "❌ HTR testing failed!")