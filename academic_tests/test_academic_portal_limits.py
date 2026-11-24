import pytest
from aihawk.academic_portal_limits import PortalLimits,PortalAccessHold,attach_limits
from aihawk.academic_auth_gate import detect_auth_challenge
from email.utils import formatdate
def test_429_shared_across_runs(tmp_path):
 clock=[10000.]
 db=tmp_path/'limit.db'
 a=PortalLimits(db,clock=lambda:clock[0])
 a.record('example.edu',429,'7200')
 b=PortalLimits(db,clock=lambda:clock[0])
 with pytest.raises(PortalAccessHold):b.check(('example.edu',))
 with pytest.raises(PortalAccessHold):b.clear_reviewed('example.edu',confirmed=True)
 b.check(('other.edu',))
 clock[0]+=7201
 b.check(('example.edu',))
def test_403_indefinite(tmp_path):
 a=PortalLimits(tmp_path/'limit.db',clock=lambda:10000.)
 a.record('example.edu',403)
 a.record('example.edu',429,'100')
 with pytest.raises(PortalAccessHold):a.check(('example.edu',))
 with pytest.raises(PermissionError):a.clear_reviewed('example.edu')
 a.clear_reviewed('example.edu',confirmed=True)
 a.check(('example.edu',))
def test_503_http_date_and_no_shortening(tmp_path):
 now=[1700000000.]
 a=PortalLimits(tmp_path/'limit.db',clock=lambda:now[0])
 a.record('example.edu',503,formatdate(now[0]+1800,usegmt=True))
 a.record('example.edu',503,'5')
 now[0]+=1000
 with pytest.raises(PortalAccessHold):a.check(('example.edu',))
 now[0]+=801
 a.check(('example.edu',))
def test_context_blocks_after_response(tmp_path):
 from types import SimpleNamespace
 class Context:
  def on(self,event,fn):self.cb=fn
  def route(self,pattern,fn):self.guard=fn
 class Route:
  def __init__(self,url):self.request=SimpleNamespace(url=url);self.result=None
  def abort(self):self.result='abort'
  def fallback(self):self.result='continue'
 c=Context()
 a=PortalLimits(tmp_path/'limit.db',clock=lambda:10000.)
 attach_limits(c,('example.edu',),a)
 r=Route('https://example.edu/form');c.guard(r);assert r.result=='continue'
 c.cb(SimpleNamespace(url='https://other.edu/image',status=429,headers={}))
 r=Route('https://example.edu/form');c.guard(r);assert r.result=='continue'
 c.cb(SimpleNamespace(url='https://example.edu/form',status=429,headers={'retry-after':'3600'}))
 r=Route('https://example.edu/form');c.guard(r);assert r.result=='abort'
 with pytest.raises(PortalAccessHold):attach_limits(Context(),('example.edu',),a)
def test_oracle_split_pin_auth_recognition():
 class Page:
  url='https://example.edu/apply/email'
  def evaluate(self,script):
   return {'fields':[{'name':'','id':f'pin-code-{i}','type':'text','autocomplete':''} for i in range(1,7)],'captcha':False,'buttons':['verify']}
 assert detect_auth_challenge(Page(),official_hosts=('example.edu',)).kind=='verification_code'
