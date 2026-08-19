"""Tests for Phase 6b: Code Execution APIs."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from backend.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestCodeExecutionAPI:
    """Test /api/code/execute endpoint."""
    
    @patch('backend.api.phase6_routes.DisposableSandbox')
    def test_execute_python_code(self, mock_sandbox, client):
        """Execute Python code successfully."""
        # Mock sandbox
        mock_sandbox.create_sandbox.return_value = {
            'success': True,
            'sandbox_id': 'sandbox-123',
            'sandbox_dir': '/tmp/sandbox-123',
        }
        mock_sandbox.execute_in_sandbox.return_value = {
            'success': True,
            'stdout': 'Hello, World!\n',
            'stderr': '',
        }
        mock_sandbox.destroy_sandbox.return_value = None
        
        # Execute code
        request = {
            'code': 'print("Hello, World!")',
            'language': 'python',
            'timeout': 30,
        }
        response = client.post('/api/code/execute', json=request)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is True
        assert 'Hello, World!' in data['output']
        assert data['error'] is None
        assert 'executionTime' in data
        assert 'timestamp' in data
    
    @patch('backend.api.phase6_routes.DisposableSandbox')
    def test_execute_javascript_code(self, mock_sandbox, client):
        """Execute JavaScript code successfully."""
        mock_sandbox.create_sandbox.return_value = {
            'success': True,
            'sandbox_id': 'sandbox-456',
            'sandbox_dir': '/tmp/sandbox-456',
        }
        mock_sandbox.execute_in_sandbox.return_value = {
            'success': True,
            'stdout': '42\n',
            'stderr': '',
        }
        mock_sandbox.destroy_sandbox.return_value = None
        
        request = {
            'code': 'console.log(6 * 7);',
            'language': 'javascript',
            'timeout': 30,
        }
        response = client.post('/api/code/execute', json=request)
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert '42' in data['output']
    
    @patch('backend.api.phase6_routes.DisposableSandbox')
    def test_execute_code_with_error(self, mock_sandbox, client):
        """Execute code that produces an error."""
        mock_sandbox.create_sandbox.return_value = {
            'success': True,
            'sandbox_id': 'sandbox-789',
            'sandbox_dir': '/tmp/sandbox-789',
        }
        mock_sandbox.execute_in_sandbox.return_value = {
            'success': False,
            'stdout': '',
            'stderr': 'NameError: name "undefined_var" is not defined',
        }
        mock_sandbox.destroy_sandbox.return_value = None
        
        request = {
            'code': 'print(undefined_var)',
            'language': 'python',
            'timeout': 30,
        }
        response = client.post('/api/code/execute', json=request)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['success'] is False
        assert data['error'] is not None
        assert 'NameError' in data['error']
    
    @patch('backend.api.phase6_routes.DisposableSandbox')
    def test_execute_code_with_custom_timeout(self, mock_sandbox, client):
        """Execute code with custom timeout."""
        mock_sandbox.create_sandbox.return_value = {
            'success': True,
            'sandbox_id': 'sandbox-timeout',
            'sandbox_dir': '/tmp/sandbox-timeout',
        }
        mock_sandbox.execute_in_sandbox.return_value = {
            'success': True,
            'stdout': 'Done\n',
            'stderr': '',
        }
        mock_sandbox.destroy_sandbox.return_value = None
        
        request = {
            'code': 'import time; time.sleep(5); print("Done")',
            'language': 'python',
            'timeout': 10,
        }
        response = client.post('/api/code/execute', json=request)
        
        assert response.status_code == 200
        
        # Verify timeout was passed correctly
        call_args = mock_sandbox.execute_in_sandbox.call_args
        assert call_args[1]['timeout'] == 10
    
    @patch('backend.api.phase6_routes.DisposableSandbox')
    def test_execute_code_sandbox_creation_fails(self, mock_sandbox, client):
        """Handle sandbox creation failure."""
        mock_sandbox.create_sandbox.return_value = {
            'success': False,
            'error': 'Failed to create sandbox directory',
        }
        
        request = {
            'code': 'print("test")',
            'language': 'python',
            'timeout': 30,
        }
        response = client.post('/api/code/execute', json=request)
        
        assert response.status_code == 500
        assert 'Failed to create sandbox' in response.json()['detail']
    
    @patch('backend.api.phase6_routes.DisposableSandbox')
    def test_execute_code_cleans_up_sandbox(self, mock_sandbox, client):
        """Verify sandbox is cleaned up after execution."""
        mock_sandbox.create_sandbox.return_value = {
            'success': True,
            'sandbox_id': 'sandbox-cleanup',
            'sandbox_dir': '/tmp/sandbox-cleanup',
        }
        mock_sandbox.execute_in_sandbox.return_value = {
            'success': True,
            'stdout': 'Done\n',
            'stderr': '',
        }
        mock_sandbox.destroy_sandbox.return_value = None
        
        request = {
            'code': 'print("test")',
            'language': 'python',
            'timeout': 30,
        }
        client.post('/api/code/execute', json=request)
        
        # Verify cleanup was called
        mock_sandbox.destroy_sandbox.assert_called_once_with('sandbox-cleanup')
    
    def test_execute_code_missing_language(self, client):
        """Reject request with missing language."""
        request = {
            'code': 'print("test")',
            'timeout': 30,
        }
        response = client.post('/api/code/execute', json=request)
        
        assert response.status_code == 422  # Validation error
    
    def test_execute_code_missing_code(self, client):
        """Reject request with missing code."""
        request = {
            'language': 'python',
            'timeout': 30,
        }
        response = client.post('/api/code/execute', json=request)
        
        assert response.status_code == 422  # Validation error


class TestCodeExecutionLanguages:
    """Test execution of different programming languages."""
    
    @patch('backend.api.phase6_routes.DisposableSandbox')
    def test_execute_bash(self, mock_sandbox, client):
        """Execute Bash script."""
        mock_sandbox.create_sandbox.return_value = {
            'success': True,
            'sandbox_id': 'sandbox-bash',
            'sandbox_dir': '/tmp/sandbox-bash',
        }
        mock_sandbox.execute_in_sandbox.return_value = {
            'success': True,
            'stdout': 'Hello from Bash\n',
            'stderr': '',
        }
        mock_sandbox.destroy_sandbox.return_value = None
        
        request = {
            'code': 'echo "Hello from Bash"',
            'language': 'bash',
            'timeout': 30,
        }
        response = client.post('/api/code/execute', json=request)
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'Hello from Bash' in data['output']
    
    @patch('backend.api.phase6_routes.DisposableSandbox')
    def test_execute_typescript(self, mock_sandbox, client):
        """Execute TypeScript code."""
        mock_sandbox.create_sandbox.return_value = {
            'success': True,
            'sandbox_id': 'sandbox-ts',
            'sandbox_dir': '/tmp/sandbox-ts',
        }
        mock_sandbox.execute_in_sandbox.return_value = {
            'success': True,
            'stdout': 'Hello TypeScript\n',
            'stderr': '',
        }
        mock_sandbox.destroy_sandbox.return_value = None
        
        request = {
            'code': 'const msg: string = "Hello TypeScript"; console.log(msg);',
            'language': 'typescript',
            'timeout': 30,
        }
        response = client.post('/api/code/execute', json=request)
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
