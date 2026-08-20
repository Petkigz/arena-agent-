"""Tests for Phase 6c: Multi-modal Attachment Analysis APIs."""

import pytest
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from backend.main import app
from backend.api.phase6_routes import UPLOAD_DIR, METADATA_FILE, load_metadata, save_metadata


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def temp_upload_dir():
    """Create temporary upload directory for tests."""
    temp_dir = Path(tempfile.mkdtemp())
    
    with patch('backend.api.phase6_routes.UPLOAD_DIR', temp_dir):
        with patch('backend.api.phase6_routes.METADATA_FILE', temp_dir / '.metadata.json'):
            yield temp_dir
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_image_file(temp_upload_dir):
    """Create a sample image file for testing."""
    # Upload a test image
    content = b'\xFF\xD8\xFF\xE0' + b'\x00' * 100  # JPEG magic bytes
    files = {'file': ('test.jpg', content, 'image/jpeg')}
    
    client = TestClient(app)
    response = client.post('/api/files/upload', files=files)
    file_id = response.json()['id']
    
    return file_id


@pytest.fixture
def sample_pdf_file(temp_upload_dir):
    """Create a sample PDF file for testing."""
    content = b'%PDF-1.4\n' + b'Test PDF content\n' * 10
    files = {'file': ('test.pdf', content, 'application/pdf')}
    
    client = TestClient(app)
    response = client.post('/api/files/upload', files=files)
    file_id = response.json()['id']
    
    return file_id


class TestAttachmentAnalysisAPI:
    """Test /api/attachments/analyze endpoint."""
    
    @patch('backend.api.phase6_routes.VisionAnalyzerTool')
    def test_analyze_image_vision(self, mock_vision, client, sample_image_file):
        """Analyze image with vision analysis."""
        mock_vision.analyze_screen_image.return_value = {
            'success': True,
            'ai_analysis': 'This is a test image showing a sample pattern.',
            'screen_changed': True,
            'model_used': 'qwen2.5-vl',
        }
        
        request = {
            'fileId': sample_image_file,
            'analysisType': 'vision',
            'promptFocus': 'Describe what you see',
        }
        response = client.post('/api/attachments/analyze', json=request)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert data['type'] == 'vision'
        assert 'test image' in data['content']
        assert data['metadata']['model_used'] == 'qwen2.5-vl'
        assert 'analyzedAt' in data
    
    @patch('backend.api.phase6_routes.OCRReaderTool')
    def test_analyze_image_ocr(self, mock_ocr, client, sample_image_file):
        """Analyze image with OCR."""
        mock_ocr.extract_text_from_image.return_value = {
            'success': True,
            'extracted_text': 'Sample text from image\nLine 2\nLine 3',
            'word_count': 8,
        }
        
        request = {
            'fileId': sample_image_file,
            'analysisType': 'ocr',
        }
        response = client.post('/api/attachments/analyze', json=request)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert data['type'] == 'ocr'
        assert 'Sample text' in data['content']
        assert data['metadata']['word_count'] == 8
    
    @patch('backend.api.phase6_routes._parse_pdf')
    def test_analyze_pdf_document(self, mock_parse_pdf, client, sample_pdf_file):
        """Analyze PDF document."""
        mock_parse_pdf.return_value = 'Extracted PDF text content\nPage 1\nPage 2'
        
        request = {
            'fileId': sample_pdf_file,
            'analysisType': 'document',
        }
        response = client.post('/api/attachments/analyze', json=request)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert data['type'] == 'document'
        assert 'Extracted PDF text' in data['content']
        assert data['metadata']['file_type'] == '.pdf'
    
    def test_analyze_auto_detects_image(self, client, sample_image_file):
        """Auto-detect analysis type for image."""
        request = {
            'fileId': sample_image_file,
            'analysisType': 'auto',
        }
        
        # Should auto-detect as 'vision' for images
        with patch('backend.api.phase6_routes.VisionAnalyzerTool') as mock_vision:
            mock_vision.analyze_screen_image.return_value = {
                'success': True,
                'ai_analysis': 'Auto-detected image analysis',
                'screen_changed': True,
                'model_used': 'qwen2.5-vl',
            }
            
            response = client.post('/api/attachments/analyze', json=request)
            
            assert response.status_code == 200
            data = response.json()
            assert data['type'] == 'vision'
    
    def test_analyze_auto_detects_document(self, client, sample_pdf_file):
        """Auto-detect analysis type for document."""
        request = {
            'fileId': sample_pdf_file,
            'analysisType': 'auto',
        }
        
        # Should auto-detect as 'document' for PDFs
        with patch('backend.api.phase6_routes._parse_pdf') as mock_parse:
            mock_parse.return_value = 'Auto-detected document content'
            
            response = client.post('/api/attachments/analyze', json=request)
            
            assert response.status_code == 200
            data = response.json()
            assert data['type'] == 'document'
    
    def test_analyze_nonexistent_file(self, client, temp_upload_dir):
        """Analyze returns 404 for nonexistent file."""
        request = {
            'fileId': 'nonexistent-id',
            'analysisType': 'vision',
        }
        response = client.post('/api/attachments/analyze', json=request)
        
        assert response.status_code == 404
    
    def test_analyze_invalid_analysis_type(self, client, sample_image_file):
        """Reject invalid analysis type."""
        request = {
            'fileId': sample_image_file,
            'analysisType': 'invalid_type',
        }
        response = client.post('/api/attachments/analyze', json=request)
        
        assert response.status_code == 400
        assert 'Unknown analysis type' in response.json()['detail']
    
    @patch('backend.api.phase6_routes.VisionAnalyzerTool')
    def test_analyze_vision_failure(self, mock_vision, client, sample_image_file):
        """Handle vision analysis failure."""
        mock_vision.analyze_screen_image.return_value = {
            'success': False,
            'error': 'Vision model unavailable',
        }
        
        request = {
            'fileId': sample_image_file,
            'analysisType': 'vision',
        }
        response = client.post('/api/attachments/analyze', json=request)
        
        assert response.status_code == 500
        # Implementation returns the actual error message from the tool
        assert 'Vision model unavailable' in response.json()['detail']
    
    @patch('backend.api.phase6_routes.OCRReaderTool')
    def test_analyze_ocr_failure(self, mock_ocr, client, sample_image_file):
        """Handle OCR failure."""
        mock_ocr.extract_text_from_image.return_value = {
            'success': False,
            'error': 'Tesseract not installed',
        }
        
        request = {
            'fileId': sample_image_file,
            'analysisType': 'ocr',
        }
        response = client.post('/api/attachments/analyze', json=request)
        
        assert response.status_code == 500
        # Implementation returns the actual error message from the tool
        assert 'Tesseract not installed' in response.json()['detail']


class TestDocumentParsing:
    """Test document parsing functions."""
    
    @patch('backend.api.phase6_routes._parse_pdf')
    def test_parse_pdf(self, mock_parse_pdf, client, sample_pdf_file):
        """Parse PDF document."""
        mock_parse_pdf.return_value = 'PDF content\nPage 1\nPage 2'
        
        request = {
            'fileId': sample_pdf_file,
            'analysisType': 'document',
        }
        response = client.post('/api/attachments/analyze', json=request)
        
        assert response.status_code == 200
        data = response.json()
        assert 'PDF content' in data['content']
    
    def test_parse_text_file(self, client, temp_upload_dir):
        """Parse plain text file."""
        # Upload text file
        content = b'This is plain text content\nLine 2\nLine 3'
        files = {'file': ('test.txt', content, 'text/plain')}
        upload_response = client.post('/api/files/upload', files=files)
        file_id = upload_response.json()['id']
        
        # Analyze
        request = {
            'fileId': file_id,
            'analysisType': 'document',
        }
        response = client.post('/api/attachments/analyze', json=request)
        
        assert response.status_code == 200
        data = response.json()
        assert 'plain text content' in data['content']


class TestMetadataExtraction:
    """Test metadata extraction for various file types."""
    
    @patch('backend.api.phase6_routes._extract_file_metadata')
    def test_extract_video_metadata(self, mock_extract, client, temp_upload_dir):
        """Extract metadata from video file."""
        # Upload video file
        content = b'\x00\x00\x00\x18ftypmp4' + b'\x00' * 100  # MP4 magic bytes
        files = {'file': ('test.mp4', content, 'video/mp4')}
        upload_response = client.post('/api/files/upload', files=files)
        file_id = upload_response.json()['id']
        
        mock_extract.return_value = {
            'filename': 'test.mp4',
            'size': 104,
            'type': 'video/mp4',
            'category': 'video',
            'media_info': {
                'format': {'duration': '120.5'},
                'streams': [{'codec_type': 'video', 'width': 1920, 'height': 1080}],
            },
        }
        
        # Analyze with metadata type
        request = {
            'fileId': file_id,
            'analysisType': 'metadata',
        }
        response = client.post('/api/attachments/analyze', json=request)
        
        assert response.status_code == 200
        data = response.json()
        assert data['type'] == 'metadata'
        assert 'media_info' in data['metadata']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
