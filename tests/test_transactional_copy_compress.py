from app.tools.universal_filesystem import UniversalFilesystem
from app.cognition.execution_control import ExecutionControlRegistry

def receipt(tmp_path,action,result):
 r=ExecutionControlRegistry(tmp_path/'e.db');x=r.begin('p',action);return r.create_rollback_receipt(x.execution_id,action,{},result)
def test_verified_copy_and_hash_guarded_rollback(tmp_path):
 src=tmp_path/'a';dst=tmp_path/'b';src.write_text('exact')
 result=UniversalFilesystem.copy_file_verified(str(src),str(dst));assert result['success'] and result['source_sha256']==result['destination_sha256']
 rb=receipt(tmp_path,'copy_file_verified',result);assert rb.compensation_action=='remove_verified_copy'
 dst.write_text('owner changed')
 refused=UniversalFilesystem.remove_verified_copy(str(dst),result['destination_sha256']);assert refused['success'] is False and dst.exists()

def test_archive_requires_all_sources_and_verifies_contents(tmp_path):
 a=tmp_path/'a.txt';a.write_text('a');zip_path=tmp_path/'x.zip'
 missing=UniversalFilesystem.compress_zip([str(a),str(tmp_path/'missing')],str(zip_path));assert missing['success'] is False and not zip_path.exists()
 result=UniversalFilesystem.compress_zip([str(a)],str(zip_path));assert result['success'] and result['source_manifest'][0]['sha256']
 rb=receipt(tmp_path,'compress_files',result);assert rb.compensation_action=='remove_verified_copy'
 removed=UniversalFilesystem.remove_verified_copy(str(zip_path),result['archive_sha256']);assert removed['success'] and not zip_path.exists()
