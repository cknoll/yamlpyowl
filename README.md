# General Information

This tool (yamlpyowl) arises from the lack of a *fast and simple* way to define an ontology "by hand", i.e. in an ordinary text editor. Its purpose is to read a yaml-file and convert it to datastructures of the package [`owlready2`](https://owlready2.readthedocs.io). From there, a reasoner can be used or the ontology can be exported to standard-owl format *rdfxml*.

Note, there is at least one similar tool already existing: [yaml2owl](https://github.com/leifw/yaml2owl), written in haskel.

# Motivation

All existing OWL2-syntax-dialects (RDF-XML, Turtle, Manchester) seem unpractical for manual authoring. On the other hand, to encourage contributions, e.g. from students, the requirement to learn a sophisticated tool like [Protégé](http://protege.stanford.edu/) seems to be a significant hurdle. See also [this blog post](https://keet.wordpress.com/2020/04/10/a-draft-requirements-catalogue-for-ontology-languages/) from knowledge engineering expert Maria Keet, and especially requirement HU-3: *"Have at least one compact, human-readable syntax defined so that it can be easily typed up in emails."* The tool yamlpyowl aims to explore in that direction.

# Example

The following example is a fragment of the "Pizza-Ontology" which is often used as introduction

```yaml

```
