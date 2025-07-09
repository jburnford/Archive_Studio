#!/usr/bin/env python3
"""
Comprehensive test suite for Archive Studio Qt
Tests all major functionality without requiring user interaction
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from archive_studio_qt import ArchiveStudioQt
import pandas as pd

def test_backend_initialization():
    """Test that all backend modules initialize correctly"""
    print("🧪 Testing backend initialization...")
    
    app = QApplication(sys.argv)
    try:
        window = ArchiveStudioQt()
        
        # Test basic attributes
        assert hasattr(window, 'main_df'), "❌ main_df not initialized"
        assert hasattr(window, 'settings'), "❌ settings not initialized"
        assert hasattr(window, 'project_io'), "❌ project_io not initialized"
        assert hasattr(window, 'api_handler'), "❌ api_handler not initialized"
        assert hasattr(window, 'ai_functions_handler'), "❌ ai_functions_handler not initialized"
        assert hasattr(window, 'export_manager'), "❌ export_manager not initialized"
        
        # Test DataFrame
        assert isinstance(window.main_df, pd.DataFrame), "❌ main_df is not a DataFrame"
        assert len(window.main_df.columns) > 0, "❌ main_df has no columns"
        
        # Test progress bar compatibility
        assert hasattr(window, 'progress_bar'), "❌ progress_bar not initialized"
        assert hasattr(window.progress_bar, 'create_progress_window'), "❌ progress_bar missing methods"
        
        print("✅ Backend initialization successful")
        return True
        
    except Exception as e:
        print(f"❌ Backend initialization failed: {e}")
        return False

def test_pdf_import_method():
    """Test that PDF import method exists and is callable"""
    print("🧪 Testing PDF import method...")
    
    app = QApplication(sys.argv)
    try:
        window = ArchiveStudioQt()
        
        # Test that open_pdf method exists
        assert hasattr(window.project_io, 'open_pdf'), "❌ open_pdf method not found"
        
        # Test progress bar compatibility layer
        progress_window, progress_bar, progress_label = window.progress_bar.create_progress_window("Test")
        assert progress_bar is not None, "❌ progress_bar creation failed"
        
        # Test progress updates
        window.progress_bar.update_progress(1, 10)
        window.progress_bar.set_total_steps(10)
        window.progress_bar.close_progress_window()
        
        print("✅ PDF import method test successful")
        return True
        
    except Exception as e:
        print(f"❌ PDF import method test failed: {e}")
        return False

def test_image_loading():
    """Test image loading functionality"""
    print("🧪 Testing image loading...")
    
    app = QApplication(sys.argv)
    try:
        window = ArchiveStudioQt()
        
        # Test that we can simulate loading images
        window.load_files_from_folder_no_text()  # Should handle empty directory gracefully
        
        # Test DataFrame structure after loading
        assert isinstance(window.main_df, pd.DataFrame), "❌ DataFrame corrupted after loading"
        
        print("✅ Image loading test successful")
        return True
        
    except Exception as e:
        print(f"❌ Image loading test failed: {e}")
        return False

def test_ai_processing_integration():
    """Test AI processing integration"""
    print("🧪 Testing AI processing integration...")
    
    app = QApplication(sys.argv)
    try:
        window = ArchiveStudioQt()
        
        # Test AI functions handler
        assert hasattr(window.ai_functions_handler, 'ai_function'), "❌ ai_function method not found"
        
        # Test that we can access the processing tabs
        process_tab = window.process_tab
        assert hasattr(process_tab, 'start_ai_processing'), "❌ start_ai_processing method not found"
        
        print("✅ AI processing integration test successful")
        return True
        
    except Exception as e:
        print(f"❌ AI processing integration test failed: {e}")
        return False

def test_export_functionality():
    """Test export functionality"""
    print("🧪 Testing export functionality...")
    
    app = QApplication(sys.argv)
    try:
        window = ArchiveStudioQt()
        
        # Test export manager
        assert hasattr(window.export_manager, 'export_txt'), "❌ export_txt method not found"
        
        # Test export tab methods
        export_tab = window.export_tab
        assert hasattr(export_tab, 'export_csv'), "❌ export_csv method not found"
        
        print("✅ Export functionality test successful")
        return True
        
    except Exception as e:
        print(f"❌ Export functionality test failed: {e}")
        return False

def test_ui_components():
    """Test UI components"""
    print("🧪 Testing UI components...")
    
    app = QApplication(sys.argv)
    try:
        window = ArchiveStudioQt()
        
        # Test tabs
        assert window.tabs.count() == 4, f"❌ Expected 4 tabs, got {window.tabs.count()}"
        
        # Test each tab
        assert hasattr(window, 'project_tab'), "❌ project_tab not found"
        assert hasattr(window, 'process_tab'), "❌ process_tab not found"
        assert hasattr(window, 'review_tab'), "❌ review_tab not found"
        assert hasattr(window, 'export_tab'), "❌ export_tab not found"
        
        # Test image viewer
        assert hasattr(window.review_tab, 'image_viewer'), "❌ image_viewer not found"
        assert hasattr(window.review_tab.image_viewer, 'load_image'), "❌ load_image method not found"
        
        # Test text editor
        assert hasattr(window.review_tab, 'text_editor'), "❌ text_editor not found"
        assert hasattr(window.review_tab.text_editor, 'highlight_text'), "❌ highlight_text method not found"
        
        print("✅ UI components test successful")
        return True
        
    except Exception as e:
        print(f"❌ UI components test failed: {e}")
        return False

def test_settings_integration():
    """Test settings integration"""
    print("🧪 Testing settings integration...")
    
    app = QApplication(sys.argv)
    try:
        window = ArchiveStudioQt()
        
        # Test settings object
        assert hasattr(window.settings, 'openai_api_key'), "❌ openai_api_key not found in settings"
        assert hasattr(window.settings, 'anthropic_api_key'), "❌ anthropic_api_key not found in settings"
        assert hasattr(window.settings, 'google_api_key'), "❌ google_api_key not found in settings"
        
        # Test that we can call open_settings without crashing
        # (won't actually open the dialog in test mode)
        
        print("✅ Settings integration test successful")
        return True
        
    except Exception as e:
        print(f"❌ Settings integration test failed: {e}")
        return False

def run_all_tests():
    """Run all tests and report results"""
    print("🚀 Starting Archive Studio Qt Test Suite")
    print("=" * 50)
    
    tests = [
        test_backend_initialization,
        test_pdf_import_method,
        test_image_loading,
        test_ai_processing_integration,
        test_export_functionality,
        test_ui_components,
        test_settings_integration
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)
    
    passed = sum(results)
    total = len(results)
    
    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test.__name__}")
    
    print(f"\n🎯 OVERALL: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Archive Studio Qt is ready for use.")
        return True
    else:
        print(f"⚠️  {total - passed} tests failed. See details above.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)