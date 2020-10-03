import unittest

import yamlpyowl as ypo


class TestCore(unittest.TestCase):

    def setUp(self):
        pass

    def test_func(self):
        ypo.main("examples/pizza-ontology.yml")
