import unittest

class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self.env = AttrDict({
            'host': 'localhost',
            'dbname': 'test',
            'user': 'test',
            'password': 'test',
            'protocol': 'xml-rpc',
            'port': 8069,
        })
