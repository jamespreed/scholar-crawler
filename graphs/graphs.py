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
        n = jellyfish.jaro_distance(self.name.lower(), other.name.lower())
        return (t, n)

    def merge(self, other):
        """Merges two Author objects.  The best values from each are shared.

        Returns a new Author object.
        """
        if self.filn != other.filn:
            raise ValueError('The names of self and other do not match.')
        
        # get the longest name
        name = max([self.name, other.name], key=len)

        # ids begining with '#' are alwayz the lowest.
        author_id = max([self.author_id, other.author_id])

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
        return self.__class__(name, author_id, pid)

    def update_to(self, other):
        """Updates this object only to mirror `other`"""
        if self.filn != other.filn:
            raise ValueError('The names of self and other do not match.')
        self.name = other.name
        self.author_id = other.author_id
        self.parent_id = other.parent_id

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
        self.authors = sorted(filter(lambda x: ' ' in x, set(authors)))
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
        # mapping of author_id to Author object
        self.author_ids = dict()
        # mapping of author_id to a set of ids of co_authors
        self.authors = defaultdict(set)
        # mapping of document to ids of authors
        self.documents = dict()

    def __repr__(self):
        n = self.__class__.__name__
        a = len(self.authors)
        d = len(self.documents)
        return f'<{n} with {a} Authors, {d} Documents at 0X{id(self):x}>'

    def add_author(self, a_dict):
        """Adds an author to the graph from the dictionary `a_dict`"""
        author = Author(
            a_dict['name'],
            a_dict['author_id'],
            None
        )
        self.author_ids[author.author_id] = author
        self.authors[author.author_id]

    def add_document(self, d_dict):
        """Adds coauthors of the document to the graph with the document
        as the edges between all authors.
        """
        d_dict = {
            k.lower().replace(' ', '_'): v
            for k, v in d_dict.items()
        }

        doc = Document(**d_dict)
        if len(doc.authors) <= 1:
            return

        parent_id = doc.parent_author
        parent = self.author_ids[parent_id]

        if doc in self.documents:
            doc_coauthors = [
                self.author_ids[a_id] for a_id in self.documents[doc]
            ]
            NEW_DOC = False
        else:
            doc_coauthors = [
                Author(name, None, parent_id) for name in doc.authors
            ]
            NEW_DOC = True
        
        # deduplicate and merge coauthors
        self.deduplicate_coauthors(parent, doc_coauthors, NEW_DOC)

        # add coauthors to parent author's set
        doc_coauthor_ids = {a.author_id for a in doc_coauthors}
        self.authors[parent_id].update(doc_coauthor_ids)

        # document as key, replace parent + coauthors as values
        doc_coauthor_ids.add(parent_id)
        self.documents[doc] = doc_coauthor_ids

    def deduplicate_coauthors(self, parent, doc_coauthors, new_doc):
        """Searches all of the parent's previous coauthors for duplicates in
        the list of `doc_coauthors`.

        Mutates doc_coauthors.
        """
        all_parent_coauthor_ids = self.authors[parent.parent_id]

        for ix in reversed(range(len(doc_coauthors))):
            dca = doc_coauthors[ix]

            # find the parent author in the coauthor list
            if parent.filn == dca.filn:
                # remove parent author from list
                doc_coauthors.pop(ix)
                if not new_doc:
                    # replace the generic coauthor with the parent
                    self.author_ids[dca.author_id] = parent
                continue

            # check if the author already exists under the parent
            for a_id in all_parent_coauthor_ids:
                pca = self.author_ids[a_id]
                if dca.filn == pca.filn:
                    if new_doc:
                        # replace with the existing coauthor
                        doc_coauthors[ix] = pca
                    else:
                        # point existing keys to new author object
                        new_auth = dca.merge(pca)
                        self.author_ids[dca.author_id] = new_auth
                        self.author_ids[pca.author_id] = new_auth
                        doc_coauthors[ix] = new_auth

    def edge_list(self):
        """Returns the edgelist of the graph"""
        yield 'author_id_1', 'author_id_2', 'doc_id'
        for doc, coauthor_ids in self.documents.items():
            for id1, id2 in combinations(coauthor_ids, 2):
                yield id1, id2, doc.doc_id

    def node_attributes(self):
        """Returns the attributes for each node/author"""
        yield 'author_id', 'name', 'filn', 'parent_id'
        ids = set()
        for a in self.author_ids.values():
            if a.author_id in ids:
                continue
            ids.add(a.author_id)
            yield a.author_id, a.name, ' '.join(a.filn), a.parent_id

    def edge_attributes(self):
        """Returns the attributes for each edge/document"""
        attrs = (
            'doc_id',
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

        def _print(*args, ps=print_status, **kwargs):
            if ps:
                print(*args, **kwargs)

        ps = print_status

        db = TinyDB(db_path)
        authors = db.table(author_table)
        documents = db.table(doc_table)
        q = Query()

        n_auth = authors.count(q)
        
        for i, a_dict in enumerate(authors.all(), 1):
            self.add_author(a_dict)
            _print(f'Authors {i} / {n_auth} | ', end='', ps=ps)
            
            q_imp = q.parent_author == a_dict['author_id']
            n_doc = documents.count(q_imp)

            for j, d_dict in enumerate(documents.search(q_imp), 1):
                self.add_document(d_dict)
                msg = f'Documents {j} / {n_doc}   '
                _print(msg + L(len(msg)), end='', ps=ps)

            _print('\r', end='', ps=ps)

        if print_status:
            print()