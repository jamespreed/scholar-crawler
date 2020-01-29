import zipfile
import csv
from io import StringIO
from collections import defaultdict
from itertools import combinations
from random import choices
from .requests import RequestQueue


class AuthorGraph:
    """
    Class for creating author network of copublications.
    """
    def __init__(self, merge_no_id_authors=False):
        """
        Creates a graph with authors as nodes and publications as edges.

        merge_no_id_authors: [bool] when True, generic authors that have 
            no unique author_id (no profile) will be merged if their names
            are the same as published on a paper.  I.e. all "J REED" authors
            with no profile will be merged.
        """
        self.merge_no_id_authors = merge_no_id_authors
        self.nodes = defaultdict(list)
        self.edges = {}
        self.request_queue = None

    def __repr__(self):
        n = len(self.nodes)
        e = len(self.edges)
        return f'<AuthorGraph {n} nodes, {e} edges at 0x{id(self):x}>'

    def add_publication(self, doc):
        """
        Add a publication to the graph with the `doc` as the edge.

        doc: [Document] document dataclass object
        return: [Authors] list of authors that were added to the graph
        """
        new_authors = []
        ### ADD EDGE
        # add the parent_author to the author list if it is not already there
        if doc in self.edges:
            current_authors = self.edges.get(doc, [])
            if doc.parent_author not in current_authors:
                current_authors.append(doc.parent_author)
                new_authors.append(doc.parent_author)
            # add paper to node's values
            if doc not in self.nodes[doc.parent_author]:
                self.nodes[doc.parent_author].append(doc)
            return new_authors
        
        # the entire paper
        self.edges[doc] = doc.authors
        # update the nodes' papers
        for author in doc.authors:
            # if not merging authors, randomize the author ids
            if not self.merge_no_id_authors:
                author.randomize_empty_id()
            # track authors that are new to the graph
            if author not in self.nodes:
                new_authors.append(author)
            # append to each author node's list
            self.nodes[author].append(doc)
        return new_authors
        
    def get_node_id(self, node):
        """
        Returns the node's id when exported.
        """
        if self.merge_no_id_authors:
            return node.name + ':' + node.author_id
        return node.author_id

    def generate_edge_list(self, header=False):
        """
        Yields an edge for each publication.

        header: [bool] Yield the column header before the data
        return: author, author, doc_id
        """
        if header:
            yield ('node1_id', 'node2_id', 'edge_id')
        for doc, authors in self.edges.items():
            for a1, a2 in combinations(authors, 2): 
                yield (self.get_node_id(a1), self.get_node_id(a2), doc.doc_id)

    def generate_edge_attrs(self, header=False):
        """
        Yields the metadata for each document (edge) in the graph.

        header: [bool] Yield the column header before the data
        return: doc_id, title
        """
        if header:
            yield ('doc_id', 'title')
        for doc in self.edges:
            yield (doc.doc_id, doc.title)

    def generate_node_attrs(self, header=False):
        """
        Yields the metadata for each author (node) in the graph.

        header: [bool] Yield the column header before the data
        return: doc_id, title
        """
        if header:
            yield (
                'node_id',
                'name',
                'profile_name',
                'author_id',
                'full_title',
                'institution',
                'email_domain',
                'interests'
            )
        for node in self.nodes:
            yield (
                self.get_node_id(node),
                node.name,
                node.profile_name,
                node.author_id,
                node.full_title,
                node.institution,
                node.email_domain,
                '|'.join(node.interests)
            )

    def export(self, path):
        """
        Saves the graph to a zip file containing 3 csv files:
        - edge_list.csv : the node to node connnections
        - edge_attrs.csv : the edges attributes
        - node_attrs.csv : the node attributes
        """
        if not path.lower().endswith('.zip'):
            path = path + '.zip' 
        archive = zipfile.ZipFile(path, 'w')

        with StringIO() as fp:
            writer = csv.writer(fp)
            for row in self.generate_edge_list(True):
                writer.writerow(row)
            archive.writestr('edge_list.csv', fp.getvalue())

        with StringIO() as fp:
            writer = csv.writer(fp)
            for row in self.generate_edge_attrs(True):
                writer.writerow(row)
            archive.writestr('edge_attrs.csv', fp.getvalue())

        with StringIO() as fp:
            writer = csv.writer(fp)
            for row in self.generate_node_attrs(True):
                writer.writerow(row)
            archive.writestr('node_attrs.csv', fp.getvalue())

        archive.close()
        return archive

    @classmethod
    def from_egde_list(cls, edge_list):
        """
        Creates a new AuthorGraph from the iterable `edge_list`.

        :param edge_list: [iterable] of author, author, doc_id
        """
        raise NotImplementedError('I will get around to this')

    def copy(self):
        ag = self.__class__() 
        ag.nodes = self.nodes.copy()
        ag.egdes = self.edges.copy()
        return ag

    def __add__(self, other):
        ag = self.copy()
        ag.nodes.update(other.nodes)
        ag.edges.update(other.edges)
        return ag