[![Build Status](https://cloud.drone.io/api/badges/cknoll/yamlpyowl/status.svg)](https://cloud.drone.io/cknoll/yamlpyowl)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# General Information

This tool (yamlpyowl) aims to read an ontology (including indivduals and SWRL rules) specified via the simple and widespread data-serialization language [YAML](https://en.wikipedia.org/wiki/YAML) and represent it as collection of python-objects via the package [`owlready2`](https://owlready2.readthedocs.io). From there, a reasoner can be used or the ontology can be exported to standard-owl format *rdfxml*.

Note, there is at least one similar tool already existing: [yaml2owl](https://github.com/leifw/yaml2owl), written in haskel.

# Motivation

All existing OWL2-syntax-dialects (RDF-XML, Turtle, Manchester) seem unpractical for manual authoring. On the other hand, to encourage contributions, e.g. from students, the requirement to learn a sophisticated tool like [Protégé](http://protege.stanford.edu/) or at least some *exotic* syntax seems to be a significant hurdle. See also [this blog post](https://keet.wordpress.com/2020/04/10/a-draft-requirements-catalogue-for-ontology-languages/) from knowledge engineering expert Maria Keet, and especially requirement HU-3: *"Have at least one compact, human-readable syntax defined so that it can be easily typed up in emails."* The tool yamlpyowl aims to explore in that direction. It relies on the widespread human-readable data-serialization language [YAML](https://en.wikipedia.org/wiki/YAML).

# Example

The following example is a strongly simplified fragment of the "Pizza-Ontology" which is often used as introduction.

```yaml
owl_concepts:
    Food:
        subClassOf: Thing
    # ---
    Pizza:
        subClassOf: Food
    # ---
    PizzaTopping:
        subClassOf: Food
        _createGenericIndividual: True
    MozarellaTopping:
        subClassOf: PizzaTopping
    TomatoTopping:
        subClassOf: PizzaTopping
    # ---
    Spiciness:
        subClassOf: Thing

owl_roles:
    hasSpiciness:
        mapsFrom: Thing
        mapsTo: Spiciness
        properties:
              - FunctionalProperty

    hasTopping:
        mapsFrom: Pizza
        mapsTo: Food

owl_individuals:
    iTomatoTopping:
        # note: this could be omited by autogeneration of generic individuals
        isA: TomatoTopping
    mypizza1:
        isA: Pizza
        hasTopping:
            - iTomatoTopping
```

More examples can be found in the [examples](examples) directory.


# Convenience Features

*yamlpyowl* implements some "magic" convenience features. To be easily recognizable the corresponding keywords all start with `X_`.

## Automatic Creation of "Generic Individuals"

If a concept *SomeConcept* specifies `X_createGenericIndividual=True` in yaml, then there will be a individual named *iSomeConcept* which is an instance of *SomeConcept* automatically added to the ontology. This allows to easily reference concepts like *MozarellaTopping* where the individual does not carry significant information.

Example: see [pizza-ontology.yml](examples/pizza-ontology.yml)

## RelationConcepts to Simplify n-ary Relations

The concept name `X_RelationConcept` has a special meaning. It is used to simplify the creation of n-ary relations. In OWL it is typically required to create a own concept for such relations and an instance (individual) for each concrete relation, see this [W3C Working Group Note](https://www.w3.org/TR/swbp-n-aryRelations/#pattern1).

The paser of *yamlpyowl* simplifies this: For every subclass of `X_RelationConcept` (which must start with `X_`and by convention should end with `_RC`, e.g. `X_DocumentReference_RC`)) the parser automatically creates a role `X_hasDocumentReference_RC`. Its domain can be specified with the attribute `X_associatedWithClasses`. The roles which can be applied to this concept are conveniently specified with the attribute `X_associatedRoles`. These roles are also created automatically. They are assumed to be functional.

Short Example:

```yaml
X_DocumentReference_RC:
    subClassOf: X_RelationConcept
    # note: yamlpyowl will automatically create a role `hasDocumentReference_RC`
    X_associatedWithClasses:
        - Directive
    X_associatedRoles:
        # FunctionalRoles; key-value pairs (<role name>: <range type>)
        hasDocument: Document
        hasSection: str
```


In the definition of an individual one can then use
```yaml
myindividual1:
    isA: Direcitve
    X_hasDocumentReference_RC:
            hasDocument: law_book_of_germany
            hasSection: "§ 1.1"

```

This construction automatically creates an individual of class `_DocumentReference_RC` and endows it with the roles  `hasDocument` and `hasSection`

Example: see [regional-rules-ontology.yml](examples/regional-rules-ontology.yml)

## Development Status

This package is currently an early prototype and will likely be expanded (and changed) in the future. If you are interested in contributing or have a feature request please contact the author or open an issue.
