from aihawk.academic_action_budget import ActionBudget
from aihawk.academic_portal_limits import PortalAccessHold
import pytest
def test_auth_once_per_window_and_restart(tmp_path):
 now=[10000.]
 db=tmp_path/'actions.db'
 a=ActionBudget(db,clock=lambda:now[0])
 a.reserve('portal.example.edu','auth_request')
 b=ActionBudget(db,clock=lambda:now[0])
 with pytest.raises(PortalAccessHold): b.reserve('portal.example.edu','auth_request')
 b.reserve('other.example.edu','auth_request')
 now[0]+=1800
 b.reserve('portal.example.edu','auth_request')
def test_hold_prevents_reservation(tmp_path):
 a=ActionBudget(tmp_path/'actions.db',clock=lambda:10000.)
 a.limits.record('portal.example.edu',429,'3600')
 with pytest.raises(PortalAccessHold):a.reserve('portal.example.edu','portal_entry')
def test_subdomains_share_budget(tmp_path):
 a=ActionBudget(tmp_path/'actions.db',clock=lambda:10000.)
 a.reserve_url('https://one.example.edu/apply','auth_request',('example.edu',))
 with pytest.raises(PortalAccessHold):
  a.reserve_url('https://two.example.edu/apply','auth_request',('example.edu',))
def test_portal_entry_cap(tmp_path):
 a=ActionBudget(tmp_path/'actions.db',clock=lambda:10000.)
 for i in range(3):a.reserve('example.edu','portal_entry')
 with pytest.raises(PortalAccessHold):a.reserve('example.edu','portal_entry')
