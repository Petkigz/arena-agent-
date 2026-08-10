# Backwards compatible DocumentReader interface pointing to DocumentManager
from app.tools.doc_manager import DocumentManager

class DocumentReader:
    @classmethod
    def read_document(cls, file_path_str: str):
        return DocumentManager.read_document(file_path_str)

    @classmethod
    def list_approved_documents(cls):
        return DocumentManager.list_workspace_files()
