"""
This file serves as a preparation to implement the yaml-parser. It finally should contain the same ontology
(represented as owlready2-objects) as if the rdf-xml-file was loaded, but with the condition that only the yml-file
is loaded to set up all the individuals, classes and roles and then restrictions should be added manually.
"""

import yamlpyowl.new_core as ypo2


world = ypo2.owl2.World()
fpath = "../examples/einsteins_zebra_riddle.owl.yaml"
om = ypo2.OntologyManager(fpath, world)
owl2 = ypo2.owl2

assert om.iri == 'https://w3id.org/yet/undefined/einstein-zebra-puzzle-ontology#'

# define `n` as shortcut to quickly access all entities (individuals, classes, roles)
n = om.n

# some basic assertation to test whether the ontology has been loaded from the yaml-file as expected


assert n.house_2.right_to == n.house_1
assert n.house_1.right_to == ypo2.owl2.Nothing
assert n.house_5.left_to == ypo2.owl2.Nothing

# this is only true after the reasoner has run
assert n.Pet not in n.dog.is_a

om.sync_reasoner(infer_property_values=True)

assert n.Pet in n.dog.is_a


# Now these facts have to be represented:

# 1. There are five houses.
# 2. The Englishman lives in the red house.
# 3. The Spaniard owns the dog.
# 4. Coffee is drunk in the green house.
# 5. The Ukrainian drinks tea.
# 6. The green house is immediately to the right of the ivory house.
# 7. The Old Gold smoker owns snails.
# 8. Kools are smoked in the yellow house.
# 9. Milk is drunk in the middle house.
# 10. The Norwegian lives in the first house.
# 11. The man who smokes Chesterfields lives in the house next to the man with the fox.
# 12. Kools are smoked in a house next to the house where the horse is kept.
# 13. The Lucky Strike smoker drinks orange juice.
# 14. The Japanese smokes Parliaments.
# 15. The Norwegian lives next to the blue house.

# Fact 3
om.add_restriction_to_individual(n.owns.value(n.dog), n.Spaniard)


# a random/wrong fact, just o demonstrate `some` and `OneOf`
# om.add_restriction_to_individual(n.lives_in.some(owl2.OneOf([n.house_1, n.house_2])), n.Japanese)
# see https://owlready2.readthedocs.io/en/latest/restriction.html?highlight=OneOf
# see https://owlready2.readthedocs.io/en/latest/restriction.html?highlight=some


# !!! add your code here:
# make use of the file `yamlpyowl/experiments/einsteins_riddle_manchester.owl`


# for interactive exploration of the objects you can use this:

# note: ipydex is in the requirements.txt
# from ipydex import IPS
# IPS()  # start interactive shell in namespace (should be run in a terminal window, not insice pycharm, spyder, ...)


# this should finally run:

task_complete = False
if task_complete:
    om.sync_reasoner(infer_property_values=True)

    assert n.Spaniard.owns == n.dog
    assert n.Englishman.owns == n.snails
    assert n.Japanese.owns == n.zebra
    assert n.Norwegian.owns == n.fox
    assert n.Ukrainian.owns == n.horse

    assert n.Norwegian.lives_in == n.house_1
    assert n.Englishman.lives_in == n.house_3
    assert n.Japanese.lives_in == n.house_5
    assert n.Ukrainian.lives_in == n.house_2
    assert n.Spaniard.lives_in == n.house_4

