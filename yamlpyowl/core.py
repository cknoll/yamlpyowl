import yaml

# noinspection PyUnresolvedReferences
import owlready2 as owl2
from owlready2 import Thing, FunctionalProperty, Imp, sync_reasoner_pellet, get_ontology, SymmetricProperty,\
    TransitiveProperty

from ipydex import IPS, activate_ips_on_exception
activate_ips_on_exception()


class Ontology(object):
    def __init__(self, iri, fpath):
        self.new_classes = []
        self.concepts = []
        self.roles = []
        self.individuals = []

        # "http://onto.ackrep.org/pandemic_rule_ontology.owl"
        self.onto = get_ontology(iri)

        self.name_mapping = {
            "Thing": Thing,
            "FunctionalProperty": FunctionalProperty,
            "SymmetricProperty": SymmetricProperty,
            "TransitiveProperty": TransitiveProperty,
        }

        self.load_ontology(fpath)

    def get_named_objects_from_sequence(self, seq):
        """

        :param seq: list of strings (coming from an yaml list)
        :return:    list of matching objects from the `self.name_mapping`
        """

        res = []
        for elt in seq:
            # assume elt is a string
            if elt not in self.name_mapping:
                raise ValueError(f"unknown name: {elt}")
            else:
                res.append(self.name_mapping[elt])
        return res

    def get_named_object(self, data_dict, key_name):
        """

        :param data_dict:   source dict (part of the parsed yaml data)
        :param key_name:    name (str) for the desired object
        :return:            the matching object from `self.name_mapping`
        """

        if key_name not in data_dict:
            return None

        value_name = data_dict[key_name]

        if value_name not in self.name_mapping:
            raise ValueError(f"unknown name: {value_name} (value for {key_name})")

        return self.name_mapping[value_name]

    def create_individual(self, i_name, data_dict):

        kwargs = {}

        isA = self.get_named_object(data_dict, "isA")
        for key, value in data_dict.items():
            if key == "isA":
                continue
            property_object = self.name_mapping.get(key)
            if not property_object:
                # key_name was not found
                continue
            property_values = self.get_named_objects_from_sequence(value)
            kwargs[key] = property_values

        new_individual = isA(**kwargs)

        return new_individual

# noinspection PyPep8Naming
    def load_ontology(self, fpath):

        with open(fpath, 'r') as myfile:
            d = yaml.load(myfile)

        self.new_classes = []
        self.concepts = []
        self.roles = []
        self.individuals = []

        # provide namespace for classes via `with` statement
        with self.onto:
            for c_name, data in d["owl_concepts"].items():
                # owl_concepts is a dict like {'GeographicEntity': {'subClassOf': 'Thing'}, ...}
                sco = self.get_named_object(data, "subClassOf")
                if c_name in self.name_mapping:
                    msg = f"This concept name was declared more than once: {c_name}"
                    raise ValueError(msg)

                # now define the class
                new_class = type(c_name, (sco,), {})

                self.name_mapping[c_name] = new_class
                self.new_classes.append(new_class)
                self.concepts.append(new_class)

            for r_name, data in d["owl_roles"].items():
                # owl_roles: dict like {'hasDirective': [{'mapsFrom': 'GeographicEntity'}, {'mapsTo': 'Directive'}]}
                try:
                    mapsFrom = self.name_mapping[data.get("mapsFrom")]
                    mapsTo = self.name_mapping[data.get("mapsTo")]
                except KeyError:
                    msg = f"Unknown concept name for `mapsFrom` or mapsTo in : {r_name}"
                    raise ValueError(msg)
                if r_name in self.name_mapping:
                    msg = f"This name was declared more than once: {r_name}"
                    raise ValueError(msg)
                assert issubclass(mapsFrom, Thing)
                assert issubclass(mapsTo, Thing)
                from_to_type = mapsFrom >> mapsTo

                additional_properties = self.get_named_objects_from_sequence(data.get("properties", []))
                kwargs = {}
                inverse_property = self.get_named_object(data, "inverse_property")
                if inverse_property:
                    kwargs["inverse_property"] = inverse_property

                new_class = type(r_name, (from_to_type, *additional_properties), kwargs)
                self.name_mapping[r_name] = new_class
                self.new_classes.append(new_class)
                self.roles.append(new_class)

            for i_name, data in d["owl_individuals"].items():
                new_individual = self.create_individual(i_name, data)

                self.individuals.append(new_individual)
                self.name_mapping[i_name] = new_individual


def main(fpath):
    o = Ontology(iri="test", fpath=fpath)
    return o

