"""Tests for Phase 6a: File Upload & Management APIs."""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from backend.main import app
from backend.api.phase6_routes import (
    detect_file_type,
    calculate_file_hash,
    check_rate_limit,
    load_metadata,
    save_metadata,
    UPLOAD_DIR,
    METADATA_FILE,
    RATE_LIMIT_REQUESTS,
)


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


class TestFileTypeDetection:
    """Test magic byte file type detection."""
    
    def test_detect_jpeg(self):
        """Detect JPEG from magic bytes."""
        content = b'\xFF\xD8\xFF\xE0' + b'\x00' * 100
        result = detect_file_type(content, 'test.jpg')
        
        assert result['mime_type'] == 'image/jpeg'
        assert result['category'] == 'image'
        assert result['confidence'] == 'high'
    
    def test_detect_png(self):
        """Detect PNG from magic bytes."""
        content = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        result = detect_file_type(content, 'test.png')
        
        assert result['mime_type'] == 'image/png'
        assert result['category'] == 'image'
        assert result['confidence'] == 'high'
    
    def test_detect_pdf(self):
        """Detect PDF from magic bytes."""
        content = b'%PDF-1.4' + b'\x00' * 100
        result = detect_file_type(content, 'test.pdf')
        
        assert result['mime_type'] == 'application/pdf'
        assert result['category'] == 'document'
        assert result['confidence'] == 'high'
    
    def test_detect_zip(self):
        """Detect ZIP from magic bytes."""
        content = b'PK\x03\x04' + b'\x00' * 100
        result = detect_file_type(content, 'test.zip')
        
        assert result['mime_type'] == 'application/zip'
        assert result['category'] == 'archive'
        assert result['confidence'] == 'high'
    
    def test_detect_python(self):
        """Detect Python from shebang."""
        content = b'#!/usr/bin/env python3\nprint("hello")'
        result = detect_file_type(content, 'test.py')
        
        assert result['mime_type'] == 'text/x-python'
        assert result['category'] == 'code'
        assert result['confidence'] == 'high'
    
    def test_fallback_to_extension(self):
        """Fallback to extension when magic bytes unknown."""
        content = b'random content'
        result = detect_file_type(content, 'test.json')
        
        assert result['mime_type'] == 'application/json'
        assert result['category'] == 'document'
        assert result['confidence'] == 'medium'
    
    def test_unknown_type(self):
        """Handle unknown file type."""
        content = b'\x00\x01\x02\x03'
        result = detect_file_type(content, 'test.unknown')
        
        assert result['mime_type'] == 'application/octet-stream'
        assert result['category'] == 'binary'
        assert result['confidence'] == 'low'


class TestFileHashing:
    """Test SHA-256 file hashing."""
    
    def test_calculate_hash(self):
        """Calculate SHA-256 hash of content."""
        content = b'test content'
        hash_value = calculate_file_hash(content)
        
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA-256 produces 64 hex chars
    
    def test_hash_consistency(self):
        """Same content produces same hash."""
        content = b'test content'
        hash1 = calculate_file_hash(content)
        hash2 = calculate_file_hash(content)
        
        assert hash1 == hash2
    
    def test_hash_uniqueness(self):
        """Different content produces different hash."""
        content1 = b'test content 1'
        content2 = b'test content 2'
        hash1 = calculate_file_hash(content1)
        hash2 = calculate_file_hash(content2)
        
        assert hash1 != hash2


class TestRateLimiting:
    """Test IP-based rate limiting."""
    
    def test_rate_limit_allows_requests(self):
        """Allow requests under limit."""
        ip = '192.168.1.1'
        
        for _ in range(RATE_LIMIT_REQUESTS - 1):
            assert check_rate_limit(ip) is True
    
    def test_rate_limit_blocks_excess(self):
        """Block requests over limit."""
        ip = '192.168.1.2'
        
        # Use up all requests
        for _ in range(RATE_LIMIT_REQUESTS):
            check_rate_limit(ip)
        
        # Next request should be blocked
        assert check_rate_limit(ip) is False
    
    def test_rate_limit_different_ips(self):
        """Different IPs have separate limits."""
        ip1 = '192.168.1.3'
        ip2 = '192.168.1.4'
        
        # Use up limit for ip1
        for _ in range(RATE_LIMIT_REQUESTS):
            check_rate_limit(ip1)
        
        # ip2 should still be allowed
        assert check_rate_limit(ip2) is True
        assert check_rate_limit(ip1) is False


class TestFileUploadAPI:
    """Test /api/files/upload endpoint."""
    
    def test_upload_text_file(self, client, temp_upload_dir):
        """Upload a text file successfully."""
        content = b'Test file content'
        files = {'file': ('test.txt', content, 'text/plain')}
        
        response = client.post('/api/files/upload', files=files)
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'id' in data
        assert data['name'] == 'test.txt'
        assert data['size'] == len(content)
        assert data['type'] == 'text/plain'
        assert 'hash' in data
        assert 'uploadedAt' in data
    
    def test_upload_with_conversation_id(self, client, temp_upload_dir):
        """Upload file with conversation ID."""
        content = b'Test content'
        files = {'file': ('test.txt', content, 'text/plain')}
        params = {'conversationId': 'conv-123'}
        
        response = client.post('/api/files/upload', files=files, params=params)
        
        assert response.status_code == 200
        data = response.json()
        assert data['conversationId'] == 'conv-123'
    
    def test_upload_detects_file_type(self, client, temp_upload_dir):
        """Upload detects file type from magic bytes."""
        # JPEG magic bytes
        content = b'\xFF\xD8\xFF\xE0' + b'\x00' * 100
        files = {'file': ('image.jpg', content, 'application/octet-stream')}
        
        response = client.post('/api/files/upload', files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data['type'] == 'image/jpeg'
        assert data['category'] == 'image'
    
    def test_upload_stores_file(self, client, temp_upload_dir):
        """Upload stores file on disk."""
        content = b'Test content'
        files = {'file': ('test.txt', content, 'text/plain')}
        
        response = client.post('/api/files/upload', files=files)
        data = response.json()
        
        # Check file exists
        file_path = temp_upload_dir / f"{data['id']}.txt"
        assert file_path.exists()
        assert file_path.read_bytes() == content
    
    def test_upload_stores_metadata(self, client, temp_upload_dir):
        """Upload stores metadata."""
        content = b'Test content'
        files = {'file': ('test.txt', content, 'text/plain')}
        
        response = client.post('/api/files/upload', files=files)
        data = response.json()
        
        # Check metadata
        metadata = load_metadata()
        assert data['id'] in metadata
        assert metadata[data['id']]['name'] == 'test.txt'
        assert metadata[data['id']]['size'] == len(content)


class TestFileDownloadAPI:
    """Test /api/files/{file_id} endpoint."""
    
    def test_download_existing_file(self, client, temp_upload_dir):
        """Download an existing file."""
        # Upload first
        content = b'Test content'
        files = {'file': ('test.txt', content, 'text/plain')}
        upload_response = client.post('/api/files/upload', files=files)
        file_id = upload_response.json()['id']
        
        # Download
        response = client.get(f'/api/files/{file_id}')
        
        assert response.status_code == 200
        assert response.content == content
    
    def test_download_nonexistent_file(self, client, temp_upload_dir):
        """Download returns 404 for nonexistent file."""
        response = client.get('/api/files/nonexistent-id')
        
        assert response.status_code == 404


class TestFileListAPI:
    """Test /api/files endpoint."""
    
    def test_list_all_files(self, client, temp_upload_dir):
        """List all uploaded files."""
        # Upload 2 files
        for i in range(2):
            content = f'Content {i}'.encode()
            files = {'file': (f'test{i}.txt', content, 'text/plain')}
            client.post('/api/files/upload', files=files)
        
        # List files
        response = client.get('/api/files')
        
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 2
        assert len(data['files']) == 2
    
    def test_list_files_by_conversation(self, client, temp_upload_dir):
        """List files filtered by conversation ID."""
        # Upload files with different conversation IDs
        files1 = {'file': ('test1.txt', b'Content 1', 'text/plain')}
        client.post('/api/files/upload', files=files1, params={'conversationId': 'conv-1'})
        
        files2 = {'file': ('test2.txt', b'Content 2', 'text/plain')}
        client.post('/api/files/upload', files=files2, params={'conversationId': 'conv-2'})
        
        # List files for conv-1
        response = client.get('/api/files', params={'conversationId': 'conv-1'})
        
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 1
        assert data['files'][0]['conversationId'] == 'conv-1'
    
    def test_list_empty(self, client, temp_upload_dir):
        """List returns empty when no files."""
        response = client.get('/api/files')
        
        assert response.status_code == 200
        data = response.json()
        assert data['total'] == 0
        assert len(data['files']) == 0


class TestFileDeleteAPI:
    """Test /api/files/{file_id} DELETE endpoint."""
    
    def test_delete_existing_file(self, client, temp_upload_dir):
        """Delete an existing file."""
        # Upload first
        content = b'Test content'
        files = {'file': ('test.txt', content, 'text/plain')}
        upload_response = client.post('/api/files/upload', files=files)
        file_id = upload_response.json()['id']
        
        # Delete
        response = client.delete(f'/api/files/{file_id}')
        
        assert response.status_code == 200
        assert response.json()['success'] is True
        
        # Verify file is gone
        file_path = temp_upload_dir / f"{file_id}.txt"
        assert not file_path.exists()
        
        # Verify metadata is gone
        metadata = load_metadata()
        assert file_id not in metadata
    
    def test_delete_nonexistent_file(self, client, temp_upload_dir):
        """Delete returns 404 for nonexistent file."""
        response = client.delete('/api/files/nonexistent-id')
        
        assert response.status_code == 404


class TestMetadataPersistence:
    """Test metadata storage and retrieval."""
    
    def test_save_and_load_metadata(self, temp_upload_dir):
        """Save and load metadata."""
        metadata = {
            'file1': {'name': 'test1.txt', 'size': 100},
            'file2': {'name': 'test2.txt', 'size': 200},
        }
        
        save_metadata(metadata)
        loaded = load_metadata()
        
        assert loaded == metadata
    
    def test_load_empty_metadata(self, temp_upload_dir):
        """Load returns empty dict when no metadata file."""
        metadata = load_metadata()
        
        assert metadata == {}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
