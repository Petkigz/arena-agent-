import subprocess
from unittest.mock import patch
from app.tools.deep_os_controller import DeepOSController

def test_update_command_success_separate_from_version_verification():
 command=subprocess.CompletedProcess(['apt'],0,'ok','')
 with patch('app.policy.PolicyEvaluator.evaluate_action',return_value=(True,'owner authorized',3)),patch.object(DeepOSController,'_installed_version',side_effect=['1.0','2.0']),patch('app.tools.deep_os_controller.run_cancellable_subprocess',return_value=command):
  r=DeepOSController.check_and_update_software('vlc')
 assert r['success'] is True and r['environment_verified'] is True
 assert r['before_version']=='1.0' and r['after_version']=='2.0'

def test_expected_version_mismatch_stays_unknown():
 command=subprocess.CompletedProcess(['apt'],0,'ok','')
 with patch('app.policy.PolicyEvaluator.evaluate_action',return_value=(True,'owner authorized',3)),patch.object(DeepOSController,'_installed_version',side_effect=['1.0','1.5']),patch('app.tools.deep_os_controller.run_cancellable_subprocess',return_value=command):
  r=DeepOSController.check_and_update_software('vlc',expected_version='2.0')
 assert r['success'] is True
 assert r['environment_verified'] is False and r['verification_unknown'] is True
