import errno
import io
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote
from unittest.mock import patch

import app as module
import files_service as service


class ExplorerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.explorer = service.Explorer(self.root, max_upload=32768)

    def tearDown(self):
        self.temp.cleanup()

    def target(self, path='/'):
        return self.explorer.list(path)['folder_id']

    def test_sorted_listing_hidden_and_pagination(self):
        (self.root/'zeta').write_text('z')
        (self.root/'alpha').write_text('a')
        (self.root/'.hidden').write_text('h')
        (self.root/'folder').mkdir()
        first=self.explorer.list('/',limit=2)
        self.assertEqual([entry['name'] for entry in first['entries']],['folder','alpha'])
        self.assertEqual(first['next_offset'],2)
        self.assertEqual(self.explorer.list('/',offset=2,limit=2)['entries'][0]['name'],'zeta')
        self.assertEqual(self.explorer.list('/',hidden=True)['total'],4)
        self.assertEqual(self.explorer.list('/',offset=100,limit=2)['offset'],2)

    def test_upload_bytes_permissions_zero_and_unicode(self):
        for name, content in [('hello.txt',b'hello'),('empty',b''),('résumé.txt',b'utf-8')]:
            result=self.explorer.upload('/',name,self.target(),io.BytesIO(content),length=len(content))
            self.assertEqual(result['size'],len(content))
            self.assertEqual((self.root/name).read_bytes(),content)
            self.assertEqual((self.root/name).stat().st_mode & 0o777,0o600)
        self.assertFalse(any(p.name.startswith(service.TEMP_PREFIX) for p in self.root.iterdir()))

    def test_existing_file_and_symlink_are_never_overwritten(self):
        (self.root/'original').write_bytes(b'original')
        (self.root/'link').symlink_to(self.root/'original')
        for name in ['original','link']:
            with self.assertRaises(FileExistsError):
                self.explorer.upload('/',name,self.target(),io.BytesIO(b'replacement'))
        self.assertEqual((self.root/'original').read_bytes(),b'original')
        self.assertTrue((self.root/'link').is_symlink())
        self.assertEqual(len(list(self.root.iterdir())),2)

    def test_traversal_and_bad_names_rejected(self):
        for path in ['/../outside','/folder/../outside','/.','/bad\\name']:
            with self.assertRaises(service.FileError):self.explorer.list(path)
        for name in ['../escape','/escape','a/b','a\\b','', '..','a\x00b','a\nb',service.TEMP_PREFIX+'evil']:
            with self.assertRaises(service.FileError):
                self.explorer.upload('/',name,self.target(),io.BytesIO(b'data'))
        self.assertEqual(list(self.root.iterdir()),[])

    def test_symlink_folder_cannot_escape_root(self):
        (self.root/'escape').symlink_to(self.root.parent,target_is_directory=True)
        with self.assertRaises(OSError):self.explorer.list('/escape')
        with self.assertRaises(OSError):self.explorer.upload('/escape','file','anything',io.BytesIO(b'no'))
        self.assertEqual(self.explorer.list('/')['entries'][0]['type'],'link')

    def test_changed_destination_rejected(self):
        (self.root/'folder').mkdir()
        token=self.target('/folder')
        (self.root/'folder').rename(self.root/'old')
        (self.root/'folder').mkdir()
        with self.assertRaises(service.FileError) as error:
            self.explorer.upload('/folder','new',token,io.BytesIO(b'no'))
        self.assertEqual(error.exception.status,409)
        self.assertFalse((self.root/'folder/new').exists())

    def test_stream_limit_failure_and_session_revocation_cleanup(self):
        class Interrupted(io.BytesIO):
            def read(self,size=-1):
                if self.tell():raise OSError(errno.EIO,'fixture disconnect')
                return super().read(2)
        cases=[(io.BytesIO(b'x'*32769),lambda:True,413),
               (Interrupted(b'data'),lambda:True,None),
               (io.BytesIO(b'data'),lambda:False,401)]
        for stream,auth,status in cases:
            with self.assertRaises((service.FileError,OSError)) as error:
                self.explorer.upload('/','partial',self.target(),stream,auth)
            if status:self.assertEqual(error.exception.status,status)
            self.assertEqual(list(self.root.iterdir()),[])
        auth=iter([True,True,False])
        with self.assertRaises(service.FileError):
            self.explorer.upload('/','late-revoked',self.target(),io.BytesIO(b'data'),lambda:next(auth))
        self.assertEqual(list(self.root.iterdir()),[])

    def test_late_sync_failure_reports_uncertainty_without_retry(self):
        token=self.target()
        with patch.object(service.os,'fsync',side_effect=[None,OSError(errno.EIO,'fixture sync failure')]):
            with self.assertRaises(service.FileError) as error:
                self.explorer.upload('/','committed',token,io.BytesIO(b'complete'))
        self.assertEqual(error.exception.status,503)
        self.assertIn('may already be present',str(error.exception))
        self.assertEqual((self.root/'committed').read_bytes(),b'complete')

    def test_incomplete_length_does_not_publish(self):
        with self.assertRaises(service.FileError):
            self.explorer.upload('/','incomplete',self.target(),io.BytesIO(b'short'),length=100)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_download_regular_only_and_no_symlink(self):
        (self.root/'document').write_bytes(b'document')
        (self.root/'link').symlink_to(self.root/'document')
        os.mkfifo(self.root/'pipe')
        stream,name,size=self.explorer.download('/document')
        with stream:self.assertEqual(stream.read(),b'document')
        self.assertEqual((name,size),('document',8))
        with self.assertRaises(OSError):self.explorer.download('/link')
        with self.assertRaises(service.FileError):self.explorer.download('/pipe')

    def test_mkdir_requires_folder_identity(self):
        self.explorer.mkdir('/','created',self.target())
        self.assertTrue((self.root/'created').is_dir())
        with self.assertRaises(service.FileError):self.explorer.mkdir('/','other','wrong')

    def test_temporary_files_not_visible_or_addressable(self):
        (self.root/(service.TEMP_PREFIX+'partial')).write_text('private partial')
        self.assertEqual(self.explorer.list('/',hidden=True)['entries'],[])
        with self.assertRaises(service.FileError):self.explorer.download('/'+service.TEMP_PREFIX+'partial')

    def test_listing_cap_and_atomic_link_fallback(self):
        for name in ['a','b','c']:(self.root/name).write_text(name)
        with patch.object(service,'MAX_ENTRIES',2):
            report=self.explorer.list('/')
            self.assertTrue(report['truncated'])
            self.assertEqual(report['total'],2)
        # A libc without renameat2 uses a same-directory non-overwriting hard link.
        with patch.object(service.ctypes,'CDLL',return_value=object()):
            self.explorer.upload('/','fallback',self.target(),io.BytesIO(b'complete'))
        self.assertEqual((self.root/'fallback').read_bytes(),b'complete')


class FilesAPITest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.config=patch.dict(module.app.config,TESTING=True,SECRET_KEY='files-test-only',FILES_ROOT=str(self.root),UPLOAD_MAX_BYTES=32768)
        self.config.start();module.attempts.clear();self.client=module.app.test_client()

    def tearDown(self):
        self.config.stop();self.temp.cleanup()

    def signin(self):
        self.client.get('/login')
        with self.client.session_transaction() as session:token=session['csrf']
        with patch.object(module,'authenticate',return_value=True):
            self.client.post('/login',data=dict(csrf=token,username=module.allowed_user,password='fixture'))
        with self.client.session_transaction() as session:return session['csrf']

    def headers(self,csrf,name='uploaded.txt',path='/',folder_id=None):
        return {'X-CSRF-Token':csrf,'X-Folder-Path':quote(path,safe=''),'X-File-Name':quote(name,safe=''),
                'X-Folder-Id':folder_id or self.client.get('/api/files?path=/').get_json()['folder_id']}

    def test_anonymous_and_csrf_no_write(self):
        self.assertEqual(self.client.get('/files').status_code,302)
        self.assertEqual(self.client.get('/api/files').status_code,401)
        self.assertEqual(self.client.get('/api/files/download?path=/any').status_code,401)
        self.signin()
        self.assertEqual(self.client.post('/api/files/upload',data=b'data',content_type='application/octet-stream').status_code,403)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_large_upload_exceeds_old_limit_but_new_limit_passes(self):
        token=self.signin();payload=b'x'*16384
        response=self.client.post('/api/files/upload',data=payload,content_type='application/octet-stream',headers=self.headers(token))
        self.assertEqual(response.status_code,201,response.get_json())
        self.assertEqual((self.root/'uploaded.txt').read_bytes(),payload)
        self.assertEqual(self.client.post('/login',data=b'x'*9000,content_type='application/x-www-form-urlencoded').status_code,413)

    def test_upload_limit_wrong_type_bad_name_and_busy(self):
        token=self.signin();headers=self.headers(token)
        self.assertEqual(self.client.post('/api/files/upload',data=b'x'*32769,content_type='application/octet-stream',headers=headers).status_code,413)
        self.assertEqual(self.client.post('/api/files/upload',data=b'data',content_type='text/plain',headers=headers).status_code,415)
        self.assertEqual(self.client.post('/api/files/upload',data=b'data',content_type='application/octet-stream',headers=self.headers(token,name='../escape')).status_code,400)
        module.upload_slots.acquire();module.upload_slots.acquire()
        try:self.assertEqual(self.client.post('/api/files/upload',data=b'data',content_type='application/octet-stream',headers=headers).status_code,429)
        finally:module.upload_slots.release();module.upload_slots.release()
        self.assertEqual(list(self.root.iterdir()),[])

    def test_download_attachment_and_duplicate_upload(self):
        token=self.signin();headers=self.headers(token,name='résumé.html')
        for expected in [201,409]:
            response=self.client.post('/api/files/upload',data=b'<script>fixture</script>',content_type='application/octet-stream',headers=headers)
            self.assertEqual(response.status_code,expected)
        with self.client.get('/api/files/download?path='+quote('/résumé.html',safe='')) as response:
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.headers['Content-Disposition'].startswith('attachment;'))
            self.assertEqual(response.mimetype,'application/octet-stream')
            self.assertEqual(response.data,b'<script>fixture</script>')

    def test_create_folder_listing_and_numberless_navigation(self):
        csrf=self.signin()
        folder_id=self.client.get('/api/files').get_json()['folder_id']
        response=self.client.post('/api/files/folders',data=dict(csrf=csrf,path='/',name='New folder',folder_id=folder_id))
        self.assertEqual(response.status_code,201)
        self.assertEqual(self.client.get('/api/files').get_json()['entries'][0]['name'],'New folder')
        html=self.client.get('/files').data
        self.assertIn(b'Files',html)
        for number in [b'<span>01</span>',b'<span>02</span>',b'<span>03</span>',b'<span>04</span>']:self.assertNotIn(number,html)

    def test_error_format_and_permission_denied(self):
        self.signin()
        self.assertEqual(self.client.get('/api/files?path=/../escape').status_code,400)
        self.assertEqual(self.client.get('/api/files?offset=bad').status_code,400)
        self.assertEqual(self.client.get('/api/files?path=/missing').status_code,404)
        with patch.object(service.Explorer,'list',side_effect=PermissionError(errno.EACCES,'fixture')):
            response=self.client.get('/api/files')
        self.assertEqual(response.status_code,403)
        self.assertIn('error',response.get_json())

    def test_root_process_refused(self):
        self.signin()
        with patch.object(module.os,'getuid',return_value=0):
            self.assertEqual(self.client.get('/api/files').status_code,403)


if __name__=='__main__':unittest.main()
