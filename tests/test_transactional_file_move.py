from app.tools.universal_filesystem import UniversalFilesystem
from app.cognition.execution_control import ExecutionControlRegistry

def test_move_verifies_hash_and_produces_reversible_facts(tmp_path):
 src=tmp_path/'a.txt';dst=tmp_path/'sub'/'b.txt';src.write_text('exact')
 r=UniversalFilesystem.rename_or_move(str(src),str(dst))
 assert r['success'] is True and r['environment_verified'] is True
 assert r['source_sha256']==r['destination_sha256']
 reg=ExecutionControlRegistry(tmp_path/'e.db');rec=reg.begin('p','move_file')
 receipt=reg.create_rollback_receipt(rec.execution_id,'move_file',{},r)
 assert receipt.supported is True and receipt.compensation_action=='move_file'
 assert receipt.compensation_payload=={'source_path':str(dst),'destination_path':str(src)}

def test_move_refuses_overwrite(tmp_path):
 src=tmp_path/'a';dst=tmp_path/'b';src.write_text('a');dst.write_text('b')
 r=UniversalFilesystem.rename_or_move(str(src),str(dst))
 assert r['success'] is False
 assert src.read_text()=='a' and dst.read_text()=='b'
