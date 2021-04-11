import os
import re
import yaml
import pydantic
from typing import Union, List, Dict, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict

# for py3.7: from typing_extensions import Literal

# noinspection PyUnresolvedReferences
import owlready2 as owl2
from owlready2 import (
    Thing,
    FunctionalProperty,
    sync_reasoner_pellet,
    SymmetricProperty,
    TransitiveProperty,
    set_render_func,
)

# noinspection PyUnresolvedReferences
from ipydex import IPS, activate_ips_on_exception

activate_ips_on_exception()


def render_using_label(entity):
    try:
        repr_str1 = entity.label.first() or entity.name
    except IndexError:
        repr_str1 = entity.name or "<no label>"

    return f"<{type(entity).name} '{repr_str1}'>"


set_render_func(render_using_label)
yaml_Atom = Union[str, int, float]
basic_types = (int, float, str)


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
        return f"<Container (len={len(self.__dict__)})>"


# easy access to some important literals
@dataclass
class Lit:
    value: str = "value"  # !introduce typing.Final (after dropping 3.7 support)
    some: str = "some"  # !introduce typing.Final (after dropping 3.7 support)


def identity_func(x):
    return x


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
        self.fpath = fpath
        self.abspath_src = os.path.abspath(fpath)
        self.abspath_dir = os.path.dirname(self.abspath_src)

        # this dict will hold mappings like
        # {"bfo": <bfo_onto_obj>, "http://purl.obolibrary.org/obo/bfo.owl#": <bfo_onto_obj>}
        self.imported_ontologies = {}

        # this implemented in its own class to reduce complexity of this class
        self.property_restriction_parser = PropertyRestrictionParser(self)

        # magic objects which have a special meaning and get a special treatment if defined
        self._RelationConcept = None
        self._RelationConcept_generic_main_role = None  # all other RC_main_roles will be a subclass of this
        self.relation_concept_main_roles = []  # list of all subclasses of self._Relation_Concept
        self.auto_generated_name_numbers = defaultdict(lambda: 0)

        # we cannot store arbitrary python attributes in owl-objects directly, hence we use this dict
        # keys will be tuples of the form: (obj, <attribute_name_as_str>)
        self.custom_attribute_store = {}

        # will be a Container later for quick access to the names of the ontology
        self.n = self.name_mapping_container = None
        self.quoted_string_re = re.compile("(^\".*\"$)|(^'.*'$)")

        # will match "bfo:SomeClass"
        self.ns_compositum_re = re.compile("(^.+:.+$)")

        self._load_yaml(fpath)

        # extract the internationalized resource identifier or use default
        self.iri = self._get_from_all_dicts("iri", "https://w3id.org/yet/undefined/ontology#")
        self.onto = self.world.get_ontology(self.iri)

        self.name_mapping = {
            "owl:Thing": Thing,
            "owl:Nothing": owl2.Nothing,
            "Functional": FunctionalProperty,
            "InverseFunctional": owl2.InverseFunctionalProperty,
            "Symmetric": SymmetricProperty,
            "Transitive": TransitiveProperty,
            "Inverse": owl2.Inverse,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
        }

        self.logic_functions = {
            "Or": owl2.Or,
            "And": owl2.And,
            "Not": owl2.Not,
        }
        self.name_mapping.update(self.logic_functions)

        self.restriction_types = {
            "some": Lit.some,
            "value": Lit.value,
        }
        self.name_mapping.update(self.restriction_types)

        self.top_level_parse_functions = {}
        self.normal_parse_functions = {}
        self.create_tl_parse_function("import", self.process_import)
        self.create_tl_parse_function("annotation", self.process_global_annotation)
        self.create_tl_parse_function("owl_individual", self.make_individual_from_dict)
        self.create_tl_parse_function("owl_multiple_individuals", self.make_multiple_individuals_from_dict)
        self.create_tl_parse_function("owl_class", self.make_class_from_dict)
        self.create_tl_parse_function("multiple_owl_classes", self.make_multiple_classes_from_list)
        self.create_tl_parse_function("owl_object_property", self.make_object_property_from_dict)
        self.create_tl_parse_function("owl_data_property", self.make_data_property_from_dict)
        self.create_tl_parse_function("owl_inverse_property", self.make_inverse_property_from_dict)
        self.create_tl_parse_function("property_facts", self.make_property_facts_from_dict)
        self.create_tl_parse_function("relation_concept_facts", self.make_relation_concept_facts_from_dict)
        self.create_tl_parse_function("restriction", self.add_restriction_from_dict)
        self.create_tl_parse_function("swrl_rule", self.add_swrl_rule_from_dict)
        self.create_tl_parse_function("different_individuals", self.different_individuals)

        self.create_nm_parse_function("types")
        self.create_nm_parse_function_cf("EquivalentTo", struct_wrapper=self.atom_or_And)
        self.create_nm_parse_function("SubClassOf", ensure_list_flag=True)
        self.create_nm_parse_function_cf("Domain", struct_wrapper=self.atom_or_Or, ensure_list_flag=True)
        self.create_nm_parse_function_cf("Range", struct_wrapper=self.atom_or_Or, ensure_list_flag=True)
        self.create_nm_parse_function_cf("Facts", inner_func=self.resolve_key_and_value, resolve_names=False)
        self.create_nm_parse_function_cf("Characteristics")
        self.create_nm_parse_function_cf("Inverse")
        self.create_nm_parse_function_cf("Subject")
        self.create_nm_parse_function_cf("Body")
        self.create_nm_parse_function("annotations", resolve_names=False, ensure_list_flag=True)
        self.create_nm_parse_function("labels", resolve_names=False, ensure_list_flag=True)

        # this function is retrieved manually later
        self.create_nm_parse_function("__rc_facts", inner_func=self.resolve_key_and_value, resolve_names=False)

        # magic attributes:
        self.create_nm_parse_function("X_associatedWithClasses", ensure_list_flag=True)
        self.create_nm_parse_function_cf(
            "X_associatedRoles", inner_func=self.resolve_key_and_value, resolve_names=False
        )

        self.create_nm_flat_parse_function("__create_proxy_individual", identity_func)

        self.create_nm_parse_function("OneOf", outer_func=owl2.OneOf)
        self.create_nm_parse_function("Or", outer_func=owl2.Or)
        self.create_nm_parse_function("And", outer_func=owl2.And)

        self.excepted_non_function_keys = ["iri"]

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

        # ...
        Facts:
            - mypizza1:
                - iTomatoTopping
                - iMozzarellaTopping
        # ...
        Facts:
            - mypizza1:
                - 10
                - 23

        ```
        :param data_dict:
        :return:
        """
        check_type(data_dict, Dict[str, Union[str, list, int, float]])

        # assert len(data_dict) == 1
        # raw_key, raw_value = list(data_dict.items())[0]
        res = {}
        for raw_key, raw_value in data_dict.items():
            key = self.resolve_name(raw_key)

            if isinstance(raw_value, str):
                value = self.resolve_name(raw_value, accept_unquoted_strs=True)
            elif isinstance(raw_value, list):
                value = [self.resolve_name(elt, accept_unquoted_strs=True) for elt in raw_value]
            elif isinstance(raw_value, (float, int)):
                value = raw_value
            else:
                msg = f"Unexpected type: {type(raw_value)} in key-value pair: {data_dict}"
                raise TypeError(msg)

            res[key] = value

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
            struct_wrapper = identity_func

        def outer_func(arg: list) -> OntoContainer:

            res = OntoContainer()

            # this applies the custom callable to the actual data-argument
            # example: struct_wrapper = `atom_or_And`
            res.data = struct_wrapper(arg)

            return res

        return outer_func

    def create_tl_parse_function(self, name: str, func: callable) -> None:
        assert name not in self.top_level_parse_functions
        self.top_level_parse_functions[name] = func

    def create_nm_parse_function_cf(self, name: str, **kwargs) -> None:
        """
        create a container factory (cf) that is used as a `outer_func` in the a parse function

        :param name:    name of the keyword
        """

        inner_func = kwargs.pop("inner_func", None)
        resolve_names = kwargs.pop("resolve_names", True)

        ensure_list_flag = kwargs.pop("ensure_list_flag", False)
        outer_func = self.containerFactoryFactory(name, **kwargs)
        self.create_nm_parse_function(
            name,
            outer_func=outer_func,
            inner_func=inner_func,
            resolve_names=resolve_names,
            ensure_list_flag=ensure_list_flag,
        )

    def create_nm_parse_function(
        self, name: str, outer_func=None, inner_func=None, resolve_names=True, ensure_list_flag=False
    ) -> None:
        """

        :param name:
        :param outer_func:          see TreeParseFunction
        :param inner_func:          see TreeParseFunction
        :param resolve_names:       see TreeParseFunction
        :param ensure_list_flag:    see TreeParseFunction
        :return:
        """

        if outer_func is None:
            outer_func = identity_func
        if inner_func is None:
            inner_func = identity_func
        assert name not in self.top_level_parse_functions
        self.normal_parse_functions[name] = TreeParseFunction(
            name, outer_func, inner_func, self, resolve_names=resolve_names, ensure_list_flag=ensure_list_flag
        )

    def create_nm_flat_parse_function(
        self,
        name: str,
        func: callable,
    ) -> None:
        """
        Add new parse function to self.normal_parse_functions.
        Unlike the mostly used tree parse functions this function here is not intended to be applied to dicts or lists,
        but to flat data instead.

        :param name:
        :param func:    callable
        :return:        None (but has side effects)
        """

        assert name not in self.top_level_parse_functions
        self.normal_parse_functions[name] = func

    def cas_get(self, key, default=None):
        return self.custom_attribute_store.get(key, default)

    def cas_set(self, key, value):
        self.custom_attribute_store[key] = value

    def resolve_name(self, object_or_name: yaml_Atom, accept_unquoted_strs=False):
        """
        Try to find object_name in `self.name_mapping` if it is not a number or a string literal.
        Raise Exception if not found.

        :param object_or_name:
        :param accept_unquoted_strs:    boolean (default=False). Specify whether unquoted strings which are no valid
                                        names should provoke an error (default) or should be returned as they are
        :return:
        """

        if isinstance(object_or_name, (float, int)):
            return object_or_name
        elif isinstance(object_or_name, str) and self.quoted_string_re.match(object_or_name):
            # quoted strings are not interpreted as names
            # note that one pair of quotes is stripped away by the yaml-parser.
            # to get a quoted string your yaml source code has to look like: `key: "'value'"`
            return object_or_name
        elif isinstance(object_or_name, str):

            res, success = self._resolve_name(name=object_or_name)
            if success:
                return res

            else:
                if accept_unquoted_strs:
                    return object_or_name
                else:
                    raise UnknownEntityError(f"unknown entity name: {object_or_name}")
        else:
            msg = (
                f"unexpected type ({type(object_or_name)}) of object <{object_or_name}>"
                "in method resolve_name (expected str, int or float)"
            )
            raise TypeError(msg)

    def _resolve_name(self, name: str) -> Tuple[Any, bool]:
        """
        Try to resolve `name` in the current namspace or in that of an imported ontology

        :param name:
        :return:
        """
        res = None
        success = False

        if name in self.name_mapping:
            res = self.name_mapping[name]
            success = True
        elif self.ns_compositum_re.match(name):
            ## !! #:marker01b: this is partially redundand with #:marker01a
            for ns, imported_onto in self.imported_ontologies.items():
                if name.startswith(ns):
                    rest_name = name.replace(ns, "")
                    res = getattr(imported_onto, rest_name)

                    success = res is not None
                    break

        return res, success

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

        return self._create_individual(individual_name, types)

    def _create_individual(self, individual_name: str, types: List[owl2.ThingClass]) -> owl2.Thing:

        main_type = types[0]
        ind = main_type(name=individual_name)

        if len(types) > 1:
            # !! maybe handle multiple types
            raise NotImplementedError

        self.name_mapping[individual_name] = ind
        return ind

    def make_multiple_individuals_from_dict(self, data_dict: dict):
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
        parent_class_list = processed_inner_dict.get("SubClassOf", [owl2.Thing])
        check_type(parent_class_list, List[owl2.ThingClass])
        assert len(parent_class_list) >= 1
        main_parent_class = parent_class_list[0]

        # create the class
        new_class = type(class_name, (main_parent_class,), {})

        # handle further parent_classes:
        # noinspection PyUnresolvedReferences
        new_class.is_a.extend(parent_class_list[1:])

        self.name_mapping[class_name] = new_class
        self.concepts.append(new_class)

        annotations = processed_inner_dict.get("annotations")  # !! introduce walrus operator
        if annotations:
            new_class.comment = ensure_list(annotations)

        labels = processed_inner_dict.get("labels")  # !! introduce walrus operator
        if labels:
            # note the subtle difference between `.labels` and `label`
            new_class.label = ensure_list(labels)

        equivalent_to = processed_inner_dict.get("EquivalentTo")  # !! introduce walrus operator
        if equivalent_to:

            # noinspection PyUnresolvedReferences
            new_class.equivalent_to.extend(ensure_list(equivalent_to.data))

        assert isinstance(new_class, owl2.entity.ThingClass)
        self._handle_relation_concept_magic(class_name, new_concept=new_class, pid=processed_inner_dict)
        self._handle_proxy_individuals(new_class, processed_inner_dict)
        return new_class

    def _handle_relation_concept_magic(self, name: str, new_concept: owl2.ThingClass, pid: dict) -> None:
        """
        Decide whether the respective concept is the root "RelationConcept" or a subclass of it.
        See Background information below:

        :param name:
        :param new_concept:
        :param pid:             processed inner dict

        :return:  None

        Background:
        OWL only allows binary relations. The workaround to model n-ary relations is to introduce special
        classes

        """

        if name == "X_RelationConcept":
            assert self._RelationConcept is None
            self._RelationConcept = new_concept
            assert self._RelationConcept_generic_main_role is None
            self._RelationConcept_generic_main_role = self.make_object_property_from_dict(
                {"generic_RC_main_role": {"Domain": "owl:Thing", "Range": "owl:Thing"}}
            )

        elif self._RelationConcept and issubclass(new_concept, self._RelationConcept):
            # this is a subclass of X_RelationConcept - automatically create roles
            if not name.startswith("X_"):
                msg = "Names of subclasses of `X_RelationConcept` are expected to start with `X_`."
                raise ValueError(msg)
            # noinspection PyTypeChecker
            self._create_rc_roles(new_concept, name, concept_data=pid)

    def _create_rc_roles(self, relation_concept, concept_name, concept_data):
        """
        Automatically create roles for relation concept
        :param concept_name:
        :param concept_data:
        :return:
        """
        assert self._RelationConcept in relation_concept.is_a
        assert concept_name[:2] == "X_"
        assert "X_associatedWithClasses" in concept_data

        # create the main role for this RelationConcept
        main_role_name = f"X_has{concept_name[2:]}"
        main_role_domain_list = concept_data["X_associatedWithClasses"]
        check_type(main_role_domain_list, List[Union[owl2.ThingClass, owl2.class_construct.ClassConstruct]])

        main_role = self.make_object_property_from_dict(
            {
                main_role_name: {
                    "Domain": main_role_domain_list,
                    "Range": [relation_concept],
                    "__content_is_parsed": True,
                }
            }
        )
        # the main role should be a subclass of self._RelationConcept_generic_main_role
        # noinspection PyUnresolvedReferences
        main_role.is_a.append(self._RelationConcept_generic_main_role)

        self.relation_concept_main_roles.append(main_role)

        # create further roles by processing yaml-code like
        # X_associatedRoles:
        #     # key-value pairs (<role name>: <range type>)
        #     - hasDocument: Document
        #     - hasSection: str

        # these roles are represented as dicts of length 1, assembled in a list
        further_roles_list = concept_data.get("X_associatedRoles")

        if not further_roles_list:
            return

        for further_role_container in further_roles_list:

            len1dict = further_role_container.data
            check_type(len1dict, Dict[owl2.PropertyClass, owl2.ThingClass])
            assert len(len1dict) == 1

            # further_role_object, further_role_range = list(len1dict.items())[0]
            # this is some dead end because the modeling approach was not continued
            raise NotImplementedError

    def _handle_proxy_individuals(self, new_class, processed_inner_dict):
        """
        To use classes in like individuals a possible workaround is to introduce "generic individuals" which act as
        proxy for their class.
        This is necessary, because meta classes and punning is not supported by owlready.

        :param new_class:
        :param processed_inner_dict:
        :return:
        """

        flag_key = "__create_proxy_individual"
        first_parent_class = new_class.is_a[0]

        flag_value = processed_inner_dict.get(flag_key)
        if flag_value is False:
            return
        elif flag_value is None:
            parent_value = self.cas_get((first_parent_class, flag_key), False)
            if parent_value == "recursive":
                flag_value = parent_value
            else:
                return
        flag_value = str(flag_value)
        allowed_values = ["True", "recursive"]
        if flag_value not in allowed_values:
            msg = f"For the flag {flag_key} only the following values are allowed: f{allowed_values}."
            raise ValueError(msg)
        self.cas_set((new_class, flag_key), flag_value)

        ind_name = f"i{new_class.name}"
        # noinspection PyUnusedLocal
        proxy_individual = new_class(name=ind_name)

    def make_multiple_classes_from_list(self, dict_list: List[dict]) -> List[owl2.entity.ThingClass]:
        check_type(dict_list, List[dict])
        res = []
        for data_dict in dict_list:
            res.append(self.make_class_from_dict(data_dict))

        return res

    def make_object_property_from_dict(self, data_dict: dict) -> owl2.PropertyClass:
        return self._create_property_from_dict_and_type(data_dict, owl2.ObjectProperty)

    def make_data_property_from_dict(self, data_dict: dict) -> owl2.PropertyClass:
        return self._create_property_from_dict_and_type(data_dict, owl2.DataProperty)

    def _create_property_from_dict_and_type(self, data_dict: dict, property_base_class) -> owl2.PropertyClass:

        name, inner_dict = unpack_len1_mapping(data_dict)

        if not inner_dict.get("__content_is_parsed"):
            # data_dict is raw (un-parsed)
            processed_inner_dict = self.process_tree(inner_dict)
            range_ = ensure_list(processed_inner_dict["Range"].data)
            domain = ensure_list(processed_inner_dict["Domain"].data)
        else:
            # the method was called from somewhere, where parsing already took place
            processed_inner_dict = inner_dict
            range_ = ensure_list(processed_inner_dict["Range"])
            domain = ensure_list(processed_inner_dict["Domain"])

        characteristics_container = processed_inner_dict.get("Characteristics")  # !! introduce walrus operator
        if characteristics_container:
            characteristics = characteristics_container.data
        else:
            characteristics = []

        kwargs = {"domain": domain, "range": range_}
        new_property = create_property(name, property_base_class, characteristics, kwargs)
        self.name_mapping[name] = new_property
        self.roles[name] = new_property

        self.process_property_facts(new_property, processed_inner_dict)

        # noinspection PyTypeChecker
        return new_property

    def make_inverse_property_from_dict(self, data_dict: dict) -> owl2.PropertyClass:
        """

        :param data_dict:
        :return:
        """

        # TODO
        """
        Instead of 
        - owl_inverse_property:
            left_to:
                Inverse: right_to
                
        We should specify:
        - owl_object_property:
            left_to:
                Characteristics:
                    - Functional
                    - InverseFunctional
    
                Domain: "owl:Thing"
                Range: "owl:Thing"
                Inverse: right_to
        """

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

    def process_property_facts(self, prop: owl2.PropertyClass, processed_inner_dict: dict) -> None:
        facts = processed_inner_dict.get("Facts")  # !! introduce walrus operator
        if facts:
            fact_data = facts.data
        else:
            fact_data = []

        for fact in fact_data:
            key, value = unpack_len1_mapping(fact)

            # check if all values have the right type
            for val in ensure_list(value):
                if isinstance(prop, owl2.ObjectPropertyClass) and not isinstance(
                    val, (owl2.Thing, owl2.entity.ThingClass)
                ):
                    msg = (
                        f"Unexpected type for property {prop}: `{val}` type: ({type(val)}). "
                        f"Expected an instance of `owl:Thing` or  `<owl:Nothing>`. \n"
                        f"Probable cause: unresolved key `{val}`."
                    )
                    raise TypeError(msg)

            if prop.is_functional_for(key):
                if isinstance(value, list):
                    msg = (
                        f"While assigning range-value of functional property `{prop.name}`: Expected scalar "
                        f"type from {prop.range} but instead got list: {value}"
                    )
                    raise TypeError(msg)
                try:
                    setattr(key, prop.name, value)
                except AttributeError as err:
                    # account for a (probable) bug in owlready2 related to inverse_property and owl:Nothing
                    # whose .__dict__ attribute is a `mapping_proxy` object which has no `.pop` method
                    if "'mappingproxy' object has no attribute 'pop'" in err.args[0]:
                        pass
                    else:
                        # something different went wrong
                        self._handle_data_property_error(prop, value, err)
            else:
                try:
                    getattr(key, prop.name).extend(ensure_list(value))
                except AttributeError as err:
                    self._handle_data_property_error(prop, value, err)

    def make_relation_concept_facts_from_dict(self, data_dict: dict) -> None:
        """

        :param data_dict:   example:
                            {"dir_rule1": {"X_hasDocumentReference_RC": ["hasSourceDocument": "law_book_of_germany"]}}

        :return:
        """

        parse_function = self._resolve_yaml_key(self.normal_parse_functions, "__rc_facts")

        for indiv_name, inner_dict in data_dict.items():
            indiv = self.resolve_name(indiv_name)
            processed_inner_dict = self.process_tree_with_entity_keys(inner_dict, parse_function)
            self.process_relation_concept_facts(indiv, processed_inner_dict)

    def process_relation_concept_facts(
        self, indiv: owl2.Thing, pid: Dict[owl2.prop.ObjectPropertyClass, List[dict]]
    ) -> None:
        """

        :param indiv:   individual to which the fact relates
        :param pid:     parsed_inner_dict (arbitrary length); Values are lists of len-n dicts

        :return:        None
        """

        for rc_prop, inner_dict_list in pid.items():
            if not isinstance(rc_prop, owl2.prop.PropertyClass):
                msg = f"Expected `PropertyClass` but got {type(rc_prop)}"
                raise TypeError(msg)
            relation_concept = rc_prop.range[0]

            check_type(inner_dict_list, List[Dict[owl2.PropertyClass, Union[yaml_Atom, owl2.Thing]]])
            if len(inner_dict_list) == 0:
                continue

            for inner_dict in inner_dict_list:
                # for every new inner dict there must be a new relation concept.
                # Each dict models a distinct relation
                rc_indiv = self._create_new_relation_concept(relation_concept)
                # equivalent to `dir_rule1.X_hasDocumentReference_RC.append(iX_DocumentReference_RC_0)
                getattr(indiv, rc_prop.name).append(rc_indiv)

                for prop, value in inner_dict.items():
                    assert isinstance(value, basic_types + (owl2.Thing,))
                    # equivalent to `iX_DocumentReference_RC_0.hasSection.append("§ 1.1")
                    assert hasattr(rc_indiv, prop.name)
                    try:
                        if prop.is_functional_for(value):
                            setattr(rc_indiv, prop.name, value)
                        else:
                            # prop is not a functional
                            getattr(rc_indiv, prop.name).append(value)
                    except AttributeError as err:
                        self._handle_data_property_error(prop, value, err)

    @staticmethod
    def _handle_data_property_error(prop: owl2.PropertyClass, value: Any, original_err: Exception):
        value = ensure_list(value)[0]
        if isinstance(prop, owl2.ObjectPropertyClass) and isinstance(value, basic_types):
            msg = (
                f"Unable to store value of type {type(value)} to ObjectProperty {prop.name}. "
                f"Probably this should be a DataProperty instead. The original error was:\n\n"
                f"{str(original_err)}"
            )
            raise TypeError(msg)
        else:
            raise original_err

    def _create_new_relation_concept(self, rc_type):
        """
        Create an RC individual (the relations are added later).

        :param rc_type:
        :return:
        """
        # generate name, create individual with role assignments
        n = self.auto_generated_name_numbers[rc_type]
        self.auto_generated_name_numbers[rc_type] += 1
        relation_name = f"i{rc_type.name}_{n}"

        relation_individual = self._create_individual(relation_name, [rc_type])

        return relation_individual

    def process_tree_with_entity_keys(
        self,
        normal_dict: Dict[str, Union[list, dict, yaml_Atom]],
        parse_function: callable,
    ) -> dict:
        """
        Interpret the keys of the input dict as entities

        :param normal_dict:         data_dict (expected to be not a top_level dict)
        :param parse_function:      function which is applied to each value of the dict)
        :return:
        """

        assert len(normal_dict) > 0
        res = {}

        for key, value in normal_dict.items():
            key_entity = self.resolve_name(key)
            parsed_value = parse_function(value)
            res[key_entity] = parsed_value

        return res

    def process_tree(
        self,
        normal_dict: dict,
        squeeze=False,
        parse_functions: dict = None,
    ) -> Union[Dict[str, Any], List[owl2.entity.ThingClass]]:
        """
        Determine parse_function from  a (standard or custom) dict-key and apply it the value

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
        key = None
        for key, value in normal_dict.items():
            key_func = self._resolve_yaml_key(parse_functions, key)

            try:
                res[key] = key_func(value)
            except UnknownEntityError as err:
                msg = f"{err.args[0]} while processing dict: {normal_dict}"
                raise UnknownEntityError(msg)

        if squeeze:
            assert len(res) == 1
            res = res[key]

        return res

    def different_individuals(self, data_list: list) -> None:
        check_type(data_list, List[str])

        individuals = []
        for elt in data_list:
            if elt == "__all__":
                individuals = list(self.onto.individuals())
                break
            else:
                indiv = self.resolve_name(elt)
                assert isinstance(indiv, owl2.Thing)
                individuals.append(indiv)

        owl2.AllDifferent(individuals)

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
        self.add_restriction_to_entity(evaluated_restriction, subject)

        # returning something is currently not necessary

    def add_restriction_to_entity(self, rstrn: owl2.class_construct.Restriction, indv: owl2.Thing) -> None:

        assert isinstance(rstrn, owl2.class_construct.Restriction)

        if rstrn.storid is None:
            # this should mitigate a bug in owlready (my current understanding)
            rstrn.storid = self.onto.world.new_blank_node()

        indv.is_a.append(rstrn)

    def add_swrl_rule_from_dict(self, data_dict: Dict[str, str]) -> None:
        """
        Construct the swrl-rule-object (Semantic Web Rule Language) from the raw yaml data

        Related yaml-code:
        ```yaml
        - swrl_rule:
            name: top_down
            label: "Meaning: A directive which is valid in a GeographicEntity is valid in all its parts as well"
            rule_src: "GeographicEntity(?ge), hasPart(?ge, ?p), hasDirective(?ge, ?r) -> hasDirective(?p, ?r)"
        ```

        :param data_dict:   un-parsed dict of strings

        :return:        None
        """

        rule_name = self._resolve_yaml_key(data_dict, "name")
        rule_src = self._resolve_yaml_key(data_dict, "src")

        # create the instance
        new_rule = owl2.Imp()
        new_rule.set_as_rule(rule_src)
        self.rules.append(new_rule)

        self.name_mapping[rule_name] = new_rule

    def process_import(self, data_dict: Dict[str, str]) -> None:

        try:
            imported_iri = data_dict["iri"]
        except KeyError:
            msg = f"Could not find IRI for import. Dict: {data_dict}"
            raise KeyError(msg)

        localpath = data_dict.get("localpath")
        if localpath:
            assert not localpath.endswith(".yml")  # this is not yet supported

            if os.path.isabs(localpath):
                localpath_abs = localpath
            else:
                localpath_abs = os.path.abspath(os.path.join(self.abspath_dir, localpath))

            imported_onto = self.world.get_ontology(localpath_abs).load()
        else:
            imported_onto = self.world.get_ontology(imported_iri).load()

        if imported_onto.base_iri != imported_iri:
            # !! Todo: this should be a UserWarning
            msg = (
                f"There is a mismatch beween imported and expected iri:\n\n"
                f"  {imported_onto.base_iri} != {imported_iri}\n"
            )
            print(msg)

        self.imported_ontologies[imported_iri] = imported_onto

        ns = data_dict.get("ns", "")  # !! introduce walrus operator
        if ns:
            if not ns.endswith(":"):
                ns = f"{ns}:"
            self.imported_ontologies[ns] = imported_onto

        # !! TODO: this should be also done for properties and individuals
        ## !! #:marker01a: this is partially redundand with #:marker01b
        for klass in imported_onto.classes():
            self.name_mapping[f"{ns}{klass.name}"] = klass

        self.onto.imported_ontologies.append(imported_onto)

    def process_global_annotation(self, annotation_str: str) -> None:
        check_type(annotation_str, str)
        self.onto.metadata.comment.append(annotation_str)

    # noinspection PyPep8Naming
    def _load_yaml(self, fpath):
        with open(fpath, "r") as myfile:
            self.raw_data = yaml.safe_load(myfile)

        assert check_type(self.raw_data, List[dict])

    def _get_from_all_dicts(self, key, default=None):
        """
        Assumes that self.raw_data is a sequence of dicts. Creates the union of all dicts and retrieves the value
        according to `key`

        :param key:
        :param default:
        :return:
        """
        # src: https://stackoverflow.com/questions/9819602/union-of-dict-objects-in-python#comment23716639_12926008
        all_dicts = dict(item for dct in self.raw_data for item in dct.items())
        return all_dicts.get(key, default)

    @staticmethod
    def _resolve_yaml_key(data_dict, key):
        """
        This method should unify the error messages when a key is not found.

        :param data_dict:
        :param key:
        :return:
        """

        if key not in data_dict:
            msg = f"Key `{key}` not found in current part of in yaml-file: \ncomplete data:\n{data_dict}"
            raise KeyError(msg)

        return data_dict[key]

    def load_ontology(self):

        # provide namespace for classes via `with` statement
        res = []
        with self.onto:

            for top_level_dict in self.raw_data:
                assert check_type(top_level_dict, Dict[str, Union[str, dict, list]])
                assert len(top_level_dict) == 1
                key, inner_dict = list(top_level_dict.items())[0]

                if key in self.excepted_non_function_keys:
                    continue

                # get function or fail gracefully
                tl_parse_function = self._resolve_yaml_key(self.top_level_parse_functions, key)

                # now call the matching function
                try:
                    parsing_res = tl_parse_function(inner_dict)
                except Exception as err:
                    # assuming first arg to be the error message
                    try:
                        old_message = err.args[0]
                    except IndexError:
                        old_message = ""

                    new_message = f"{old_message}\n\nThis error occurred while parsing the `inner_dict`: {inner_dict}."
                    err.args = (new_message, *err.args[1:])
                    raise err
                res.append(parsing_res)

        # shortcut for quick access to the name of the ontology
        self.n = self.name_mapping_container = Container(self.name_mapping)

    def make_query(self, qsrc):
        """
        Wrapper around owlready2.query_owlready(...) which makes the result a set

        :param qsrc:    query source

        :return:        set of results
        """

        g = self.world.as_rdflib_graph()

        r = g.query_owlready(qsrc)
        res_list = []
        for elt in r:
            # ensure that here each element is a sequences of length 1
            assert len(elt) == 1
            res_list.append(elt[0])

        # drop duplicates
        return set(res_list)

    def sync_reasoner(self, debug=False, **kwargs):
        sync_reasoner_pellet(x=self.world, debug=debug, **kwargs)


def ensure_list(obj: Any, allow_tuple: bool = True) -> Union[list, tuple]:
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
    type checks (together with other assertions) for performance reasons, e.g. with `python -O ...` .


    :param obj:             the object to check
    :param expected_type:   primitive or complex type (like typing.List[dict])
    :return:                True (or raise an TypeError)
    """

    class Model(pydantic.BaseModel):
        data: expected_type

        class Config:
            # necessary because https://github.com/samuelcolvin/pydantic/issues/182
            # otherwise check_type raises() an error for types as Dict[str, owl2.Thing]
            arbitrary_types_allowed = True

    # convert ValidationError to TypeError if the obj does not match the expected type
    try:
        Model(data=obj)
    except pydantic.ValidationError as ve:
        msg = (
            f"Unexpected type. Got: {type(obj)}. Expected: {expected_type}. "
            f"Further Information:\n {str(ve.errors())}"
        )
        raise TypeError(msg)

    return True  # allow constructs like assert check_type(x, List[float])


def unpack_len1_mapping(data_dict: dict) -> tuple:
    assert isinstance(data_dict, dict)
    assert len(data_dict) == 1

    return tuple(data_dict.items())[0]


def create_property(
    name: str,
    property_base_class: owl2.prop.PropertyClass,
    characteristics: List[owl2.prop.PropertyClass],
    kwargs: dict,
) -> owl2.PropertyClass:
    """

    :param name:                    name of the property: (e.g. "has_color")
    :param property_base_class:     e.g. ObjectProperty or DataProperty
    :param characteristics:         e.g. [<FunctionalProperty>, <TransitiveProperty>]
    :param kwargs:                  e.g. {'domain': <Thing>, 'range': <Thing>}


    :return:    the property object
    """
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

    def __init__(
        self,
        name: str,
        outer_func: callable,
        inner_func: callable,
        om: OntologyManager,
        resolve_names: bool = True,
        ensure_list_flag: bool = False,
    ) -> None:
        """

        :param name:
        :param outer_func:          callable that is applied to the whole result
        :param inner_func:          callable that is applied to every element of the sequence right after parsing
        :param om:                  Reference to the ontology manager
        :param resolve_names:       flag whether to resolve the names automatically (otherwise leave this to inner_func)
        :param ensure_list_flag:    flag whether treat plain strings as len-1 List[str]
        om: OntologyManager
        """

        self.name = name
        self.inner_func = inner_func
        self.outer_func = outer_func
        self.om = om
        self.accept_unquoted_strings = False
        self.resolve_names = resolve_names
        self.ensure_list_flag = ensure_list_flag

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
                key_func = self.om.normal_parse_functions.get(key)
                results.append(key_func(value))
        elif isinstance(arg, str):
            if self.ensure_list_flag:
                # this makes it convenient to use plain strings instead of len1-lists
                return self.__call__([arg], **kwargs)
            else:
                # the string should be either interpreted as name or as string-literal
                # Note that it is no passed through outer_func nor inner_func
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
        self.objects = None
        self.restriction_type_names = None
        self.valid_restriction_types = (Lit.value, Lit.some)

    def process_restriction_body(self, data_dict: dict) -> owl2.class_construct.Restriction:
        """
        Convert a raw yaml dict to a restriction object (like `lives_in.some(has_color.value(red)`).

        :param data_dict:

        Assumed situation: Restriction is given by
            {'Subject': ...,
             'Body': {'lives_in': {'some': {'has_color': {'value': 'red'}}}}

        Here we handle the `Body: {...}`-dict to generate the call:
            lives_in.some(has_color.value(red))

        :return: restriction object
        """

        # this fills `self.objects` and `self.restriction_type_names`
        self.parse_dict_to_lists(data_dict, init=True)

        final_value = self.objects.pop()
        self.objects.reverse()
        self.restriction_type_names.reverse()

        assert len(self.objects) == len(self.restriction_type_names)

        arg = final_value  # initialize with the last value (e.g. `red`)
        for restriction_type_name, role_object in zip(self.restriction_type_names, self.objects):
            # produce something like `has_color.value(red)`
            assert restriction_type_name in self.valid_restriction_types
            restriction = getattr(role_object, restriction_type_name)
            arg = restriction(arg)

        evaluated_restriction = arg
        return evaluated_restriction

    def parse_dict_to_lists(self, data_dict: dict, init: bool = False) -> None:
        """
        Recursive function

        :param init:
        :param data_dict:

        input data example:
            {'lives_in': {'some': {'has_color': {'value': 'red'}} }}

        should finally be converted in a call:

            lives_in.some(has_color.value(red)
        Here we do the preparation.

        :return:    list of objects and list of restriction_type_names
        """

        if init:
            self.objects = []  # hold the actual role-objects and the final argument
            self.restriction_type_names = []  # holds something like "some" or "value"

        key, value = self._unpack_dict(data_dict)

        if key in self.om.roles:
            self.objects.append(self.om.roles[key])
            self._process_role_value_dict(key, value)

        elif key == "Inverse":
            # assumed situation (example for data_dict):
            # {'Inverse': {'drinks': {'some': {'lives_in': {'some': {'has_color': {'value': 'green'}}}}}}}
            inner_key, inner_value = self._unpack_dict(value)
            try:
                role = self.om.roles[inner_key]
            except KeyError:
                msg = f"A role name is expected after `Inverse:`. Instead got {inner_key}."
                raise ValueError(msg)

            # ensure that the final call is `Inverse(drinks).some(...)`
            self.objects.append(owl2.Inverse(role))

            # Assumption for inner_value:
            # {'some': {'lives_in': {'some': {'has_color': {'value': 'green'}}}}}
            assert isinstance(inner_value, dict)
            self._process_role_value_dict(key, inner_value)

        else:
            msg = f"Unknown key: {key}. Expected role name."
            raise ValueError(msg)

        assert len(self.objects) == len(self.restriction_type_names) + 1
        # return self.objects, self.restriction_type_names

    def _process_role_value_dict(self, role_name: str, value_dict: dict) -> None:
        """

        :param role_name:   str; only need for error messages
        :param value_dict:  the dict which should be parsed

        :return:    None (but extends `self.objects` etc.)
        """
        assert isinstance(value_dict, dict)
        inner_key, inner_value = self._unpack_dict(value_dict)

        try:
            restriction_type = self.om.restriction_types[inner_key]
        except KeyError:
            msg = (
                f"Malformed restriction: role name {role_name} must be followed by"
                f"restriction type like `some`. Instead got {inner_key}"
            )
            raise ValueError(msg)
        self.restriction_type_names.append(restriction_type)

        if restriction_type in self.valid_restriction_types:
            assert isinstance(inner_value, (dict, str, int, float))
            if isinstance(inner_value, str):
                final_value = self.om.resolve_name(inner_value, accept_unquoted_strs=True)
                self.objects.append(final_value)
            elif isinstance(inner_value, (int, float)):
                # handle numbers
                final_value = inner_value
                self.objects.append(final_value)
            else:
                # example for assumed situation: {'some': {'has_color': {'value': 'red'}} }
                # -> inner_value  = {'has_color': {'value': 'red'}}
                # different example (total body-dict):
                assert isinstance(inner_value, dict)
                assert restriction_type == Lit.some
                self.parse_dict_to_lists(inner_value)

        else:
            msg = f"Unknown restriction_type: {restriction_type}"
            raise ValueError(msg)

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
