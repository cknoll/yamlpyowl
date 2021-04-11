# command line interface for yamlpyowl

import argparse
import time
import os
from ipydex import IPS
import yamlpyowl as ypo


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("inputfile", help="yaml file which should be processed")

    # optionales argument
    parser.add_argument("-c", "--convert-to-owl-rdf", help="convert to owl rdf format", action="store_true")
    parser.add_argument("-o", "--output", help="optional path of output (otherwise it is derived from the input path)")
    parser.add_argument("-i", "--interactive", help="start interactive shell")
    parser.add_argument("-f", "--force", help="override security preventions", action="store_true")
    args = parser.parse_args()

    if args.convert_to_owl_rdf:
        convert_to_owl_rdf(args)
    elif args.interactive:
        om = ypo.OntologyManager(args.inputfile)
        IPS()
    else:
        print("nothing to do")


def convert_to_owl_rdf(args):

    om = ypo.OntologyManager(args.inputfile)
    op_fname = args.output

    if not op_fname:
        if args.inputfile.endswith(".owl.yml"):
            op_fname = args.inputfile[:-4]
        else:
            op_fname = f"{args.inputfile}.owl"

    if os.path.exists(op_fname) and not args.force:
        print(f"The ouput file {op_fname} already exists. Use option `--force` to overwrite it.")
        exit()
    else:
        msg = (
            f"This file was automatically created by yamlpyowl on {time.strftime(r'%Y-%m-%d %H:%M:%S')} "
            f"from {args.inputfile}."
        )
        om.onto.metadata.comment.append(msg)
        om.onto.save(file=op_fname, format="rdfxml")
        print(f"File written: {op_fname}")
