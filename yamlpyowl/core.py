import yaml

# noinspection PyUnresolvedReferences
import owlready2 as owl2
from owlready2 import Thing, FunctionalProperty, Imp, sync_reasoner_pellet, get_ontology, SymmetricProperty,\
    TransitiveProperty

from ipydex import IPS, activate_ips_on_exception
activate_ips_on_exception()

name_mapping = {
    "Thing": Thing,
    "FunctionalProperty": FunctionalProperty,
    "SymmetricProperty": SymmetricProperty,
    "TransitiveProperty": TransitiveProperty,
}


def get_named_objects_from_sequence(seq):
    """

    :param seq: list of strings (coming from an yaml list)
    :return:    list of matching objects from the `name_mapping`
    """

    res = []
    for elt in seq:
        # assume elt is a string
        if elt not in name_mapping:
            raise ValueError(f"unknown name: {elt}")
        else:
            res.append(name_mapping[elt])
    return res


def get_named_object(data_dict, key_name):
    """

    :param data_dict:   source dict (part of the parsed yaml data)
    :param key_name:    name (str) for the desired object
    :return:            the matching object from `name_mapping`
    """

    if key_name not in data_dict:
        return None

    value_name = data_dict[key_name]

    if value_name not in name_mapping:
        raise ValueError(f"unknown name: {value_name} (value for {key_name})")

    return name_mapping[value_name]


def create_individual(i_name, data_dict):

    kwargs = {}

    isA = get_named_object(data_dict, "isA")
    for key, value in data_dict.items():
        if key == "isA":
            continue
        property_object = name_mapping.get(key)
        if not property_object:
            # key_name was not found
            continue
        property_values = get_named_objects_from_sequence(value)
        kwargs[key] = property_values

    new_individual = isA(**kwargs)

    return new_individual


# noinspection PyPep8Naming
def main(fpath):

    with open(fpath, 'r') as myfile:
        d = yaml.load(myfile)

    onto = get_ontology("http://onto.ackrep.org/pandemic_rule_ontology.owl")

    new_classes = []
    concepts = []
    roles = []
    individuals = []

    # provide namespace for classes via `with` statement
    with onto:
        for concept in d["owl_concepts"]:
            # concept is a dict like {'GeographicEntity': {'subClassOf': 'Thing'}}
            c_name, data = tuple(concept.items())[0]
            sco = get_named_object(data, "subClassOf")
            if c_name in name_mapping:
                msg = f"This concept name was declared more than once: {c_name}"
                raise ValueError(msg)

            # now define the class
            new_class = type(c_name, (sco,), {})

            name_mapping[c_name] = new_class
            new_classes.append(new_class)
            concepts.append(new_class)

        for role in d["owl_roles"]:
            # dict like {'hasDirective': [{'mapsFrom': 'GeographicEntity'}, {'mapsTo': 'Directive'}]}
            r_name, data = tuple(role.items())[0]
            try:
                mapsFrom = name_mapping[data.get("mapsFrom")]
                mapsTo = name_mapping[data.get("mapsTo")]
            except KeyError:
                msg = f"Unknown concept name for `mapsFrom` or mapsTo in : {role}"
                raise ValueError(msg)
            if r_name in name_mapping:
                msg = f"This name was declared more than once: {r_name}"
                raise ValueError(msg)
            assert issubclass(mapsFrom, Thing)
            assert issubclass(mapsTo, Thing)
            from_to_type = mapsFrom >> mapsTo

            additional_properties = get_named_objects_from_sequence(data.get("properties", []))
            kwargs = {}
            inverse_property = get_named_object(data, "inverse_property")
            if inverse_property:
                kwargs["inverse_property"] = inverse_property

            new_class = type(r_name, (from_to_type, *additional_properties), kwargs)
            name_mapping[r_name] = new_class
            new_classes.append(new_class)
            roles.append(new_class)

        for individual in d["owl_individuals"]:
            i_name, data = tuple(individual.items())[0]
            new_individual = create_individual(i_name, data)

            individuals.append(new_individual)
            name_mapping[i_name] = new_individual

    IPS()
