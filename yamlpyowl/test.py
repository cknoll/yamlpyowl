import unittest
import yamlpyowl as ypo
import yamlpyowl.new_core as ypo2
import typing
import pydantic

# noinspection PyUnresolvedReferences
from ipydex import IPS, activate_ips_on_exception


# noinspection PyPep8Naming
class TestCore(unittest.TestCase):

    def setUp(self):
        # prevent that the tests do influence each other -> create a new world each time
        self.world = ypo.owl2.World()

    # mark tests which only work for the "old core"
    @unittest.expectedFailure
    def test_pizza(self):
        onto = ypo2.OntologyManager("examples/pizza-ontology.yml", self.world)
        n = onto.n
        self.assertTrue(n.mypizza1.hasNumber == [10])
        self.assertTrue(n.mypizza2.hasNumber == [12.5, -3])
        self.assertTrue(n.mypizza2.hasStrAttribute == ['Tasty', 'Pizza!',
                                                       'Multi line\nstring\n\nattribute\n',
                                                       'Second multi line string attribute\n'])

        self.assertEqual(onto.onto.base_iri, "https://w3id.org/yet/undefined/simplified-pizza-ontology#")

        onto.sync_reasoner(infer_property_values=True, infer_data_property_values=True)

    @unittest.expectedFailure
    def test_pizza_generic_individuals(self):
        """

        :return:
        """
        onto = ypo2.OntologyManager("examples/pizza-ontology.yml", self.world)
        n = onto.n

        # ensure that an individual `iMozarellaTopping` exists and that it is an instance of MozzarellaTopping
        # note that this individual is not explicitly created in the source file
        self.assertTrue(n.MozarellaTopping in n.iMozarellaTopping.is_instance_of)
        self.assertTrue("iTomatoTopping" in onto.name_mapping)

        # explicitly turned of with `_createGenericIndividual=False`
        self.assertFalse("iOnionTopping" in onto.name_mapping)

    @unittest.expectedFailure
    def test_regional_rules(self):
        onto = ypo2.OntologyManager("examples/regional-rules-ontology.yml", self.world)
        n = onto.n

        self.assertFalse(n.dir_rule1 in n.dresden.hasDirective)
        self.assertFalse(n.dir_rule2 in n.dresden.hasDirective)

        # test special syntax with automatic creation of RelationConcept-roles and -individuals
        self.assertTrue(n.dir_rule2.X_hasDocumentReference_RC[0].hasDocument == n.law_book_of_saxony )
        self.assertTrue(n.dir_rule2.X_hasDocumentReference_RC[0].hasSection == "§ 1.5")

        # test Or-Syntax:
        self.assertEqual(n.X_hasTesting_RC.domain, [n.Directive | n.Facility])

        # now run the reasoner (which applies transitive properties and swrl-rules)
        onto.sync_reasoner(infer_property_values=True, infer_data_property_values=True)

        self.assertTrue(n.dir_rule1 in n.dresden.hasDirective)
        self.assertTrue(n.dir_rule2 in n.dresden.hasDirective)
        self.assertTrue(n.dir_rule3 in n.dresden.hasDirective)

        self.assertTrue("dresden" in onto.name_mapping)
        self.assertTrue("Federal Republic of Germany" in repr(onto.n.germany))

        self.assertEquals(set(n.dir_rule3.affects), {n.dresden, n.passau, n.regensburg})
        self.assertFalse(n.leipzig in n.dir_rule3.affects)

        # test basic stipulation:

        self.assertTrue(n.dir_rule2 in n.munich.hasDirective)
        self.assertTrue(n.dir_rule3 in n.munich.hasDirective)

        # test RC stipulation:

        tmp = [x.hasTarget for x in n.munich.X_hasInterRegionRelation_RC]
        self.assertTrue(tmp == [n.dresden, n.passau, n.regensburg, n.leipzig])
        self.assertTrue(n.munich.X_hasInterRegionRelation_RC[0].hasValue == 0.5)

    @unittest.expectedFailure
    def test_regional_rules_query(self):
        # this largely is oriented on calls to query_owlready() in
        # https://bitbucket.org/jibalamy/owlready2/src/master/test/regtest.py
        onto = ypo2.OntologyManager("examples/regional-rules-ontology.yml", self.world)

        q_hasSection1 = f"""
        PREFIX P: <{onto.iri}>
        SELECT ?x WHERE {{
        ?x P:hasSection "§ 1.1".
        }}
        """
        r = onto.make_query(q_hasSection1)
        self.assertEquals(r, {onto.n.iX_DocumentReference_RC_0})

        q_hasPart1 = f"""
        PREFIX P: <{onto.iri}>
        SELECT ?x WHERE {{
        ?x P:hasPart P:dresden.
        }}
        """
        r = onto.make_query(q_hasPart1)
        self.assertEquals(r, {onto.n.saxony})

        onto.sync_reasoner(infer_property_values=True, infer_data_property_values=True)
        r = onto.make_query(q_hasPart1)
        self.assertEquals(r, {onto.n.saxony, onto.n.germany})

    def test_check_type(self):

        obj1 = [3, 4, 5]
        obj2 = [3, 4, "5"]

        # pass silently
        ypo.check_type(obj1, typing.List[pydantic.StrictInt])

        with self.assertRaises(TypeError) as cm:
            ypo.check_type(obj2, typing.List[pydantic.StrictInt])

        obj3 = {
                "key 1": 1.0,
                "key 2": 2.0,
                "key 3": 3.0
                }

        ypo.check_type(obj3, typing.Dict[str, pydantic.StrictFloat])

        obj3["key 3"] = "3.0"
        obj3["key 4"] = 5

        with self.assertRaises(TypeError) as cm:
            ypo.check_type(obj3, typing.Dict[str, pydantic.StrictFloat])

        # allow for multiple types:

        ypo.check_type(obj3, typing.Dict[str, typing.Union[pydantic.StrictInt, pydantic.StrictFloat, str]])

    def test_zebra_puzzle(self):
        fpath = "examples/einsteins_zebra_riddle.owl.yaml"
        om = ypo2.OntologyManager(fpath, self.world)
        owl2 = ypo2.owl2

        self.assertEqual(om.iri, 'https://w3id.org/yet/undefined/einstein-zebra-puzzle-ontology#')

        n = om.n
        # remember: dog is created as a `Thing` (not a pet before the reasoner is called)
        self.assertNotIn(n.Pet, n.dog.is_a)
        self.assertTrue(n.house_2.right_to, n.house_1)
        self.assertTrue(n.house_1.right_to, ypo2.owl2.Nothing)
        self.assertTrue(n.house_5.left_to, ypo2.owl2.Nothing)
        self.assertTrue(n.right_to.is_functional_for(n.House))
        self.assertTrue(n.left_to.is_functional_for(n.House))

        if 0:
            om.sync_reasoner()
            # after the reasoner finished these assertions hold true
            self.assertIn(n.Pet, n.dog.is_a)
            self.assertIn(n.Pet, n.fox.is_a)
            self.assertTrue(n.house_2.left_to, n.house_3)

        # test some random restrictions
        om.add_restriction_to_individual(n.lives_in.value(n.house_1), n.Spaniard)
        om.add_restriction_to_individual(n.lives_in.some(owl2.OneOf([n.house_1, n.house_2])), n.Japanese)

        # owl2.AllDifferent([n.Spaniard, n.Japanese, n.house_1, n.house_2])

        all_indis = list(om.onto.individuals())

        IPS()
        return
        owl2.AllDifferent(all_indis[:15])
        om.sync_reasoner(infer_property_values=True)
        self.assertEquals(n.Japanese.lives_in, n.house_2)

        # start the interactive shell to explore the objects in the namespace
        IPS()


