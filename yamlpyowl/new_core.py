from collections import defaultdict

import re
import yaml
import pydantic
from typing import Union, List, Dict, Tuple, Callable, Any, Literal

# for py3.7: from typing_extensions import Literal

# noinspection PyUnresolvedReferences
import owlready2 as owl2
from owlready2 import Thing, FunctionalProperty, Imp, sync_reasoner_pellet, SymmetricProperty,\
    TransitiveProperty, set_render_func, ObjectProperty, DataProperty

# noinspection PyUnresolvedReferences
from ipydex import IPS, activate_ips_on_exception
activate_ips_on_exception()


def render_using_label(entity):
    repr_str1 = entity.label.first() or entity.name
    return f"<{type(entity).name} '{repr_str1}'>"


set_render_func(render_using_label)


class UnknownEntityError(ValueError):
    pass


class MissingKeywordError(ValueError):
    pass


class Container(object):
    def __init__(self, arg=None, **data_dict):
        if isinstance(arg, dict) and not data_dict:
            data_dict = arg
        self.__dict__.update(data_dict)

    def __repr__(self):
        name = getattr(self, "name", "<unnamed>")
        data = getattr(self, "data", [])

        return f"<{name}-Container: {data}"


# easy access to some important literals
lit = Container(some=Literal["some"], value=Literal["value"])


class OntologyManager(object):
    def __init__(self, fpath, world=None):
        """

        :param fpath:   path of the yaml-file containing the ontology
        :param world:   owl2 world object holding all the RDF-data (default: None)
        """
        if world is None:
            world = owl2.default_world

        self.world = world
        self.raw_data = None
        self.new_python_classes = []
        self.concepts = []
        self.roles = {}
        self.individuals = []
        self.rules = []

        # this implemented in its own class to reduce complexity of this class
        self.property_restriction_parser = PropertyRestrictionParser(self)

        # we cannot store arbitrary python attributes in owl-objects directly, hence we use this dict
        # keys will be tuples of the form: (obj, <attribute_name_as_str>)
        self.custom_attribute_store = {}

        # will be a Container later for quick access to the names of the ontology
        self.n = None
        self.quoted_string_re = re.compile("(^\".*\"$)|(^'.*'$)")

        self._load_yaml(fpath)

        # extract the internationalized ressource identifier or use default
        self.iri = self._get_from_all_dicts("iri", "https://w3id.org/yet/undefined/ontology#")
        self.onto = self.world.get_ontology(self.iri)

        self.name_mapping = {
            "owl:Thing": Thing,
            "owl:Nothing": owl2.Nothing,
            "Functional": FunctionalProperty,
            "InverseFunctional": owl2.InverseFunctionalProperty,
            "SymmetricProperty": SymmetricProperty,
            "TransitiveProperty": TransitiveProperty,
            "Inverse": owl2.Inverse,
            "Imp": Imp,
            "int": int,
            "float": float,
            "str": str,

        }

        self.logic_functions = {
            "Or": owl2.Or,
            "And": owl2.And,
            "Not": owl2.Not,
        }
        self.name_mapping.update(self.logic_functions)

        self.restriction_types = {
            "some": lit.some,
            "value": lit.value,
        }
        self.name_mapping.update(self.restriction_types)

        self.top_level_parse_functions = {}
        self.normal_parse_functions = {}
        self.create_tl_parse_function("owl_individual", self.make_individual_from_dict)
        self.create_tl_parse_function("owl_multiple_individuals", self.make_multiple_individuals_from_dict)
        self.create_tl_parse_function("owl_class", self.make_class_from_dict)
        self.create_tl_parse_function("owl_object_property", self.make_object_property_from_dict)
        self.create_tl_parse_function("owl_inverse_property", self.make_inverse_property_from_dict)
        self.create_tl_parse_function("property_facts", self.make_property_facts_from_dict)
        self.create_tl_parse_function("restriction", self.add_restriction_from_dict)

        self.create_nm_parse_function("types")
        self.create_nm_parse_function_cf("EquivalentTo", struct_wrapper=self.atom_or_And)
        self.create_nm_parse_function_cf("Domain", struct_wrapper=self.atom_or_Or)
        self.create_nm_parse_function_cf("Range", struct_wrapper=self.atom_or_Or)
        self.create_nm_parse_function_cf("Facts", inner_func=self.resolve_key_and_value, resolve_names=False)
        self.create_nm_parse_function_cf("Characteristics")
        self.create_nm_parse_function_cf("Inverse")
        self.create_nm_parse_function_cf("Subject")
        self.create_nm_parse_function_cf("Body")

        self.create_nm_parse_function("OneOf", outer_func=owl2.OneOf)

        self.excepted_non_function_keys = [
            "iri",
            "annotation"
        ]

        self.load_ontology()

    # noinspection PyPep8Naming
    @staticmethod
    def atom_or_And(arg: list):
        """
        convert a list into an And-connective (or return arg[0])
        :param arg:
        :return:
        """

        if len(arg) == 1:
            return arg[0]
        else:
            return owl2.And(arg)

    # noinspection PyPep8Naming
    @staticmethod
    def atom_or_Or(arg: list):
        """
        convert a list into an Or-connective (or return arg[0])
        :param arg:
        :return:
        """

        if len(arg) == 1:
            return arg[0]
        else:
            return owl2.Or(arg)

    def resolve_key_and_value(self, data_dict: dict) -> dict:
        """
        used to resolve constructs like

        ```
        Facts:
          - house_2: house_1
          - house_3: house_2
          - house_4: house_3
          - house_5: house_4
        ```
        :param data_dict:
        :return:
        """
        assert len(data_dict) == 1
        key, value = list(data_dict.items())[0]

        res = {self.resolve_name(key): self.resolve_name(value)}
        return res

    # noinspection PyPep8Naming
    def containerFactoryFactory(self, container_name: str, struct_wrapper: callable = None) -> callable:
        """

        :param container_name:
        :param struct_wrapper:      E.g. callable like `atom_or_And`
        :return:
        """

        class OntoContainer(Container):
            def __init__(self):
                super().__init__(self)
                self.name = container_name
                self.data = None

        if struct_wrapper is None:
            def struct_wrapper(arg): return arg

        def outer_func(arg: list) -> OntoContainer:

            res = OntoContainer()
            res.data = struct_wrapper(arg)

            return res

        return outer_func

    def create_tl_parse_function(self, name: str, func: callable) -> None:
        assert name not in self.top_level_parse_functions
        self.top_level_parse_functions[name] = func

    def create_nm_parse_function_cf(self, name: str, **kwargs) -> None:
        """
        create a container factory (cf) as a parse function

        :param name:    name of the keyword
        """

        inner_func = kwargs.pop("inner_func", None)
        resolve_names = kwargs.pop("resolve_names", True)

        self.create_nm_parse_function(name, outer_func=self.containerFactoryFactory(name, **kwargs),
                                      inner_func=inner_func, resolve_names=resolve_names)

    def create_nm_parse_function(self, name: str, outer_func=None, inner_func=None, resolve_names=True) -> None:
        """

        :param name:
        :param outer_func:
        :param inner_func:
        :param resolve_names:   see TreeParseFunction
        :return:
        """
        if outer_func is None:
            outer_func = lambda x: x
        if inner_func is None:
            inner_func = lambda x: x
        assert name not in self.top_level_parse_functions
        self.normal_parse_functions[name] = TreeParseFunction(name, outer_func, inner_func, self,
                                                              resolve_names=resolve_names)

    def cas_get(self, key, default=None):
        return self.custom_attribute_store.get(key, default)

    def cas_set(self, key, value):
        self.custom_attribute_store[key] = value

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

        elif isinstance(object_name, str):
            if object_name in self.name_mapping:
                return self.name_mapping[object_name]
            else:
                if accept_unquoted_strs:
                    return object_name
                else:
                    raise UnknownEntityError(f"unknown entity name: {object_name}")
        else:
            msg = f"unexpeted type ({type(object_name)}) of object <{object_name}>"\
                  "in method resolve_name (expected str, int or float)"
            raise TypeError(msg)

    def ensure_is_known_name(self, name):
        if name not in self.name_mapping:
            msg = f"The name {name} was not found in the name space"
            raise ValueError(msg)

    def ensure_is_new_name(self, name):
        if name in self.name_mapping:
            msg = f"This concept name was declared more than once: {name}"
            raise ValueError(msg)

    def make_individual_from_dict(self, data_dict: dict) -> dict:
        """
        :param data_dict:
        :return:
        """

        assert len(data_dict) == 1
        assert check_type(data_dict, Dict[str, dict])

        individual_name, inner_dict = list(data_dict.items())[0]
        self.ensure_is_new_name(individual_name)

        types = self.process_tree({"types": inner_dict.get("types")}, squeeze=True)

        main_type = types[0]
        ind = main_type(name=individual_name)

        if len(types) > 1:
            # !! maybe handle multiple types
            raise NotImplementedError

        self.name_mapping[individual_name] = ind

        return ind

    def make_multiple_individuals_from_dict(self, data_dict: dict) -> dict:
        """
        :param data_dict:
        :return:
        """

        try:
            names = data_dict.pop("names")
        except KeyError:
            msg = f"Statement `owl_multiple_individuals` must have attribute `names`. {data_dict}"
            raise KeyError(msg)

        for name in names:
            self.make_individual_from_dict({name: dict(data_dict)})

    def make_class_from_dict(self, data_dict: dict) -> owl2.entity.ThingClass:
        assert len(data_dict) == 1
        assert check_type(data_dict, Dict[str, dict])

        class_name, inner_dict = list(data_dict.items())[0]

        processed_inner_dict = self.process_tree(inner_dict)
        sco = (owl2.Thing,)
        # create the class
        new_class = type(class_name, sco, {})
        self.name_mapping[class_name] = new_class
        self.concepts.append(new_class)

        # !! 3.8 -> use `:=` here

        if equivalent_to := processed_inner_dict["EquivalentTo"]:

            # noinspection PyUnresolvedReferences
            new_class.equivalent_to.extend(ensure_list(equivalent_to.data))

        assert isinstance(new_class, owl2.entity.ThingClass)
        return new_class

    def make_object_property_from_dict(self, data_dict: dict) -> owl2.PropertyClass:

        name, inner_dict = unpack_len1_mapping(data_dict)
        processed_inner_dict = self.process_tree(inner_dict)

        basic_types = {int, float, str}

        range_ = ensure_list(processed_inner_dict["Range"].data)
        domain = ensure_list(processed_inner_dict["Domain"].data)
        if set(range_).intersection(basic_types):
            # the range contains basic data types
            # assert that it *only* contains basic types
            assert set(range_).union(basic_types) == basic_types
            property_base_class = DataProperty
        else:
            property_base_class = ObjectProperty

        characteristics = processed_inner_dict["Characteristics"].data
        kwargs = {"domain": domain, "range": range_}

        new_property = create_property(name, property_base_class, characteristics, kwargs)
        self.name_mapping[name] = new_property
        self.roles[name] = new_property

        self.process_property_facts(new_property, processed_inner_dict)

        # noinspection PyTypeChecker
        return new_property

    def make_inverse_property_from_dict(self, data_dict: dict) -> owl2.PropertyClass:

        name, inner_dict = unpack_len1_mapping(data_dict)
        processed_inner_dict = self.process_tree(inner_dict)

        existing_inverse_property = processed_inner_dict.get("Inverse")
        if existing_inverse_property is None:
            msg = f"keyword `Inverse` is required in owl_inverse_property: {data_dict}"
            raise MissingKeywordError(msg)

        domain = existing_inverse_property.range
        range_ = existing_inverse_property.domain

        mro = existing_inverse_property.mro()
        if owl2.ObjectProperty in mro:
            property_base_class = owl2.ObjectProperty
        elif owl2.DataProperty in mro:
            # !! currently unclear whether this can meaningfully happen: Inverse of a DataProperty
            property_base_class = owl2.DataProperty
        else:
            msg = f"Unexpected mro for property: {existing_inverse_property}"
            raise ValueError(msg)

        characteristics = []
        if owl2.InverseFunctionalProperty in mro:
            characteristics.append(owl2.FunctionalProperty)
        if owl2.FunctionalProperty in mro:
            characteristics.append(owl2.InverseFunctionalProperty)

        kwargs = {"domain": domain, "range": range_, "inverse_property": existing_inverse_property}

        new_property = create_property(name, property_base_class, characteristics=characteristics, kwargs=kwargs)
        self.process_property_facts(new_property, processed_inner_dict)

        self.name_mapping[name] = new_property
        self.roles[name] = new_property

        return new_property

    def make_property_facts_from_dict(self, data_dict: dict) -> None:
        """

        :param data_dict:   example: 'left_to': {'Facts': [{'house_5': 'owl:Nothing'}]}}

        :return:
        """
        for property_name, inner_dict in data_dict.items():
            property_ = self.resolve_name(property_name)
            processed_inner_dict = self.process_tree(inner_dict)
            self.process_property_facts(property_, processed_inner_dict)

    @staticmethod
    def process_property_facts(property_: owl2.PropertyClass, processed_inner_dict: dict) -> None:
        if facts := processed_inner_dict.get("Facts"):
            fact_data = facts.data
        else:
            fact_data = []

        for fact in fact_data:
            key, value = unpack_len1_mapping(fact)
            if property_.is_functional_for(key):
                try:
                    setattr(key, property_.name, value)
                except AttributeError as err:
                    # account for a (probable bug in owlready2 realted to inverse_property and owl:Nothing
                    # whose .__dict__ attribute is a `mapping_proxy` object which has no `.pop` method
                    if "'mappingproxy' object has no attribute 'pop'" in err.args[0]:
                        pass
                    else:
                        # something different went wrong
                        raise err
            else:
                getattr(key, property_.name).append(value)

    def process_tree(self, normal_dict: dict, squeeze=False, parse_functions: dict = None) -> Dict[str, Any]:
        """
        Determine parsefunction from  a (standard or custom) dict-key and apply it the value

        :param normal_dict:         data_dict (expected to be not a top_level dict)
        :param squeeze:             flag for squeezing the output
        :param parse_functions:     dict where the parse_functions should be taken from
                                    default: None -> use self.normal_parse_functions
        :return:
        """

        assert len(normal_dict) > 0

        if parse_functions is None:
            parse_functions = self.normal_parse_functions
        check_type(parse_functions, dict)

        res = {}
        for key, value in normal_dict.items():
            key_func = self._resolve_yaml_key(parse_functions, key)

            try:
                res[key] = key_func(value)
            except UnknownEntityError as err:
                msg = f"{err.args[0]} while processig dict: {normal_dict}"
                raise UnknownEntityError(msg)
            # except TypeError as err:
            #     msg = f"{err.args[0]} while processig dict: {normal_dict}"
            #     raise TypeError(msg)

        if squeeze:
            assert len(res) == 1
            res = res[key]

        return res

    def add_restriction_from_dict(self, data_dict: dict) -> None:
        """
        Create a restriction form a raw yaml-dict

        :param data_dict:   raw yaml-dict
        :return: None

        Expected input data (example):
            {'Subject': 'Englishman',
             'Body': {'lives_in': {'some': {'has_color': {'value': 'red'}}}}}
        """

        subject_name = self._resolve_yaml_key(data_dict, "Subject")
        check_type(subject_name, str)

        # get the corresponding individual object
        subject = self.resolve_name(subject_name)

        body_dict = self._resolve_yaml_key(data_dict, "Body")
        check_type(body_dict, dict)

        evaluated_restriction = self.property_restriction_parser.process_restriction_body(body_dict)
        self.add_restriction_to_individual(evaluated_restriction, subject)

        # returning something is currently not necessary

    def add_restriction_to_individual(self, rstrn: owl2.class_construct.Restriction, indv: owl2.Thing) -> None:

        assert isinstance(rstrn, owl2.class_construct.Restriction)

        if rstrn.storid is None:
            # this should mitigate a bug in owlready (my current understanding)
            rstrn.storid = self.onto.world.new_blank_node()

        indv.is_a.append(rstrn)

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
    def _load_yaml(self, fpath):
        with open(fpath, 'r') as myfile:
            self.raw_data = yaml.safe_load(myfile)

        assert check_type(self.raw_data, List[dict])

    def _get_from_all_dicts(self, key, default=None):
        # src: https://stackoverflow.com/questions/9819602/union-of-dict-objects-in-python#comment23716639_12926008
        all_dicts = dict(i for dct in self.raw_data for i in dct.items())
        return all_dicts.get(key, default)

    @staticmethod
    def _resolve_yaml_key(data_dict, key):

        if key not in data_dict:
            msg = f"Key  {key} not found in current part of in yaml-file: \ncomplete data:\n{data_dict}"
            raise KeyError(msg)

        return data_dict[key]

    def load_ontology(self):

        # provide namespace for classes via `with` statement
        res = []
        with self.onto:

            for top_level_dict in self.raw_data:
                assert check_type(top_level_dict, Dict[str, Union[str, dict]])
                assert len(top_level_dict) == 1
                key, inner_dict = list(top_level_dict.items())[0]

                if key in self.excepted_non_function_keys:
                    continue

                # get function or fail gracefully
                tl_parse_function = self._resolve_yaml_key(self.top_level_parse_functions, key)

                # now call the matching function
                res.append(tl_parse_function(inner_dict))

        # shortcut for quic access to the name of the ontology
        self.n = Container(self.name_mapping)

    def make_query(self, qsrc):
        """
        Wrapper arround owlready2.query_owlready(...) which makes the result a set

        :param qsrc:    query source

        :return:        set of results
        """

        g = self.world.as_rdflib_graph()

        r = g.query_owlready(qsrc)
        res_list = []
        for elt in r:
            # ensure that here each element is a sequences of lenght 1
            assert len(elt) == 1
            res_list.append(elt[0])

        # drop duplicates
        return set(res_list)

    def sync_reasoner(self, **kwargs):
        sync_reasoner_pellet(x=self.world, **kwargs)


def ensure_list(obj, allow_tuple=True):
    """
    return [obj] if obj is not already a list (or optionally tuple)

    :param obj:
    :param allow_tuple:
    :return:
    """
    if isinstance(obj, list):
        return obj

    elif allow_tuple and isinstance(obj, tuple):
        return obj
    elif not allow_tuple and isinstance(obj, tuple):
        return list(obj)
    else:
        return [obj]


def check_type(obj, expected_type):
    """
    Use the pydantic package to check for (complex) types from the typing module.
    If type checking passes returns `True`. This allows to use `assert check_type(...)` which allows to omit those
    type checks (together with other assertations) for performance reasons, e.g. with `python -O ...` .


    :param obj:             the object to check
    :param expected_type:   primitive or complex type (like typing.List[dict])
    :return:                True (or raise an TypeError)
    """

    class Model(pydantic.BaseModel):
        data: expected_type

    # convert ValidationError to TypeError if the obj does not match the expected type
    try:
        Model(data=obj)
    except pydantic.ValidationError as ve:
        raise TypeError(str(ve.errors()))

    return True  # allow constructs like assert check_type(x, List[float])


def unpack_len1_mapping(data_dict: dict) -> tuple:
    assert isinstance(data_dict, dict)
    assert len(data_dict) == 1

    return tuple(data_dict.items())[0]


def create_property(name, property_base_class, characteristics, kwargs) -> owl2.PropertyClass:
    res = type(name, (property_base_class, *characteristics), kwargs)
    assert isinstance(res, owl2.PropertyClass)
    # noinspection PyTypeChecker
    return res


class TreeParseFunction(object):
    """
    This callable object is applied to lists or dicts.

    Lists:
        results = apply self.inner_func to every list element

    Dicts:
        key -> key_func
        results.append(key_func(value))

    """
    def __init__(self, name: str, outer_func: callable, inner_func: callable,
                 om: OntologyManager, resolve_names: bool = True) -> None:
        """

        :param name:
        :param inner_func:
        :param om:              Reference to the ontology manager
        :param resolve_names:   flag whether to resolve the names automatically (otherwise leave this to inner_func)
        om: OntologyManager
        """

        self.name = name
        self.inner_func = inner_func
        self.outer_func = outer_func
        self.om = om
        self.accept_unquoted_strings = False
        self.resolve_names = resolve_names

    def _process_name(self, obj):
        """
        try to resolve the name `obj` or do nothing depending on `self.resolve_names`
        :return:
        """
        if self.resolve_names:
            assert isinstance(obj, str)
            return self.om.resolve_name(obj, self.accept_unquoted_strings)
        else:
            return obj

    def __call__(self, arg, **kwargs):

        if isinstance(arg, list):
            results = [self.inner_func(self._process_name(elt)) for elt in arg]
        elif isinstance(arg, dict):
            results = []
            for key, value in arg.items():
                IPS(key == "owns")
                key_func = self.om.normal_parse_functions.get(key)
                results.append(key_func(value))
        elif isinstance(arg, str):
            return self._process_name(arg)
        else:
            msg = f"unexpected type of value in TreeParseFunction {self.name}."
            raise TypeError(msg)

        return self.outer_func(results)


class PropertyRestrictionParser(object):
    """
    serves to appropriately represent an object like:

    {n.ives_in: {"some": {n.has_color: {"value": n.red}}}}
    """

    def __init__(self, om: OntologyManager) -> None:
        """

        :param om:      Reference to the ontology manager
        """

        self.om = om

    def process_restriction_body(self, data_dict: dict) -> owl2.class_construct.Restriction:
        """
        Convert a raw yaml dict to a restriction object (like `lives_in.some(has_color.value(red)`).

        :param data_dict:

        Assumed situation: Restriction is given by
            {'Subject': ...,
             'Body': {'lives_in': {'some': {'has_color': {'value': 'red'}}}}

        Here we generate the call:
            lives_in.some(has_color.value(red))

        :return: restriction object
        """

        objects, restriction_type_names = self.parse_dict_to_lists(data_dict)
        final_value = objects.pop()
        objects.reverse()
        restriction_type_names.reverse()

        assert len(objects) == len(restriction_type_names)

        arg = final_value  # initialize with the last value (e.g. `red`)
        for restriction_type_name, role_object in zip(restriction_type_names, objects):
            # produce something like `has_color.value(red)`
            restriction = getattr(role_object, lit2str(restriction_type_name))
            arg = restriction(arg)

        evaluated_restriction = arg
        return evaluated_restriction

    def parse_dict_to_lists(self, data_dict: dict) -> Tuple[List, List]:
        """
        Recursive function

        :param data_dict:

        input data example:
            {'lives_in': {'some': {'has_color': {'value': 'red'}} }}

        should finally be converted in a call:

            lives_in.some(has_color.value(red)
        Here we do the preparation.

        :return:    list of objects and list of restriction_type_names
        """

        objects = []  # hold the actual role-objects and the final argument
        restriction_type_names = []  # holds something like "some" or "value"

        key, value = self._unpack_dict(data_dict)

        if key in self.om.roles:
            objects.append(self.om.roles[key])
            assert isinstance(value, dict)

            inner_key, inner_value = self._unpack_dict(value)

            try:
                restriction_type = self.om.restriction_types[inner_key]
            except KeyError:
                msg = f"Malformed restriction: role name {key} must be followed by" \
                      f"restriction type like `some`. Instead got {inner_key}"
                raise ValueError(msg)
            restriction_type_names.append(restriction_type)

            if restriction_type == lit.value:
                assert isinstance(inner_value, (str, int, float))
                if isinstance(inner_value, str):
                    final_value = self.om.resolve_name(inner_value, accept_unquoted_strs=True)
                else:
                    # handle numbers
                    final_value = inner_value
                objects.append(final_value)

            elif restriction_type == lit.some:
                # example for assumed situation: {'some': {'has_color': {'value': 'red'}} }
                # -> inner_value  = {'has_color': {'value': 'red'}}
                assert isinstance(inner_value, dict)

                inner_objects, inner_restriction_type_names = self.parse_dict_to_lists(inner_value)
                objects.extend(inner_objects)
                restriction_type_names.extend(inner_restriction_type_names)

            else:
                msg = f"Unknown restriction_type: {restriction_type}"
                raise ValueError(msg)
        else:
            msg = f"Unknown key: {key}. Expected role name."
            raise ValueError(msg)

        assert len(objects) == len(restriction_type_names) + 1
        return objects, restriction_type_names

    @staticmethod
    def _unpack_dict(data_dict):
        """
        Assume and check a special structure of `data_dict` and return key and value-dict

        :return:
        """
        assert len(data_dict) == 1

        key, value = tuple(data_dict.items())[0]
        check_type(key, str)
        check_type(value, Union[dict, str, int, float])

        return key, value


def lit2str(literal) -> str:
    """
    Convert a Literal (like `Literal["demo"]` to a str like `"demo"`)
    :param literal:
    :return:
    """

    # some dirty typechecking because Type for "unindexed" Literal is hard to access:
    assert "Literal[" in str(literal)

    args = literal.__args__
    assert len(args) == 1
    assert isinstance(args[0], str)
    return args[0]
