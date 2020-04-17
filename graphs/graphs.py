import random
import unicodedata
import string
import jellyfish
from collections import defaultdict
from itertools import combinations, permutations
from hashlib import md5
from tinydb import TinyDB, Query


def shave_marks_latin(txt):
    """Remove all diacritic marks from Latin base characters"""
    norm_txt = unicodedata.normalize('NFD', txt)
    latin_base = False
    keepers = []
    for c in norm_txt:
        if unicodedata.combining(c) and latin_base:
            continue # ignore diacritic on Latin base char
        keepers.append(c)
        # if it isn't combining char, it's a new base char
        if not unicodedata.combining(c):
            latin_base = c in string.ascii_letters
    shaved = ''.join(keepers)
    return unicodedata.normalize('NFC', shaved)


class Author:
    _chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789' 

    def __init__(self, name, author_id=None, parent_id=None):
        self.name = shave_marks_latin(name)
        self.author_id = self._make_id(author_id)
        self.parent_id = parent_id
        f, l = name.lower().rsplit(' ', 1)
        self.filn = (f[0], l)
        self.docs = []

    def __repr__(self):
        n = self.__class__.__name__
        return f'<{n} "{self.name}" {self.author_id}>'

    def _make_id(self, x):
        if x:
            return x
        return '#'+''.join(random.choices(self._chars, k=7))

    def __eq__(self, other):
        #return self.parent_id == other.parent_id and self.filn == other.filn
        return hash(self) == hash(other)

    def compare(self, other):
        t = self.filn == other.filn
        p = bool(self.parent_id) and (self.parent_id == other.parent_id)
        n = jellyfish.jaro_distance(self.name.lower(), other.name.lower())
        return (t, p, n)

    def symmetric_update(self, other):
        """Merges two Author objects.  The best values from each are shared."""
        if self.filn != other.filn:
            raise ValueError('The names of self and other do not match.')
        
        # get the longest name
        self.name = other.name = max([self.name, other.name], key=len)

        # ids begining with '#' are alwayz the lowest.
        self.author_id = other.author_id = max(
            [
                self.author_id, 
                other.author_id,
            ]
        )

        # merge docs, if using
        self.docs = other.docs = list(set(self.docs).union(other.docs))

        # set parent id to none if either is none
        if (self.parent_id is None) or (other.parent_id is None):
            pid = None
        else:
            pid = '|'.join(
                sorted(
                    self.parent_id.split('|')
                    + other.parent_id.split('|')
                )
            )
        self.parent_id = other.parent_id = pid

    def update_to(self, other):
        """Updates this object only to mirror `other`"""
        if self.filn != other.filn:
            raise ValueError('The names of self and other do not match.')
        self.name = other.name
        self.author_id = other.author_id
        self.parent_id = other.parent_id
        self.docs = other.docs

    def __hash__(self):
        return int(md5(self.author_id.encode()).hexdigest()[:11], 16)
    

class Document:
    _chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789' 
    
    def __init__(self, 
                 title,
                 parent_author,
                 authors,
                 publication_date='',
                 pages='',
                 publisher='',
                 journal='',
                 volume='',
                 issue='',
                 conference='',
                 book='',
                 **kwargs):
        self.title = title
        self.parent_author = parent_author
        self.authors = authors
        self.publication_date = publication_date
        self.pages = pages
        self.publisher = publisher
        self.journal = journal
        self.volume = volume
        self.issue = issue
        self.conference = conference
        self.book = book
        self.doc_id = self._make_id()
        self._hash = self._make_hash()

    def __repr__(self):
        n = self.__class__.__name__
        return f'<{n} "{self.title[:20]}..." by {self.parent_author}>'

    def _make_id(self):
        return '@'+''.join(random.choices(self._chars, k=7))

    def compare(self, other):
        """jaro distance + jaccard similary of metadata"""
        t = jellyfish.jaro_distance(self.title.lower(), other.title.lower())
        m = self.dict_similarity(self.metadata, other.metadata)
        return (t + m) / 2

    @property
    def metadata(self):
        metadata = {
            'n_authors': len(self.authors),
            'publication_date': self.publication_date,
            'pages': self.pages,
            'publisher': self.publisher,
            'journal': self.journal,
            'volume': self.volume,
            'issue': self.issue,
            'conference': self.conference,
            'book': self.book,
        }
        metadata = {k: v for k, v in metadata.items() if v}
        return metadata

    def _make_hash(self):
        j = self.journal or self.conference or self.book
        v = self.volume + self.issue
        p = self.pages
        d = self.publication_date
        b = self.publisher
        parts = [x for x in (j, v, p, d, b) if x]
        if len(parts) >= 4:
            h = md5(''.join(parts).encode()).hexdigest()
        elif self.title:
            h = md5(self.title.encode(errors='ignore')).hexdigest()
        elif self.book:
            h = md5(self.book.encode(errors='ignore')).hexdigest()
        else:
            h = md5(
                (
                    ''.join(parts) 
                    + ''.join(self.authors) 
                    + self.parent_author
                ).encode(errors='ignore')
            )
        return int(h[:11], 16)

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        return hash(self) == hash(other)

    @staticmethod
    def dict_similarity(x, y):
        """Score of the similarity between 2 dictionaries.  Harmonic mean
        of the jaccard similarity of the keys and the boolean overlap of the
        matching values of the shared keys"""
        a = set(x)
        b = set(y)
        i = a.intersection(b)
        u = a.union(b)
        j = len(i) / len(u)

        matches = [x[k]==y[k] for k in i]
        if matches:
            v = sum(matches)/len(matches)
        else:
            v = 0
        return 2 / ((j +1)**-1 + (v+1)**-1) - 1


class Graph:

    def __init__(self):
        self.authors = defaultdict(self.ddictlist)    # dict[dict[list]]
        self.documents = defaultdict(set)
        self.ids = dict()

    def __repr__(self):
        n = self.__class__.__name__
        a = len(self.authors)
        d = len(self.documents)
        return f'<{n} with {a} Authors, {d} Documents at 0X{id(self):x}>'

    @staticmethod
    def ddictlist():
        return defaultdict(list)

    def add_author(self, a_dict):
        """Adds an author to the graph from the dictionary `a_dict`"""
        author = Author(
            a_dict['name'],
            a_dict['author_id'],
            None
        )
        self.authors[author]
        self.ids[author.author_id] = author

    def add_document(self, d_dict):
        """Adds coauthors of the document to the graph with the document
        as the edges between all authors.
        """
        d_dict = {
            k.lower().replace(' ', '_'): v
            for k, v in d_dict.items()
        }

        doc = Document(**d_dict)
        if len(doc.authors) == 1:
            return

        parent_id = d_dict['parent_author']
        parent = self.ids[parent_id]

        if doc in self.documents:
            doc_coauthors = self.documents[doc]
        else:
            doc_coauthors = {
                Author(name, None, parent_id) for name in doc.authors
            }
        
        # deduplicate and merge coauthors
        self.deduplicate_coauthors(parent, doc_coauthors)

        # add document as key and coauthors as values
        self.documents[doc].update(doc_coauthors)

        # create fully-connected subgraphs
        for a1, a2 in permutations(doc_coauthors, 2):
            self.authors[a1][a2].append(doc)

    def deduplicate_coauthors(self, parent, doc_coauthors):
        """Searches all of the parent's previous coauthors for duplicates in
        the list of `doc_coauthors`.

        Mutates objects in doc_coauthors and self.authors[parent]
        """
        all_parent_coauthors = self.authors[parent]

        for author in doc_coauthors:
            # check if doc author is the parent author
            if parent.filn == author.filn:
                author.update_to(parent)
            
            # check if the author already exists under the parent
            for author2 in all_parent_coauthors:
                if author.filn == author2.filn:
                    # this mutates both authors to be the same...
                    author.symmetric_update(author2)

    def edge_list(self):
        """Returns the edgelist of the graph"""
        yield 'author_id_1', 'author_id_2', 'doc_id'
        for doc, coauthors in self.documents.items():
            for a1, a2 in combinations(coauthors, 2):
                yield a1.author_id, a2.author_id, doc.doc_id

    def node_attributes(self):
        """Returns the attributes for each node/author"""
        yield 'author_id', 'name', 'filn', 'parent_id'
        for a in self.authors:
            yield a.author_id, a.name, ' '.join(a.filn), a.parent_id

    def edge_attributes(self):
        """Returns the attributes for each edge/document"""
        attrs = (
            'doc_id'
            'title',
            'conference',
            'book',
            'journal',
            'publisher',
            'publication_date',
            'issue',
            'volume',
            'pages',
            'parent_author',
        )
        yield attrs
        for doc in self.documents:
            out = tuple(
                getattr(doc, attr, '') for attr in attrs
            )
            yield out

    def ingest_tindydb(self, 
                       db_path, 
                       author_table='authors', 
                       doc_table='documents',
                       print_status=True):
        """Reads in the authors and documents from a TinyDB datastore
        into the graph.
        """
        # moves the cursor left by n characters
        def L(n):
            return f'\033[{n}D'

        db = TinyDB(db_path)
        authors = db.table(author_table)
        documents = db.table(doc_table)
        q = Query()

        n_auth = authors.count(q)
        
        for i, a_dict in enumerate(authors.all(), 1):
            self.add_author(a_dict)

            if print_status:
                print(f'Authors {i} / {n_auth} | ', end='')
            
            q_imp = q.parent_author == a_dict['author_id']
            n_doc = documents.count(q_imp)
            for j, d_dict in enumerate(documents.search(q_imp), 1):
                self.add_document(d_dict)

                if print_status:
                    msg = f'Documents {j} / {n_doc}   '
                    print(msg + L(len(msg)), end='')
        if print_status:
            print()