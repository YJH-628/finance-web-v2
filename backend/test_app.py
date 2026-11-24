"""运行：python -m unittest -v。所有写入均在临时数据库。"""
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import app


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db = app.DB_PATH
        self.original_key, self.original_client = app.DS_API_KEY, app.ds_client
        app.DB_PATH = str(Path(self.tmp.name) / "test.db")
        app.init_db()
        self.client = app.app.test_client()
        self.record = dict(date="2026-11-24", category="餐饮", type="支出", amount=25, description="测试")

    def tearDown(self):
        app.DB_PATH = self.original_db
        app.DS_API_KEY, app.ds_client = self.original_key, self.original_client
        self.tmp.cleanup()

    def test_crud_stats(self):
        self.assertEqual(self.client.post('/api/records', json=self.record).status_code, 200)
        self.assertIn('收入为零', app.build_financial_context())
        self.assertEqual(self.client.get('/api/stats').json['total_expense'], 25)
        record = self.client.get('/api/records').json[0]
        self.client.delete(f"/api/records/{record['id']}")
        self.assertEqual(self.client.get('/api/records').json, [])

    def test_invalid_records(self):
        for data in ([], {}, {**self.record, 'date': '2026-02-30'}, {**self.record, 'type': '错误'}, *({**self.record, 'amount': n} for n in ('Infinity', 'NaN', -1, 0, True, 1.234))):
            with self.subTest(data=data):
                self.assertEqual(self.client.post('/api/records', json=data).status_code, 400)
        self.assertEqual(self.client.get('/api/records').json, [])

    def test_csv_atomic_validation(self):
        def upload(text):
            return self.client.post('/api/import', data={'file': (io.BytesIO(text.encode()), 'test.csv')})
        self.assertEqual(upload('foo,bar\na,b\n').status_code, 400)
        self.assertEqual(upload('日期,分类,类型,金额\n2026-11-24,餐饮,支出,10\n2026-11-24,餐饮,支出,-1\n').status_code, 400)
        self.assertEqual(self.client.get('/api/records').json, [])
        self.assertEqual(upload('日期,分类,类型,金额,描述\n2026-11-24,工资,收入,100,测试\n').json['count'], 1)
        self.assertTrue(self.client.get('/api/export').data.startswith(b'\xef\xbb\xbf'))

    def test_categories_and_demo(self):
        self.assertEqual(self.client.post('/api/categories', json={'name': '测试', 'type': '收入', 'color': '#123456'}).status_code, 200)
        self.assertEqual(self.client.post('/api/categories', json={'name': 123}).status_code, 400)
        self.assertEqual(self.client.post('/api/records/seed').json['count'], 36)
        self.assertEqual(self.client.post('/api/records/random').json['count'], 30)
        self.client.post('/api/records/clear')
        self.assertEqual(self.client.get('/api/records').json, [])

    def test_ai_mock_and_validation(self):
        app.DS_API_KEY = ''
        self.assertEqual(self.client.post('/api/ai/advice').status_code, 503)
        app.DS_API_KEY = 'test-only'
        def create(**kwargs):
            if kwargs.get('stream'):
                return [NS(choices=[NS(delta=NS(content='测试回答'))])]
            return NS(choices=[NS(message=NS(content='测试报告'))])
        app.ds_client = NS(chat=NS(completions=NS(create=create)))
        self.assertEqual(self.client.post('/api/ai/advice').json['advice'], '测试报告')
        self.assertEqual(self.client.post('/api/ai/chat', json={'message': '测试', 'history': [{}]}).status_code, 400)
        result = self.client.post('/api/ai/chat', json={'message': '测试'}).data.decode()
        self.assertIn('测试回答', result)
        self.assertIn('[DONE]', result)


if __name__ == '__main__':
    unittest.main()