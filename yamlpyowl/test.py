import unittest

import yamlpyowl as ypo


class TestCore(unittest.TestCase):

    def setUp(self):
        pass

    def test_pizza(self):
        onto = ypo.main("examples/pizza-ontology.yml")

    def test_regional_rules(self):
        onto = ypo.main("examples/regional-rules-ontology.yml")
