import os
import unittest
from unittest.mock import patch
import cloud


class CloudBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'LAB_PUBLIC_ORIGIN':'https://lab.example', 'LAB_ALLOWED_USERS':'owner'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = cloud.app.test_client()
        self.headers = {'Host':'lab.example','X-MS-CLIENT-PRINCIPAL-ID':'owner','X-MS-CLIENT-PRINCIPAL-IDP':'aad'}

    def test_fail_closed_and_health_probe(self):
        self.assertEqual(self.client.get('/').status_code,403)
        self.assertEqual(self.client.get('/app.js').status_code,403)
        self.assertEqual(self.client.get('/healthz').status_code,200)
        with patch.dict(os.environ, {'LAB_ALLOWED_USERS':''}):
            self.assertEqual(self.client.get('/',headers=self.headers).status_code,503)

    def test_assets_require_authorization(self):
        for path in ('/app.js','/style.css','/portal.css','/slides','/slides.html','/slides.css','/slides.js'):
            self.assertEqual(self.client.get(path).status_code,403)
            with self.client.get(path,headers=self.headers) as response:
                self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/private.txt',headers=self.headers).status_code,404)

    def test_allowlisted_user_only_and_revocation(self):
        with self.client.get('/',headers=self.headers) as response:
            self.assertEqual(response.status_code,200)
        with patch.dict(os.environ, {'LAB_ALLOWED_USERS':'someone-else'}):
            self.assertEqual(self.client.get('/',headers=self.headers).status_code,403)
        headers = {**self.headers,'X-MS-CLIENT-PRINCIPAL-IDP':'other'}
        self.assertEqual(self.client.get('/',headers=headers).status_code,403)

    def test_post_origin_and_private_paths(self):
        payload={'runtime':'python','target':'aoai','scenario':'burst'}
        self.assertEqual(self.client.post('/api/run',json=payload,headers=self.headers).status_code,403)
        self.assertEqual(self.client.get('/python/config.local.json',headers=self.headers).status_code,404)
        self.assertEqual(self.client.get('/',headers={**self.headers,'Host':'evil.example'}).status_code,403)

    def test_simulation_is_bounded_and_serialized(self):
        headers={**self.headers,'Origin':'https://lab.example'}
        payload={'runtime':'python','target':'aoai','scenario':'burst'}
        with patch.object(cloud.subprocess,'run') as execute, patch.object(cloud.server,'runs',return_value={'runs':[], 'dotnet':True}):
            execute.return_value.returncode=0
            self.assertEqual(self.client.post('/api/run',json=payload,headers=headers).status_code,200)
            self.assertNotIn('--live',execute.call_args.args[0])
            self.assertEqual(execute.call_args.kwargs['timeout'],180)
            cloud.server.LOCK.acquire()
            try:
                self.assertEqual(self.client.post('/api/run',json=payload,headers=headers).status_code,409)
            finally:
                cloud.server.LOCK.release()
