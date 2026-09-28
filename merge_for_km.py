#!/usr/bin/env python3
"""Merge base + extension ontology into ONE import-free RDF/XML graph for
backends that don't resolve owl:imports (Kobayashi-MaRust km, and for
single-file distribution).

Merging = strip both headers/footers, keep ONE rdf:RDF element carrying the
union of xmlns declarations, and drop the owl:Ontology/imports block (the
merged graph needs no imports by construction). Pure stdlib text surgery —
both files are generated, machine-written RDF/XML with identical formatting.
"""
import re
import sys

def merge(base_path, ext_path, out_path):
    base = open(base_path).read()
    ext = open(ext_path).read()

    def header_of(text):
        m = re.search(r'<rdf:RDF\b[^>]*>', text, re.S)
        return m.group(0)

    def body_of(text):
        # everything between the closing '>' of rdf:RDF and '</rdf:RDF>'
        start = re.search(r'<rdf:RDF\b[^>]*>', text, re.S).end()
        end = text.rfind('</rdf:RDF>')
        body = text[start:end]
        # drop the owl:Ontology + imports block (it ends with </owl:Ontology>)
        body = re.sub(r'<owl:Ontology\b.*?</owl:Ontology>\n?', '', body, flags=re.S)
        # the base declares its ontology via a bare rdf:Description typed owl:Ontology
        # (about="...ontomat#") — also unmapped in km; drop typed-Ontology decls too
        body = re.sub(r'<rdf:Description rdf:about="[^"]*">\s*<rdf:type rdf:resource="http://www.w3.org/2002/07/owl#Ontology"/>\s*</rdf:Description>\n?', '', body)
        return body

    ext_header = header_of(ext)
    base_header = header_of(base)
    # use the EXTENSION header (it declares every namespace the merged doc
    # needs; the base's are a subset)
    merged = ext_header + '\n' + body_of(base) + body_of(ext) + '</rdf:RDF>\n'
    open(out_path, 'w').write(merged)
    print(f'wrote {out_path} ({len(merged)} bytes)')

if __name__ == '__main__':
    base, ext, out = sys.argv[1], sys.argv[2], sys.argv[3]
    merge(base, ext, out)