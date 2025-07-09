# util/DocumentAIHandler.py

"""
Google Document AI Handler for Archive Studio
Provides OCR and handwriting recognition using Google's Document AI service.
"""

import os
import json
import tempfile
from typing import Optional, Dict, Any
from google.cloud import documentai
from google.oauth2 import service_account
from util.ErrorLogger import log_error

class DocumentAIHandler:
    """Handler for Google Document AI OCR and handwriting recognition."""
    
    def __init__(self):
        self.client = None
        self.project_id = None
        self.location = None
        self.processor_id = None
        self.processor_name = None
        self.credentials = None
        
    def setup_credentials(self, credentials_json: str, project_id: str, 
                         location: str = "us", processor_id: str = None) -> bool:
        """
        Setup Document AI credentials and configuration.
        
        Args:
            credentials_json: JSON string containing service account credentials
            project_id: Google Cloud project ID
            location: Document AI location (default: "us")
            processor_id: Document AI processor ID (optional, will use default OCR)
            
        Returns:
            bool: True if setup successful, False otherwise
        """
        try:
            # Parse credentials JSON
            credentials_dict = json.loads(credentials_json)
            
            # Create credentials object
            self.credentials = service_account.Credentials.from_service_account_info(
                credentials_dict
            )
            
            # Initialize client
            self.client = documentai.DocumentProcessorServiceClient(
                credentials=self.credentials
            )
            
            # Store configuration
            self.project_id = project_id
            self.location = location
            
            # Set processor ID (use default OCR if not provided)
            if processor_id:
                self.processor_id = processor_id
            else:
                # Use the general document processor for OCR/HTR
                self.processor_id = "general"
                
            # Build processor name
            self.processor_name = f"projects/{project_id}/locations/{location}/processors/{self.processor_id}"
            
            log_error("Document AI configured successfully")
            return True
            
        except Exception as e:
            log_error(f"Failed to setup Document AI credentials: {str(e)}")
            return False
    
    def is_configured(self) -> bool:
        """Check if Document AI is properly configured."""
        return (self.client is not None and 
                self.project_id is not None and 
                self.processor_name is not None)
    
    def process_image(self, image_path: str, mime_type: str = None) -> Optional[str]:
        """
        Process an image using Document AI for OCR/HTR.
        
        Args:
            image_path: Path to the image file
            mime_type: MIME type of the image (auto-detected if None)
            
        Returns:
            str: Extracted text or None if processing failed
        """
        if not self.is_configured():
            log_error("Document AI not configured")
            return None
            
        try:
            # Auto-detect MIME type if not provided
            if mime_type is None:
                _, ext = os.path.splitext(image_path.lower())
                mime_types = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg', 
                    '.png': 'image/png',
                    '.pdf': 'application/pdf',
                    '.tiff': 'image/tiff',
                    '.tif': 'image/tiff'
                }
                mime_type = mime_types.get(ext, 'image/jpeg')
            
            # Read image file
            with open(image_path, "rb") as image_file:
                image_content = image_file.read()
            
            # Create the document object
            raw_document = documentai.RawDocument(
                content=image_content,
                mime_type=mime_type
            )
            
            # Configure the process request
            request = documentai.ProcessRequest(
                name=self.processor_name,
                raw_document=raw_document
            )
            
            # Process the document
            result = self.client.process_document(request=request)
            document = result.document
            
            # Extract clean text from Document AI response
            text = document.text
            
            # Advanced text cleaning for historical documents
            if not text or text.strip() == "":
                return "No text detected in document"
            
            # Split into lines and clean each line
            lines = text.split('\n')
            cleaned_lines = []
            
            for line in lines:
                line = line.strip()
                if line:  # Only keep non-empty lines
                    # Remove excessive spaces while preserving intentional spacing
                    line = ' '.join(line.split())
                    cleaned_lines.append(line)
            
            # Join lines with single line breaks
            cleaned_text = '\n'.join(cleaned_lines)
            
            # Final cleanup - remove excessive line breaks but preserve paragraph structure
            import re
            cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)  # Max 2 consecutive line breaks
            
            return cleaned_text.strip()
            
        except Exception as e:
            log_error(f"Document AI processing failed for {image_path}: {str(e)}")
            return None
    
    def get_available_processors(self) -> Dict[str, str]:
        """
        Get list of available Document AI processors.
        
        Returns:
            dict: Dictionary of processor display names -> processor IDs
        """
        if not self.is_configured():
            return {}
            
        try:
            parent = f"projects/{self.project_id}/locations/{self.location}"
            
            # List processors
            processors = self.client.list_processors(parent=parent)
            
            processor_dict = {}
            for processor in processors:
                # Extract processor ID from full name
                processor_id = processor.name.split('/')[-1]
                display_name = processor.display_name or processor.type_
                processor_dict[display_name] = processor_id
                
            return processor_dict
            
        except Exception as e:
            log_error(f"Failed to list Document AI processors: {str(e)}")
            return {}
    
    def test_connection(self) -> bool:
        """
        Test the Document AI connection.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        if not self.is_configured():
            return False
            
        try:
            # Try to list processors as a connection test
            parent = f"projects/{self.project_id}/locations/{self.location}"
            list(self.client.list_processors(parent=parent))
            return True
            
        except Exception as e:
            log_error(f"Document AI connection test failed: {str(e)}")
            return False

# Global instance
document_ai_handler = DocumentAIHandler()