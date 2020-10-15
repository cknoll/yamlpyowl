import re
import yaml

# noinspection PyUnresolvedReferences
import owlready2 as owl2
from owlready2 import Thing, FunctionalProperty, Imp, sync_reasoner_pellet, get_ontology, SymmetricProperty,\
    TransitiveProperty, set_render_func, ObjectProperty, DataProperty

# noinspection PyUnresolvedReferences
from ipydex import IPS, activate_ips_on_exception
activate_ips_on_exception()


def render_using_label(entity):
    repr_str1 = entity.label.first() or entity.name
    return f"<{type(entity).name} '{repr_str1}'>"


set_render_func(render_using_label)


class Container(object):
    def __init__(self, data_dict):
        self.__dict__.update(data_dict)


class Ontology(object):
    def __init__(self, iri, fpath):
        """

        :param iri:     str; similar to uri
        :param fpath:   path of the owl file
        """
        self.new_classes = []
        self.concepts = []
        self.roles = []
        self.individuals = []
        self.rules = []

        # intermediate variables
        self.tmp_sco = None  # list of parent classes
        self.tmp_cgi = None  # flag whether or not create a generic individual

        # we cannot store arbitrary python attributes in owl-objects directly, hence we use this dict
        # keys will be tuples of the form: (obj, <attribute_name_as_str>)
        self.custom_attribute_store = {}

        # will be a Container later
        self.n = None
        self.quoted_string_re = re.compile("(^\".*\"$)|(^'.*'$)")

        # "http://onto.ackrep.org/pandemic_rule_ontology.owl"
        self.onto = get_ontology(iri)

        self.name_mapping = {
            "Thing": Thing,
            "FunctionalProperty": FunctionalProperty,
            "SymmetricProperty": SymmetricProperty,
            "TransitiveProperty": TransitiveProperty,
            "Imp": Imp,
            "int": int,
            "float": float,
            "str": str,

        }

        self.load_ontology(fpath)

    def get_objects_from_sequence(self, seq, accept_unquoted_strs=False):
        """
        If an element of the sequence is a number or a string literal delimited by `"` it is unchanged.
        Other strings are interpreted as names from `self.name_mapping`.

        :param seq: list of objects (coming from an yaml list)
        :return:    list of matching objects from the `self.name_mapping`
        :param accept_unquoted_strs:
        """

        res = []
        for elt in seq:
            res.append(self.resolve_name(elt, accept_unquoted_strs))

        return res

    def get_named_object(self, data_dict, key_name, default="<raise exception>"):
        """

        :param data_dict:   source dict (part of the parsed yaml data)
        :param key_name:    name (str) for the desired object
        :return:            the matching object from `self.name_mapping`
        :param default:     value which should be returned, if the key is not found.
                            This parameter defaults to a special string literal which results
                            in an exception being raised instead returning that literal.
        """

        if key_name not in data_dict:
            return None

        # `data_dict[key_name]` could be a single value or a list
        # ensure list
        value_name_list = data_dict[key_name]
        if not isinstance(value_name_list, list):
            assert isinstance(value_name_list, str)
            value_name_list = [value_name_list]
            list_flag = False
        else:
            list_flag = True

        res = []
        for value_name in value_name_list:
            if value_name not in self.name_mapping:
                if default == "<raise exception>":
                    raise ValueError(f"unknown name: {value_name} (value for {key_name})")
                else:
                    # !! TODO: is this still needed/useful?
                    res.append(default)
            else:
                res.append(self.name_mapping[value_name])

        if list_flag:
            return res
        else:
            # there was no list -> return the only value
            return res[0]

    def resolve_name(self, object_name, accept_unquoted_strs=False):
        """
        Try to find object_name in `self.name_mapping` if it is not a number or a string literal.
        Raise Exception if not found.

        :param object_name:
        :param accept_unquoted_strs:    boolean (default=False). Specify whether unquoted strings which are no valid
                                        names should provoke an error (default) or should be returned as they are
        :return:
        """

        # assume elt is a string
        if isinstance(object_name, (float, int)):
            return object_name
        elif isinstance(object_name, str) and self.quoted_string_re.match(object_name):
            # quoted strings are not interpreted as names
            return object_name

        elif isinstance(object_name, str) and object_name in self.name_mapping:
            return self.name_mapping[object_name]
        else:
            if accept_unquoted_strs:
                return object_name
            else:
                raise ValueError(f"unknown name (or type): {object_name}")

    def ensure_is_known_name(self, name):
        if name not in self.name_mapping:
            msg = f"The name {name} was not found in the name space"
            raise ValueError(msg)

    def ensure_is_new_name(self, name):
        if name in self.name_mapping:
            msg = f"This concept name was declared more than once: {name}"
            raise ValueError(msg)

    # noinspection PyPep8Naming
    def make_individual(self, i_name, data_dict):

        kwargs = {}
        label = []
        name = None

        isA = self.get_named_object(data_dict, "isA")
        for key, value in data_dict.items():
            if key == "isA":
                continue
            if key == "name":
                name = data_dict[key]
            elif key == "label":
                label_object = data_dict[key]
                if isinstance(label_object, str):
                    label.append(label_object)
                elif isinstance(label_object, list):
                    label.extend(label_object)
                else:
                    msg = f"Invalid type ({type(label_object)}) for label of individual '{i_name}'." \
                          f"Expected str or list."
                    raise TypeError(msg)

            else:
                property_object = self.name_mapping.get(key)
                if not property_object:
                    # key_name was not found
                    continue
                if isinstance(value, list):
                    accept_unquoted_strs = (str in property_object.range)
                    property_values = self.get_objects_from_sequence(value, accept_unquoted_strs)
                elif isinstance(value, (float, int, str)):
                    property_values = value
                else:
                    msg = f"Invalid type ({type(value)}) for property '{key}' of individual '{i_name}'." \
                          f"Expected int, float, str or list."
                    raise TypeError(msg)

                kwargs[key] = property_values
        if name is None:
            name = i_name

        new_individual = isA(name=name, label=label, **kwargs)
        self.individuals.append(new_individual)
        self.name_mapping[i_name] = new_individual

        return new_individual

    def make_concept(self, name, data):

        self.ensure_is_new_name(name)
        self._spec_sco(data)

        # auto-create a generic individual (which is useful to be referenced in roles)
        # noinspection PyTypeChecker
        self._spec_cgi_flag(data)

        # now define the class
        new_class = type(name, self.tmp_sco, {})

        self.name_mapping[name] = new_class
        self.new_classes.append(new_class)
        self.concepts.append(new_class)

        if self.tmp_cgi:
            # store that property in the class-object (available for look-up of child classes)
            self.custom_attribute_store[(new_class, "_createGenericIndividual")] = True

            # create the generic individual:
            gi_name = f"i{name}"
            gi = new_class(name=gi_name)
            self.individuals.append(gi)
            self.name_mapping[gi_name] = gi

    def _spec_sco(self, data):
        """
        extract parent class(es) from data-dict and ensure thats a tuple

        :param data:
        :return:        None
        """

        # owl_concepts is a dict like {'GeographicEntity': {'subClassOf': 'Thing'}, ...}
        self.tmp_sco = self.get_named_object(data, "subClassOf")

        if not isinstance(self.tmp_sco, (list, tuple)):
            self.tmp_sco = (self.tmp_sco,)
        else:
            self.tmp_sco = tuple(self.tmp_sco)

    def _spec_cgi_flag(self, data):
        """
        Look for `_createGenericIndividual` attribute in data-dict. If not found, look in parent class(es).
        If not found set to `False` (default). Raise error for inconsistency.

        :param data:
        :return:
        """

        self.tmp_cgi = data.get("_createGenericIndividual")

        if self.tmp_cgi is None:
            # look at the parent classes (could be more than one)
            cgi_flags = []
            for parent_class in self.tmp_sco:
                cgi_flags.append(self.custom_attribute_store.get((parent_class, "_createGenericIndividual"), False))

            # check for inconsistency
            assert len(cgi_flags) > 0
            if not cgi_flags.count(cgi_flags[0]) == len(cgi_flags):
                msg = f"Inconsistency found wrt the createGenericIndividual Option deduced from the following " \
                      f"parent classes: {self.tmp_sco} ({cgi_flags})"
                raise ValueError(msg)

            # now we can assume that all flags are identical
            self.tmp_cgi = cgi_flags[0]

    # noinspection PyPep8Naming
    def make_role(self, name, data):

        self.ensure_is_new_name(name)

        # owl_roles: dict like {'hasDirective': [{'mapsFrom': 'GeographicEntity'}, {'mapsTo': 'Directive'}]}
        try:
            mapsFrom = self.name_mapping[data.get("mapsFrom")]

            mapping_target = data.get("mapsTo")
            if not isinstance(mapping_target, list):
                mapsTo = [self.name_mapping[mapping_target]]
            else:
                mapsTo = [self.name_mapping[elt] for elt in mapping_target]
        except KeyError:
            msg = f"Unknown concept name for `mapsFrom` or mapsTo in : {name}"
            raise ValueError(msg)

        assert issubclass(mapsFrom, Thing)

        for elt in mapsTo:
            assert issubclass(elt, (Thing, int, float, str))

        additional_properties = self.get_objects_from_sequence(data.get("properties", []))
        kwargs = {"domain": [mapsFrom], "range": mapsTo}
        inverse_property = self.get_named_object(data, "inverse_property")
        if inverse_property:
            kwargs["inverse_property"] = inverse_property

        # choose the right base class for the property and check consistency
        basic_types = {int, float, str}

        if set(mapsTo).intersection(basic_types):
            # the range contains basic data types
            # assert that it *only* contains basic types
            assert set(mapsTo).union(basic_types) == basic_types
            PropertyBaseClass = DataProperty
        else:
            PropertyBaseClass = ObjectProperty

        new_class = type(name, (PropertyBaseClass, *additional_properties), kwargs)
        self.name_mapping[name] = new_class
        self.new_classes.append(new_class)
        self.roles.append(new_class)

    def process_stipulation(self, role_name, data):
        """
        A stipulation is a piece of knowledge which is added after the initial creation of a knowledge base.
        This method assigns roles to exisiting individuals. Example: ind_1.hasPart.extend(ind_x, ind_y)

        :param role_name:   name of the role (like 'hasPart')
        :param data:        dict like: {'ind_1': ['ind_x', 'ind_y'], ...}
                            the occuring strings are assumed to be valid names
        :return:
        """
        self.ensure_is_known_name(role_name)
        role = self.name_mapping[role_name]
        if not issubclass(role, owl2.ObjectProperty):
            msg = f"{role_name} should have been a role-name. Instead it is a {type(role)}"
            raise ValueError(msg)

        for ind_name, seq in data.items():
            self.ensure_is_known_name(ind_name)
            individual = self.name_mapping[ind_name]
            ind_seq = self.get_objects_from_sequence(seq)

            # apply this role to the individual
            getattr(individual, role_name).extend(ind_seq)

    def process_swrl_rule(self, rule_name, data):
        """
        Construnct the swrl-object (Semantic Web Rule Language) from the source code

        :param rule_name:
        :param data:
        :return:
        """
        self.ensure_is_new_name(rule_name)

        type_object = self.get_named_object(data, "isA")

        # TODO find out what Imp actually means and whether it is needed in the yaml-source at all
        assert type_object is Imp

        rule_src = data["rule_src"]

        # create the instance
        new_rule = type_object()
        new_rule.set_as_rule(rule_src)
        self.rules.append(new_rule)

        self.name_mapping[rule_name] = new_rule

    # noinspection PyPep8Naming
    def load_ontology(self, fpath):

        with open(fpath, 'r') as myfile:
            d = yaml.load(myfile)

        # provide namespace for classes via `with` statement
        with self.onto:

            # class _createGenericIndividual(Thing >> bool, FunctionalProperty):
            #     pass

            for name, data in d.get("owl_concepts", {}).items():
                self.make_concept(name, data)

            for name, data in d.get("owl_roles", {}).items():
                self.make_role(name, data)

            for name, data in d.get("owl_individuals", {}).items():
                self.make_individual(name, data)

            for name, data in d.get("owl_stipulations", {}).items():
                self.process_stipulation(name, data)

            for name, data in d.get("swrl_rules", {}).items():
                self.process_swrl_rule(name, data)

        # shortcut for quic access to the name of the ontology
        self.n = Container(self.name_mapping)

    @staticmethod
    def sync_reasoner(**kwargs):
        sync_reasoner_pellet(**kwargs)


def main(fpath):
    o = Ontology(iri="test", fpath=fpath)
    return o
