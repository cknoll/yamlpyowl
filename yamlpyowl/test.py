import unittest
import yamlpyowl as ypo

# noinspection PyUnresolvedReferences
from ipydex import IPS, activate_ips_on_exception


class TestCore(unittest.TestCase):

    def setUp(self):
        pass

    def test_pizza(self):
        onto = ypo.main("examples/pizza-ontology.yml")

    def test_regional_rules(self):
        onto = ypo.main("examples/regional-rules-ontology.yml")
        n = onto.n

        self.assertFalse(n.dir_rule1 in n.d_dresden.hasDirective)
        self.assertFalse(n.dir_rule2 in n.d_dresden.hasDirective)

        # now run the reasoner (which applies transitive properties and swrl-rules)
        onto.sync_reasoner(infer_property_values=True, infer_data_property_values=True)

        self.assertTrue(n.dir_rule1 in n.d_dresden.hasDirective)
        self.assertTrue(n.dir_rule2 in n.d_dresden.hasDirective)
        self.assertTrue(n.dir_rule3 in n.d_dresden.hasDirective)
