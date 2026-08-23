import json,zipfile
from app.tools.backup_manager import BackupManager
from app.cognition.execution_control import ExecutionControlRegistry

def setup(tmp_path,monkeypatch):
 monkeypatch.setattr(BackupManager,'BACKUP_DIR',tmp_path/'backups');monkeypatch.setattr(BackupManager,'INDEX_PATH',tmp_path/'backups'/'index.json')
def test_create_backup_rollback_deletes_created_artifact(tmp_path,monkeypatch):
 setup(tmp_path,monkeypatch);src=tmp_path/'a';src.write_text('x');result=BackupManager.create_backup([str(src)])
 reg=ExecutionControlRegistry(tmp_path/'e.db');r=reg.begin('p','create_backup');receipt=reg.create_rollback_receipt(r.execution_id,'create_backup',{},result)
 assert receipt.compensation_action=='delete_backup' and receipt.compensation_payload=={'backup_id':result['backup_id']}

def test_restore_rejects_zip_slip(tmp_path,monkeypatch):
 setup(tmp_path,monkeypatch);BackupManager.ensure_dir();path=BackupManager.BACKUP_DIR/'bad.zip'
 with zipfile.ZipFile(path,'w') as z:z.writestr('../escape.txt','bad')
 bid='bad';BackupManager.INDEX_PATH.write_text(json.dumps({bid:{'id':bid,'path':str(path),'sha256':BackupManager._sha256(path),'file_count':1}}))
 result=BackupManager.restore_backup(bid,str(tmp_path/'dest'))
 assert result['success'] is False and 'Unsafe archive path' in result['error']
 assert not (tmp_path/'escape.txt').exists()
