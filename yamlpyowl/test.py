import unittest
import yamlpyowl as ypo

# noinspection PyUnresolvedReferences
from ipydex import IPS, activate_ips_on_exception


class TestCore(unittest.TestCase):

    def setUp(self):
        pass

    def test_pizza(self):
        onto = ypo.main("examples/pizza-ontology.yml")
        n = onto.n
        self.assertTrue(n.mypizza1.hasNumber == [10])
        self.assertTrue(n.mypizza2.hasNumber == [12.5, -3])
        self.assertTrue(n.mypizza2.hasStrAttribute == ['Tasty', 'Pizza!',
                                                       'Multi line\nstring\n\nattribute\n',
                                                       'Second multi line string attribute\n'])

        self.assertEqual(onto.onto.base_iri, "https://w3id.org/yet/undefined/simplified-pizza-ontology#")

        onto.sync_reasoner(infer_property_values=True, infer_data_property_values=True)

    def test_pizza_generic_individuals(self):
        """

        :return:
        """
        onto = ypo.main("examples/pizza-ontology.yml")
        n = onto.n

        # ensure that an individual `iMozarellaTopping` exists and that it is an instance of MozzarellaTopping
        # note that this individual is not explicitly created in the source file
        self.assertTrue(n.MozarellaTopping in n.iMozarellaTopping.is_instance_of)
        self.assertTrue("iTomatoTopping" in onto.name_mapping)

        # explicitly turned of with `_createGenericIndividual=False`
        self.assertFalse("iOnionTopping" in onto.name_mapping)

    def test_regional_rules(self):
        onto = ypo.main("examples/regional-rules-ontology.yml")
        n = onto.n

        self.assertFalse(n.dir_rule1 in n.dresden.hasDirective)
        self.assertFalse(n.dir_rule2 in n.dresden.hasDirective)

        # test special syntax with automatic creation of RelationConcept-roles and -individuals
        self.assertTrue(n.dir_rule2.X_hasDocumentReference_RC[0].hasDocument == n.law_book_of_saxony )
        self.assertTrue(n.dir_rule2.X_hasDocumentReference_RC[0].hasSection == "§ 1.5")

        # now run the reasoner (which applies transitive properties and swrl-rules)
        onto.sync_reasoner(infer_property_values=True, infer_data_property_values=True)

        self.assertTrue(n.dir_rule1 in n.dresden.hasDirective)
        self.assertTrue(n.dir_rule2 in n.dresden.hasDirective)
        self.assertTrue(n.dir_rule3 in n.dresden.hasDirective)

        self.assertTrue("dresden" in onto.name_mapping)
        self.assertTrue("Federal Republic of Germany" in repr(onto.n.germany))
