import os
import sys
import unittest
import yamlpyowl as ypo
import typing
import pydantic

# noinspection PyUnresolvedReferences
from ipydex import IPS, activate_ips_on_exception

BASEPATH = os.path.dirname(os.path.dirname(os.path.abspath(sys.modules.get(__name__).__file__)))


# noinspection PyPep8Naming
class TestCore(unittest.TestCase):
    def setUp(self):
        # prevent that the tests do influence each other -> create a new world each time
        self.world = ypo.owl2.World()

    # mark tests which only work for the "old core"
    def test_pizza(self):
        onto = ypo.OntologyManager("examples/pizza.owl.yml", self.world)
        n = onto.n
        self.assertEqual(n.mypizza1.hasNumericalValues, [10])
        self.assertEqual(n.mypizza2.hasNumericalValues, [12.5, -3])
        self.assertEqual(n.mypizza1.hasBase, n.iThinAndCrispyBase)
        self.assertEqual(
            n.mypizza2.hasStrAttribute,
            ["Tasty", "Pizza!", "Multi line\nstring\n\nattribute\n", "Second multi line string attribute\n"]
        )

        self.assertEqual(onto.onto.base_iri, "https://w3id.org/yet/undefined/simplified-pizza-ontology#")

        self.assertEqual(n.iMozzarellaTopping.X_hasCombinedTasteValue_RC[1].hasFunctionValue, 0.5)

        onto.sync_reasoner(infer_property_values=True, infer_data_property_values=True)

    def test_pizza_generic_individuals(self):
        """

        :return:
        """
        onto = ypo.OntologyManager("examples/pizza.owl.yml", self.world)
        n = onto.n

        # ensure that an individual `iMozzarellaTopping` exists and that it is an instance of MozzarellaTopping
        # note that this individual is not explicitly created in the source file
        self.assertTrue(n.MozzarellaTopping in n.iMozzarellaTopping.is_instance_of)
        self.assertTrue("iTomatoTopping" in onto.name_mapping)

        # explicitly turned of with `_createGenericIndividual=False`
        self.assertFalse("iOnionTopping" in onto.name_mapping)

    def test_regional_rules(self):
        onto = ypo.OntologyManager("examples/regional-rules.owl.yml", self.world)
        n = onto.n

        self.assertTrue(n.leipzig in n.saxony.hasPart)
        self.assertTrue("dresden" in onto.name_mapping)

        # test if labels work as expected
        # !! not yet implemented
        # self.assertTrue("Federal Republic of Germany" in repr(onto.n.germany))

        # test proper handling of multiple subclasses
        self.assertTrue(issubclass(n.TrainStation, n.Facility))
        self.assertTrue(issubclass(n.TrainStation, n.LocationType))
        self.assertFalse(issubclass(n.TrainStation, n.FederalState))

        # test proper handling of the RelationConcept magic mechanism
        self.assertEqual(n.dir_rule1.X_hasDocumentReference_RC[0].hasSection, "§ 1.1")
        self.assertTrue(n.dir_rule2.X_hasDocumentReference_RC[0].hasSourceDocument == n.law_book_of_saxony)
        self.assertTrue(n.dir_rule2.X_hasDocumentReference_RC[0].hasSection == "§ 1.5")

        self.assertEqual(n.munich.X_hasInterRegionRelation_RC[0].hasIRRTarget, n.dresden)
        self.assertEqual(n.munich.X_hasInterRegionRelation_RC[0].hasIRRValue, 0.5)
        self.assertEqual(n.munich.X_hasInterRegionRelation_RC[2].hasIRRTarget, n.regensburg)
        self.assertEqual(n.munich.X_hasInterRegionRelation_RC[2].hasIRRValue, 0.7)

        # test Or-Syntax:
        self.assertEqual(n.X_hasTesting_RC.domain, [n.Directive | n.Facility])

        self.assertEqual(len(n.dresden.hasDirective), 0)

        self.assertTrue(n.dir_rule0 in n.germany.hasDirective)
        self.assertFalse(n.dir_rule0 in n.saxony.hasDirective)
        self.assertFalse(n.dir_rule0 in n.leipzig.hasDirective)

        # run the reasoner (which applies transitive properties and swrl-rules)
        onto.sync_reasoner(infer_property_values=True, infer_data_property_values=True)
        self.assertTrue(n.leipzig in n.germany.hasPart)

        # after the reasoner has run, the rules should be applied (due to swrl-rules)
        # rule: top_down
        self.assertTrue(n.dir_rule0 in n.saxony.hasDirective)
        self.assertTrue(n.dir_rule0 in n.leipzig.hasDirective)

        self.assertTrue(n.dir_rule0 in n.dresden.hasDirective)
        self.assertTrue(n.dir_rule2 in n.dresden.hasDirective)
        self.assertTrue(n.dir_rule3 in n.dresden.hasDirective)
        self.assertTrue(n.dir_rule2 in n.munich.hasDirective)
        self.assertTrue(n.dir_rule3 in n.munich.hasDirective)

        self.assertEqual(set(n.dir_rule3.affects), {n.dresden, n.passau, n.regensburg})
        self.assertFalse(n.leipzig in n.dir_rule3.affects)

        # test RC stipulations (InterRegionalRelations, IRR):
        tmp = [x.hasIRRTarget for x in n.munich.X_hasInterRegionRelation_RC]
        self.assertTrue(tmp == [n.dresden, n.passau, n.regensburg, n.leipzig])
        self.assertTrue(n.munich.X_hasInterRegionRelation_RC[0].hasIRRValue == 0.5)

    def test_regional_rules_query(self):
        # this largely is oriented on calls to query_owlready() in
        # https://bitbucket.org/jibalamy/owlready2/src/master/test/regtest.py
        om = ypo.OntologyManager("examples/regional-rules.owl.yml", self.world)

        q_hasSection1 = f"""
        PREFIX P: <{om.iri}>
        SELECT ?x WHERE {{
        ?x P:hasSection "§ 1.1".
        }}
        """
        r = om.make_query(q_hasSection1)
        self.assertEqual(r, {om.n.iX_DocumentReference_RC_0})

        q_hasPart1 = f"""
        PREFIX P: <{om.iri}>
        SELECT ?x WHERE {{
        ?x P:hasPart P:dresden.
        }}
        """
        r = om.make_query(q_hasPart1)
        self.assertEqual(r, {om.n.saxony})

        om.sync_reasoner(infer_property_values=True, infer_data_property_values=True)
        r = om.make_query(q_hasPart1)
        self.assertEqual(r, {om.n.saxony, om.n.germany})

    def test_check_type(self):

        obj1 = [3, 4, 5]
        obj2 = [3, 4, "5"]

        # pass silently
        ypo.check_type(obj1, typing.List[pydantic.StrictInt])

        with self.assertRaises(TypeError):
            ypo.check_type(obj2, typing.List[pydantic.StrictInt])

        obj3 = {"key 1": 1.0, "key 2": 2.0, "key 3": 3.0}

        ypo.check_type(obj3, typing.Dict[str, pydantic.StrictFloat])

        obj3["key 3"] = "3.0"
        obj3["key 4"] = 5

        with self.assertRaises(TypeError):
            ypo.check_type(obj3, typing.Dict[str, pydantic.StrictFloat])

        # allow for multiple types:

        ypo.check_type(obj3, typing.Dict[str, typing.Union[pydantic.StrictInt, pydantic.StrictFloat, str]])

    def test_zebra_puzzle(self):
        fpath = "examples/einsteins_zebra_riddle.owl.yml"
        om = ypo.OntologyManager(fpath, self.world)

        self.assertEqual(om.iri, "https://w3id.org/yet/undefined/einstein-zebra-puzzle-ontology#")

        n = om.n
        # remember: dog is created as a `Thing` (not a pet before the reasoner is called)
        self.assertNotIn(n.Pet, n.dog.is_a)
        self.assertTrue(n.house_2.right_to, n.house_1)
        self.assertTrue(n.house_1.right_to, ypo.owl2.Nothing)
        self.assertTrue(n.house_5.left_to, ypo.owl2.Nothing)
        self.assertTrue(n.right_to.is_functional_for(n.House))
        self.assertTrue(n.left_to.is_functional_for(n.House))

        om.sync_reasoner(infer_property_values=True)
        # after the reasoner finished these assertions hold true
        self.assertIn(n.Pet, n.dog.is_a)
        self.assertIn(n.Pet, n.fox.is_a)
        self.assertTrue(n.house_2.left_to, n.house_3)

        restriction_tuples = []

        # noinspection PyShadowingNames
        def append_restriction_tuple(restr, indiv):
            restriction_tuples.append((restr, indiv))

        # note these restrictions are defined in the yaml-file and are tested here
        append_restriction_tuple(n.lives_in.some(n.has_color.value(n.red)), n.Englishman)

        # 3. The Spaniard owns the dog.
        append_restriction_tuple(n.owns.value(n.dog), n.Spaniard)

        # 4. Coffee is drunk in the green house.
        append_restriction_tuple(n.Inverse(n.drinks).some(n.lives_in.some(n.has_color.value(n.green))), n.coffee)

        # 5. The Ukrainian drinks tea.
        # append_restriction_tuple(n.drinks.value(n.tea), n.Ukrainian)
        # this is tested directly:
        self.assertEqual(n.Ukrainian.drinks, n.tea)

        # 6. The green house is immediately to the right of the ivory house.
        append_restriction_tuple(n.Inverse(n.has_color).some(n.right_to.some(n.has_color.value(n.ivory))), n.green)

        # 7. The Old Gold smoker owns snails.
        append_restriction_tuple(n.Inverse(n.smokes).some(n.owns.value(n.snails)), n.Old_Gold)

        # 8. Kools are smoked in the yellow house.
        append_restriction_tuple(n.Inverse(n.smokes).some(n.lives_in.some(n.has_color.value(n.yellow))), n.Kools)

        # 9. Milk is drunk in the middle house.
        append_restriction_tuple(n.Inverse(n.drinks).some(n.lives_in.value(n.house_3)), n.milk)

        # 10. The Norwegian lives in the first house.
        # append_restriction_tuple(n.lives_in.value(n.house_1), n.Norwegian)
        # this is tested directly:
        self.assertEqual(n.Norwegian.lives_in, n.house_1)

        # 11. The man who smokes Chesterfields lives in the house next to the man with the fox.
        # right_to ist additional information
        append_restriction_tuple(
            n.Inverse(n.smokes).some(n.lives_in.some(n.right_to.some(n.Inverse(n.lives_in).some(n.owns.value(n.fox))))),
            n.Chesterfields,
        )

        # 12. Kools are smoked in a house next to the house where the horse is kept.
        # left_to ist additional information
        append_restriction_tuple(
            n.Inverse(n.smokes).some(
                n.lives_in.some(n.left_to.some(n.Inverse(n.lives_in).some(n.owns.value(n.horse))))
            ),
            n.Kools,
        )

        # 13. The Lucky Strike smoker drinks orange juice.
        append_restriction_tuple(n.Inverse(n.smokes).some(n.drinks.value(n.orange_juice)), n.Lucky_Strike)

        # 14. The Japanese smokes Parliaments.
        # append_restriction_tuple(n.smokes.value(n.Parliaments), n.Japanese)
        # this is tested directly:
        self.assertEqual(n.Japanese.smokes, n.Parliaments)

        # 15. The Norwegian lives next to the blue house.
        # !! "left_to" is additional knowledge
        append_restriction_tuple(n.lives_in.some(n.left_to.some(n.has_color.value(n.blue))), n.Norwegian)

        for rstrn, indiv in restriction_tuples:
            with self.subTest(rstrn=rstrn, indiv=indiv):

                self.assertIn(rstrn, indiv.is_a)

        # this is only true if the puzzle is solved completely
        self.assertEqual(n.Japanese.owns, n.zebra)


# for historical reasons this class contains newer tests
class TestCore2(unittest.TestCase):
    def setUp(self):
        # prevent that the tests do influence each other -> create a new world each time
        self.world = ypo.owl2.World()
        fpath = f"{BASEPATH}/tests/test_ontologies/basic_feature_ontology.owl.yaml"
        self.om = ypo.OntologyManager(fpath, self.world)

    def test_basic_features(self):
        # several features are tested in one unit test for better performance

        # iri
        self.assertEquals(self.om.onto.base_iri, "https://w3id.org/unpublished/yamlpyowl/basic-feature-ontology#")

        # annotation
        self.assertEqual(len(self.om.n.Class1.comment), 1)
        self.assertTrue("utc_annotation" in self.om.n.Class1.comment[0])
        self.assertEqual(len(self.om.n.Class2.comment), 4)
        self.assertTrue("\n" in self.om.n.Class2.comment[-1][:-1])

        # imports
        self.assertEqual(len(self.om.onto.imported_ontologies), 1)
        imported_onto = self.om.onto.imported_ontologies[0]
        self.assertEqual(imported_onto.name, "bfo")
        self.assertEqual(imported_onto.base_iri, "http://purl.obolibrary.org/obo/bfo.owl#")

